"""P0-01 Domain Contract Unit Tests.

At least 20 tests covering:
- Core contract creation and immutability
- Case D01-D08 from the spec
- Adapter functions for v1/v2 backward compatibility
- Edge cases (nulls, empty collections, None measurements)
"""

import pytest
from src.domain.contracts import (
    AssertionType,
    AuthorityAssertion,
    BoundaryHypothesis,
    BoundaryRepresentation,
    BoundaryType,
    Evidence,
    EvidenceType,
    HypothesisStatus,
    Observation,
    OntologyType,
    ProviderResult,
    ProviderStatus,
    RelationMeasurement,
    RelationType,
    RepresentationOrigin,
    SpatialEntity,
    SpatialRelation,
    SpatialRepresentation,
    TrustedSpatialState,
    ValidationResult,
    ValidationStatus,
    _new_id,
)
from src.domain.ontology import is_valid_ontology_type, ontology_type_from_name


# ── Core Contract Creation ────────────────────────────────────────────────────


class TestObservation:
    def test_create_with_minimal_fields(self):
        o = Observation()
        assert o.id
        assert o.source == ""
        assert o.raw_geometry is None

    def test_create_with_all_fields(self):
        o = Observation(
            source="OSM",
            source_record_id="way/12345",
            observed_features=("龙湖小区", "北京朝阳"),
            raw_geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            observed_at="2026-07-01",
            provenance="overpass-api",
        )
        assert o.source == "OSM"
        assert "龙湖小区" in o.observed_features

    def test_immutable(self):
        o = Observation()
        with pytest.raises(AttributeError):
            o.source = "changed"  # type: ignore

    # Case D02: one observation supports multiple features
    def test_one_observation_multiple_features(self):
        o = Observation(
            source="Microsoft Buildings",
            observed_features=("building-a", "building-b", "building-c"),
        )
        assert len(o.observed_features) == 3


class TestSpatialRepresentation:
    def test_create(self):
        r = SpatialRepresentation(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            origin=RepresentationOrigin.OSM_INFERRED,
        )
        assert r.entity_id == "ent-1"
        assert r.geometry.startswith("POLYGON")

    # Case D01: one entity, multiple representations
    def test_multiple_representations(self):
        r1 = SpatialRepresentation(
            entity_id="compound-1", geometry="POLYGON((0 0, 1 0, 1 1, 0 0))"
        )
        r2 = SpatialRepresentation(
            entity_id="compound-1",
            geometry="POLYGON((0.5 0.5, 1.5 0.5, 1.5 1.5, 0.5 0.5))",
        )
        entity = SpatialEntity(
            id="compound-1", representations=(r1, r2), ontology_type=OntologyType.RESIDENTIAL_COMPOUND
        )
        assert len(entity.representations) == 2
        assert entity.representations[0] is r1
        assert entity.representations[1] is r2


class TestBoundaryRepresentation:
    def test_create(self):
        br = BoundaryRepresentation(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            boundary_type=BoundaryType.INFERRED,
        )
        assert br.boundary_type == BoundaryType.INFERRED
        assert br.origin == RepresentationOrigin.OTHER


class TestRelationMeasurement:
    # Case D03: relation without geometry metric
    def test_relation_without_measurement(self):
        rel = SpatialRelation(
            source_entity_id="phase-a",
            target_entity_id="estate-1",
            relation_type=RelationType.PART_OF,
            measurements=None,
        )
        assert rel.measurements is None
        assert rel.relation_type == RelationType.PART_OF

    def test_relation_with_partial_measurement(self):
        m = RelationMeasurement(iou=None, distance=150.0, semantic_score=0.85)
        rel = SpatialRelation(
            source_entity_id="entrance-1",
            target_entity_id="compound-1",
            relation_type=RelationType.HAS_ENTRANCE,
            measurements=m,
        )
        assert rel.measurements.iou is None  # IoU not applicable
        assert rel.measurements.distance == 150.0


class TestSpatialRelation:
    def test_entrance_of_without_geometry(self):
        """Entrance → Compound: no IoU, no distance required."""
        rel = SpatialRelation(
            source_entity_id="entrance-1",
            target_entity_id="compound-1",
            relation_type=RelationType.HAS_ENTRANCE,
            measurements=None,
        )
        assert rel.measurements is None

    def test_part_of_without_geometry(self):
        rel = SpatialRelation(
            source_entity_id="phase-1",
            target_entity_id="estate-1",
            relation_type=RelationType.PART_OF,
            measurements=None,
        )
        assert rel.measurements is None


class TestSpatialEntity:
    def test_create_with_all_collections(self):
        entity = SpatialEntity(
            ontology_type=OntologyType.RESIDENTIAL_COMPOUND,
            name="龙湖小区",
            observations=(
                Observation(source="OSM", raw_geometry="POLYGON((0 0, 1 0, 1 1, 0 0))"),
            ),
            representations=(
                SpatialRepresentation(
                    entity_id="ent-1",
                    geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
                    origin=RepresentationOrigin.OSM_INFERRED,
                ),
            ),
            relations=(
                SpatialRelation(
                    source_entity_id="ent-1",
                    target_entity_id="estate-1",
                    relation_type=RelationType.PART_OF,
                ),
            ),
        )
        assert entity.name == "龙湖小区"
        assert len(entity.observations) == 1
        assert len(entity.representations) == 1
        assert len(entity.relations) == 1

    # Case D04: conflicting polygons from different sources — retain both
    def test_conflicting_polygons_retained(self):
        osm_obs = Observation(
            source="OSM",
            observed_features=("龙湖小区",),
            raw_geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
        )
        overture_obs = Observation(
            source="Overture",
            observed_features=("龙湖小区",),
            raw_geometry="POLYGON((0.2 0.2, 0.8 0.2, 0.8 0.8, 0.2 0.2))",
        )
        entity = SpatialEntity(
            name="龙湖小区",
            observations=(osm_obs, overture_obs),
        )
        # Both observations are retained, not overwritten
        assert len(entity.observations) == 2
        assert entity.observations[0].source == "OSM"
        assert entity.observations[1].source == "Overture"


class TestAuthorityAssertion:
    def test_create(self):
        aa = AuthorityAssertion(
            entity_id="ent-1",
            authority="OSM",
            assertion_type=AssertionType.BOUNDARY,
            confidence=0.9,
            evidence_refs=("ev-1", "ev-2"),
        )
        assert aa.authority == "OSM"
        assert aa.confidence == 0.9

    def test_immutable_tuple(self):
        aa = AuthorityAssertion(
            entity_id="ent-1", authority="test", evidence_refs=("ev-1",)
        )
        with pytest.raises(AttributeError):  # frozen dataclass blocks reassignment
            aa.evidence_refs = ("ev-1", "ev-2")
        assert isinstance(aa.evidence_refs, tuple)


class TestEvidence:
    def test_create(self):
        e = Evidence(
            source="OSM",
            evidence_type=EvidenceType.GEOMETRY,
            content="POLYGON((0 0, 1 0, 1 1, 0 0))",
            confidence=0.95,
        )
        assert e.evidence_type == EvidenceType.GEOMETRY
        assert e.confidence == 0.95


class TestBoundaryHypothesis:
    def test_create(self):
        bh = BoundaryHypothesis(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            generator="RoadBlockProvider",
            confidence=0.85,
            status=HypothesisStatus.PROPOSED,
        )
        assert bh.generator == "RoadBlockProvider"
        assert bh.status == HypothesisStatus.PROPOSED

    def test_lifecycle(self):
        bh = BoundaryHypothesis(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            generator="RoadBlockProvider",
            confidence=0.85,
        )
        assert bh.status == HypothesisStatus.PROPOSED


class TestValidationResult:
    # Case D06: invalid geometry → not TRUSTED
    def test_invalid_geometry_blocked(self):
        vr = ValidationResult(
            entity_id="ent-1",
            validator="GeometryGate",
            status=ValidationStatus.FAILED,
            findings=("self-intersection",),
            decision_ready=False,
        )
        assert vr.decision_ready is False
        assert ValidationStatus.FAILED in vr.status

    # Case D07: insufficient evidence → UNRESOLVED
    def test_insufficient_evidence(self):
        vr = ValidationResult(
            entity_id="ent-1",
            validator="EvidenceGate",
            status=ValidationStatus.FAILED,
            findings=("evidence_insufficient: no road or building data",),
            decision_ready=False,
        )
        assert vr.decision_ready is False
        assert "evidence_insufficient" in vr.findings[0]


class TestTrustedSpatialState:
    def test_empty_state(self):
        state = TrustedSpatialState()
        assert len(state.entities) == 0
        assert len(state.trusted_projections) == 0
        assert state.created_at is not None

    def test_with_entities(self):
        entity = SpatialEntity(id="ent-1", name="龙湖小区")
        state = TrustedSpatialState(
            entities={"ent-1": entity},
            unresolved=("ent-2",),
        )
        assert state.entities["ent-1"].name == "龙湖小区"
        assert "ent-2" in state.unresolved


class TestProviderResult:
    # Case D05: provider with no road data
    def test_no_road_data(self):
        result = ProviderResult(
            status=ProviderStatus.NOT_APPLICABLE,
            provenance="RoadBlockProvider: no road data in bbox",
        )
        assert result.status == ProviderStatus.NOT_APPLICABLE
        assert len(result.hypotheses) == 0

    def test_with_hypotheses(self):
        bh = BoundaryHypothesis(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            generator="RoadBlockProvider",
        )
        result = ProviderResult(
            status=ProviderStatus.APPLICABLE,
            hypotheses=(bh,),
            provenance="RoadBlockProvider: generated 1 hypothesis",
        )
        assert result.status == ProviderStatus.APPLICABLE
        assert len(result.hypotheses) == 1


# ── Ontology Tests ────────────────────────────────────────────────────────────


class TestOntology:
    def test_all_types_valid(self):
        for t in OntologyType:
            assert is_valid_ontology_type(t)

    def test_string_validation(self):
        assert is_valid_ontology_type("ResidentialCompound")
        assert not is_valid_ontology_type("NotARealType")

    def test_ontology_type_from_name(self):
        assert ontology_type_from_name("龙湖小区") == OntologyType.RESIDENTIAL_COMPOUND
        assert ontology_type_from_name("朝阳路") == OntologyType.ROAD
        assert ontology_type_from_name("北门") == OntologyType.ENTRANCE
        assert ontology_type_from_name("未知类型") is None

    def test_exactly_14_types(self):
        assert len(OntologyType) == 14


# ── Edge Case Tests ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_observations_tuple(self):
        entity = SpatialEntity(name="test")
        assert entity.observations == ()

    def test_none_raw_geometry(self):
        obs = Observation(source="test", raw_geometry=None)
        assert obs.raw_geometry is None

    def test_very_long_confidence(self):
        bh = BoundaryHypothesis(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            generator="test",
            confidence=0.999999,
        )
        assert 0 <= bh.confidence <= 1.0

    # Case D08: highest score but validation blocks
    def test_high_score_but_validation_blocks(self):
        bh = BoundaryHypothesis(
            entity_id="ent-1",
            geometry="POLYGON((0 0, 1 0, 1 1, 0 0))",
            generator="BestProvider",
            confidence=0.95,
        )
        vr = ValidationResult(
            entity_id="ent-1",
            validator="GeometryGate",
            status=ValidationStatus.BLOCKED,
            findings=("self-intersection detected",),
            decision_ready=False,
        )
        # Hypothesis has high confidence but validation blocks it
        assert bh.confidence == 0.95
        assert vr.decision_ready is False
        assert vr.status == ValidationStatus.BLOCKED


# ── Adapter Tests ─────────────────────────────────────────────────────────────


class TestAdapters:
    def test_observation_from_source_record(self):
        """Test that SourceRecord → Observation adapter works."""
        from src.domain.contracts import observation_from_source_record
        from src.domain.models import SourceRecord

        record = SourceRecord(
            source_record_id="SR-BJ-001",
            source_system="excel_import",
            source_batch_id="batch-1",
            source_business_id="BJ-001",
            name_raw="龙湖小区",
            address_raw="北京朝阳",
            province_raw="北京",
            city_raw="北京",
            district_raw="朝阳",
            street_raw="",
            point_raw_lng=116.4,
            point_raw_lat=39.9,
            geometry_raw_wkt="POLYGON((0 0, 1 0, 1 1, 0 0))",
        )
        obs = observation_from_source_record(record)
        assert obs.source == "excel_import"
        assert obs.source_record_id == "SR-BJ-001"
        assert "龙湖小区" in obs.observed_features
        assert obs.raw_geometry == record.geometry_raw_wkt

    def test_spatial_relation_from_entity_relation(self):
        """Test that EntityRelation → SpatialRelation adapter works."""
        from src.domain.contracts import spatial_relation_from_entity_relation
        from src.domain.models import EntityRelation, RelationType as V1RelationType

        er = EntityRelation(
            relation_id="REL-1",
            subject_id="src-1",
            object_id="tgt-1",
            relation_type=V1RelationType.SAME_ENTITY,
            same_entity_probability=0.95,
            relation_confidence=0.95,
            metrics={"iou": 0.95, "centroid_dist_meters": 0.0, "name_sim": 0.98},
        )
        rel = spatial_relation_from_entity_relation(er)
        assert rel.relation_type == RelationType.SAME_AS
        assert rel.source_entity_id == "src-1"
        assert rel.measurements is not None
        assert rel.measurements.iou == 0.95
        assert rel.measurements.semantic_score == 0.98