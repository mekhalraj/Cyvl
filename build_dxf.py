"""
Phases D-F : reproject Cyvl layers to the LiDAR CRS, drape them in 3-D on the DTM,
compute an elevation-aware ponding-risk ranking, and write a georeferenced DXF
(+ companion GeoJSON / CSV / README) for Autodesk Civil 3D.

Output CRS = EPSG:32619 (WGS84 / UTM 19N, meters) -- matches the LiDAR.
Run AFTER build_dtm.py has produced data/processed/dtm.* .
"""
import json, os, math, time
import numpy as np
from pyproj import Transformer
import ezdxf
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = r"C:\Users\mekha\somerville-rainrisk"
RAW  = ROOT + r"\data\raw"
PROC = ROOT + r"\data\processed"
OUT  = ROOT + r"\output"
TARGET = 32619
to_utm = Transformer.from_crs(4326, TARGET, always_xy=True)

# ---------- load DTM ----------
meta = json.load(open(PROC + r"\dtm_meta.json"))
MINX, MINY, RES, NX, NY = meta["minx"], meta["miny"], meta["res"], meta["nx"], meta["ny"]
DTM   = np.load(PROC + r"\dtm.npy")          # [iy, ix], iy=0 -> south
DEPR  = np.load(PROC + r"\depression.npy")

def cell_idx(x, y):
    ix = np.clip(((np.asarray(x) - MINX) / RES).astype(int), 0, NX - 1)
    iy = np.clip(((np.asarray(y) - MINY) / RES).astype(int), 0, NY - 1)
    return ix, iy

def sample(arr, x, y):
    ix, iy = cell_idx(x, y)
    return arr[iy, ix]

# ---------- load + reproject a Cyvl geojson ----------
def load_layer(name):
    """Return list of dicts: {geom_type, utm:[(x,y)...], lonlat:[(lon,lat)...], props}."""
    fp = os.path.join(RAW, name)
    if not os.path.exists(fp):
        return []
    feats = json.load(open(fp, encoding="utf-8")).get("features", [])
    out = []
    for ft in feats:
        g = ft.get("geometry")
        if not g:
            continue
        gt = g["type"]; co = g["coordinates"]
        if gt == "Point":
            lonlat = [tuple(co[:2])]
        elif gt in ("LineString",):
            lonlat = [tuple(c[:2]) for c in co]
        elif gt in ("MultiLineString", "Polygon"):
            lonlat = [tuple(c[:2]) for part in co for c in part]
        else:
            continue
        utm = [to_utm.transform(lon, lat) for lon, lat in lonlat]
        out.append(dict(gt=gt, utm=utm, lonlat=lonlat, props=ft.get("properties", {})))
    return out

layers = {n: load_layer(n + ".geojson") for n in
          ["catch_basin", "manhole", "ramp", "sidewalk", "curb",
           "crosswalk", "stopbar", "markings", "pavement"]}
for n, fs in layers.items():
    print(f"{n:12s}: {len(fs)} features")

# split markings into crosswalk / stopbar if a combined markings file was used
if layers["markings"]:
    def mtype(f): return str(f["props"].get("type", "")).upper()
    cw = [f for f in layers["markings"] if "CROSS" in mtype(f) or mtype(f) in ("CONTINENTAL", "LADDER", "STANDARD")]
    sb = [f for f in layers["markings"] if "STOP BAR" in mtype(f)]
    layers["crosswalk"] = layers["crosswalk"] or cw
    layers["stopbar"]   = layers["stopbar"]   or sb
    print(f"  split markings -> crosswalk {len(cw)}, stopbar {len(sb)}")

# ---------- USGS EPQS secondary elevation (best-effort, parallel) ----------
def epqs(lon, lat):
    try:
        r = requests.get("https://epqs.nationalmap.gov/v1/json",
                         params=dict(x=lon, y=lat, units="Meters", wkid=4326),
                         timeout=8)
        v = r.json().get("value")
        return float(v) if v not in (None, "", -1000000) else None
    except Exception:
        return None

_UCACHE_FP = os.path.join(OUT, "usgs_cache.json")
_UCACHE = json.load(open(_UCACHE_FP)) if os.path.exists(_UCACHE_FP) else {}
def add_usgs(feats, cap=500):
    pts = [(i, f["lonlat"][0]) for i, f in enumerate(feats) if f["gt"] == "Point"][:cap]
    if not pts:
        return 0
    todo = [(i, ll) for i, ll in pts if f"{ll[0]:.6f},{ll[1]:.6f}" not in _UCACHE]
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(epqs, ll[0], ll[1]): (ll) for i, ll in todo}
        for fut in as_completed(futs):
            ll = futs[fut]; _UCACHE[f"{ll[0]:.6f},{ll[1]:.6f}"] = fut.result()
    json.dump(_UCACHE, open(_UCACHE_FP, "w"))
    ok = 0
    for i, ll in pts:
        v = _UCACHE.get(f"{ll[0]:.6f},{ll[1]:.6f}")
        feats[i]["props"]["Z_usgs"] = v
        if v is not None: ok += 1
    return ok

# ---------- elevation-aware ponding-risk ranking (grid, 50 m) ----------
def build_ranking():
    CELL = 50.0
    bas = np.array([f["utm"][0] for f in layers["catch_basin"]]) if layers["catch_basin"] else np.empty((0, 2))
    mhs = np.array([f["utm"][0] for f in layers["manhole"]])     if layers["manhole"]     else np.empty((0, 2))
    pav = [(np.mean([p[0] for p in f["utm"]]), np.mean([p[1] for p in f["utm"]]),
            f["props"].get("condition_score")) for f in layers["pavement"]]
    ncx = int(math.ceil(NX * RES / CELL)); ncy = int(math.ceil(NY * RES / CELL))
    rows = []
    for cy in range(ncy):
        for cx in range(ncx):
            x0, x1 = MINX + cx*CELL, MINX + (cx+1)*CELL
            y0, y1 = MINY + cy*CELL, MINY + (cy+1)*CELL
            i0, i1 = int(cx*CELL/RES), min(int((cx+1)*CELL/RES), NX)
            j0, j1 = int(cy*CELL/RES), min(int((cy+1)*CELL/RES), NY)
            if i1 <= i0 or j1 <= j0:
                continue
            pond = float(DEPR[j0:j1, i0:i1].mean())
            zmean = float(DTM[j0:j1, i0:i1].mean())
            B = 15.0  # buffer so assets at a cell edge still count
            def inq(a): return 0 if len(a) == 0 else int(((a[:,0]>=x0-B)&(a[:,0]<x1+B)&(a[:,1]>=y0-B)&(a[:,1]<y1+B)).sum())
            nb, nm = inq(bas), inq(mhs)
            pcis = [p[2] for p in pav if x0 <= p[0] < x1 and y0 <= p[1] < y1 and p[2] is not None]
            pci = float(np.mean(pcis)) if pcis else None
            rows.append(dict(cx=cx, cy=cy, xc=(x0+x1)/2, yc=(y0+y1)/2,
                             pond=pond, zmean=zmean, basins=nb, manholes=nm, pci=pci))
    # normalize + score
    ponds = np.array([r["pond"] for r in rows])
    p95 = np.percentile(ponds, 95) or 1.0
    for r in rows:
        s_pond = float(np.clip(r["pond"] / p95, 0, 1))                 # low-lying / ponding
        s_basin = 1.0 / (1.0 + r["basins"])                            # drainage deficit
        s_pci = float(np.clip((100 - r["pci"]) / 100, 0, 1)) if r["pci"] is not None else 0.5
        r["s_pond"], r["s_basin"], r["s_pci"] = s_pond, s_basin, s_pci
        r["priority"] = round(100 * (0.50*s_pond + 0.30*s_basin + 0.20*s_pci), 1)
    rows.sort(key=lambda r: r["priority"], reverse=True)
    # only rank cells that actually contain infrastructure (drainage asset or paved road);
    # cells with no assets AND no pavement are off-street data voids, not findings.
    rows = [r for r in rows if r["basins"] or r["manholes"] or (r["pci"] is not None)]
    return rows

# ---------- write companion GeoJSON (reprojected, with Z) ----------
def write_geojson(name, feats):
    fc = {"type": "FeatureCollection", "crs": {"type": "name",
          "properties": {"name": f"EPSG:{TARGET}"}}, "features": []}
    for f in feats:
        zs = sample(DTM, [p[0] for p in f["utm"]], [p[1] for p in f["utm"]])
        if f["gt"] == "Point":
            geom = {"type": "Point", "coordinates": [f["utm"][0][0], f["utm"][0][1], float(zs[0])]}
        else:
            geom = {"type": "LineString",
                    "coordinates": [[p[0], p[1], float(z)] for p, z in zip(f["utm"], zs)]}
        fc["features"].append({"type": "Feature", "geometry": geom, "properties": f["props"]})
    json.dump(fc, open(os.path.join(OUT, name + "_utm.geojson"), "w"))

# ===================== MAIN =====================
t0 = time.time()
print("USGS EPQS (catch basins + manholes, best-effort)...")
ok_cb = add_usgs(layers["catch_basin"]); ok_mh = add_usgs(layers["manhole"])
print(f"  USGS hits: catch_basin {ok_cb}/{len(layers['catch_basin'])}, manhole {ok_mh}/{len(layers['manhole'])}")

rank = build_ranking()
print(f"ranking cells with signal: {len(rank)} (top priority {rank[0]['priority'] if rank else 'NA'})")

# ---------- DXF ----------
doc = ezdxf.new("R2018", setup=True)
doc.header["$INSUNITS"] = 6  # meters
doc.appids.add("CYVL")
msp = doc.modelspace()

LYR = {  # layer: aci color
 "CB_CATCH_BASIN":4, "CB_CATCH_BASIN_TXT":4, "CB_MANHOLE":8, "CB_MANHOLE_TXT":8,
 "CB_RAMP":3, "CB_RAMP_TXT":3, "CB_SIDEWALK":7, "CB_CURB":7,
 "MK_CROSSWALK":2, "MK_CROSSWALK_TXT":2, "MK_STOPBAR":2,
 "PV_PAVEMENT_PCI":1, "PV_PAVEMENT_PCI_TXT":1, "RD_STREETS":7,
 "TERRAIN_CONTOUR":34, "TERRAIN_CONTOUR_TXT":34,
 "RANK_PRIORITY":6, "RANK_PRIORITY_TXT":6}
for ln, col in LYR.items():
    doc.layers.add(ln, color=col)

def pci_color(v):
    if v is None: return 7
    return 3 if v >= 70 else (2 if v >= 55 else (30 if v >= 40 else 1))  # green/yellow/orange/red
def rank_color(p):
    return 3 if p < 40 else (2 if p < 60 else (30 if p < 75 else 1))

# point block factory (marker + attribute defs -> visible text)
def make_block(name, fields, r=1.2):
    blk = doc.blocks.new(name=name)
    blk.add_circle((0, 0), radius=r)
    blk.add_line((-r, 0), (r, 0)); blk.add_line((0, -r), (0, r))
    yoff = r + 0.5
    for tag in fields:
        blk.add_attdef(tag=tag, insert=(r + 0.5, yoff), height=1.2,
                       dxfattribs={"layer": name + "_TXT"})
        yoff -= 1.6
    return blk

make_block("CBB", ["FEATURE_ID", "Z_LIDAR", "Z_USGS"])
make_block("MHB", ["FEATURE_ID", "Z_LIDAR"])
make_block("RNK", ["PRIORITY", "POND_M", "BASINS"], r=4.0)

def place_point(feats, blockname, layer, attr_fn):
    n = 0
    for f in feats:
        x, y = f["utm"][0]; z = float(sample(DTM, [x], [y])[0])
        ref = msp.add_blockref(blockname, (x, y, z), dxfattribs={"layer": layer})
        ref.add_auto_attribs(attr_fn(f, z))
        ref.set_xdata("CYVL", [(1000, json.dumps(f["props"])[:240])])
        n += 1
    return n

def place_lines(feats, layer, txt_layer=None, label_fn=None, color_fn=None):
    n = 0
    for f in feats:
        zs = sample(DTM, [p[0] for p in f["utm"]], [p[1] for p in f["utm"]])
        pts = [(p[0], p[1], float(z)) for p, z in zip(f["utm"], zs)]
        if len(pts) < 2:
            continue
        attribs = {"layer": layer}
        if color_fn: attribs["color"] = color_fn(f)
        pl = msp.add_polyline3d(pts, dxfattribs=attribs)
        pl.set_xdata("CYVL", [(1000, json.dumps(f["props"])[:240])])
        if label_fn and txt_layer:
            mid = pts[len(pts)//2]
            t = msp.add_text(label_fn(f), height=1.2, dxfattribs={"layer": txt_layer})
            t.set_placement((mid[0], mid[1], mid[2]))
        n += 1
    return n

counts = {}
counts["CB_CATCH_BASIN"] = place_point(
    layers["catch_basin"], "CBB", "CB_CATCH_BASIN",
    lambda f, z: {"FEATURE_ID": str(f["props"].get("feature_id", "")),
                  "Z_LIDAR": f"{z:.2f}",
                  "Z_USGS": ("" if f["props"].get("Z_usgs") is None else f"{f['props']['Z_usgs']:.2f}")})
counts["CB_MANHOLE"] = place_point(
    layers["manhole"], "MHB", "CB_MANHOLE",
    lambda f, z: {"FEATURE_ID": str(f["props"].get("feature_id", "")), "Z_LIDAR": f"{z:.2f}"})

counts["PV_PAVEMENT_PCI"] = place_lines(
    layers["pavement"], "PV_PAVEMENT_PCI", "PV_PAVEMENT_PCI_TXT",
    label_fn=lambda f: f"PCI {f['props'].get('condition_score','?')}",
    color_fn=lambda f: pci_color(f["props"].get("condition_score")))

# pedestrian/marking layers (may be empty in this footprint)
counts["CB_SIDEWALK"] = place_lines(layers["sidewalk"], "CB_SIDEWALK")
counts["CB_CURB"]     = place_lines(layers["curb"], "CB_CURB")
counts["MK_CROSSWALK"]= place_lines(layers["crosswalk"], "MK_CROSSWALK")
counts["MK_STOPBAR"]  = place_lines(layers["stopbar"], "MK_STOPBAR")
counts["CB_RAMP"]     = place_point(layers["ramp"], "MHB", "CB_RAMP",
    lambda f, z: {"FEATURE_ID": str(f["props"].get("feature_id", "")), "Z_LIDAR": f"{z:.2f}"}) if layers["ramp"] else 0

# ranking layer
nr = 0
for r in rank:
    z = float(sample(DTM, [r["xc"]], [r["yc"]])[0])
    ref = msp.add_blockref("RNK", (r["xc"], r["yc"], z), dxfattribs={"layer": "RANK_PRIORITY"})
    ref.dxf.color = rank_color(r["priority"])
    ref.add_auto_attribs({"PRIORITY": str(r["priority"]), "POND_M": f"{r['pond']:.2f}", "BASINS": str(r["basins"])})
    nr += 1
counts["RANK_PRIORITY"] = nr

# contours from DTM (2 m interval)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
xs = MINX + (np.arange(NX) + 0.5) * RES
ys = MINY + (np.arange(NY) + 0.5) * RES
Xc, Yc = np.meshgrid(xs, ys)
zmin, zmax = np.floor(DTM.min()), np.ceil(DTM.max())
levels = np.arange(zmin, zmax + 0.1, 2.0)
cs = plt.contour(Xc, Yc, DTM, levels=levels)
ncont = 0
for lvl, segs in zip(cs.levels, cs.allsegs):
    for seg in segs:
        if len(seg) < 2:
            continue
        pts = [(float(x), float(y), float(lvl)) for x, y in seg]
        msp.add_polyline3d(pts, dxfattribs={"layer": "TERRAIN_CONTOUR"})
        ncont += 1
counts["TERRAIN_CONTOUR"] = ncont
plt.close("all")

dxf_path = os.path.join(OUT, "somerville_rainrisk.dxf")
doc.saveas(dxf_path)
print("layer entity counts:", counts)
print("wrote", dxf_path)

# ---------- companions ----------
for n in ["catch_basin", "manhole", "pavement", "sidewalk", "curb", "crosswalk", "stopbar"]:
    if layers[n]:
        write_geojson(n, layers[n])

import csv
with open(os.path.join(OUT, "priority_ranking.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["rank", "xc_utm", "yc_utm", "zmean_m", "ponding_m", "basins", "manholes",
                "mean_pci", "s_pond", "s_basin_deficit", "s_pci", "priority"])
    for i, r in enumerate(rank, 1):
        w.writerow([i, round(r["xc"], 2), round(r["yc"], 2), round(r["zmean"], 2),
                    round(r["pond"], 3), r["basins"], r["manholes"],
                    ("" if r["pci"] is None else round(r["pci"], 1)),
                    round(r["s_pond"], 3), round(r["s_basin"], 3), round(r["s_pci"], 3), r["priority"]])

readme = f"""SOMERVILLE RAIN-RISK DXF -- README
=====================================
Coordinate system : EPSG:32619  (WGS84 / UTM zone 19N, METERS)  -- matches the LiDAR.
Vertical          : LiDAR native (WGS84 ellipsoidal). Z_USGS attribute = USGS EPQS (NAVD88, meters),
                    a secondary cross-check; it differs from LiDAR Z by ~the geoid (~ -27 m in MA).
Drawing units     : meters ($INSUNITS=6).

IN CIVIL 3D: assign coordinate system "UTM84-19N" (or EPSG:32619) to the drawing, then bring in your
LiDAR surface in the same system. All asset points carry true Z (sampled from the LiDAR DTM), so they
sit on the surface. DXFIN / MAPIMPORT this file.

LAYERS (entity counts): {counts}

RANKING: elevation-aware ponding-risk SCREEN over a 50 m grid:
  priority = 100 * (0.50*ponding + 0.30*drainage_deficit + 0.20*poor_pavement)
   - ponding          = how far the cell sits below its local ~50 m average (DTM low spot)
   - drainage_deficit = 1/(1+catch_basin_count) in the cell
   - poor_pavement    = (100 - mean PCI)/100
This is a SCREEN, not a hydraulic simulation -- the full flood model is the Autodesk+LiDAR step.
See priority_ranking.csv for all scored cells and sub-scores.

NOTE ON COVERAGE: inside the LiDAR footprint the Cyvl project carries catch basins, manholes and
pavement (with PCI), but NOT ramps/sidewalks/curbs/markings (those layers only cover central/west
Somerville, west of ~lon -71.090). Those DXF layers therefore exist but are empty here.
"""
open(os.path.join(OUT, "README_DXF.txt"), "w").write(readme)
print(f"DONE in {time.time()-t0:.0f}s -> {OUT}")
