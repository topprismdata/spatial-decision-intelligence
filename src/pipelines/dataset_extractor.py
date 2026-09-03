"""
Weak-Supervision Silver Dataset Extractor.
Extracts high-quality (QA >= 80, topologically clean, geometrically sound) fences
from the 9,039 governance dataset to build the training set for AI fence generation.
"""

from __future__ import annotations

import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[2])

import os
import sys
import json
import logging
from typing import Dict, Any, List

import pandas as pd
from shapely import wkt
from shapely.geometry import mapping

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ingestion.parser import ExcelIngestionParser
from src.coordinate.assessment import CoordinateIntelligence
from src.coordinate.transforms import wgs84_to_gcj02, transform_geometry_wkt
from src.geometry.validation import GeometryQAEngine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("dataset_extractor")
class SilverDatasetExtractor:
    """Filters verified, clean fences to serve as ground-truth for deep learning."""

    def __init__(
        self,
        excel_path: str = str(_REPO / 'data/client_a_sites.xlsx'),
        output_dir: str = os.path.join(PROJECT_ROOT, "outputs"),
        min_qa_score: float = 0.80,
        min_area_m2: float = 1000.0,
        max_area_m2: float = 500000.0,
    ):
        self.excel_path = excel_path
        self.output_dir = output_dir
        self.min_qa_score = min_qa_score
        self.min_area_m2 = min_area_m2
        self.max_area_m2 = max_area_m2

    def extract(self) -> Dict[str, Any]:
        logger.info("[extractor] parsing source excel ...")
        records = ExcelIngestionParser.parse_file(self.excel_path)
        logger.info(f"[extractor] loaded {len(records)} total records")

        qa_csv = os.path.join(self.output_dir, "qa_issues_report.csv")
        df_qa = pd.read_csv(qa_csv) if os.path.exists(qa_csv) else None
        qa_map = {}
        if df_qa is not None:
            for _, row in df_qa.iterrows():
                qa_map[str(row["source_record_id"])] = row

        silver_records = []
        rejected_reasons = {}

        for r in records:
            rid = str(r.source_record_id)
            c_eval, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
            if not n_wkt:
                rejected_reasons["NO_GEOMETRY"] = rejected_reasons.get("NO_GEOMETRY", 0) + 1
                continue

            qa_res, clean_wkt, qa_feats = GeometryQAEngine.validate_and_extract_features(rid, n_wkt)

            if qa_res.score < self.min_qa_score:
                rejected_reasons["LOW_QA_SCORE"] = rejected_reasons.get("LOW_QA_SCORE", 0) + 1
                continue

            area = qa_feats.get("area_m2", 0.0)
            if area < self.min_area_m2 or area > self.max_area_m2:
                rejected_reasons["OUT_OF_BOUNDS_AREA"] = rejected_reasons.get("OUT_OF_BOUNDS_AREA", 0) + 1
                continue

            qa_issues = qa_res.issues or []
            if "NARROW_STRIP" in qa_issues:
                rejected_reasons["NARROW_STRIP"] = rejected_reasons.get("NARROW_STRIP", 0) + 1
                continue

            # Convert to GCJ-02 for alignment with Amap satellite tiles
            gcj_lng, gcj_lat = wgs84_to_gcj02(n_lng, n_lat)
            gcj_wkt = transform_geometry_wkt(clean_wkt, wgs84_to_gcj02)

            geom_obj = wkt.loads(gcj_wkt)
            bounds = geom_obj.bounds  # minx, miny, maxx, maxy

            silver_records.append({
                "record_id": rid,
                "name": r.name_raw,
                "city": r.city_raw,
                "address": r.address_raw,
                "center_gcj02": [round(gcj_lng, 6), round(gcj_lat, 6)],
                "area_m2": round(area, 2),
                "qa_score": qa_res.score,
                "bounds_gcj02": [round(b, 6) for b in bounds],
                "geometry_gcj02_wkt": gcj_wkt,
                "geojson": mapping(geom_obj),
            })

        logger.info(f"[extractor] Extracted {len(silver_records)} silver samples (of {len(records)}).")
        logger.info(f"[extractor] Rejection breakdown: {rejected_reasons}")

        # Save JSON
        json_path = os.path.join(self.output_dir, "silver_fence_dataset.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(silver_records, f, ensure_ascii=False, indent=2)

        # Save CSV (without bulky geojson)
        csv_path = os.path.join(self.output_dir, "silver_fence_dataset.csv")
        csv_df = pd.DataFrame([{k: v for k, v in item.items() if k != "geojson"} for item in silver_records])
        csv_df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        stats = {
            "total_input": len(records),
            "silver_samples": len(silver_records),
            "yield_rate": f"{len(silver_records) / len(records) * 100:.1f}%",
            "rejected_breakdown": rejected_reasons,
            "json_path": json_path,
            "csv_path": csv_path,
        }
        return stats


if __name__ == "__main__":
    extractor = SilverDatasetExtractor()
    stats = extractor.extract()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
