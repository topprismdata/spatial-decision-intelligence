"""R3 Validation Gate Verification Tests: 14 Combination Matrix Cases.

Verifies:
- Ontology / Geometry / Evidence / DecisionReadiness
- FinalDisposition (TRUSTED / PROVISIONAL / UNRESOLVED / REJECTED)
- Consumer-Aware DecisionReadiness (VisitCheckIn vs TerritoryOptimization)
"""

import pytest
from src.domain.contracts import (
    BoundaryHypothesis,
    Evidence,
    EvidenceType,
    HypothesisStatus,
    OntologyType,
    ValidationStatus,
)
from src.validation.pipeline import (
    ConsumerDecision,
    ConsumerProfile,
    FinalDisposition,
    PROFILE_TERRITORY_OPTIMIZATION,
    PROFILE_VISIT_CHECKIN,
    ValidationPipeline,
)

# Standard Valid Beijing Polygon (~95,000 m²)
VALID_POLY = "POLYGON((116.3500 39.9000, 116.3600 39.9000, 116.3600 39.9100, 116.3500 39.9100, 116.3500 39.9000))"
# Invalid self-intersecting polygon (bowtie)
SELF_INTERSECT_POLY = "POLYGON((116.35 39.90, 116.36 39.91, 116.36 39.90, 116.35 39.91, 116.35 39.90))"
# Tiny sliver (< 50 m²)
TINY_POLY = "POLYGON((116.35000 39.90000, 116.35005 39.90000, 116.35005 39.90005, 116.35000 39.90005, 116.35000 39.90000))"
# Giant polygon (> 10 km²)
GIANT_POLY = "POLYGON((116.0 39.5, 116.5 39.5, 116.5 40.0, 116.0 40.0, 116.0 39.5))"
# Low compactness jagged sliver
JAGGED_POLY = "POLYGON((116.3500 39.9000, 116.3800 39.9001, 116.3800 39.9002, 116.3500 39.9001, 116.3500 39.9000))"

VALID_EV_OSM = Evidence(source="OSM", evidence_type=EvidenceType.GEOMETRY, content="residential_polygon", confidence=0.85)
VALID_EV_BUILDINGS = Evidence(source="MicrosoftBuildings", evidence_type=EvidenceType.GEOMETRY, content="building_footprints", confidence=0.90)
FATAL_CONFLICT_EV = Evidence(source="Inspection", evidence_type=EvidenceType.OTHER, content="fatal_evidence_conflict_explicit_exclusion", confidence=1.0)
WEAK_PRIOR_EV = Evidence(source="AreaPriorBaseline", evidence_type=EvidenceType.OTHER, content="circular_prior", confidence=0.30)


@pytest.fixture
def pipeline():
    return ValidationPipeline()


def _make_hyp(geom_wkt=VALID_POLY, evidence=(VALID_EV_OSM, VALID_EV_BUILDINGS), score=0.85):
    h = BoundaryHypothesis(
        entity_id="test_entity",
        geometry=geom_wkt,
        generator="BaselineProvider",
        status=HypothesisStatus.PROPOSED,
        evidence=tuple(evidence),
    )
    # BoundaryHypothesis is frozen, use object.__setattr__ directly
    object.__setattr__(h, "generation_score", score)
    return h


def test_v01_gold_standard_sample(pipeline):
    """V01: Ontology PASS, Geometry PASS, Evidence PASS -> TRUSTED, Both READY."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM, VALID_EV_BUILDINGS], score=0.90)
    # Territory optimization without topology requirement for V01
    consumer_b = ConsumerProfile(name="Territory", min_confidence=0.80, allow_provisional=False)
    results, disposition, decisions = pipeline.run(
        OntologyType.RESIDENTIAL_COMPOUND, hyp, consumers=[PROFILE_VISIT_CHECKIN, consumer_b]
    )
    assert disposition == FinalDisposition.TRUSTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY
    assert decisions["Territory"] == ConsumerDecision.READY


def test_v02_geometry_blocked_self_intersection(pipeline):
    """V02: Self-intersecting geometry -> REJECTED, All NOT_READY."""
    hyp = _make_hyp(SELF_INTERSECT_POLY, [VALID_EV_OSM])
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.REJECTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.NOT_READY
    assert decisions["TerritoryOptimization"] == ConsumerDecision.NOT_READY


def test_v03_invalid_ontology_type(pipeline):
    """V03: Undefined/invalid ontology type -> REJECTED."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM])
    results, disposition, decisions = pipeline.run("INVALID_TYPE", hyp)  # type: ignore
    assert disposition == FinalDisposition.REJECTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.NOT_READY


def test_v04_zero_evidence_abstention(pipeline):
    """V04: Zero evidence support -> UNRESOLVED (System Abstention)."""
    hyp = _make_hyp(VALID_POLY, evidence=[])
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.UNRESOLVED
    assert decisions["VisitCheckIn"] == ConsumerDecision.NOT_READY
    assert decisions["TerritoryOptimization"] == ConsumerDecision.NOT_READY


def test_v05_single_weak_prior_evidence(pipeline):
    """V05: Only weak B0 prior evidence -> PROVISIONAL, Visit READY, Territory NOT_READY."""
    hyp = _make_hyp(VALID_POLY, evidence=[WEAK_PRIOR_EV], score=0.65)
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.PROVISIONAL
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY_WITH_WARNING
    assert decisions["TerritoryOptimization"] == ConsumerDecision.NOT_READY


def test_v06_geometry_low_compactness_warning(pipeline):
    """V06: Low compactness geometry warning -> PROVISIONAL."""
    hyp = _make_hyp(JAGGED_POLY, [VALID_EV_OSM], score=0.70)
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.PROVISIONAL
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY_WITH_WARNING
    assert decisions["TerritoryOptimization"] == ConsumerDecision.NOT_READY


def test_v07_ontology_estate_role_warning(pipeline):
    """V07: ResidentialEstate directly used as physical boundary -> WARNED / PROVISIONAL."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM], score=0.75)
    results, disposition, decisions = pipeline.run(
        OntologyType.RESIDENTIAL_ESTATE, hyp, boundary_role="PHYSICAL_BOUNDARY"
    )
    assert disposition == FinalDisposition.PROVISIONAL
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY_WITH_WARNING


def test_v08_area_exceeds_maximum_bounds(pipeline):
    """V08: Outlier giant area polygon (> 5km²) -> REJECTED."""
    hyp = _make_hyp(GIANT_POLY, [VALID_EV_OSM])
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.REJECTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.NOT_READY


def test_v09_fatal_exclusion_evidence_conflict(pipeline):
    """V09: Fatal evidence conflict -> REJECTED."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM, FATAL_CONFLICT_EV])
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.REJECTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.NOT_READY


def test_v10_multiple_failures_strict_rejection(pipeline):
    """V10: Broken geometry + no evidence + bad type -> REJECTED."""
    hyp = _make_hyp(SELF_INTERSECT_POLY, evidence=[])
    results, disposition, decisions = pipeline.run("BAD_TYPE", hyp)  # type: ignore
    assert disposition == FinalDisposition.REJECTED


def test_v11_consumer_confidence_threshold_separation(pipeline):
    """V11: Hypothesis score 0.70 satisfies Visit (min 0.6) but fails Territory (min 0.85)."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM, VALID_EV_BUILDINGS], score=0.70)
    consumer_b = ConsumerProfile(name="StrictTerritory", min_confidence=0.85, allow_provisional=False)
    results, disposition, decisions = pipeline.run(
        OntologyType.RESIDENTIAL_COMPOUND, hyp, consumers=[PROFILE_VISIT_CHECKIN, consumer_b]
    )
    assert disposition == FinalDisposition.TRUSTED
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY
    assert decisions["StrictTerritory"] == ConsumerDecision.NOT_READY


def test_v12_accumulated_warnings(pipeline):
    """V12: Geometry warning + Weak Evidence warning -> PROVISIONAL, Warning passed to consumer."""
    hyp = _make_hyp(JAGGED_POLY, evidence=[WEAK_PRIOR_EV], score=0.65)
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.PROVISIONAL
    assert decisions["VisitCheckIn"] == ConsumerDecision.READY_WITH_WARNING


def test_v13_consumer_topology_requirement_unattested(pipeline):
    """V13: TerritoryOptimization requires topology consistency check."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM, VALID_EV_BUILDINGS], score=0.90)
    results, disposition, decisions = pipeline.run(
        OntologyType.RESIDENTIAL_COMPOUND, hyp, consumers=[PROFILE_TERRITORY_OPTIMIZATION]
    )
    assert disposition == FinalDisposition.TRUSTED
    assert decisions["TerritoryOptimization"] == ConsumerDecision.NOT_READY


def test_v14_independent_dual_source_confirmation(pipeline):
    """V14: Independent multi-source evidence -> TRUSTED."""
    hyp = _make_hyp(VALID_POLY, [VALID_EV_OSM, VALID_EV_BUILDINGS], score=0.95)
    results, disposition, decisions = pipeline.run(OntologyType.RESIDENTIAL_COMPOUND, hyp)
    assert disposition == FinalDisposition.TRUSTED
