# -*- coding: utf-8 -*-
"""按文献标准(MIC 最大内切圆 + 均宽)复核 NARROW_STRIP 判定。

文献依据:
- ArcGIS Data Reviewer / Sci Rep 2025: 薄度比率 4*pi*A/P^2 识别 sliver
- JTS MaximumInscribedCircle / PostGIS ST_MaximumInscribedCircle: 不可达极点半径
  = 多边形最宽处半宽, 是"窄多边形检测"的工业标准
- Mestetskiy VISAPP 2015: 中轴宽度函数(径向函数)是宽度的严格定义,
  均宽(2A/P)为其一阶近似, MIC 半径为其最大值
"""
import math
import pandas as pd
from shapely import wkt, maximum_inscribed_circle
from shapely.geometry import MultiPolygon, Polygon
from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence

EXCEL = "data/client_a_sites.xlsx"

df = pd.read_csv("outputs/qa_issues_report.csv",
                 usecols=["source_record_id", "qa_issues", "mean_width_m", "area_m2"])
narrow_ids = set(df[df["qa_issues"].fillna("").str.contains("NARROW_STRIP")]["source_record_id"])
print(f"NARROW_STRIP 待复核: {len(narrow_ids)} 条")

records = ExcelIngestionParser.parse_file(EXCEL)
rows = []
for r in records:
    if r.source_record_id not in narrow_ids:
        continue
    _, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
    if not n_wkt:
        continue
    try:
        geom = wkt.loads(n_wkt)
    except Exception:
        continue
    if isinstance(geom, MultiPolygon):
        # 多碎块: 取最大块算 MIC
        geom = max(geom.geoms, key=lambda p: p.area)
    if not isinstance(geom, Polygon):
        continue
    m_lat = 111132.954
    m_lng = 111412.84 * math.cos(math.radians(n_lat or 39.9))
    # MIC 在度空间算, 半径换算成米: 用两轴均值近似
    try:
        mic = maximum_inscribed_circle(geom)
        mic_r_m = mic.length * (m_lat + m_lng) / 2.0
    except Exception:
        mic_r_m = float("nan")
    perim_m = geom.length * (m_lat + m_lng) / 2.0
    area_m2 = geom.area * m_lat * m_lng
    mean_w = 2 * area_m2 / perim_m if perim_m > 0 else 0
    rows.append((r.source_record_id, r.name_raw, mean_w, 2 * mic_r_m, mic_r_m / (mean_w / 2)))

d = pd.DataFrame(rows, columns=["id", "name", "mean_w_m", "mic_diam_m", "mic_ratio"])
d = d.dropna(subset=["mic_diam_m"])
print(f"\n成功计算: {len(d)} 条")
print("\n== MIC 直径分布 ==")
print(d["mic_diam_m"].describe().round(1).to_string())

print("\n== 按文献双指标分类 ==")
uniform = d[d["mic_diam_m"] < 50]
mixed = d[d["mic_diam_m"] >= 50]
print(f"A. 整体窄走廊 (均宽<25 且 MIC直径<50m): {len(uniform)} 条")
print(f"B. 大块带窄尾/锯齿 (均宽<25 但 MIC直径>=50m): {len(mixed)} 条")
print(f"   B 类 MIC直径中位数: {mixed['mic_diam_m'].median() if len(mixed) else 0:.0f}m")

print("\n== B 类典型(大块主体+窄尾巴/锯齿边界) TOP10 ==")
if len(mixed):
    print(mixed.sort_values("mic_diam_m", ascending=False).head(10).to_string(index=False))

print("\n== A 类最窄 TOP10 (真·线状退化) ==")
if len(uniform):
    print(uniform.sort_values("mean_w_m").head(10).to_string(index=False))

# 尺度交叉验证: A 类里均宽与 MIC 直径的比值(接近1=均匀窄, 远小于1=宽窄不均)
print("\n== A 类 均宽/MIC直径 比值分布 (1=粗细均匀) ==")
if len(uniform):
    ratio = (uniform["mean_w_m"] / uniform["mic_diam_m"]).clip(0, 1)
    print(ratio.describe().round(2).to_string())
    print(f"比值<0.5 (宽窄严重不均, 有细脖子): {(ratio < 0.5).sum()} 条")

# 对照: 全量里均宽>=25 的正常围栏, MIC 直径是否都大(规则不误伤验证)
ok_ids = set(df[df["mean_width_m"] >= 25]["source_record_id"]) - narrow_ids
print(f"\n== 对照组(均宽>=25 未标记): {len(ok_ids)} 条, 抽样 300 条验 MIC ==")
import random
random.seed(42)
sample_ids = random.sample(sorted(ok_ids), min(300, len(ok_ids)))
sample_set = set(sample_ids)
checked = 0
fp = 0
for r in records:
    if r.source_record_id not in sample_set:
        continue
    _, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
    if not n_wkt:
        continue
    try:
        geom = wkt.loads(n_wkt)
    except Exception:
        continue
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda p: p.area)
    if not isinstance(geom, Polygon):
        continue
    m_lat = 111132.954
    m_lng = 111412.84 * math.cos(math.radians(n_lat or 39.9))
    try:
        mic = maximum_inscribed_circle(geom)
        mic_r_m = mic.length * (m_lat + m_lng) / 2.0
    except Exception:
        continue
    checked += 1
    if 2 * mic_r_m < 50:  # 对照组出现 MIC 直径<50 -> 若单用 MIC 会误伤
        fp += 1
print(f"对照组检查 {checked} 条, 其中 MIC直径<50m 的: {fp} 条 (即单纯 MIC 规则会误伤的数量)")
