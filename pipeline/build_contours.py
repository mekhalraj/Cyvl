"""
Terrain contour lines for the web map, derived from the citywide LiDAR DEM
(pipeline/data/processed/dem_city.npy, feet, UTM 19N). Fully offline — reads the cached
DEM, extracts contours with matplotlib, simplifies, reprojects to WGS84.

Output: public/data/contours.geojson  (LineStrings, properties {elev} in feet)
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless: no display, just contour extraction
import matplotlib.pyplot as plt
from pyproj import Transformer
from shapely.geometry import LineString

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
PROC = os.path.join(HERE, "data", "processed"); WEB = os.path.join(ROOT, "public", "data")
to_wgs = Transformer.from_crs(32619, 4326, always_xy=True)

INTERVAL = 10.0   # ft between contours
SIMPLIFY = 4.0    # m, Douglas-Peucker tolerance in UTM
MIN_LEN = 15.0    # m, drop fragments shorter than this

meta = json.load(open(os.path.join(PROC, "dem_city_meta.json")))
MINX, MINY, RES = meta["minx"], meta["miny"], meta["res"]
dem = np.load(os.path.join(PROC, "dem_city.npy"))
Z = np.ma.masked_invalid(dem)  # NaN outside City Limits -> not contoured

lo = int(np.floor(np.nanmin(dem) / INTERVAL) * INTERVAL)
hi = int(np.ceil(np.nanmax(dem) / INTERVAL) * INTERVAL)
levels = [v for v in np.arange(lo, hi + INTERVAL, INTERVAL) if v >= 0]
cs = plt.contour(Z, levels=levels)

feats, nseg = [], 0
for lev, segs in zip(cs.levels, cs.allsegs):
    for seg in segs:  # seg: array of (col, row) in grid coords
        if len(seg) < 2:
            continue
        # grid -> UTM (DEM row0 = south, so y grows with row index)
        utm = [(MINX + px * RES, MINY + py * RES) for px, py in seg]
        line = LineString(utm).simplify(SIMPLIFY)
        if line.is_empty or line.length < MIN_LEN:
            continue
        ring = [list(to_wgs.transform(x, y)) for x, y in line.coords]
        feats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": ring},
                      "properties": {"elev": float(lev)}})
        nseg += 1

json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(WEB, "contours.geojson"), "w"))
nv = sum(len(f["geometry"]["coordinates"]) for f in feats)
print(f"contours: {nseg} lines over levels {levels[0]:.0f}..{levels[-1]:.0f} ft "
      f"(every {INTERVAL:.0f} ft), {nv:,} vertices -> public/data/contours.geojson")
