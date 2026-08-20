"""
评估 EXTREME_ASPECT_RATIO 判据的准确性:
- 误报: 已标记的 83 条中, 最小外接矩形短边(实际宽度)其实不窄的
- 漏报: 未标记的围栏中, 实际宽度很窄(带状走廊)但比例不超 10 的
"""
import math
import os

import pandas as pd
from shapely import wkt

from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = "data/client_a_sites.xlsx"

df_qa = pd.read_csv(os.path.join(PROJECT_ROOT, "outputs", "qa_issues_report.csv"),
                    usecols=["source_record_id", "qa_issues", "area_m2", "aspect_ratio"])

flagged_ids = set(df_qa[df_qa["qa_issues"].fillna("").str.contains("EXTREME_ASPECT_RATIO")]["source_record_id"])
all_flagged_ids = set(df_qa["source_record_id"])  # 已纳入报告的(带任何标记)
print(f"已标记 EXTREME_ASPECT_RATIO: {len(flagged_ids)} 条")

records = ExcelIngestionParser.parse_file(EXCEL_PATH)
rec_map = {r.source_record_id: r for r in records}
print(f"解析记录: {len(records)}")


def rect_dims_m(geom, lat):
    """最小旋转外接矩形的长/宽(米)。"""
    rect = geom.minimum_rotated_rectangle
    if rect.is_empty:
        return None
    from shapely.geometry import Polygon
    if not isinstance(rect, Polygon):
        return None
    c = list(rect.exterior.coords)
    if len(c) < 4:
        return None
    m_lat = 111132.954
    m_lng = 111412.84 * math.cos(math.radians(lat))
    d1 = math.hypot((c[1][0] - c[0][0]) * m_lng, (c[1][1] - c[0][1]) * m_lat)
    d2 = math.hypot((c[2][0] - c[1][0]) * m_lng, (c[2][1] - c[1][1]) * m_lat)
    return max(d1, d2), min(d1, d2)


# 分析已标记的 83 条 + 全量扫描漏报
NARROW_W = 30.0   # 宽度 < 30m 视为真窄
LONG_L = 300.0    # 长度 > 300m 视为长走廊

false_pos = []   # 已标记但宽度不窄
true_pos = []    # 已标记且真窄
missed = []      # 未标记但宽度窄+长度长

count = 0
for r in records:
    rid = r.source_record_id
    _, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
    if not n_wkt:
        continue
    try:
        geom = wkt.loads(n_wkt)
    except Exception:
        continue
    dims = rect_dims_m(geom, n_lat if n_lat else 39.9)
    if not dims:
        continue
    length_m, width_m = dims
    count += 1
    is_flagged = rid in flagged_ids
    if is_flagged:
        if width_m < NARROW_W:
            true_pos.append((rid, r.name_raw, r.city_raw, length_m, width_m))
        else:
            false_pos.append((rid, r.name_raw, r.city_raw, length_m, width_m))
    else:
        if width_m < NARROW_W and length_m > LONG_L:
            missed.append((rid, r.name_raw, r.city_raw, length_m, width_m))

print(f"\n有效几何: {count} 条")
print(f"\n=== 已标记 83 条的实证 ===")
print(f"真窄(宽度<30m): {len(true_pos)} 条")
print(f"不窄(宽度>=30m, 疑似误报): {len(false_pos)} 条")
if false_pos:
    print("\n误报明细(前15):")
    for rid, name, city, l, w in sorted(false_pos, key=lambda x: -x[4])[:15]:
        print(f"  {rid} {name} [{city}] 长{l:.0f}m x 宽{w:.0f}m")
print(f"\n=== 未标记但疑似漏报(宽<30m 且 长>300m) ===")
print(f"共 {len(missed)} 条")
for rid, name, city, l, w in sorted(missed, key=lambda x: -x[3])[:15]:
    print(f"  {rid} {name} [{city}] 长{l:.0f}m x 宽{w:.0f}m")
