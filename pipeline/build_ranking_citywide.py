"""
Citywide ponding-risk ranking over all of Somerville (50 m grid, clipped to City Limits).
Inputs: citywide DEM/depression (build_city_dem), merged catch basins (merge_basins),
citywide Cyvl pavement (S3). Same screening formula as the prototype.

Outputs: public/data/ranking.geojson (citywide) + public/data/priority_ranking.csv
"""
import json, os, math, urllib.request, urllib.parse
import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
PROC = os.path.join(HERE, "data", "processed"); WEB = os.path.join(ROOT, "public", "data")
to_utm = Transformer.from_crs(4326, 32619, always_xy=True)
to_wgs = Transformer.from_crs(32619, 4326, always_xy=True)

def getbytes(u, t=120):
    req = urllib.request.Request(u, headers={"User-Agent": "cyvl"})
    with urllib.request.urlopen(req, timeout=t) as r: return r.read()

meta = json.load(open(os.path.join(PROC, "dem_city_meta.json")))
MINX, MINY, RES, NX, NY = meta["minx"], meta["miny"], meta["res"], meta["nx"], meta["ny"]
DEM = np.load(os.path.join(PROC, "dem_city.npy"))
DEPR = np.load(os.path.join(PROC, "depression_city.npy"))
inside = np.isfinite(DEM)

# merged catch basins -> UTM
basins = json.load(open(os.path.join(PROC, "merged_catch_basins.geojson")))["features"]
bxy = np.array([to_utm.transform(*f["geometry"]["coordinates"][:2]) for f in basins]) if basins else np.empty((0, 2))

# citywide Cyvl pavement from S3 (cache locally)
pcache = os.path.join(PROC, "pavement_city.geojson")
if not os.path.exists(pcache):
    open(pcache, "wb").write(getbytes("https://cyvl-hackathon.s3.amazonaws.com/data/pavements_v2.geojson"))
pav_raw = json.load(open(pcache))
def pci_of(p):
    for k in ("condition_score", "pci", "PCI", "conditionScore", "score"):
        if p.get(k) is not None:
            try: return float(p[k])
            except Exception: return None
    return None
pav = []
for f in pav_raw["features"]:
    g = f.get("geometry");
    if not g: continue
    co = g["coordinates"]
    pts = co if g["type"] == "LineString" else [c for part in co for c in part]
    if not pts: continue
    lon = np.mean([c[0] for c in pts]); lat = np.mean([c[1] for c in pts])
    mx, my = to_utm.transform(lon, lat)
    pav.append((mx, my, pci_of(f.get("properties", {}))))
pav = np.array([(x, y, (np.nan if v is None else v)) for x, y, v in pav]) if pav else np.empty((0, 3))
print(f"basins {len(bxy)}, pavement segs {len(pav)}")

# hydrography (OSM water) -> one UTM polygon, used to drop open-water cells (Mystic + ponds)
def load_water():
    cache = os.path.join(PROC, "water_city.json")
    if not os.path.exists(cache):
        lons, lats = [], []
        for x in (MINX, MINX + NX*RES):
            for y in (MINY, MINY + NY*RES):
                lo, la = to_wgs.transform(x, y); lons.append(lo); lats.append(la)
        w, e = min(lons), max(lons); s, n = min(lats), max(lats)
        q = ("[out:json][timeout:90];("
             f'way["natural"="water"]({s},{w},{n},{e});'
             f'way["waterway"="riverbank"]({s},{w},{n},{e});'
             f'relation["natural"="water"]({s},{w},{n},{e});'
             f'relation["waterway"="riverbank"]({s},{w},{n},{e});'
             ");out geom;")
        body = urllib.parse.urlencode({"data": q}).encode()
        req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                     data=body, headers={"User-Agent": "cyvl"})
        with urllib.request.urlopen(req, timeout=120) as r:
            open(cache, "wb").write(r.read())
    try:
        js = json.load(open(cache))
    except Exception as ex:
        print("water: could not load hydrography, skipping mask:", ex); return None
    def ring(geom):
        if not geom or len(geom) < 4: return None
        try:
            p = Polygon([to_utm.transform(pt["lon"], pt["lat"]) for pt in geom])
            if not p.is_valid: p = p.buffer(0)
            return p if (not p.is_empty and p.area > 0) else None
        except Exception:
            return None
    polys = []
    for el in js.get("elements", []):
        if el["type"] == "way":
            p = ring(el.get("geometry"));  polys.append(p) if p else None
        elif el["type"] == "relation":
            for m in el.get("members", []):
                if m.get("role") == "outer":
                    p = ring(m.get("geometry"));  polys.append(p) if p else None
    return unary_union(polys) if polys else None

water = load_water()
print(f"water mask: {'none' if water is None else '%.2f km2 from hydrography' % (water.area/1e6)}")

CELL = 50.0; F = int(CELL / RES)
ncx = int(math.ceil(NX / F)); ncy = int(math.ceil(NY / F)); B = 15.0
rows = []
for cy in range(ncy):
    for cx in range(ncx):
        i0, i1 = cx*F, min((cx+1)*F, NX); j0, j1 = cy*F, min((cy+1)*F, NY)
        sub_in = inside[j0:j1, i0:i1]
        if not sub_in.any(): continue  # outside City Limits
        pond = float(DEPR[j0:j1, i0:i1][sub_in].mean())
        zmean = float(DEM[j0:j1, i0:i1][sub_in].mean())
        x0, x1 = MINX + i0*RES, MINX + i1*RES; y0, y1 = MINY + j0*RES, MINY + j1*RES
        if len(bxy):
            nb = int(((bxy[:,0]>=x0-B)&(bxy[:,0]<x1+B)&(bxy[:,1]>=y0-B)&(bxy[:,1]<y1+B)).sum())
        else: nb = 0
        pci = None
        if len(pav):
            m = (pav[:,0]>=x0)&(pav[:,0]<x1)&(pav[:,1]>=y0)&(pav[:,1]<y1)
            vals = pav[m,2]; vals = vals[~np.isnan(vals)]
            pci = float(vals.mean()) if len(vals) else None
        wfrac = 0.0
        if water is not None:
            cell = box(x0, y0, x1, y1)
            wfrac = (water.intersection(cell).area / cell.area) if cell.area else 0.0
        rows.append(dict(cx=cx, cy=cy, x0=x0, x1=x1, y0=y0, y1=y1, pond=pond, zmean=zmean, basins=nb, pci=pci, wfrac=wfrac))

# keep only cells with drainage/pavement evidence and drop open-water cells; normalize on survivors.
# (un-instrumented + water-fringe cells otherwise score ~90 by default and form a false red rim.)
n_before = len(rows)
rows = [r for r in rows if r["wfrac"] < 0.5 and (r["basins"] > 0 or r["pci"] is not None)]
print(f"cells: {n_before} candidate -> {len(rows)} ranked "
      f"({n_before - len(rows)} dropped: un-instrumented voids + open water)")
ponds = np.array([r["pond"] for r in rows]); p95 = float(np.percentile(ponds, 95)) or 1.0
for r in rows:
    s_pond = float(np.clip(r["pond"]/p95, 0, 1))
    s_basin = 1.0/(1.0 + r["basins"])
    s_pci = float(np.clip((100 - r["pci"])/100, 0, 1)) if r["pci"] is not None else 0.5
    r["s_pond"], r["s_basin"], r["s_pci"] = s_pond, s_basin, s_pci
    r["priority"] = round(100*(0.50*s_pond + 0.30*s_basin + 0.20*s_pci), 1)
rows.sort(key=lambda r: r["priority"], reverse=True)
for i, r in enumerate(rows, 1): r["rank"] = i

# ranking.geojson (polygons in WGS84)
feats = []
for r in rows:
    ring_u = [(r["x0"],r["y0"]),(r["x1"],r["y0"]),(r["x1"],r["y1"]),(r["x0"],r["y1"]),(r["x0"],r["y0"])]
    ring = [list(to_wgs.transform(x, y)) for x, y in ring_u]
    feats.append({"type":"Feature","geometry":{"type":"Polygon","coordinates":[ring]},
        "properties":{"rank":r["rank"],"priority":r["priority"],"ponding_ft":round(r["pond"],2),
            "basins":r["basins"],"mean_pci":(None if r["pci"] is None else round(r["pci"],1)),
            "s_pond":round(r["s_pond"],3),"s_basin_deficit":round(r["s_basin"],3),"s_pci":round(r["s_pci"],3)}})
json.dump({"type":"FeatureCollection","features":feats}, open(os.path.join(WEB,"ranking.geojson"),"w"))

import csv
with open(os.path.join(WEB, "priority_ranking.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["rank","x0_utm","y0_utm","zmean_ft","ponding_ft","basins","mean_pci","s_pond","s_basin_deficit","s_pci","priority"])
    for r in rows:
        w.writerow([r["rank"], round(r["x0"],1), round(r["y0"],1), round(r["zmean"],1), round(r["pond"],3),
                    r["basins"], ("" if r["pci"] is None else round(r["pci"],1)),
                    round(r["s_pond"],3), round(r["s_basin"],3), round(r["s_pci"],3), r["priority"]])
print(f"citywide ranked cells: {len(rows)} (top priority {rows[0]['priority']}); wrote ranking.geojson + csv")
