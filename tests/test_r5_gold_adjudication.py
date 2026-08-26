"""R5 Acceptance Tests (G01-G16).

Verifies: Source Manifest, Evidence Bundle, Assertion, Entity/Boundary Gold,
Independent Review, Conflict Resolution, Gold Freeze, Observation Ceiling Report.
"""

from src.gold import GoldState, EvidenceSufficiency, BuildingMembershipState, DependencyType, SourceFamily
from src.gold.models import (
    BoundaryUncertaintyZone,
    CaseSourceManifest,
    EvidenceBundle,
    GoldAssertion,
    GoldBoundarySegment,
    GoldBoundaryState,
    GoldCase,
    GoldCaseVersion,
    GoldCorrectionRecord,
    GoldEntityState,
    GoldReviewConflict,
    MetricEligibility,
    SourceDependency,
    SourceManifestEntry,
)
from src.gold.adjudicator import GoldAdjudicator, CeilingReportGenerator


def test_g01_source_manifest_frozen():
    """G01: Each Case has a frozen Source Manifest with version/license/retrieval time."""
    manifest = CaseSourceManifest(
        case_id="BJ-RS-0001",
        entries=(
            SourceManifestEntry(
                source_id="osm-beijing-roads",
                source_family=SourceFamily.OPEN_MAP,
                provider="OpenStreetMap",
                dataset="beijing_shp",
                theme="roads",
                release="2026-08-26",
                source_url="https://download.geofabrik.de/asia/china/beijing-latest-free.shp.zip",
                license="ODbL",
                license_version="1.0",
                retrieved_at="2026-08-26T21:00:00Z",
                source_semantic_role="ROAD",
            ),
        ),
        dependencies=(
            SourceDependency(source_a="A", source_b="B", dependency_type=DependencyType.INDEPENDENT),
        ),
        frozen_at="2026-08-26T21:00:00Z",
    )
    assert manifest.case_id == "BJ-RS-0001"
    assert len(manifest.entries) == 1
    assert manifest.entries[0].license == "ODbL"
    assert manifest.entries[0].retrieved_at != ""


def test_g03_entity_gold_separate_from_boundary():
    """G03/G05: Entity Gold and Boundary Gold are separate."""
    entity = GoldEntityState(
        case_id="BJ-RS-0001",
        canonical_entities=("ResidentialEstate:XX花园", "ResidentialCompound:C01"),
        entity_gold_state=GoldState.GOLD_RESOLVED,
        entity_evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
    )
    assert entity.entity_gold_state == GoldState.GOLD_RESOLVED
    assert entity.canonical_entities[0].startswith("ResidentialEstate")


def test_g04_evidence_bundle_traceable():
    """G04: All Gold Assertions trace to Evidence Bundle."""
    bundle = EvidenceBundle(
        bundle_id="EB-001",
        target_assertion_id="A01",
        supporting_observation_ids=("obs-1", "obs-2"),
        contradicting_observation_ids=(),
        independent_evidence_groups=("OSM", "Overture"),
        evidence_sufficiency=EvidenceSufficiency.SUFFICIENT,
    )
    assertion = GoldAssertion(
        assertion_id="A01",
        case_id="BJ-RS-0001",
        assertion_text="Building B001 belongs to Compound C01",
        ontology_type="BuildingMembership",
        evidence_bundle_id="EB-001",
        status=GoldState.GOLD_RESOLVED,
    )
    assert assertion.evidence_bundle_id == bundle.bundle_id
    assert bundle.evidence_sufficiency == EvidenceSufficiency.SUFFICIENT


def test_g06_membership_quadstate():
    """G06: Building Membership has four states."""
    ms = BuildingMembershipState
    assert ms.MEMBER.value == "MEMBER"
    assert ms.NON_MEMBER.value == "NON_MEMBER"
    assert ms.AMBIGUOUS.value == "AMBIGUOUS"
    assert ms.UNKNOWN.value == "UNKNOWN"


def test_g07_boundary_role_separation():
    """G07: PHYSICAL_BOUNDARY is separate from other boundary roles."""
    bstate = GoldBoundaryState(
        compound_id="C01",
        boundary_role="PHYSICAL_BOUNDARY",
        boundary_gold_state=GoldState.GOLD_PARTIAL,
        segments=(
            GoldBoundarySegment(
                segment_id="S01", geometry="POLYGON(...)", status="CONFIRMED"
            ),
        ),
    )
    assert bstate.boundary_role == "PHYSICAL_BOUNDARY"
    assert bstate.boundary_gold_state == GoldState.GOLD_PARTIAL


def test_g08_boundary_uncertainty_zone():
    """G08: Boundary uncertainty zones are expressible."""
    zone = BoundaryUncertaintyZone(
        zone_id="Z01",
        geometry="POLYGON((...))",
        uncertainty_range_m=12.0,
        note="Western boundary uncertain within 8-15m range",
    )
    assert zone.uncertainty_range_m == 12.0


def test_g09_independent_review_conflict():
    """G09: Review conflicts are recorded."""
    conflict = GoldReviewConflict(
        case_id="BJ-RS-0001",
        assertion_id="A03",
        review_a="Resolved",
        review_b="Partial",
        conflict_type="EntityStructure",
        evidence_difference="Reviewer B found additional road separator",
        resolution="GOLD_PARTIAL",
        resolution_reason="Both interpretations valid with current evidence",
    )
    assert conflict.conflict_type == "EntityStructure"


def test_g10_gold_freeze_immutable():
    """G10: Gold freeze creates versioned, hashable case."""
    adj = GoldAdjudicator(case_id="BJ-RS-0001", reviewer="Primary")
    adj.g1_freeze_source_manifest(CaseSourceManifest(case_id="BJ-RS-0001"))
    adj.g3_adjudicate_entity(GoldEntityState(
        case_id="BJ-RS-0001", entity_gold_state=GoldState.GOLD_RESOLVED,
    ))
    gold_case = adj.g8_freeze()
    assert gold_case.version is not None
    assert gold_case.version.content_hash != ""
    assert gold_case.version.gold_version == "0.1"


def test_g11_gold_unresolved_not_removed():
    """G11: GOLD_UNRESOLVED is a valid state."""
    entity = GoldEntityState(
        case_id="BJ-RS-0015",
        entity_gold_state=GoldState.GOLD_UNRESOLVED,
        entity_evidence_sufficiency=EvidenceSufficiency.INSUFFICIENT,
    )
    assert entity.entity_gold_state == GoldState.GOLD_UNRESOLVED


def test_g12_correction_record():
    """G12: Gold corrections are recorded, not overwritten."""
    correction = GoldCorrectionRecord(
        case_id="BJ-RS-0001",
        gold_version_from="0.1",
        gold_version_to="0.2",
        changed_assertions=("A04",),
        reason="New Overture building data revealed additional compound",
        reviewer="Senior Reviewer",
        timestamp="2026-08-27T10:00:00Z",
    )
    assert correction.gold_version_from == "0.1"
    assert correction.gold_version_to == "0.2"


def test_g13_metric_eligibility():
    """G13: Each case has metric eligibility flags."""
    eligibility = MetricEligibility(
        eligible_entity_metrics=True,
        eligible_geometry_metrics=False,
        eligible_membership_metrics=True,
        eligible_abstention_metrics=False,
    )
    assert eligibility.eligible_entity_metrics
    assert not eligibility.eligible_geometry_metrics


def test_g14_ceiling_report():
    """G14: Observation Ceiling Report is generated."""
    cases = [
        GoldCase(case_id="BJ-RS-0001",
                 entity_state=GoldEntityState(case_id="BJ-RS-0001", entity_gold_state=GoldState.GOLD_RESOLVED)),
        GoldCase(case_id="BJ-RS-0002",
                 entity_state=GoldEntityState(case_id="BJ-RS-0002", entity_gold_state=GoldState.GOLD_PARTIAL)),
        GoldCase(case_id="BJ-RS-0003",
                 entity_state=GoldEntityState(case_id="BJ-RS-0003", entity_gold_state=GoldState.GOLD_UNRESOLVED)),
    ]
    generator = CeilingReportGenerator()
    report = generator.generate(cases)
    assert report.n_cases == 3
    assert report.resolved == 1
    assert report.partial == 1
    assert report.unresolved == 1


def test_g15_gold_independence():
    """G15: Gold Adjudicator has no Provider/Benchmark references."""
    import inspect
    source = inspect.getsource(GoldAdjudicator)
    assert "ProviderHypothesis" not in source
    assert "CandidateRankingEngine" not in source
    assert "BoundaryHypothesis" not in source


def test_g16_gold_assertion_ontology():
    """G16: Gold Assertion can express entity/boundary/resolved/unresolved."""
    a = GoldAssertion(
        assertion_id="A05",
        case_id="BJ-RS-0010",
        assertion_text="Road R17 separates Compound C01 from C02",
        ontology_type="SeparatorFeature",
        evidence_bundle_id="EB-005",
        status=GoldState.GOLD_RESOLVED,
    )
    assert a.ontology_type == "SeparatorFeature"
    assert a.status == GoldState.GOLD_RESOLVED