"""Generate a synthetic, publicly-safe demo dataset for the pipeline.

Writes data/sample/sample_sites.xlsx whose column names exactly match the
ingestion contract in src/ingestion/parser.py::parse_file (sheet name
"sheet1"), so `python3 run.py --input data/sample/sample_sites.xlsx` works
out of the box without any client data.

All geometry is procedurally generated in an open area (no real addresses,
no client names, coordinates are random blocks inside a coarse Beijing-area
bbox). Optionally fetches a small Overpass window to make the OSM-backed
scripts runnable; network failures degrade gracefully to synthetic-only.

Usage:
    python3 scripts/prepare_sample_data.py [--records 30] [--bbox lat0,lon0,lat1,lon1]
"""

import argparse
import json
import math
import os
import random
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_REPO = Path(os.environ.get("SDI_ROOT") or Path(__file__).resolve().parents[1])
OUT_DIR = _REPO / "data" / "sample"
OVERPASS = "https://overpass-api.de/api/interpreter"
SHEET = "sheet1"

COLUMNS = [
    "小区编码", "小区名称", "小区地址",
    "省份名称", "城市", "区[内置]", "街道[内置]",
    "经度", "纬度", "坐标面[内置]", "面积[内置]",
]


def rectangle(lng, lat, w, h, jitter=0.0, seed=0):
    """Axis-aligned WKT polygon around (lng, lat), degrees."""
    rnd = random.Random(seed)
    x0, y0 = lng - w / 2, lat - h / 2
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h), (x0, y0)]
    if jitter:
        pts = [(x + rnd.uniform(-jitter, jitter), y + rnd.uniform(-jitter, jitter)) for x, y in pts]
    pts[-1] = pts[0]  # keep ring closed (RFC 7946 style)
    return "POLYGON((" + ", ".join(f"{x:.6f} {y:.6f}" for x, y in pts) + "))"


def build_records(n=30, bbox=(39.85, 116.25, 39.95, 116.45), seed=42):
    rnd = random.Random(seed)
    lat0, lng0, lat1, lng1 = bbox
    rows = []
    for i in range(1, n + 1):
        lng = rnd.uniform(lng0 + 0.004, lng1 - 0.004)
        lat = rnd.uniform(lat0 + 0.004, lat1 - 0.004)
        w = rnd.uniform(0.0008, 0.0028)
        h = w * rnd.uniform(0.55, 1.15)
        area = round((w * 111320 * math.cos(math.radians(lat))) * (h * 110540), 1)
        rows.append({
            "小区编码": f"SAMPLE{i:04d}",
            "小区名称": f"示例小区{i:02d}区",
            "小区地址": f"北京市示例区示例路{i}号",
            "省份名称": "北京市",
            "城市": "北京市",
            "区[内置]": "示例区",
            "街道[内置]": f"示例街道{i % 7 + 1}",
            "经度": round(lng, 6),
            "纬度": round(lat, 6),
            "坐标面[内置]": rectangle(lng, lat, w, h, jitter=w * 0.03, seed=seed + i),
            "面积[内置]": area,
        })
    return rows


def fetch_osm_window(bbox, out_path, timeout=90):
    """Best-effort small Overpass pull so OSM-backed scripts have input."""
    lat0, lng0, lat1, lng1 = bbox
    q = (f'[out:json][timeout:60];'
         f'(way["highway"]({lat0},{lng0},{lat1},{lng1});'
         f'way["landuse"="residential"]({lat0},{lng0},{lat1},{lng1}););out geom;')
    try:
        req = urllib.request.Request(
            OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
            headers={"User-Agent": "sdi-sample-data/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # network optional
        print(f"[osm] skipped ({type(exc).__name__}: {str(exc)[:80]})")
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (out_path.parent / (out_path.stem + "_manifest.json")).write_text(
        json.dumps({
            "source": "OpenStreetMap", "url": OVERPASS, "query": q,
            "bbox": ",".join(f"{v:.4f}" for v in bbox),
            "element_count": len(data.get("elements", [])),
            "license": "ODbL", "frozen": True,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[osm] {len(data.get('elements', []))} elements -> {out_path.relative_to(_REPO)}")
    return True


def _overpass_to(name, q, out_dir, timeout=180):
    try:
        req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "sdi-sample-data/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print(f"[fixtures] {name}: fetch skipped ({type(exc).__name__}: {str(exc)[:70]})")
        return False
    (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n = len(data.get("elements", []))
    print(f"[fixtures] {name}: {n} elements")
    return n > 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--records", type=int, default=30)
    ap.add_argument("--bbox", default="39.85,116.25,39.95,116.45",
                    help="lat0,lng0,lat1,lon1 coarse area for synthetic blocks")
    ap.add_argument("--skip-osm", action="store_true")
    ap.add_argument("--with-fixtures", action="store_true",
                    help="(re)pull data/beijing_fixtures/*.json (ODbL) used by "
                         "tests/test_r2_real_osm_smoke.py — collaborators fetch locally, "
                         "the repo stays free of raw geo data")
    a = ap.parse_args()
    bbox = tuple(float(v) for v in a.bbox.split(","))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_records(a.records, bbox)
    df = pd.DataFrame(rows, columns=COLUMNS)
    xlsx = OUT_DIR / "sample_sites.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=SHEET, index=False)
    print(f"[xlsx] {len(df)} records -> {xlsx.relative_to(_REPO)} (sheet '{SHEET}')")

    csv = OUT_DIR / "sample_sites.csv"
    df.to_csv(csv, index=False, encoding="utf-8-sig")
    print(f"[csv ] {csv.relative_to(_REPO)} (spreadsheet-safe copy)")

    if not a.skip_osm:
        ok = fetch_osm_window(bbox, _REPO / "data" / "sample" / "osm_window.json")
        if not ok:
            print("[hint] offline? set --skip-osm; OSM-backed steps need network later")

    if a.with_fixtures:
        fx = _REPO / "data" / "beijing_fixtures"
        fx.mkdir(parents=True, exist_ok=True)
        wide = (39.70, 115.70, 40.70, 116.90)
        for key, q in (
            ("residential_500", f'[out:json][timeout:120];(way["landuse"="residential"]({wide[0]},{wide[1]},{wide[2]},{wide[3]}););out geom 500;'),
            ("buildings_500", f'[out:json][timeout:120];(way["building"]({wide[0]},{wide[1]},{wide[2]},{wide[3]}););out geom 500;'),
            ("roads_strong_500", f'[out:json][timeout:120];(way["highway"~"primary|secondary"]({wide[0]},{wide[1]},{wide[2]},{wide[3]}););out geom 500;'),
        ):
            _overpass_to(key, q, fx)
        print("[fixtures] test_r2_real_osm_smoke inputs refreshed (counts may differ "
              "from the original freeze; assertions only need >=1 element geometry)")

    print("\nNext: python3 run.py --input data/sample/sample_sites.xlsx")


if __name__ == "__main__":
    main()
