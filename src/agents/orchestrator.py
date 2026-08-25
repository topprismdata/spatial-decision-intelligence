"""
Master Orchestrator for the Spatial Intelligence Agent Platform.
Executes the sequential 4-Agent pipeline to transform raw spatial briefs into Trusted Spatial States.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.agents.entity_resolution_agent import EntityResolutionAgent, ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryReasoningAgent, BoundaryConstraints
from src.agents.geometry_generation_agent import GeometryGenerationAgent, GeometryGenerationResult
from src.agents.geometry_qa_agent import GeometryQAAgent, QAAuditResult
from src.domain.world_model import TrustedSpatialState, SpatialEntity, GeometryObservation

logger = logging.getLogger("spatial_agent_platform")


@dataclass
class SpatialGenerationPipelineResult:
    """Full trace of the 4-Agent execution pipeline for a single entity."""
    entity_context: ResolvedEntityContext
    constraints: BoundaryConstraints
    generation_result: GeometryGenerationResult
    qa_audit: QAAuditResult
    is_decision_ready: bool
    execution_trace: List[str] = field(default_factory=list)


class SpatialIntelligencePlatform:
    """Orchestrates the 4-Agent spatial understanding, reasoning, and synthesis pipeline."""

    def __init__(self, min_qa_score: float = 0.70):
        self.entity_agent = EntityResolutionAgent()
        self.boundary_agent = BoundaryReasoningAgent()
        self.geometry_agent = GeometryGenerationAgent()
        self.qa_agent = GeometryQAAgent(min_qa_score=min_qa_score)

    def generate_single_fence(
        self,
        name: str,
        address: str = "",
        lng: float = 116.40,
        lat: float = 39.90,
        prior_area_m2: Optional[float] = None,
        road_network_wkt: Optional[str] = None,
        building_footprints_wkt: Optional[List[str]] = None
    ) -> SpatialGenerationPipelineResult:
        """Executes the full 4-Agent workflow for a single community/parcel brief."""
        trace = []

        # Step 1: Entity Resolution Agent
        t_start = datetime.now()
        entity_ctx = self.entity_agent.resolve(name=name, address=address)
        trace.append(f"Agent 1 (Entity): Canonical='{entity_ctx.canonical_name}', Scale='{entity_ctx.scale_level}'")

        # Step 2: Boundary Reasoning Agent
        constraints = self.boundary_agent.reason_constraints(
            entity_ctx=entity_ctx,
            seed_lng=lng,
            seed_lat=lat,
            prior_area_m2=prior_area_m2
        )
        trace.append(
            f"Agent 2 (Boundary): TargetArea={constraints.target_area_m2:.0f}m², "
            f"Radius={constraints.search_radius_m:.0f}m, Zoom={constraints.zoom_level}"
        )

        # Step 3: Geometry Generation Agent
        gen_result = self.geometry_agent.generate(
            entity_ctx=entity_ctx,
            constraints=constraints,
            road_network_wkt=road_network_wkt,
            building_footprints_wkt=building_footprints_wkt
        )
        trace.append(
            f"Agent 3 (Geometry): TopHypothesis='{gen_result.chosen_hypothesis.method}', "
            f"Area={gen_result.chosen_hypothesis.area_m2:.0f}m², Score={gen_result.confidence_score:.3f}"
        )

        # Step 4: Geometry QA Agent
        qa_audit = self.qa_agent.audit(
            entity_ctx=entity_ctx,
            constraints=constraints,
            gen_result=gen_result
        )
        trace.append(f"Agent 4 (QA): {qa_audit.decision_summary}")

        return SpatialGenerationPipelineResult(
            entity_context=entity_ctx,
            constraints=constraints,
            generation_result=gen_result,
            qa_audit=qa_audit,
            is_decision_ready=qa_audit.is_decision_ready,
            execution_trace=trace
        )

    def batch_generate_and_govern(
        self,
        briefs: List[Dict[str, Any]]
    ) -> TrustedSpatialState:
        """Batch processes spatial briefs and compiles them into a Trusted Spatial State."""
        entities: Dict[str, SpatialEntity] = {}
        geometries: Dict[str, GeometryObservation] = {}
        all_findings = []

        for b in briefs:
            name = b.get("name", "Unknown")
            addr = b.get("address", "")
            lng = float(b.get("lng", 116.40))
            lat = float(b.get("lat", 39.90))
            area = float(b.get("area_m2", 0)) if b.get("area_m2") else None

            pipe_res = self.generate_single_fence(
                name=name,
                address=addr,
                lng=lng,
                lat=lat,
                prior_area_m2=area
            )

            ent = pipe_res.qa_audit.entity
            geom_obs = pipe_res.qa_audit.geometry_observation

            entities[ent.entity_id] = ent
            geometries[geom_obs.observation_id] = geom_obs
            all_findings.extend(pipe_res.qa_audit.findings)

        return TrustedSpatialState(
            state_version=datetime.now().strftime("%Y.%m.%d.v1"),
            published_at=datetime.now().isoformat(),
            entities=entities,
            geometries=geometries,
            findings=all_findings
        )
