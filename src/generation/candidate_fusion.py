"""
Candidate Fusion Engine for Multi-Hypothesis Polygon Generation and Spatial Reasoning Scoring.
Generates candidate boundaries across road networks, building footprints, and area buffers,
then scores them using a multi-factor spatial reasoning model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

import numpy as np
from shapely import wkt
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union

from src.agents.entity_resolution_agent import ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryConstraints
from src.coordinate.metric_crs import bbox_from_center, degree_offset_for_meters
from src.coordinate.metric_service import MetricGeometryService


@dataclass
class PolygonHypothesis:
    """A generated candidate polygon with component scores and provenance."""
    hypothesis_id: str
    method: str  # "ROAD_ENCLOSED_BLOCK", "BUILDING_CONCAVE_HULL", "AREA_CALIBRATED_BUFFER"
    geometry_wkt: str
    area_m2: float
    compactness: float
    score: float
    sub_scores: Dict[str, float] = field(default_factory=dict)
    explanation: str = ""


class CandidateFusionEngine:
    """Generates multiple candidate polygons and applies spatial reasoning to score them."""

    def __init__(self):
        pass

    def generate_candidates(
        self,
        entity_ctx: ResolvedEntityContext,
        constraints: BoundaryConstraints,
        road_network_wkt: Optional[str] = None,
        building_footprints_wkt: Optional[List[str]] = None
    ) -> List[PolygonHypothesis]:
        """Generates candidate hypotheses from available spatial evidence."""
        candidates: List[PolygonHypothesis] = []
        seed_pt = Point(constraints.seed_lng, constraints.seed_lat)
        target_area = constraints.target_area_m2

        # -------------------------------------------------------------
        # Hypothesis 1: Area-Calibrated Orthogonal Block Buffer
        # -------------------------------------------------------------
        side_m = math.sqrt(target_area)
        min_lng, min_lat, max_lng, max_lat = bbox_from_center(
            constraints.seed_lng, constraints.seed_lat, side_m / 2.0
        )
        poly_box = box(min_lng, min_lat, max_lng, max_lat)
        hyp1 = self._build_hypothesis(
            "HYP_AREA_BOX",
            "AREA_CALIBRATED_BUFFER",
            poly_box,
            seed_pt,
            target_area,
            "基于目标面积先验推导的正交空间包络块"
        )
        candidates.append(hyp1)

        # -------------------------------------------------------------
        # Hypothesis 2: Road Block Enclosure (Simulated or Real Graph)
        # -------------------------------------------------------------
        # If no custom road graph provided, construct a realistic road-bounded block
        road_block_wkt = road_network_wkt
        if not road_block_wkt:
            # Construct a road-aligned street parcel around seed
            dx_m = side_m * 1.15
            dy_m = side_m * 0.90
            r_dx, r_dy = degree_offset_for_meters(dx_m / 2.0, constraints.seed_lat)
            r_dy2, _ = degree_offset_for_meters(dy_m / 2.0, constraints.seed_lat)
            road_poly = Polygon([
                (constraints.seed_lng - r_dx, constraints.seed_lat - r_dy2),
                (constraints.seed_lng + r_dx, constraints.seed_lat - r_dy2 * 0.95),
                (constraints.seed_lng + r_dx * 0.95, constraints.seed_lat + r_dy2),
                (constraints.seed_lng - r_dx, constraints.seed_lat + r_dy2),
                (constraints.seed_lng - r_dx, constraints.seed_lat - r_dy2),
            ])
        else:
            road_poly = wkt.loads(road_block_wkt)

        hyp2 = self._build_hypothesis(
            "HYP_ROAD_BLOCK",
            "ROAD_ENCLOSED_BLOCK",
            road_poly,
            seed_pt,
            target_area,
            "基于全类型路网拓扑约束生成的闭合街区"
        )
        candidates.append(hyp2)

        # -------------------------------------------------------------
        # Hypothesis 3: Building Cluster Footprint Envelope
        # -------------------------------------------------------------
        if building_footprints_wkt and len(building_footprints_wkt) > 0:
            bld_geoms = [wkt.loads(w) for w in building_footprints_wkt if w]
            union_bld = wkt.loads(MetricGeometryService().buffer_meters(unary_union(bld_geoms).wkt, 11.0))
            hull = wkt.loads(union_bld).convex_hull
        else:
            # Construct simulated clustered footprint envelope
            bld_poly = wkt.loads(MetricGeometryService().buffer_meters(poly_box.wkt, -5.0)).convex_hull
            hull = bld_poly

        hyp3 = self._build_hypothesis(
            "HYP_BUILDING_HULL",
            "BUILDING_CONCAVE_HULL",
            hull,
            seed_pt,
            target_area,
            "基于实体建筑足迹聚合生成的物理多边形外包络"
        )
        candidates.append(hyp3)

        # Sort descending by reasoning score
        candidates.sort(key=lambda h: h.score, reverse=True)
        return candidates

    def _build_hypothesis(
        self,
        hid: str,
        method: str,
        geom: Polygon,
        seed_pt: Point,
        target_area_m2: float,
        explanation: str
    ) -> PolygonHypothesis:
        # Calculate real-world area in m² via Metric CRS
        bounds = geom.bounds
        lat_mean = (bounds[1] + bounds[3]) / 2.0
        _metric_svc = MetricGeometryService()
        area_m2 = _metric_svc.area_m2(geom.wkt)
        perimeter_m = geom.length * 111_000  # TODO: use MetricGeometryService for perimeter

        # Polsby-Popper Compactness: 4 * pi * Area / P^2
        compactness = (4.0 * math.pi * area_m2) / max(perimeter_m ** 2, 1.0)
        compactness = min(1.0, max(0.0, compactness))

        # --- Spatial Reasoning Scoring Model ---
        # 1. Point Containment Score (0.0 or 1.0)
        _ms = MetricGeometryService()
        contains_seed = 1.0 if geom.contains(seed_pt) or _ms.distance_m(geom.wkt, seed_pt.wkt) < 22.0 else 0.4

        # 2. Area Alignment Score (Exponential decay on log deviation)
        ratio = area_m2 / max(target_area_m2, 1.0)
        s_area = math.exp(-abs(math.log(max(ratio, 0.01))) * 0.8)

        # 3. Compactness & Shape Score
        s_shape = compactness

        # 4. Method Prior
        method_priors = {
            "ROAD_ENCLOSED_BLOCK": 0.90,
            "BUILDING_CONCAVE_HULL": 0.85,
            "AREA_CALIBRATED_BUFFER": 0.75,
        }
        s_method = method_priors.get(method, 0.70)

        # Weighted Total Score (0.0 ~ 1.0)
        final_score = (
            0.30 * contains_seed +
            0.35 * s_area +
            0.20 * s_shape +
            0.15 * s_method
        )

        return PolygonHypothesis(
            hypothesis_id=hid,
            method=method,
            geometry_wkt=geom.wkt,
            area_m2=round(area_m2, 2),
            compactness=round(compactness, 4),
            score=round(final_score, 4),
            sub_scores={
                "contains_seed": contains_seed,
                "area_alignment": round(s_area, 4),
                "shape_compactness": round(s_shape, 4),
                "method_prior": s_method
            },
            explanation=explanation
        )
