"""P0-08 / R3 Validation Pipeline & Gate Verification.

Proposal 3 refactor: gate DECISION LOGIC is data (GateSpec in
src/validation/gate_spec.py); each gate class is now a thin adapter that
(1) extracts facts from its input objects, (2) interprets its spec, and
(3) maps the outcome onto ValidationResult. Thresholds, branches, and
combinators live in serializable spec constants - onboarding a new facility
domain means writing a spec dict, not patching engine code. Facts extraction
(WKT parsing, metric area, evidence scans) remains code by design: the
interpreter is domain-blind (INV-9).
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
from src.validation.gate_spec import (
    AllOf,
    AnyOf,
    Fact,
    GateOutcome,
    GateSpec,
    MinCount,
    Not,
    WarnIf,
    evaluate_spec,
)


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


# ── Gate Specifications (data - the constraint "files") ──────────────────────

#: Ontology: the entity type must be a legal OntologyType; an Estate acting
#: directly as a physical boundary is warnable, not fatal.
ONTOLOGY_SPEC = GateSpec(
    gate_id="OntologyGate",
    must=AllOf(children=(
        Fact(field="entity_type_valid", op="eq", value=True),
        WarnIf(child=Fact(field="estate_role_ok", op="eq", value=True)),
    )),
)

#: Geometry: parse failures / empty / self-intersecting are BLOCKED; area
#: outside profile bounds is FAILED; low compactness is a warnable downgrade.
GEOMETRY_SPEC = GateSpec(
    gate_id="GeometryGate",
    blocked=AnyOf(children=(
        Fact(field="wkt_empty", op="eq", value=True),
        Fact(field="wkt_parse_error", op="present"),
        Fact(field="geom_is_valid", op="eq", value=False),
    )),
    must=AllOf(children=(
        Fact(field="area_m2", op="between", value=(100.0, 5_000_000.0)),
    )),
    warns=WarnIf(child=Fact(field="compactness_ok", op="eq", value=True)),
)

#: Evidence: at least one evidence item (must); a fatal contradiction is
#: BLOCKED; a single weak area-prior is a warnable downgrade.
EVIDENCE_SPEC = GateSpec(
    gate_id="EvidenceGate",
    blocked=Fact(field="has_fatal_conflict", op="eq", value=True),
    must=AllOf(children=(MinCount(field="evidence", n=1),)),
    warns=WarnIf(child=Fact(field="single_weak_prior", op="eq", value=False)),
)

#: Consumer readiness matrix (routing rules for REJECTED/UNRESOLVED/topology
#: stay in the adapter - they are cross-gate routing, not domain policy).
READINESS_SPEC_TEMPLATE = GateSpec(
    gate_id="DecisionReadinessGate",
    must=AllOf(children=(
        AnyOf(children=(
            Fact(field="disposition", op="ne", value="PROVISIONAL"),
            Fact(field="allow_provisional", op="eq", value=True),
        )),
        Fact(field="confidence_ok", op="eq", value=True),
    )),
    warns=WarnIf(child=AllOf(children=(
        Fact(field="has_warnings", op="eq", value=False),
        Fact(field="disposition", op="ne", value="PROVISIONAL"),
    ))),
)



def readiness_spec_for(consumer: ConsumerProfile) -> GateSpec:
    """A consumer profile instantiates its own readiness spec - this is the
    'new domain = new data' seam. min_confidence is baked into a precomputed
    fact by the adapter; allow_provisional flows from the profile."""
    return GateSpec(
        gate_id=f"DecisionReadinessGate/{consumer.name}",
        must=AllOf(children=(
            AnyOf(children=(
                Fact(field="disposition", op="ne", value="PROVISIONAL"),
                Fact(field="allow_provisional", op="eq", value=True),
            )),
            Fact(field="confidence_ok", op="eq", value=True),
        )),
        warns=WarnIf(child=AllOf(children=(
            Fact(field="has_warnings", op="eq", value=False),
            Fact(field="disposition", op="ne", value="PROVISIONAL"),
        ))),
    )


def _outcome_to_result(
    outcome: GateOutcome, entity_id: str, validator: str
) -> ValidationResult:
    return ValidationResult(
        entity_id=entity_id,
        validator=validator,
        status=ValidationStatus[outcome.status],
        findings=tuple(outcome.findings),
        decision_ready=outcome.decision_ready,
    )


# ── Gates (spec-driven adapters) ─────────────────────────────────────────────


class OntologyGate:
    SPEC = ONTOLOGY_SPEC

    @staticmethod
    def validate(
        entity_type: OntologyType,
        boundary_role: str = "PHYSICAL_BOUNDARY",
        hypothesis: Optional[BoundaryHypothesis] = None
    ) -> ValidationResult:
        entity_id = hypothesis.entity_id if hypothesis else ""
        facts = {
            "entity_type_valid": isinstance(entity_type, OntologyType)
            and entity_type in OntologyType,
            "estate_role_ok": not (
                entity_type == OntologyType.RESIDENTIAL_ESTATE
                and boundary_role == "PHYSICAL_BOUNDARY"
            ),
        }
        return _outcome_to_result(
            evaluate_spec(OntologyGate.SPEC, facts), entity_id, "OntologyGate"
        )


class GeometryGate:
    SPEC = GEOMETRY_SPEC
    MIN_AREA_M2 = 100.0
    MAX_AREA_M2 = 5_000_000.0

    def __init__(self, metric_service: Optional[MetricGeometryService] = None):
        self._ms = metric_service or MetricGeometryService()

    def validate(self, hypothesis: BoundaryHypothesis) -> ValidationResult:
        entity_id = hypothesis.entity_id
        geom_wkt = hypothesis.geometry

        facts: dict = {
            "wkt_empty": (
                not geom_wkt or geom_wkt.strip() == ""
                or geom_wkt.upper() == "POLYGON EMPTY"
            ),
            "wkt_parse_error": None,
            "geom_is_valid": True,
            "area_m2": None,
            "compactness_ok": True,
        }
        if not facts["wkt_empty"]:
            try:
                from shapely import wkt as _wkt
                geom = _wkt.loads(geom_wkt)
                if geom.is_empty:
                    facts["wkt_empty"] = True
                else:
                    facts["geom_is_valid"] = geom.is_valid
                    if geom.is_valid:
                        area_m2 = self._ms.area_m2(geom.wkt)
                        facts["area_m2"] = area_m2
                        p = geom.length * 111_000.0  # rough perimeter in meters
                        compactness = (4.0 * 3.14159 * area_m2) / max(p * p, 1.0)
                        facts["compactness_ok"] = compactness >= 0.05
            except Exception as e:
                facts["wkt_parse_error"] = str(e)

        return _outcome_to_result(
            evaluate_spec(GeometryGate.SPEC, facts), entity_id, "GeometryGate"
        )


class EvidenceGate:
    SPEC = EVIDENCE_SPEC

    @staticmethod
    def validate(hypothesis: BoundaryHypothesis) -> ValidationResult:
        entity_id = hypothesis.entity_id
        ev_list = hypothesis.evidence
        facts = {
            "evidence": list(ev_list),
            "has_fatal_conflict": any(
                "conflict_contradiction" in ev.content.lower()
                or "explicit_exclusion" in ev.content.lower()
                for ev in ev_list
            ),
            "single_weak_prior": (
                len(ev_list) == 1
                and ev_list[0].source == "AreaPriorBaseline"
            ),
        }
        return _outcome_to_result(
            evaluate_spec(EvidenceGate.SPEC, facts), entity_id, "EvidenceGate"
        )


class DecisionReadinessGate:
    """Consumer-aware gate. Routing rules (REJECTED -> BLOCKED, UNRESOLVED ->
    FAILED, topology attestation) stay in the adapter; the profile-dependent
    matrix is the per-consumer spec."""

    @staticmethod
    def evaluate(
        hypothesis: BoundaryHypothesis,
        gate_results: Sequence[ValidationResult],
        consumer: ConsumerProfile,
        disposition: FinalDisposition,
    ) -> ValidationResult:
        entity_id = hypothesis.entity_id
        validator = f"DecisionReadinessGate/{consumer.name}"

        # Routing rules (cross-gate, not domain policy).
        if disposition == FinalDisposition.REJECTED:
            return ValidationResult(
                entity_id=entity_id, validator=validator,
                status=ValidationStatus.BLOCKED,
                findings=("disposition_rejected",), decision_ready=False
            )
        if disposition == FinalDisposition.UNRESOLVED:
            return ValidationResult(
                entity_id=entity_id, validator=validator,
                status=ValidationStatus.FAILED,
                findings=("disposition_unresolved",), decision_ready=False
            )
        if consumer.require_topology_consistency:
            return ValidationResult(
                entity_id=entity_id, validator=validator,
                status=ValidationStatus.WARNED,
                findings=("topology_consistency_not_attested",),
                decision_ready=False
            )

        # Confidence extraction (unchanged legacy chain).
        gen_score = getattr(hypothesis, "generation_score", None)
        if gen_score is None and hasattr(hypothesis, "metadata") and isinstance(hypothesis.metadata, dict):
            gen_score = hypothesis.metadata.get("generation_score", None)
        if gen_score is None and hypothesis.evidence:
            gen_score = max(ev.confidence for ev in hypothesis.evidence)
        if gen_score is None:
            gen_score = 0.5

        facts = {
            "disposition": disposition.value,
            "allow_provisional": consumer.allow_provisional,
            "confidence_ok": gen_score >= consumer.min_confidence,
            "has_warnings": any(
                r.status == ValidationStatus.WARNED for r in gate_results
            ),
        }
        return _outcome_to_result(
            evaluate_spec(readiness_spec_for(consumer), facts),
            entity_id, validator,
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
