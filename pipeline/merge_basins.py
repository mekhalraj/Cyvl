"""
Merge catch basins: Cyvl (citywide, from the public cyvl-hackathon S3) + City of Somerville (591).
Dedupe: drop a City basin if a Cyvl basin is within ~6 m (keep Cyvl). Tag `source`. Cyvl highlighted.

Outputs: public/data/merged_catch_basins.geojson  +  public/data/cyvl_catch_basins.geojson
         pipeline/data/processed/merged_catch_basins.geojson (for the ranking)
"""
import json, os, urllib.request
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CITY = os.path.join(HERE, "data", "city"); PROC = os.path.join(HERE, "data", "processed")
WEB = os.path.join(ROOT, "public", "data")
to_utm = Transformer.from_crs(4326, 32619, always_xy=True)

def getbytes(u, t=120):
    req = urllib.request.Request(u, headers={"User-Agent": "cyvl"})
    with urllib.request.urlopen(req, timeout=t) as r: return r.read()

def is_cb(p):
    s = " ".join(str(p.get(k, "")) for k in ("asset_type", "type", "Type", "assetType")).lower()
    return "catch" in s and "basin" in s

# Cyvl basins citywide (S3 GeoJSON export)
ag = json.loads(getbytes("https://cyvl-hackathon.s3.amazonaws.com/data/aboveGroundAssets_v2.geojson"))
cyvl = [f for f in ag["features"]
        if f.get("geometry") and f["geometry"]["type"] == "Point" and is_cb(f.get("properties", {}))]
# City basins
city = json.load(open(os.path.join(CITY, "catch_basins.geojson")))["features"]

cyvl_xy = np.array([to_utm.transform(*f["geometry"]["coordinates"][:2]) for f in cyvl]) if cyvl else np.empty((0, 2))
tree = cKDTree(cyvl_xy) if len(cyvl_xy) else None

merged = [{"type": "Feature", "geometry": f["geometry"],
           "properties": {"source": "cyvl", "feature_id": f["properties"].get("feature_id")}} for f in cyvl]
kept_city = 0
for f in city:
    xy = to_utm.transform(*f["geometry"]["coordinates"][:2])
    if tree is not None and tree.query(xy)[0] <= 6.0:
        continue  # duplicate of a Cyvl basin -> keep Cyvl, drop City
    merged.append({"type": "Feature", "geometry": f["geometry"], "properties": {"source": "city"}})
    kept_city += 1

fc = {"type": "FeatureCollection", "features": merged}
json.dump(fc, open(os.path.join(WEB, "merged_catch_basins.geojson"), "w"))
json.dump(fc, open(os.path.join(PROC, "merged_catch_basins.geojson"), "w"))
json.dump({"type": "FeatureCollection", "features": [m for m in merged if m["properties"]["source"] == "cyvl"]},
          open(os.path.join(WEB, "cyvl_catch_basins.geojson"), "w"))
print(f"cyvl basins {len(cyvl)} | city basins {len(city)} | city kept (non-dup) {kept_city} | merged {len(merged)}")
