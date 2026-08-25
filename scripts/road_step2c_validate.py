"""Step 2c: 用底表自带点坐标(经度/纬度)独立交叉验证双假设 CRS 判定.

原理: 点坐标与多边形必须同一坐标系。设点为 GCJ-02:
  d_gcj = dist(point, 原始多边形)          → 多边形原始坐标也是 GCJ-02 时应很小
  d_wgs = dist(point, 原始多边形升到GCJ)    → 多边形原始坐标是 WGS-84 时应很小
两者取小者即为多边形真实 CRS，与路网打标 label 对照。
另计算 GCJ 偏移量级 |wgs84_to_gcj02(centroid)-centroid| 供参考。
"""
import sys, math
sys.path.insert(0, "/Users/user/WorkBuddy/2026-08-18-17-47-15")

import pandas as pd
from shapely import wkt
from shapely.geometry import Point
from shapely.ops import transform as shp_transform

from src.coordinate.transforms import wgs84_to_gcj02

EXCEL = "data/client_a_sites.xlsx"
ALIGN = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/road_alignment_beijing.csv"
OUT = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/road_alignment_beijing_validated.csv"

M_LAT = 111320.0

def dist_m2(p, geom):
    q = shapely_nearest_point(p, geom)
    dx = (q.x - p.x) * M_LAT * math.cos(math.radians(p.y))
    dy = (q.y - p.y) * M_LAT
    return math.hypot(dx, dy)

def shapely_nearest_point(p, geom):
    # shapely 2.x
    import shapely
    return shapely.ops.nearest_points(geom, p)[0]

def lift_gcj(geom):
    def _t(x, y, z=None):
        gx, gy = wgs84_to_gcj02(x, y)
        return (gx, gy) if z is None else (gx, gy, z)
    return shp_transform(_t, geom)

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
al = pd.read_csv(ALIGN)

m2 = al.merge(df[["source_record_id", "经度", "纬度", "坐标面[内置]"]], on="source_record_id", how="left")
rows = []
for _, r in m2.iterrows():
    rec = {"source_record_id": r["source_record_id"], "name": r["name"], "label": r["label"]}
    try:
        lon, lat = float(r["经度"]), float(r["纬度"])
        g_raw = wkt.loads(str(r["坐标面[内置]"]))
    except Exception:
        rec["point_valid"] = False
        rows.append(rec)
        continue
    if not (115 < lon < 118) or not (39 < lat < 42) or g_raw.is_empty:
        rec["point_valid"] = False
        rows.append(rec)
        continue
    p = Point(lon, lat)
    g_gcj = lift_gcj(g_raw)  # 假设原始是 WGS-84, 升到 GCJ 与点比
    d_gcj = dist_m2(p, g_raw)
    d_wgs = dist_m2(p, g_gcj)
    # GCJ 偏移量级 (多边形质心)
    c = g_raw.centroid
    cg = wgs84_to_gcj02(c.x, c.y)
    off = math.hypot((cg[0]-c.x) * M_LAT * math.cos(math.radians(c.y)), (cg[1]-c.y) * M_LAT)
    if d_gcj <= d_wgs:
        crs_vote = "GCJ02"
    else:
        crs_vote = "WGS84"
    rec.update({"point_valid": True, "d_gcj_m": round(d_gcj, 1), "d_wgs_m": round(d_wgs, 1),
                "crs_vote": crs_vote, "gcj_offset_m": round(off, 0)})
    rows.append(rec)

v = pd.DataFrame(rows)
v.to_csv(OUT, index=False)

ok = v[v["point_valid"] == True].copy()
print(f"有效点 {len(ok)} / {len(v)}")
print("\nGCJ 偏移量级 (北京): min %.0f med %.0f max %.0f m" %
      (ok["gcj_offset_m"].min(), ok["gcj_offset_m"].median(), ok["gcj_offset_m"].max()))

# 点投票 vs 路网打标 交叉表
def group(l):
    if l == "ROAD_ALIGNED": return "ROAD_ALIGNED(gcj)"
    if l.startswith("POLYGON_CRS_WGS84"): return "WGS84(路网)"
    if l.startswith("ORPHAN"): return "ORPHAN"
    return "NONE"
ok["grp"] = ok["label"].map(group)
print("\n=== 点坐标投票 × 路网打标 (行=打标, 列=点投票) ===")
print(pd.crosstab(ok["grp"], ok["crs_vote"]).to_string())
print("\n=== 一致率 ===")
for g in ["ROAD_ALIGNED(gcj)", "WGS84(路网)", "ORPHAN", "NONE"]:
    sub = ok[ok["grp"] == g]
    if len(sub) == 0: continue
    if g == "WGS84(路网)":
        agree = (sub["crs_vote"] == "WGS84").mean()
    elif g == "ROAD_ALIGNED(gcj)":
        agree = (sub["crs_vote"] == "GCJ02").mean()
    else:
        agree = None
    print(f"{g}: n={len(sub)}" + (f" 点投票一致率={agree:.0%}" if agree is not None else ""))

# WGS84 组里点投票不一致的样例
bad = ok[(ok["grp"] == "WGS84(路网)") & (ok["crs_vote"] != "WGS84")]
print("\n路网判 WGS84 但点投 GCJ02 的不一致样例 (d_gcj 应小):")
print(bad[["source_record_id", "name", "d_gcj_m", "d_wgs_m", "gcj_offset_m"]].head(10).to_string(index=False))

bad2 = ok[(ok["grp"] == "ROAD_ALIGNED(gcj)") & (ok["crs_vote"] != "GCJ02")]
print("\n路网判 ROAD_ALIGNED 但点投 WGS84 的不一致样例:")
print(bad2[["source_record_id", "name", "d_gcj_m", "d_wgs_m"]].head(10).to_string(index=False))
