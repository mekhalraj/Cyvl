SOMERVILLE RAIN-RISK DXF -- README
=====================================
Coordinate system : EPSG:32619  (WGS84 / UTM zone 19N, METERS)  -- matches the LiDAR.
Vertical          : LiDAR native (WGS84 ellipsoidal). Z_USGS attribute = USGS EPQS (NAVD88, meters),
                    a secondary cross-check; it differs from LiDAR Z by ~the geoid (~ -27 m in MA).
Drawing units     : meters ($INSUNITS=6).

IN CIVIL 3D: assign coordinate system "UTM84-19N" (or EPSG:32619) to the drawing, then bring in your
LiDAR surface in the same system. All asset points carry true Z (sampled from the LiDAR DTM), so they
sit on the surface. DXFIN / MAPIMPORT this file.

LAYERS (entity counts): {'CB_CATCH_BASIN': 119, 'CB_MANHOLE': 265, 'PV_PAVEMENT_PCI': 123, 'CB_SIDEWALK': 0, 'CB_CURB': 0, 'MK_CROSSWALK': 0, 'MK_STOPBAR': 0, 'CB_RAMP': 0, 'RANK_PRIORITY': 169, 'TERRAIN_CONTOUR': 2366}

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
