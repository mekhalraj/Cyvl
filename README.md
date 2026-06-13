# Cyvl Hackathon — Somerville Rain-Risk

A stormwater/ponding-risk screening tool + CAD deliverable for **East Somerville / Inner Belt**.
It ranks locations by flood risk and exports the infrastructure layers as a **georeferenced 3-D DXF**
for Autodesk Civil 3D, draped onto a LiDAR terrain surface.

- **Cyvl** supplies the 2-D infrastructure: catch basins, manholes, pavement (with PCI).
- A **LiDAR point cloud** (EPSG:32619 / UTM 19N) supplies the terrain; every asset is sampled to
  its true Z, with a **USGS EPQS** elevation as a secondary cross-check.
- Elevation-aware **ponding-risk ranking** over a 50 m grid.

## Pipeline
1. **`build_dtm.py`** — streams the LiDAR, builds a 1 m bare-earth DTM (min-Z) + a depression/ponding grid.
2. **`build_dxf.py`** — loads the Cyvl layers, reprojects to EPSG:32619, samples Z (LiDAR + USGS),
   computes the ranking, and writes the DXF + companion files.

## Outputs (`output/`)
- `somerville_rainrisk.dxf` — the deliverable (EPSG:32619, meters): catch basins, manholes,
  pavement-PCI, ranked ponding cells, terrain contours. Points are blocks carrying `Z_LIDAR` /
  `Z_USGS` / `FEATURE_ID`.
- `priority_ranking.csv` — ranked grid cells with sub-scores.
- `*_utm.geojson` — reprojected layers with Z. `README_DXF.txt` — Civil 3D import notes + ranking formula.

## CRS
All outputs are **EPSG:32619 (WGS84 / UTM 19N, meters)** to match the LiDAR. In Civil 3D, assign
coordinate system **UTM84-19N** and bring the LiDAR surface in the same system.

## Coverage note
Inside the modeled LiDAR footprint, Cyvl carries catch basins / manholes / pavement, but not
ramps/sidewalks/curbs/markings (those layers cover central/west Somerville, west of ~lon −71.090).
The ranking is an elevation-aware **screen**, not a hydraulic simulation — the full flood model runs
in Autodesk on the LiDAR surface.
