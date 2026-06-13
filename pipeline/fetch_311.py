"""
311 validation overlay: Somerville 311 flooding/drainage complaints (dataset 4pyi-uqq6,
resolved to 2020 census blocks via Census TIGERweb) joined to the ponding-risk ranking.

Outputs:
  ../public/data/complaints_blocks.geojson  -- census-block polygons w/ flooding-complaint counts
  ../public/data/validation.json            -- headline validation stats for the UI
"""
import json, os, urllib.request, urllib.parse, csv
from shapely.geometry import shape, Point
from pyproj import Transformer
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "public", "data"); os.makedirs(WEB, exist_ok=True)
OUT = os.path.join(HERE, "output")

# footprint + ~120 m buffer
W, S, E, N = -71.0889, 42.3865, -71.0768, 42.3997
FLOOD = ("lower(type) like '%catch basin%' or lower(type) like '%flood%' or "
         "lower(type) like '%sewer%' or lower(type) like '%drain%' or lower(type) like '%standing water%'")

def get(url, t=90):
    req = urllib.request.Request(url, headers={"User-Agent": "cyvl-hackathon"})
    with urllib.request.urlopen(req, timeout=t) as r:
        return json.load(r)

def bucket(t):
    t = t.lower()
    if "catch basin" in t: return "catch_basin"
    if "flood" in t: return "flooding"
    if "standing water" in t: return "standing_water"
    if "sewer" in t: return "sewer"
    if "drain" in t: return "drain"
    return "other"

# 1) TIGER 2020 census blocks (layer 10) intersecting the footprint, as GeoJSON
svc = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer/10/query"
params = {"where": "1=1", "geometry": f"{W},{S},{E},{N}", "geometryType": "esriGeometryEnvelope",
          "inSR": "4326", "outSR": "4326", "spatialRel": "esriSpatialRelIntersects",
          "outFields": "GEOID", "returnGeometry": "true", "f": "geojson"}
blocks = get(svc + "?" + urllib.parse.urlencode(params))["features"]
print(f"blocks in footprint bbox: {len(blocks)}")

# 2) flooding complaints per block_code + category
q = {"$select": "block_code, type, count(1) as n", "$group": "block_code, type", "$where": FLOOD, "$limit": 8000}
rows = get("https://data.somervillema.gov/resource/4pyi-uqq6.json?" + urllib.parse.urlencode(q))
per_block = {}   # geoid -> {total, cats:{}}
for r in rows:
    bc = r.get("block_code");
    if not bc or bc.strip() == "NA": continue
    n = int(r["n"]); b = per_block.setdefault(bc.strip(), {"total": 0, "cats": {}})
    b["total"] += n; cat = bucket(r["type"]); b["cats"][cat] = b["cats"].get(cat, 0) + n

# date range (flooding)
try:
    dr = get("https://data.somervillema.gov/resource/4pyi-uqq6.json?" +
             urllib.parse.urlencode({"$select": "min(date_created) mn, max(date_created) mx", "$where": FLOOD}))[0]
    date_range = [dr["mn"][:10], dr["mx"][:10]]
except Exception:
    date_range = None

# 3) assemble choropleth (blocks in footprint, attach counts; keep those with >=1)
feats, total_fp, cat_tot = [], 0, {}
block_geoms = []  # (geoid, shapely, total) for point-in-polygon
for ft in blocks:
    gid = str(ft["properties"].get("GEOID"))
    rec = per_block.get(gid, {"total": 0, "cats": {}})
    geom = ft["geometry"]
    block_geoms.append((gid, shape(geom), rec["total"]))
    if rec["total"] > 0:
        total_fp += rec["total"]
        for k, v in rec["cats"].items(): cat_tot[k] = cat_tot.get(k, 0) + v
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {"geoid": gid, "complaints": rec["total"], **rec["cats"]}})
json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(WEB, "complaints_blocks.geojson"), "w"))
print(f"footprint blocks with complaints: {len(feats)}; total complaints: {total_fp}")

# 4) validation vs ranked cells
to4326 = Transformer.from_crs(32619, 4326, always_xy=True)
cells = []
with open(os.path.join(OUT, "priority_ranking.csv")) as fh:
    for row in csv.DictReader(fh):
        lon, lat = to4326.transform(float(row["xc_utm"]), float(row["yc_utm"]))
        cells.append({"priority": float(row["priority"]), "rank": int(row["rank"]), "pt": Point(lon, lat)})
# assign each cell its block's complaint count
for c in cells:
    c["bc"] = 0
    for gid, poly, tot in block_geoms:
        if poly.contains(c["pt"]):
            c["bc"] = tot; break
prio = [c["priority"] for c in cells]; bc = [c["bc"] for c in cells]
rho, p = spearmanr(prio, bc) if len(cells) > 2 else (None, None)
cells.sort(key=lambda c: -c["priority"])
top10 = cells[:10]
val = {
    "source": "City of Somerville 311 (dataset 4pyi-uqq6), flooding/drainage requests, resolved to 2020 US Census blocks (TIGERweb).",
    "date_range": date_range,
    "flood_types": ["Catch basin complaint", "Flooding Report", "Sewer issue", "Sewers and Drains", "Standing water"],
    "footprint_complaints": total_fp,
    "by_category": cat_tot,
    "blocks_with_complaints": len(feats),
    "ranked_cells": len(cells),
    "cells_in_complaint_blocks": sum(1 for c in cells if c["bc"] > 0),
    "top10_validated": sum(1 for c in top10 if c["bc"] > 0),
    "top10_block_complaints": sum(c["bc"] for c in top10),
    "spearman_rho": round(rho, 3) if rho is not None else None,
    "spearman_p": round(p, 4) if p is not None else None,
}
json.dump(val, open(os.path.join(WEB, "validation.json"), "w"), indent=2)
print("validation:", json.dumps(val, indent=2))
