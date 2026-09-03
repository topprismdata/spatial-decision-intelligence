"""Verify every dataset required by the pipeline is present and usable.

Reads docs/DATA.md requirements from a static manifest below (kept in sync by
hand); prints PASS/MISSING per dataset plus the exact fetch/rebuild command.
Exit code: 0 = runnable demo path exists, 1 = no usable input at all.

Usage: python3 scripts/verify_data_readiness.py
"""

import os
import sys
from pathlib import Path

_REPO = Path(os.environ.get("SDI_ROOT") or Path(__file__).resolve().parents[1])

# (path, min_files, min_mb, why, how_to_get)
DATASETS = [
    ("data/sample/sample_sites.xlsx", 1, 0.001, "demo pipeline input (no client data)",
     "python3 scripts/prepare_sample_data.py"),
    ("data/client_a_sites.xlsx", 0, 0, "client source list (private; REQUIRED for real runs)",
     "ask project owner; see docs/DATA.md §6 for the column contract"),
    ("data/beijing_shp", 20, 50, "OSM shapefiles consumed by scenic_*/satellite_wall_detection",
     "see docs/DATA.md §3.1 (Geofabrik beijing free shapefiles, ODbL)"),
    ("data/roads", 1, 1, "road tile extracts (road_step2*)",
     "python3 scripts/road_step2a_tiles.py"),
    ("data/buildings", 1, 0.1, "Overpass building windows (draw_step1*)",
     "python3 scripts/draw_step1_buildings.py"),
    ("data/roads_windows", 1, 0.1, "all-road windows (draw_step1b)",
     "python3 scripts/draw_step1b_allroads.py"),
    ("data/beijing_fixtures", 3, 0.5, "frozen OSM fixtures for tests/test_r2_real_osm_smoke.py",
     "docs/DATA.md §3.2, or request originals"),
    ("data/osm_snapshots", 2, 0.001, "committed ODM snapshot used by tests",
     "already in repo (git tracked)"),
    ("data/satellite", 1, 100, "satellite npz tiles for U-Net train/eval (draw_step9/10)",
     "requires client Excel first: docs/DATA.md §5"),
    ("data/osm_snapshots", 2, 0.001, "frozen OSM snapshot some tests reference",
     "python3 scripts/prepare_sample_data.py (writes sample/osm_window.json; or copy from project owner)"),
]

def check(rel, min_files, min_mb):
    p = _REPO / rel
    if not p.exists():
        return None
    if p.is_file():
        return 1, p.stat().st_size / 1048576
    files = sum(1 for _ in p.rglob("*") if _.is_file())
    mb = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576
    return files, mb


def main():
    demo_ok = False
    print(f"repo root: {_REPO}\n")
    for rel, mfiles, mmb, why, how in DATASETS:
        res = check(rel, mfiles, mmb)
        if res and res[0] >= mfiles and res[1] >= mmb:
            print(f"  OK      {rel:34} {res[0]:6} files {res[1]:8.1f} MB  — {why}")
            if rel == "data/sample/sample_sites.xlsx":
                demo_ok = True
        elif res:
            print(f"  PARTIAL {rel:34} {res[0]:6} files {res[1]:8.1f} MB  — {why}")
            print(f"          expected >= {mfiles} files / {mmb} MB — fix: {how}")
        else:
            print(f"  MISSING {rel:34} {'':6}        — {why}")
            print(f"          get it: {how}")
    if demo_ok:
        print("\nRESULT: demo path ready -> python3 run.py --input data/sample/sample_sites.xlsx")
        return 0
    client = (_REPO / "data/client_a_sites.xlsx").exists()
    if client:
        print("\nRESULT: client data present; generate demo set only if you also want samples.")
        return 0
    print("\nRESULT: no usable input. Run: python3 scripts/prepare_sample_data.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
