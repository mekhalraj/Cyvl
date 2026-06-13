"""
Phase C - Build a bare-earth DTM from the LiDAR point cloud.

Input : the .laz (EPSG:32619 / UTM 19N, meters), 93.3M points, unclassified.
Method: stream in chunks, take the MINIMUM Z per 1 m cell (lowest return ~= ground),
        fill gaps by nearest, median-filter to kill isolated low-noise spikes.
Output: data/processed/dtm.npy        (float32 grid[iy, ix], iy=0 at south/miny)
        data/processed/depression.npy  (local-mean minus dtm; positive = low spot)
        data/processed/dtm_meta.json    (minx,miny,maxx,maxy,res,nx,ny,crs)
        data/processed/dtm.tif          (georeferenced raster, EPSG:32619)
"""
import json, time
import numpy as np
import pandas as pd
import laspy
from scipy import ndimage

LAZ = r"C:\Users\mekha\Downloads\global_xyz_rgb_icgu_93_6000_8000.laz"
OUT = r"C:\Users\mekha\somerville-rainrisk\data\processed"
RES = 1.0  # meters

t0 = time.time()
with laspy.open(LAZ) as f:
    h = f.header
    minx, miny = h.mins[0], h.mins[1]
    maxx, maxy = h.maxs[0], h.maxs[1]
    nx = int(np.ceil((maxx - minx) / RES))
    ny = int(np.ceil((maxy - miny) / RES))
    print(f"bounds X[{minx:.2f},{maxx:.2f}] Y[{miny:.2f},{maxy:.2f}]  grid {nx}x{ny}  pts {h.point_count:,}")
    grid = np.full(nx * ny, np.inf, dtype=np.float64)
    n_seen = 0
    for chunk in f.chunk_iterator(5_000_000):
        x = np.asarray(chunk.x); y = np.asarray(chunk.y); z = np.asarray(chunk.z)
        # drop gross outliers (noise well below/above any plausible terrain or structure)
        m = (z > -80) & (z < 150) & (x >= minx) & (x <= maxx) & (y >= miny) & (y <= maxy)
        x, y, z = x[m], y[m], z[m]
        ix = np.clip(((x - minx) / RES).astype(np.int64), 0, nx - 1)
        iy = np.clip(((y - miny) / RES).astype(np.int64), 0, ny - 1)
        lin = iy * nx + ix
        # reduce this chunk to per-cell minima first (fast), then scatter-min into global
        s = pd.Series(z).groupby(lin).min()
        np.minimum.at(grid, s.index.to_numpy(), s.to_numpy())
        n_seen += len(z)
    print(f"streamed {n_seen:,} pts in {time.time()-t0:.0f}s")

grid = grid.reshape(ny, nx)            # grid[iy, ix], iy=0 -> miny (south)
grid[np.isinf(grid)] = np.nan
valid = ~np.isnan(grid)                # cells that actually received LiDAR returns
print(f"empty cells before fill: {(~valid).mean()*100:.2f}%  (corridor coverage -> mostly streets)")

# robust noise clip from the REAL cells (kills stray low/high returns before fill)
vv = grid[valid]
lo, hi = np.percentile(vv, 0.5), np.percentile(vv, 99.5)
grid = np.clip(grid, lo, hi)
print(f"clip ground to [{lo:.2f}, {hi:.2f}] (0.5/99.5 pct of real cells)")

# fill gaps by nearest valid cell, then smooth out 1 m speckle
mask = np.isnan(grid)
idx = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
dtm = grid[tuple(idx)]
dtm = ndimage.median_filter(dtm, size=3).astype(np.float32)

# depression / ponding proxy: how far below the local ~50 m average a cell sits.
# capped at 3 m -- deeper "lows" over corridor-interpolated terrain are artifacts, not ponding.
local = ndimage.uniform_filter(dtm, size=51, mode="nearest")
depression = np.clip(local - dtm, 0.0, 3.0).astype(np.float32)
np.save(OUT + r"\valid_mask.npy", valid)

np.save(OUT + r"\dtm.npy", dtm)
np.save(OUT + r"\depression.npy", depression)
meta = dict(minx=minx, miny=miny, maxx=maxx, maxy=maxy, res=RES, nx=nx, ny=ny, crs="EPSG:32619")
json.dump(meta, open(OUT + r"\dtm_meta.json", "w"), indent=2)

print(f"DTM   z: min {np.nanmin(dtm):.2f}  med {np.median(dtm):.2f}  max {np.nanmax(dtm):.2f}")
print(f"DEPR  : max {depression.max():.2f} m below local avg;  cells>0.3m: {(depression>0.3).sum():,}")

# georeferenced raster (row 0 = north -> flipud)
try:
    import rasterio
    from rasterio.transform import from_origin
    tr = from_origin(minx, maxy, RES, RES)
    with rasterio.open(OUT + r"\dtm.tif", "w", driver="GTiff", height=ny, width=nx,
                       count=1, dtype="float32", crs="EPSG:32619", transform=tr,
                       nodata=np.nan) as ds:
        ds.write(np.flipud(dtm), 1)
    print("wrote dtm.tif")
except Exception as e:
    print("rasterio write skipped:", repr(e))
print(f"DONE in {time.time()-t0:.0f}s")
