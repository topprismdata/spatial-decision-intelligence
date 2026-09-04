"""Step 1b: 逐样本 Overpass 取局部路网 + 对齐度量（仅北京）."""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, json, time, math, random
sys.path.insert(0, str(_REPO))
import urllib.request, urllib.parse

import pandas as pd
from shapely import wkt
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from src.coordinate.transforms import transform_geometry_wkt, gcj02_to_wgs84

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
QA = str(_REPO / 'outputs/qa_issues_report.csv')
OVERPASS = "https://overpass-api.de/api/interpreter"

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
qa = pd.read_csv(QA)
m = qa.merge(df[["source_record_id", "小区名称", "城市", "坐标面[内置]"]], on="source_record_id", how="left")
m = m[m["坐标面[内置]"].notna() & (m["坐标面[内置]"].astype(str).str.len() > 10)]
m = m[m["城市"].astype(str).str.contains("北京")]

import re
street_pat = re.compile(r"街|路|胡同|巷|大道|大街")
street_ns = m[m["qa_issues"].str.contains("NARROW_STRIP") & m["小区名称"].astype(str).str.contains(street_pat)]
street_sample = street_ns.sample(20, random_state=42).assign(group="street")
rest = m[~m["source_record_id"].isin(street_sample["source_record_id"])]
rand_sample = rest.sample(20, random_state=42).assign(group="random")
sample = pd.concat([street_sample, rand_sample])
print("样本:", len(sample), "(北京 only)")

def fetch_roads(s, w, n, e, retries=3):
    q = f'[out:json][timeout:25];(way["highway"]({s:.6f},{w:.6f},{n:.6f},{e:.6f}););out geom;'
    for i in range(retries):
        try:
            req = urllib.request.Request(OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "fence-road-precheck/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception as ex:
            print(f"  retry {i+1}: {ex}")
            time.sleep(5 * (i + 1))
    return None

def fence_wgs84(row):
    wgs = transform_geometry_wkt(str(row["坐标面[内置]"]), gcj02_to_wgs84)
    return wkt.loads(wgs) if wgs else None

def axle_points(geom, step_m=20):
    """窄条取最小旋转外接矩形长轴中线；其他取骨架近似（centroid±长轴）。"""
    rect = geom.minimum_rotated_rectangle
    try:
        coords = list(rect.exterior.coords) if rect.geom_type == "Polygon" else list(rect.coords)
    except Exception:
        return None
    if len(coords) < 3:
        return None
    # 找外接矩形最长的两条对边 -> 长轴方向
    pts = coords[:-1] if coords[0] == coords[-1] else coords
    edges = [(pts[i], pts[(i+1) % len(pts)]) for i in range(len(pts))]
    e_sorted = sorted(edges, key=lambda e: math.dist(e[0], e[1]), reverse=True)
    (x1, y1), (x2, y2) = e_sorted[0]
    (x3, y3), (x4, y4) = e_sorted[1]
    # 两条长边中点连线 = 中轴线
    ax1, ay1 = (x1+x2)/2, (y1+y2)/2
    ax2, ay2 = (x3+x4)/2, (y3+y4)/2
    axis = LineString([(ax1, ay1), (ax2, ay2)])
    # 每步长采样（经纬度→米 近似：1° lat≈111320m）
    m_per_deg = 111320.0
    n = max(int(axis.length * m_per_deg / step_m), 2)
    pts_ax = [axis.interpolate(t / n, normalized=True) for t in range(n + 1)]
    return pts_ax, axis

def m_per_deg_lng(lat):
    return 111320.0 * math.cos(math.radians(lat))

results = []
for idx, row in sample.reset_index(drop=True).iterrows():
    g = fence_wgs84(row)
    if g is None or g.is_empty:
        continue
    minx, miny, maxx, maxy = g.bounds
    pad = 0.0025  # ~250m
    data = fetch_roads(miny - pad, minx - pad, maxy + pad, maxx + pad)
    if data is None:
        print(f"[{idx}] {row['source_record_id']} overpass fail")
        results.append({"id": row["source_record_id"], "name": row["小区名称"], "group": row["group"], "error": "overpass_fail"})
        continue
    lines = []
    for el in data.get("elements", []):
        if el.get("type") == "way" and "geometry" in el:
            c = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if len(c) >= 2:
                lines.append(LineString(c))
    if not lines:
        results.append({"id": row["source_record_id"], "name": row["小区名称"], "group": row["group"],
                        "n_roads": 0, "error": "no_roads"})
        continue
    tree = STRtree(lines)
    ap = axle_points(g if g.geom_type == "Polygon" else g.convex_hull)
    if ap is None:
        continue
    pts_ax, axis = ap
    dists, dxs, dys = [], [], []
    for p in pts_ax:
        i = tree.nearest(p)
        road = lines[i]
        np_ = nearest_points(road, p)[0]
        d = math.hypot((np_.x - p.x) * m_per_deg_lng(p.y), (np_.y - p.y) * 111320.0)
        dists.append(d)
        dxs.append((np_.x - p.x) * m_per_deg_lng(p.y))
        dys.append((np_.y - p.y) * 111320.0)
    dists_sorted = sorted(dists)
    med = dists_sorted[len(dists)//2]
    p90 = dists_sorted[int(len(dists)*0.9)]
    cov = sum(1 for d in dists if d < 15) / len(dists)
    results.append({
        "id": row["source_record_id"], "name": row["小区名称"], "group": row["group"],
        "n_roads": len(lines), "n_axle_pts": len(pts_ax),
        "dist_median_m": round(med, 1), "dist_p90_m": round(p90, 1),
        "cov15m": round(cov, 2),
        "mean_dx_m": round(sum(dxs)/len(dxs), 1), "mean_dy_m": round(sum(dys)/len(dys), 1),
    })
    print(f"[{idx}] {row['group']:6s} {row['source_record_id']} {str(row['小区名称'])[:14]:14s} roads={len(lines):3d} med={med:6.1f}m p90={p90:6.1f}m cov15={cov:.2f} dx={sum(dxs)/len(dxs):+6.1f} dy={sum(dys)/len(dys):+6.1f}")
    time.sleep(1.5)  # politeness

_out = _REPO / "outputs" / "road_precheck"; _out.mkdir(parents=True, exist_ok=True)
json.dump(results, open(_out / "precheck_results.json", "w"), ensure_ascii=False, indent=1)
print(f"\nsaved {_out / 'precheck_results.json'} | {len(results)} fences")
