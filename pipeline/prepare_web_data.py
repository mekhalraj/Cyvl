"""
DEPRECATED -- do not run.

This was the PROTOTYPE web exporter for the small single-LiDAR-footprint pipeline
(build_dtm.py -> build_dxf.py). It wrote public/data/ranking.geojson + contours.geojson
in METERS with a `manholes` column and only covered the prototype footprint.

The live app is now CITYWIDE and those files are owned by other scripts:
  - public/data/ranking.geojson + priority_ranking.csv  <- build_ranking_citywide.py (feet, ponding_ft)
  - public/data/pavement.geojson                        <- build_ranking_citywide.py (citywide, slim)
  - public/data/merged_catch_basins.geojson, cyvl_*     <- merge_basins.py
  - public/data/complaints_blocks.geojson, validation   <- fetch_311.py

Running this script would OVERWRITE the citywide ranking.geojson with the prototype schema and
break the map (the UI reads `ponding_ft`, which the prototype output does not contain). It is kept
only for git history; the prototype web export is no longer part of the build.
"""
import sys

print(__doc__)
print("prepare_web_data.py is deprecated and intentionally does nothing. "
      "Use build_ranking_citywide.py / merge_basins.py / fetch_311.py instead.")
sys.exit(0)
