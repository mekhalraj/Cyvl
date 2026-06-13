"""
Citywide DEM from the City's LiDAR-derived 1-ft contours (ArcGIS layer 29, ~86.7k lines).
Burn contour-vertex elevations into a 5 m grid (UTM 19N), nearest-fill between contours,
smooth, clip to City Limits, then derive a ponding/depression grid.

Outputs: pipeline/data/processed/dem_city.npy, depression_city.npy, dem_city_meta.json
"""
import json, os, re, urllib.request, urllib.parse
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import unary_union, transform as shp_transform
from scipy import ndimage
import rasterio.features
from rasterio.transform import from_origin

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CITY = os.path.join(HERE, "data", "city"); PROC = os.path.join(HERE, "data", "processed")
os.makedirs(PROC, exist_ok=True)
BASE = "https://maps.somervillema.gov/arcgis/rest/services/UtilitiesAndAssets2/MapServer"
RES = 5.0
to_utm = Transformer.from_crs(4326, 32619, always_xy=True)

def get(url, t=120, tries=5):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cyvl-hack"})
            with urllib.request.urlopen(req, timeout=t) as r: return json.load(r)
        except Exception as ex:
            last = ex; print(f"    retry {k+1}/{tries} ({ex})", flush=True)
    raise last

# --- boundary -> UTM bounds ---
bnd = json.load(open(os.path.join(CITY, "boundary.geojson")))
poly_wgs = unary_union([shape(f["geometry"]) for f in bnd["features"]])
poly = shp_transform(lambda x, y, z=None: to_utm.transform(x, y), poly_wgs)
minx, miny, maxx, maxy = poly.bounds
nx = int(np.ceil((maxx - minx) / RES)); ny = int(np.ceil((maxy - miny) / RES))
print(f"city UTM bounds X[{minx:.0f},{maxx:.0f}] Y[{miny:.0f},{maxy:.0f}] grid {nx}x{ny}")

# --- fetch contour vertices (cached: the ArcGIS pull is ~86.7k lines and slow) ---
ccache = os.path.join(PROC, "contour_vertices.npz")
if os.path.exists(ccache):
    z = np.load(ccache)
    LON, LAT, ELV = z["lon"].tolist(), z["lat"].tolist(), z["elv"].tolist()
    print(f"contours from cache: vertices {len(LON):,}")
else:
    meta = get(BASE + "/29?f=json"); oidf = meta.get("objectIdFieldName", "OBJECTID")
    fields = [f["name"] for f in meta["fields"]]
    elevf = next((f for f in fields if re.search(r"elev|contour|value", f, re.I)), None)
    print("contour fields:", fields, "-> elevation field:", elevf)
    PAGE = 400  # smaller pages: lighter responses, far less likely to time out on a slow server
    LON, LAT, ELV = [], [], []; last = -1; n = 0
    for pg in range(500):
        q = {"where": f"{oidf}>{last}", "outFields": f"{oidf},{elevf}", "returnGeometry": "true",
             "outSR": "4326", "f": "json", "orderByFields": oidf, "resultRecordCount": PAGE}
        d = get(BASE + "/29/query?" + urllib.parse.urlencode(q)); fs = d.get("features", [])
        if not fs: break
        for ft in fs:
            last = ft["attributes"][oidf]; e = ft["attributes"].get(elevf)
            if e is None: continue
            for path in ft.get("geometry", {}).get("paths", []):
                for x, y in path:
                    LON.append(x); LAT.append(y); ELV.append(e)
        n += len(fs)
        print(f"  page {pg+1}: +{len(fs)} lines (total {n}, vertices {len(LON):,})", flush=True)
        if len(fs) < PAGE: break
    print(f"contours fetched: {n}; vertices: {len(LON):,}")
    np.savez(ccache, lon=np.array(LON), lat=np.array(LAT), elv=np.array(ELV, float))

# --- burn into grid (vectorized reprojection) ---
X, Y = to_utm.transform(np.array(LON), np.array(LAT))
ELV = np.array(ELV, float)
ix = ((X - minx) / RES).astype(int); iy = ((Y - miny) / RES).astype(int)
m = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
dem = np.full((ny, nx), np.nan, np.float32)
dem[iy[m], ix[m]] = ELV[m]
print(f"burned cells: {np.isfinite(dem).sum():,} / {nx*ny:,}")

# --- nearest-fill between contours + smooth ---
mask = np.isnan(dem)
idx = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
dem = dem[tuple(idx)]
dem = ndimage.gaussian_filter(dem, sigma=2).astype(np.float32)
dem_full = dem.copy()  # nearest-filled + smoothed, full extent (real terrain everywhere, no NaN)

# --- clip to City Limits (rasterize boundary; grid row0 = south, so flipud the raster mask) ---
tr = from_origin(minx, maxy, RES, RES)
inside = rasterio.features.rasterize([(poly, 1)], out_shape=(ny, nx), transform=tr, fill=0, dtype="uint8")
inside = np.flipud(inside).astype(bool)
dem[~inside] = np.nan

# --- ponding / depression (local ~250 m mean minus DEM), capped ---
# Use the full-extent nearest-filled terrain (dem_full) for the neighborhood mean so cells near the
# City Limits keep real neighbors instead of being dragged toward the citywide mean. Cap raised so the
# top of the distribution is not pre-truncated (the ranking normalizes ponding separately).
local = ndimage.uniform_filter(dem_full, size=51, mode="nearest")
depression = np.clip(local - dem_full, 0.0, 8.0).astype(np.float32)
depression[~inside] = 0.0

np.save(os.path.join(PROC, "dem_city.npy"), dem)
np.save(os.path.join(PROC, "depression_city.npy"), depression)
json.dump({"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy, "res": RES, "nx": nx, "ny": ny,
           "crs": "EPSG:32619"}, open(os.path.join(PROC, "dem_city_meta.json"), "w"), indent=2)
print(f"DEM z: min {np.nanmin(dem):.1f} med {np.nanmedian(dem):.1f} max {np.nanmax(dem):.1f} (units = contour units)")
print(f"DEPR cells>0.5: {(depression>0.5).sum():,}; max {depression.max():.2f}")
print("DONE")
