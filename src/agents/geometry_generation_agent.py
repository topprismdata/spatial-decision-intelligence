"""
Agent 3: Geometry Generation Agent (几何生成智能体).
Orchestrates multi-hypothesis boundary creation, spatial reasoning scoring,
and candidate synthesis to produce the most plausible physical parcel polygon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from src.agents.entity_resolution_agent import ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryConstraints
from src.generation.candidate_fusion import CandidateFusionEngine, PolygonHypothesis


@dataclass
class GeometryGenerationResult:
    """The synthesized polygon result selected by the Geometry Generation Agent."""
    chosen_hypothesis: PolygonHypothesis
    all_hypotheses: List[PolygonHypothesis]
    confidence_score: float
    method: str


class GeometryGenerationAgent:
    """Executes multi-source candidate generation and spatial reasoning ranking."""

    def __init__(self):
        self.fusion_engine = CandidateFusionEngine()

    def generate(
        self,
        entity_ctx: ResolvedEntityContext,
        constraints: BoundaryConstraints,
        road_network_wkt: Optional[str] = None,
        building_footprints_wkt: Optional[List[str]] = None
    ) -> GeometryGenerationResult:
        """Runs candidate generation and returns top-scored boundary polygon."""
        hypotheses = self.fusion_engine.generate_candidates(
            entity_ctx=entity_ctx,
            constraints=constraints,
            road_network_wkt=road_network_wkt,
            building_footprints_wkt=building_footprints_wkt
        )

        top_hyp = hypotheses[0]
        return GeometryGenerationResult(
            chosen_hypothesis=top_hyp,
            all_hypotheses=hypotheses,
            confidence_score=top_hyp.score,
            method=top_hyp.method
        )
