"""
Agent 4: Geometry QA Agent (质量审核智能体).
Applies deterministic geometric health checks, topological self-healing,
and decision readiness gates before publishing to the Trusted Spatial State.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from src.agents.entity_resolution_agent import ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryConstraints
from src.agents.geometry_generation_agent import GeometryGenerationResult
from src.geometry.ai_fence_guard import AIFenceGuard, FenceGuardDecision
from src.domain.world_model import (
    SpatialEntity,
    GeometryObservation,
    ValidationStatus,
    QualityFinding,
    FindingSeverity,
    EvidencePacket,
    DecisionImpact
)


@dataclass
class QAAuditResult:
    """The final audited and decision-gated result of the 4-Agent platform."""
    entity: SpatialEntity
    geometry_observation: GeometryObservation
    findings: List[QualityFinding]
    is_decision_ready: bool
    decision_summary: str


class GeometryQAAgent:
    """Final quality gate for AI-generated and harvested spatial entities."""

    def __init__(self, min_qa_score: float = 0.70):
        self.guard = AIFenceGuard(min_qa_score=min_qa_score)

    def audit(
        self,
        entity_ctx: ResolvedEntityContext,
        constraints: BoundaryConstraints,
        gen_result: GeometryGenerationResult,
        fallback_wkt: Optional[str] = None
    ) -> QAAuditResult:
        """Audits candidate geometry and packages it into a Trusted Spatial Entity."""
        chosen_hyp = gen_result.chosen_hypothesis

        # 1. Inspect and Guard Geometry
        guard_decision: FenceGuardDecision = self.guard.inspect_and_guard(
            ai_candidate_wkt=chosen_hyp.geometry_wkt,
            poi_lng=constraints.seed_lng,
            poi_lat=constraints.seed_lat,
            fallback_route_a_wkt=fallback_wkt,
            entity_id=entity_ctx.canonical_name
        )

        # 2. Map Validation Status
        if guard_decision.status == "PASSED":
            val_status = ValidationStatus.VERIFIED_VALID
            is_ready = True
            severity = FindingSeverity.INFO
        elif guard_decision.status == "HEALED":
            val_status = ValidationStatus.REPAIRED_AUTO
            is_ready = True
            severity = FindingSeverity.INFO
        elif guard_decision.status == "DEGRADED_FALLBACK":
            val_status = ValidationStatus.REPAIRED_AUTO
            is_ready = True
            severity = FindingSeverity.WARNING
        else:
            val_status = ValidationStatus.REJECTED
            is_ready = False
            severity = FindingSeverity.CRITICAL

        # 3. Create GeometryObservation
        obs_id = f"GEO_{entity_ctx.base_name}"
        geom_obs = GeometryObservation(
            observation_id=obs_id,
            geometry_wkt=guard_decision.geometry_wkt,
            geometry_type="POLYGON",
            crs="WGS84",
            observed_at="NOW",
            source=guard_decision.method_used,
            qa_score=guard_decision.qa_score,
            transformation_history=[f"GENERATED_VIA_{guard_decision.method_used}"],
            validation_status=val_status
        )

        # 4. Create Findings & Evidence Packets
        findings = []
        if guard_decision.status != "PASSED":
            f_id = f"FIND_{entity_ctx.base_name}"
            finding = QualityFinding(
                finding_id=f_id,
                target_id=entity_ctx.canonical_name,
                category=guard_decision.status,
                severity=severity,
                evidence=EvidencePacket(
                    diagnostic_rule="GEOMETRIC_INTEGRITY_AUDIT",
                    explanation="; ".join(guard_decision.reasons),
                    metrics={
                        "qa_score": guard_decision.qa_score,
                        "area_m2": chosen_hyp.area_m2,
                        "method": guard_decision.method_used
                    }
                ),
                decision_impact=DecisionImpact(
                    risk_level="HIGH_CORRUPTION" if not is_ready else "LOW_NOISE",
                    polluted_decisions=[] if is_ready else ["TERRITORY_BOUNDARY_CORRUPTION"],
                    blocked_consumers=[] if is_ready else ["market-partition"]
                ),
                recommended_review="人工确认自愈/降级几何是否贴合实际社区边界"
            )
            findings.append(finding)

        # 5. Create Canonical SpatialEntity
        entity = SpatialEntity(
            entity_id=f"ENT_{entity_ctx.canonical_name}",
            category=entity_ctx.category,
            canonical_name=entity_ctx.canonical_name,
            aliases=entity_ctx.aliases,
            city="北京市",
            address=entity_ctx.raw_address,
            point_wgs84=(constraints.seed_lng, constraints.seed_lat),
            geometry_observation_id=obs_id,
            attributes={
                "area_m2": chosen_hyp.area_m2,
                "scale_level": entity_ctx.scale_level,
                "generation_method": guard_decision.method_used,
                "confidence_score": gen_result.confidence_score
            },
            active_findings=[f.finding_id for f in findings],
            is_decision_ready=is_ready
        )

        summary = (
            f"QA Status: {guard_decision.status} (Score: {guard_decision.qa_score:.2f}) | "
            f"Method: {guard_decision.method_used} | Decision-Ready: {is_ready}"
        )

        return QAAuditResult(
            entity=entity,
            geometry_observation=geom_obs,
            findings=findings,
            is_decision_ready=is_ready,
            decision_summary=summary
        )
