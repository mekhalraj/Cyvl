"""
Fetch the City of Somerville's complete citywide stormwater network from the official
ArcGIS REST service (UtilitiesAndAssets2). Uses f=json (esri) + geometry conversion — the
server's f=geojson drops polyline layers. WGS84. Separate-provenance enrichment layers.

Outputs:  pipeline/data/city/<name>.geojson (full)  +  public/data/city_<name>.geojson (slim)
"""
import json, os, re, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CITY = os.path.join(HERE, "data", "city"); WEB = os.path.join(ROOT, "public", "data")
os.makedirs(CITY, exist_ok=True); os.makedirs(WEB, exist_ok=True)
BASE = "https://maps.somervillema.gov/arcgis/rest/services/UtilitiesAndAssets2/MapServer"
LAYERS = {2: "boundary", 8: "catch_basins", 13: "inlets", 14: "laterals",
          15: "outfalls", 16: "manholes", 19: "storm_mains", 31: "street_slopes"}
KEEP = re.compile(r"(objectid|^id$|type|material|diam|size|condition|elevation|name|slope|width|owner)", re.I)

def get(url, t=180):
    req = urllib.request.Request(url, headers={"User-Agent": "cyvl-hack"})
    with urllib.request.urlopen(req, timeout=t) as r: return json.load(r)

def to_geom(g):
    if not g: return None
    if "x" in g and g.get("x") is not None: return {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "paths" in g:
        ps = g["paths"]; return {"type": "LineString", "coordinates": ps[0]} if len(ps) == 1 else {"type": "MultiLineString", "coordinates": ps}
    if "rings" in g:
        return {"type": "Polygon", "coordinates": g["rings"]}
    return None

def fetch_layer(lid):
    # OBJECTID-cursor paging — robust even when the layer doesn't support resultOffset
    meta = get(BASE + f"/{lid}?f=json"); oidf = meta.get("objectIdFieldName", "OBJECTID")
    feats, last = [], -1
    for _ in range(120):  # safety cap (120k features)
        q = {"where": f"{oidf}>{last}", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
             "f": "json", "orderByFields": oidf, "resultRecordCount": 1000}
        d = get(BASE + f"/{lid}/query?" + urllib.parse.urlencode(q))
        fs = d.get("features", [])
        if not fs: break
        for ft in fs:
            geom = to_geom(ft.get("geometry"))
            if geom: feats.append({"type": "Feature", "geometry": geom, "properties": ft.get("attributes", {})})
            last = ft["attributes"].get(oidf, last)
        if len(fs) < 1000: break
    return feats

def slim(feats):
    out = []
    for f in feats:
        p = f.get("properties", {}) or {}
        out.append({"type": "Feature", "geometry": f["geometry"], "properties": {k: p[k] for k in p if KEEP.search(k)}})
    return out

summary = {}
for lid, name in LAYERS.items():
    feats = fetch_layer(lid)
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(CITY, f"{name}.geojson"), "w"))
    json.dump({"type": "FeatureCollection", "features": slim(feats)}, open(os.path.join(WEB, f"city_{name}.geojson"), "w"))
    gt = feats[0]["geometry"]["type"] if feats else "—"
    summary[name] = [len(feats), gt]
    print(f"  {name:14} {len(feats):>6}  {gt}")
print("DONE", json.dumps(summary))
