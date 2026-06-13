"""
311 validation overlay: Somerville 311 flooding/drainage complaints (dataset 4pyi-uqq6,
resolved to 2020 census blocks via Census TIGERweb) joined to the ponding-risk ranking.

Outputs:
  ../public/data/complaints_blocks.geojson  -- census-block polygons w/ flooding-complaint counts
  ../public/data/validation.json            -- headline validation stats for the UI
"""
import json, os, time, urllib.request, urllib.parse, csv
from shapely.geometry import shape, Point
from shapely import STRtree
from pyproj import Transformer
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "public", "data"); os.makedirs(WEB, exist_ok=True)
OUT = os.path.join(HERE, "output")

# entire City of Somerville
W, S, E, N = -71.138, 42.370, -71.069, 42.421
FLOOD = ("lower(type) like '%catch basin%' or lower(type) like '%flood%' or "
         "lower(type) like '%sewer%' or lower(type) like '%drain%' or lower(type) like '%standing water%'")

def get(url, t=90, tries=5):
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cyvl-hackathon"})
            with urllib.request.urlopen(req, timeout=t) as r:
                return json.load(r)
        except Exception as ex:
            last = ex; print(f"  retry {k+1}/{tries} ({ex})", flush=True); time.sleep(3 * (k + 1))
    raise last

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

# 2) flooding complaints per block_code + category (live Socrata; fall back to the cached
#    complaints_blocks.geojson when the City endpoint is down -- the complaint counts are static,
#    so we can still recompute the validation join against the current ranking).
CB_PATH = os.path.join(WEB, "complaints_blocks.geojson")
per_block = {}   # geoid -> {total, cats:{}}
used_cache = False
try:
    q = {"$select": "block_code, type, count(1) as n", "$group": "block_code, type", "$where": FLOOD, "$limit": 8000}
    rows = get("https://data.somervillema.gov/resource/4pyi-uqq6.json?" + urllib.parse.urlencode(q))
    for r in rows:
        bc = r.get("block_code")
        if not bc or bc.strip() == "NA": continue
        n = int(r["n"]); b = per_block.setdefault(bc.strip(), {"total": 0, "cats": {}})
        b["total"] += n; cat = bucket(r["type"]); b["cats"][cat] = b["cats"].get(cat, 0) + n
except Exception as ex:
    if not os.path.exists(CB_PATH): raise
    used_cache = True
    print(f"warning: live 311 fetch failed ({ex}); reusing cached complaints_blocks.geojson", flush=True)
    for ft in json.load(open(CB_PATH))["features"]:
        pr = ft["properties"]; gid = str(pr.get("geoid"))
        cats = {k: int(v) for k, v in pr.items() if k not in ("geoid", "complaints")}
        per_block[gid] = {"total": int(pr.get("complaints", 0)), "cats": cats}

# date range (flooding) -- discover the date column from a sample row (it is not "date_created"
# on this dataset, which is why this was silently null), then min/max it.
date_range = None
try:
    sample = get("https://data.somervillema.gov/resource/4pyi-uqq6.json?" +
                 urllib.parse.urlencode({"$limit": 1, "$where": FLOOD}))
    keys = list(sample[0].keys()) if sample else []
    datef = next((k for k in keys if "date" in k.lower()
                  or k.lower() in ("opened", "created", "requested_datetime", "open_dt")), None)
    if datef:
        dr = get("https://data.somervillema.gov/resource/4pyi-uqq6.json?" +
                 urllib.parse.urlencode({"$select": f"min({datef}) mn, max({datef}) mx", "$where": FLOOD}))[0]
        date_range = [str(dr.get("mn", ""))[:10], str(dr.get("mx", ""))[:10]]
        print(f"311 date field: {datef} -> range {date_range}")
    else:
        print(f"warning: no date-like field in 311 records (keys={keys}); date_range left null")
except Exception as ex:
    print("warning: 311 date-range fetch failed:", ex)

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
if not used_cache:
    json.dump({"type": "FeatureCollection", "features": feats}, open(CB_PATH, "w"))
print(f"footprint blocks with complaints: {len(feats)}; total complaints: {total_fp}{' (from cache)' if used_cache else ''}")

# 4) validation vs citywide ranked cells (read ranking.geojson centroids; STRtree spatial join)
rk = json.load(open(os.path.join(WEB, "ranking.geojson")))["features"]
cells = []
for f in rk:
    ring = f["geometry"]["coordinates"][0]
    lon = sum(c[0] for c in ring) / len(ring); lat = sum(c[1] for c in ring) / len(ring)
    cells.append({"priority": f["properties"]["priority"], "pt": Point(lon, lat)})
polys = [bg[1] for bg in block_geoms]; counts = [bg[2] for bg in block_geoms]
tree = STRtree(polys)
for c in cells:
    c["bc"] = 0
    for i in tree.query(c["pt"]):
        if polys[i].contains(c["pt"]): c["bc"] = counts[i]; break
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
