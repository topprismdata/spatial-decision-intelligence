"""
Agent 2: Boundary Reasoning Agent (边界推理智能体).
Infers physical scale constraints, target search bounding boxes, and expected
area envelopes based on entity semantics and geographic seed points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from src.agents.entity_resolution_agent import ResolvedEntityContext
from src.coordinate.metric_crs import degree_offset_for_meters


@dataclass
class BoundaryConstraints:
    """Calculated geographic bounding box and area constraints for candidate generation."""
    seed_lng: float
    seed_lat: float
    target_area_m2: float
    min_area_m2: float
    max_area_m2: float
    search_radius_m: float
    search_bbox: Tuple[float, float, float, float]  # min_lng, min_lat, max_lng, max_lat
    zoom_level: int
    scale_type: str


class BoundaryReasoningAgent:
    """Translates semantic entity identity into concrete spatial search constraints."""

    # Default statistical area priors (m²) from 9,039 operational fences
    SCALE_AREA_PRIORS = {
        "COURTYARD_LEVEL": {"target": 3500.0, "min": 500.0, "max": 12000.0, "radius": 150.0, "zoom": 18},
        "COMMUNITY_LEVEL": {"target": 25000.0, "min": 5000.0, "max": 120000.0, "radius": 350.0, "zoom": 17},
        "LARGE_ESTATE": {"target": 120000.0, "min": 40000.0, "max": 500000.0, "radius": 700.0, "zoom": 16},
    }

    def __init__(self):
        pass

    def reason_constraints(
        self,
        entity_ctx: ResolvedEntityContext,
        seed_lng: float,
        seed_lat: float,
        prior_area_m2: Optional[float] = None
    ) -> BoundaryConstraints:
        """Infers spatial search bounding box and area expectation."""
        scale_cfg = self.SCALE_AREA_PRIORS.get(entity_ctx.scale_level, self.SCALE_AREA_PRIORS["COMMUNITY_LEVEL"])

        if prior_area_m2 and prior_area_m2 > 100.0:
            target_area = float(prior_area_m2)
            min_area = max(500.0, target_area * 0.4)
            max_area = target_area * 2.5
            radius_m = math.sqrt(target_area / math.pi) * 1.6
            zoom = 18 if target_area < 15000 else (17 if target_area < 80000 else 16)
        else:
            target_area = scale_cfg["target"]
            min_area = scale_cfg["min"]
            max_area = scale_cfg["max"]
            radius_m = scale_cfg["radius"]
            zoom = scale_cfg["zoom"]

        # Compute degree deltas at latitude via Metric CRS
        dlat, dlng = degree_offset_for_meters(radius_m, seed_lat)

        bbox = (
            round(seed_lng - dlng, 6),
            round(seed_lat - dlat, 6),
            round(seed_lng + dlng, 6),
            round(seed_lat + dlat, 6),
        )

        return BoundaryConstraints(
            seed_lng=seed_lng,
            seed_lat=seed_lat,
            target_area_m2=target_area,
            min_area_m2=min_area,
            max_area_m2=max_area,
            search_radius_m=radius_m,
            search_bbox=bbox,
            zoom_level=zoom,
            scale_type=entity_ctx.scale_level
        )
