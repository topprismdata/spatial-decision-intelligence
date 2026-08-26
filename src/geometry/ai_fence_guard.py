"""
Defensive Quality Gate & Graceful Fallback Guard for AI-Generated Fences.
Applies M0-M1 validation to AI-generated candidate polygons and handles automatic fallback.
"""

from __future__ import annotations

import os
import sys
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple

from shapely import wkt, make_valid
from shapely.geometry import Point, Polygon, MultiPolygon
from typing import Optional, Dict, Any, Tuple, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.geometry.validation import GeometryQAEngine
from src.domain.models import QAResult
from src.coordinate.metric_service import MetricGeometryService
_metric_service = MetricGeometryService()

logger = logging.getLogger(__name__)


@dataclass
class FenceGuardDecision:
    status: str  # "PASSED", "HEALED", "DEGRADED_FALLBACK", "REJECTED_UNRECOVERABLE"
    geometry_wkt: str
    qa_score: float
    is_degraded: bool
    method_used: str  # "AI_PRIMARY", "AI_HEALED", "ROUTE_A_FALLBACK", "NONE"
    reasons: List[str]


class AIFenceGuard:
    """Dogfoods the diagnostic engine to intercept defective AI outputs."""

    def __init__(
        self,
        min_qa_score: float = 0.70,
        min_area_m2: float = 500.0,
        max_area_m2: float = 800000.0,
        max_poi_distance_m: float = 300.0,
    ):
        self.min_qa_score = min_qa_score
        self.min_area_m2 = min_area_m2
        self.max_area_m2 = max_area_m2
        self.max_poi_distance_m = max_poi_distance_m

    def inspect_and_guard(
        self,
        ai_candidate_wkt: Optional[str],
        poi_lng: float,
        poi_lat: float,
        fallback_route_a_wkt: Optional[str] = None,
        entity_id: str = "ai_sample",
    ) -> FenceGuardDecision:
        """Evaluates AI-generated geometry and returns the guarded/fallback result."""
        reasons = []

        if not ai_candidate_wkt or not isinstance(ai_candidate_wkt, str) or not ai_candidate_wkt.strip():
            reasons.append("AI_EMPTY_GEOMETRY")
            return self._trigger_fallback(fallback_route_a_wkt, poi_lng, poi_lat, entity_id, reasons)

        try:
            geom = wkt.loads(ai_candidate_wkt)
        except Exception as e:
            reasons.append(f"AI_WKT_PARSE_ERROR({str(e)})")
            return self._trigger_fallback(fallback_route_a_wkt, poi_lng, poi_lat, entity_id, reasons)

        if not geom.is_valid:
            reasons.append("AI_TOPOLOGY_INVALID")
            geom = make_valid(geom)

        if geom.is_empty:
            reasons.append("AI_GEOM_EMPTY_AFTER_CLEAN")
            return self._trigger_fallback(fallback_route_a_wkt, poi_lng, poi_lat, entity_id, reasons)

        clean_wkt = geom.wkt
        qa_res, verified_wkt, qa_feats = GeometryQAEngine.validate_and_extract_features(entity_id, clean_wkt)

        area = qa_feats.get("area_m2", 0.0)
        if area < self.min_area_m2:
            reasons.append(f"AI_AREA_TOO_SMALL({area:.1f}m2)")
        elif area > self.max_area_m2:
            reasons.append(f"AI_AREA_TOO_LARGE({area:.1f}m2)")

        if "NARROW_STRIP" in (qa_res.issues or []):
            reasons.append("AI_NARROW_STRIP_DEGRADATION")

        # POI proximity check (using approximate degree distance)
        poi_pt = Point(poi_lng, poi_lat)
        try:
            poly_obj = wkt.loads(verified_wkt)
            if not poly_obj.contains(poi_pt):
                # distance in meters approx
                dist_m = _metric_service.distance_m(poly_obj.wkt, f'POINT({poi_pt.x} {poi_pt.y})')
                if dist_m > self.max_poi_distance_m:
                    reasons.append(f"AI_POI_DISCONNECTED({dist_m:.0f}m)")
        except Exception:
            pass

        # Check if passed or needs fallback
        hard_failures = [r for r in reasons if "AREA_TOO" in r or "NARROW_STRIP" in r or "DISCONNECTED" in r]
        if not hard_failures and qa_res.score >= self.min_qa_score:
            method = "AI_HEALED" if "AI_TOPOLOGY_INVALID" in reasons else "AI_PRIMARY"
            status = "HEALED" if "AI_TOPOLOGY_INVALID" in reasons else "PASSED"
            return FenceGuardDecision(
                status=status,
                geometry_wkt=verified_wkt,
                qa_score=qa_res.score,
                is_degraded=False,
                method_used=method,
                reasons=reasons or ["CLEAN_AI_PASS"],
            )

        # Triggers Fallback
        return self._trigger_fallback(fallback_route_a_wkt, poi_lng, poi_lat, entity_id, reasons)

    def _trigger_fallback(
        self,
        fallback_wkt: Optional[str],
        poi_lng: float,
        poi_lat: float,
        entity_id: str,
        prior_reasons: List[str],
    ) -> FenceGuardDecision:
        if fallback_wkt and isinstance(fallback_wkt, str) and fallback_wkt.strip():
            try:
                qa_res, verified_wkt, _ = GeometryQAEngine.validate_and_extract_features(
                    f"{entity_id}_fallback", fallback_wkt
                )
                prior_reasons.append("FALLBACK_ROUTE_A_ACTIVATED")
                return FenceGuardDecision(
                    status="DEGRADED_FALLBACK",
                    geometry_wkt=verified_wkt,
                    qa_score=qa_res.score,
                    is_degraded=True,
                    method_used="ROUTE_A_FALLBACK",
                    reasons=prior_reasons,
                )
            except Exception as e:
                prior_reasons.append(f"FALLBACK_FAILED({str(e)})")

        prior_reasons.append("UNRECOVERABLE_DEFECT")
        return FenceGuardDecision(
            status="REJECTED_UNRECOVERABLE",
            geometry_wkt="",
            qa_score=0.0,
            is_degraded=True,
            method_used="NONE",
            reasons=prior_reasons,
        )
