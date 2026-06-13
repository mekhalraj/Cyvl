"""Generate WGS84 GeoJSON for the web map into ../public/data/ ."""
import json, csv, os
import numpy as np
from pyproj import Transformer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW  = os.path.join(HERE, "data", "raw")
PROC = os.path.join(HERE, "data", "processed")
OUT  = os.path.join(HERE, "output")
WEB  = os.path.join(ROOT, "public", "data")
os.makedirs(WEB, exist_ok=True)
to4326 = Transformer.from_crs(32619, 4326, always_xy=True)

def slim_copy(name, keep):
    d = json.load(open(os.path.join(RAW, name), encoding="utf-8"))
    for ft in d["features"]:
        p = ft["properties"]
        ft["properties"] = {k: p.get(k) for k in keep}
    json.dump(d, open(os.path.join(WEB, name), "w"))
    return len(d["features"])

n_cb = slim_copy("catch_basin.geojson", ["feature_id", "condition", "image_url"])
n_mh = slim_copy("manhole.geojson",     ["feature_id", "condition", "image_url"])
n_pv = slim_copy("pavement.geojson",    ["condition_score", "condition_label"])

# ranking 50 m cells: UTM(32619) square -> 4326 polygon
def num(v): return None if v in ("", "None", None) else float(v)
CELL = 50.0
feats = []
with open(os.path.join(OUT, "priority_ranking.csv")) as fh:
    for row in csv.DictReader(fh):
        xc, yc = float(row["xc_utm"]), float(row["yc_utm"])
        ring_utm = [(xc-CELL/2, yc-CELL/2), (xc+CELL/2, yc-CELL/2),
                    (xc+CELL/2, yc+CELL/2), (xc-CELL/2, yc+CELL/2), (xc-CELL/2, yc-CELL/2)]
        ring = [list(to4326.transform(x, y)) for x, y in ring_utm]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"rank": int(float(row["rank"])), "priority": num(row["priority"]),
                "ponding_m": num(row["ponding_m"]), "basins": int(float(row["basins"])),
                "manholes": int(float(row["manholes"])), "mean_pci": num(row["mean_pci"]),
                "s_pond": num(row["s_pond"]), "s_basin_deficit": num(row["s_basin_deficit"]),
                "s_pci": num(row["s_pci"])}})
json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(WEB, "ranking.geojson"), "w"))

# contours from the DTM (2 m), reprojected + decimated to keep the file light
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
meta = json.load(open(os.path.join(PROC, "dtm_meta.json")))
MINX, MINY, RES, NX, NY = meta["minx"], meta["miny"], meta["res"], meta["nx"], meta["ny"]
dtm = np.load(os.path.join(PROC, "dtm.npy"))
Xc, Yc = np.meshgrid(MINX + (np.arange(NX)+0.5)*RES, MINY + (np.arange(NY)+0.5)*RES)
cs = plt.contour(Xc, Yc, dtm, levels=np.arange(np.floor(dtm.min()), np.ceil(dtm.max())+0.1, 2.0))
cfeats = []
for lvl, segs in zip(cs.levels, cs.allsegs):
    for seg in segs:
        if len(seg) < 8:
            continue
        line = [list(to4326.transform(x, y)) for x, y in seg[::2]]
        cfeats.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line},
                       "properties": {"level": round(float(lvl), 1)}})
plt.close("all")
json.dump({"type": "FeatureCollection", "features": cfeats}, open(os.path.join(WEB, "contours.geojson"), "w"))

print(f"catch_basin {n_cb}, manhole {n_mh}, pavement {n_pv}, ranking {len(feats)}, contours {len(cfeats)}")
for f in sorted(os.listdir(WEB)):
    print("  ", f, round(os.path.getsize(os.path.join(WEB, f))/1024, 1), "KB")
