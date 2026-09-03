"""
Rebuild qa_issues_report.csv with the literature-grounded width rules:
- NARROW_STRIP:   MIC diameter < 50m AND rect length > 100m (JTS/PostGIS
                  MaximumInscribedCircle standard + length guard)
- JAGGED_BOUNDARY: mean width < 30% of MIC width (perimeter inflated by
                  zigzag boundary; distinct defect from narrowness)
- ELONGATED_BLOCK: ratio > 10 but widths healthy (informational)
Lightweight: rule-based semantics + geometry QA only, no embeddings/rerank.
"""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[2])
import os
import sys

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence
from src.geometry.validation import GeometryQAEngine
from src.entity_resolution.pair_features import parse_chinese_community_semantics
from src.domain.models import EntityType

OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
EXCEL_PATH = str(_REPO / 'data/client_a_sites.xlsx')

old = pd.read_csv(os.path.join(OUTPUT_DIR, "qa_issues_report.csv"))
old_extreme = set(old[old["qa_issues"].fillna("").str.contains("EXTREME_ASPECT_RATIO")]["source_record_id"])
print(f"旧报告: {len(old)} 行; 其中 EXTREME_ASPECT_RATIO {len(old_extreme)} 条")

records = ExcelIngestionParser.parse_file(EXCEL_PATH)
print(f"解析记录: {len(records)}")

qa_rows = []
new_narrow, new_elongated, new_jagged = [], [], []
for r in records:
    sem = parse_chinese_community_semantics(r)
    coord_eval, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
    qa_res, clean_wkt, feats = GeometryQAEngine.validate_and_extract_features(r.source_record_id, n_wkt)

    if qa_res.issues or coord_eval.notes or qa_res.score < 1.0 or sem["entity_type"] != EntityType.RESIDENTIAL_COMMUNITY:
        qa_rows.append({
            "source_record_id": r.source_record_id,
            "name": r.name_raw,
            "entity_type": sem["entity_type"].value,
            "city": r.city_raw,
            "district": r.district_raw,
            "coord_status": coord_eval.coordinate_status.value,
            "delta_lng": coord_eval.delta_lng,
            "delta_lat": coord_eval.delta_lat,
            "geom_qa_score": qa_res.score,
            "geom_decision": qa_res.decision,
            "area_m2": feats.get("area_m2", 0.0),
            "compactness": feats.get("compactness", 0.0),
            "aspect_ratio": feats.get("aspect_ratio", 1.0),
            "rect_length_m": feats.get("rect_length_m", 0.0),
            "rect_width_m": feats.get("rect_width_m", 0.0),
            "mean_width_m": feats.get("mean_width_m", 0.0),
            "max_width_m": feats.get("max_width_m", 0.0),
            "qa_issues": "; ".join(qa_res.issues),
            "coord_notes": "; ".join(coord_eval.notes)
        })
        if "NARROW_STRIP" in qa_res.issues:
            new_narrow.append(r.source_record_id)
        if "ELONGATED_BLOCK" in qa_res.issues:
            new_elongated.append(r.source_record_id)
        if "JAGGED_BOUNDARY" in qa_res.issues:
            new_jagged.append(r.source_record_id)

df = pd.DataFrame(qa_rows)
df.to_csv(os.path.join(OUTPUT_DIR, "qa_issues_report.csv"), index=False, encoding="utf-8-sig")
print(f"\n新报告: {len(df)} 行")
print(f"NARROW_STRIP(窄条退化, MIC直径<50m): {len(new_narrow)} 条")
print(f"JAGGED_BOUNDARY(锯齿边界, 均宽<30%最大宽): {len(new_jagged)} 条")
print(f"ELONGATED_BLOCK(长条地块,仅提示): {len(new_elongated)} 条")
print(f"其中 窄条+锯齿双重: {len(set(new_narrow) & set(new_jagged))} 条")

# 交叉核对旧标记的去向
both = old_extreme & (set(new_narrow) | set(new_elongated))
print(f"旧83条全部落位: {len(both) == len(old_extreme)}")
newly_flagged = (set(new_narrow) | set(new_elongated)) - old_extreme
print(f"新发现(旧漏报): {len(newly_flagged)} 条")
if newly_flagged:
    sub = df[df["source_record_id"].isin(newly_flagged)][
        ["source_record_id", "name", "city", "aspect_ratio", "rect_length_m", "rect_width_m", "mean_width_m"]]
    print(sub.sort_values("mean_width_m").head(20).to_string(index=False))
