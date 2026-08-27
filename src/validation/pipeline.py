"""P0-08 / R3 Validation Pipeline & Gate Verification.

Includes:
- OntologyGate, GeometryGate, EvidenceGate, DecisionReadinessGate
- FinalDisposition resolution (TRUSTED, PROVISIONAL, UNRESOLVED, REJECTED)
- ConsumerProfile aware DecisionReadiness
- Full findings and provenance preservation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from src.domain.contracts import (
    BoundaryHypothesis,
    BoundaryType,
    Evidence,
    EvidenceType,
    OntologyType,
    ValidationResult,
    ValidationStatus,
)
from src.coordinate.metric_service import MetricGeometryService
from src.validation.external_coverage_gate import ExternalCoverageGate, PolygonContext



class FinalDisposition(str, Enum):
    """Objective world model trust status (Design Note §3)."""
    TRUSTED = "TRUSTED"          # All gates passed, multi-source evidence sufficient
    PROVISIONAL = "PROVISIONAL"  # Non-fatal warnings present (e.g. single source / low compactness)
    UNRESOLVED = "UNRESOLVED"    # Evidence insufficient or ambiguous; system abstains
    REJECTED = "REJECTED"        # Hard block (geometry broken, invalid type, severe overlap)


class ConsumerDecision(str, Enum):
    """Consumer-specific readiness status."""
    READY = "READY"
    READY_WITH_WARNING = "READY_WITH_WARNING"
    NOT_READY = "NOT_READY"


@dataclass(frozen=True)
class ConsumerProfile:
    name: str
    min_confidence: float = 0.8
    allow_provisional: bool = False
    require_valid_geometry: bool = True
    require_evidence: bool = True
    require_topology_consistency: bool = False


# Pre-defined Consumer Profiles
PROFILE_VISIT_CHECKIN = ConsumerProfile(
    name="VisitCheckIn",
    min_confidence=0.6,
    allow_provisional=True,
    require_valid_geometry=True,
    require_evidence=True,
    require_topology_consistency=False,
)

PROFILE_TERRITORY_OPTIMIZATION = ConsumerProfile(
    name="TerritoryOptimization",
    min_confidence=0.85,
    allow_provisional=False,
    require_valid_geometry=True,
    require_evidence=True,
    require_topology_consistency=True,
)


# ── Gates ────────────────────────────────────────────────────────────────────


class OntologyGate:
    @staticmethod
    def validate(
        entity_type: OntologyType,
        boundary_role: str = "PHYSICAL_BOUNDARY",
        hypothesis: Optional[BoundaryHypothesis] = None
    ) -> ValidationResult:
        findings = []
        entity_id = hypothesis.entity_id if hypothesis else ""

        if not isinstance(entity_type, OntologyType) or entity_type not in OntologyType:
            findings.append(f"invalid_ontology_type:{entity_type}")
            return ValidationResult(
                entity_id=entity_id, validator="OntologyGate",
                status=ValidationStatus.FAILED, findings=tuple(findings), decision_ready=False
            )

        # Disallow raw Estate acting directly as un-subdivided physical boundary with high warning
        if entity_type == OntologyType.RESIDENTIAL_ESTATE and boundary_role == "PHYSICAL_BOUNDARY":
            findings.append("role_warning:ResidentialEstate used directly as physical boundary without phase subdivision")
            return ValidationResult(
                entity_id=entity_id, validator="OntologyGate",
                status=ValidationStatus.WARNED, findings=tuple(findings), decision_ready=True
            )

        return ValidationResult(
            entity_id=entity_id, validator="OntologyGate",
            status=ValidationStatus.PASSED, findings=(), decision_ready=True
        )


class GeometryGate:
    MIN_AREA_M2 = 100.0
    MAX_AREA_M2 = 5_000_000.0

    def __init__(self, metric_service: Optional[MetricGeometryService] = None):
        self._ms = metric_service or MetricGeometryService()

    def validate(self, hypothesis: BoundaryHypothesis) -> ValidationResult:
        findings = []
        entity_id = hypothesis.entity_id
        geom_wkt = hypothesis.geometry

        if not geom_wkt or geom_wkt.strip() == "" or geom_wkt.upper() == "POLYGON EMPTY":
            return ValidationResult(
                entity_id=entity_id, validator="GeometryGate",
                status=ValidationStatus.BLOCKED, findings=("empty_geometry",), decision_ready=False
            )

        try:
            from shapely import wkt as _wkt
            geom = _wkt.loads(geom_wkt)

            if geom.is_empty:
                return ValidationResult(
                    entity_id=entity_id, validator="GeometryGate",
                    status=ValidationStatus.BLOCKED, findings=("empty_geometry",), decision_ready=False
                )
            if not geom.is_valid:
                return ValidationResult(
                    entity_id=entity_id, validator="GeometryGate",
                    status=ValidationStatus.BLOCKED, findings=("invalid_geometry:self_intersection_or_corrupt",), decision_ready=False
                )

            # Projected Metric CRS area calculation
            area_m2 = self._ms.area_m2(geom.wkt)
            if area_m2 < self.MIN_AREA_M2:
                findings.append(f"area_too_small:{area_m2:.0f}m2")
                return ValidationResult(
                    entity_id=entity_id, validator="GeometryGate",
                    status=ValidationStatus.FAILED, findings=tuple(findings), decision_ready=False
                )
            elif area_m2 > self.MAX_AREA_M2:
                findings.append(f"area_too_large:{area_m2:.0f}m2")
                return ValidationResult(
                    entity_id=entity_id, validator="GeometryGate",
                    status=ValidationStatus.FAILED, findings=tuple(findings), decision_ready=False
                )

            # Compactness warning (non-fatal)
            p = geom.length * 111_000.0  # rough perimeter in meter
            compactness = (4.0 * 3.14159 * area_m2) / max(p * p, 1.0)
            if compactness < 0.05:
                findings.append(f"low_compactness:{compactness:.3f}")
                return ValidationResult(
                    entity_id=entity_id, validator="GeometryGate",
                    status=ValidationStatus.WARNED, findings=tuple(findings), decision_ready=True
                )

        except Exception as e:
            return ValidationResult(
                entity_id=entity_id, validator="GeometryGate",
                status=ValidationStatus.BLOCKED, findings=(f"parse_error:{e}",), decision_ready=False
            )

        return ValidationResult(
            entity_id=entity_id, validator="GeometryGate",
            status=ValidationStatus.PASSED, findings=(), decision_ready=True
        )


class EvidenceGate:
    @staticmethod
    def validate(hypothesis: BoundaryHypothesis) -> ValidationResult:
        entity_id = hypothesis.entity_id
        ev_list = hypothesis.evidence

        if not ev_list or len(ev_list) == 0:
            return ValidationResult(
                entity_id=entity_id, validator="EvidenceGate",
                status=ValidationStatus.FAILED, findings=("evidence_insufficient:zero_evidence",), decision_ready=False
            )

        # Check for explicit contradiction/exclusion
        for ev in ev_list:
            if "conflict_contradiction" in ev.content.lower() or "explicit_exclusion" in ev.content.lower():
                return ValidationResult(
                    entity_id=entity_id, validator="EvidenceGate",
                    status=ValidationStatus.BLOCKED, findings=(f"fatal_evidence_conflict:{ev.content}",), decision_ready=False
                )

        # Single weak prior warning
        if len(ev_list) == 1 and ev_list[0].source == "AreaPriorBaseline":
            return ValidationResult(
                entity_id=entity_id, validator="EvidenceGate",
                status=ValidationStatus.WARNED, findings=("single_weak_prior_evidence",), decision_ready=True
            )

        return ValidationResult(
            entity_id=entity_id, validator="EvidenceGate",
            status=ValidationStatus.PASSED, findings=(), decision_ready=True
        )


class DecisionReadinessGate:
    """Consumer-aware gate. Assesses if the state matches specific consumer constraints."""

    @staticmethod
    def evaluate(
        hypothesis: BoundaryHypothesis,
        gate_results: Sequence[ValidationResult],
        consumer: ConsumerProfile,
        disposition: FinalDisposition,
    ) -> ValidationResult:
        entity_id = hypothesis.entity_id
        findings = []

        # 1. Hard blocked if disposition is REJECTED
        if disposition == FinalDisposition.REJECTED:
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.BLOCKED, findings=("disposition_rejected",), decision_ready=False
            )

        # 2. Unresolved is never ready for consumers
        if disposition == FinalDisposition.UNRESOLVED:
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.FAILED, findings=("disposition_unresolved",), decision_ready=False
            )

        # 3. Provisional handling
        if disposition == FinalDisposition.PROVISIONAL and not consumer.allow_provisional:
            findings.append("consumer_disallows_provisional")
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.FAILED, findings=tuple(findings), decision_ready=False
            )

        # 4. Confidence threshold check
        # Extract or calculate confidence from hypothesis evidence or score
        gen_score = getattr(hypothesis, "generation_score", None)
        if gen_score is None and hasattr(hypothesis, "metadata") and isinstance(hypothesis.metadata, dict):
            gen_score = hypothesis.metadata.get("generation_score", None)
        if gen_score is None and hypothesis.evidence and len(hypothesis.evidence) > 0:
            gen_score = max(ev.confidence for ev in hypothesis.evidence)
        if gen_score is None:
            gen_score = 0.5
        if gen_score < consumer.min_confidence:
            findings.append(f"insufficient_confidence:{gen_score:.2f}<{consumer.min_confidence:.2f}")
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.FAILED, findings=tuple(findings), decision_ready=False
            )

        # 5. Topology requirement
        if consumer.require_topology_consistency:
            findings.append("topology_consistency_not_attested")
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.WARNED, findings=tuple(findings), decision_ready=False
            )

        # Warnings check
        has_warnings = any(r.status == ValidationStatus.WARNED for r in gate_results)
        if has_warnings or disposition == FinalDisposition.PROVISIONAL:
            return ValidationResult(
                entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
                status=ValidationStatus.WARNED, findings=tuple(findings), decision_ready=True
            )

        return ValidationResult(
            entity_id=entity_id, validator=f"DecisionReadinessGate/{consumer.name}",
            status=ValidationStatus.PASSED, findings=(), decision_ready=True
        )


# ── Full Validation & FinalDisposition Resolver ──────────────────────────────


class ValidationPipeline:
    """Core 3-gate pipeline with optional R14-P2 external coverage gate.

    Args:
        metric_service: metric CRS service for GeometryGate.
        coverage_gate: optional ExternalCoverageGate (R14-P2). When wired,
            its verdict participates in FinalDisposition resolution; a BLOCKED
            finding rejects unnamed POI-less polygons outright.
    """

    def __init__(
        self,
        metric_service: Optional[MetricGeometryService] = None,
        coverage_gate: Optional["ExternalCoverageGate"] = None,
    ):
        self.ontology_gate = OntologyGate()
        self.geometry_gate = GeometryGate(metric_service)
        self.evidence_gate = EvidenceGate()
        self.decision_readiness_gate = DecisionReadinessGate()
        self.coverage_gate = coverage_gate

    @staticmethod
    def resolve_final_disposition(gate_results: Sequence[ValidationResult]) -> FinalDisposition:
        """Determines objective world model FinalDisposition from core gates (Ontology/Geometry/Evidence)."""
        statuses = [r.status for r in gate_results]

        if ValidationStatus.BLOCKED in statuses:
            return FinalDisposition.REJECTED

        # Ontology or Geometry failure -> REJECTED
        for r in gate_results:
            if r.validator in ("OntologyGate", "GeometryGate") and r.status == ValidationStatus.FAILED:
                return FinalDisposition.REJECTED

        # Evidence insufficiency -> UNRESOLVED (Abstention)
        for r in gate_results:
            if r.validator == "EvidenceGate" and r.status == ValidationStatus.FAILED:
                return FinalDisposition.UNRESOLVED

        # Any non-fatal warning -> PROVISIONAL
        if ValidationStatus.WARNED in statuses:
            return FinalDisposition.PROVISIONAL

        # All passed
        if all(s == ValidationStatus.PASSED for s in statuses):
            return FinalDisposition.TRUSTED

        return FinalDisposition.UNRESOLVED

    def run(
        self,
        entity_type: OntologyType,
        hypothesis: BoundaryHypothesis,
        boundary_role: str = "PHYSICAL_BOUNDARY",
        consumers: Sequence[ConsumerProfile] = (PROFILE_VISIT_CHECKIN, PROFILE_TERRITORY_OPTIMIZATION),
        polygon_context: Optional["PolygonContext"] = None,
    ) -> tuple[list[ValidationResult], FinalDisposition, dict[str, ConsumerDecision]]:
        # 1. Run Core Validation Gates
        core_results = [
            self.ontology_gate.validate(entity_type, boundary_role, hypothesis),
            self.geometry_gate.validate(hypothesis),
            self.evidence_gate.validate(hypothesis),
        ]

        # 1b. R14-P2 external coverage gate (opt-in via constructor wiring).
        if self.coverage_gate is not None and polygon_context is not None:
            core_results.append(self.coverage_gate.validate(polygon_context, hypothesis))

        # 2. Resolve Objective FinalDisposition
        disposition = self.resolve_final_disposition(core_results)

        # 3. Evaluate Consumer-Aware Decision Readiness
        all_results = list(core_results)
        consumer_decisions: dict[str, ConsumerDecision] = {}

        for cp in consumers:
            cr = self.decision_readiness_gate.evaluate(hypothesis, core_results, cp, disposition)
            all_results.append(cr)
            if cr.status == ValidationStatus.PASSED:
                consumer_decisions[cp.name] = ConsumerDecision.READY
            elif cr.status == ValidationStatus.WARNED and cr.decision_ready:
                consumer_decisions[cp.name] = ConsumerDecision.READY_WITH_WARNING
            else:
                consumer_decisions[cp.name] = ConsumerDecision.NOT_READY

        return all_results, disposition, consumer_decisions
