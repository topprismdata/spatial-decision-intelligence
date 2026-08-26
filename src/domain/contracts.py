"""P0-01 Domain Contracts: Spatial World Model core data types.

These contracts replace the prototype assumptions in models.py and world_model.py
with a clean separation of Observation, SpatialRepresentation, and SpatialEntity.

Beijing Residential Ontology Profile v1.0 alignment.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class OntologyType(str, Enum):
    """Frozen minimal ontology. Beijing Residential Ontology Profile v1.0."""

    RESIDENTIAL_ESTATE = "ResidentialEstate"
    RESIDENTIAL_PHASE = "ResidentialPhase"
    RESIDENTIAL_COMPOUND = "ResidentialCompound"
    PROPERTY_MANAGEMENT_AREA = "PropertyManagementArea"
    RESIDENTIAL_LAND_USE = "ResidentialLandUse"
    ADMINISTRATIVE_COMMUNITY = "AdministrativeCommunity"
    LAND_PARCEL = "LandParcel"
    BUILDING = "Building"
    ENTRANCE = "Entrance"
    GATE = "Gate"
    ROAD = "Road"
    BARRIER = "Barrier"
    UNKNOWN_RESIDENTIAL_ENTITY = "UnknownResidentialEntity"
    OTHER_BUILT_FEATURE = "OtherBuiltFeature"


class RepresentationOrigin(str, Enum):
    """Origin of a SpatialRepresentation."""

    OSM_INFERRED = "OSM_INFERRED"
    HISTORICAL_BOUNDARY = "HISTORICAL_BOUNDARY"
    PHYSICAL_HYPOTHESIS = "PHYSICAL_HYPOTHESIS"
    OPERATIONAL_GEOFENCE = "OPERATIONAL_GEOFENCE"
    OVERTURE = "OVERTURE"
    MICROSOFT_BUILDINGS = "MICROSOFT_BUILDINGS"
    OTHER = "OTHER"


class BoundaryType(str, Enum):
    """Type of boundary representation."""

    ADMINISTRATIVE = "ADMINISTRATIVE"
    OPERATIONAL = "OPERATIONAL"
    PHYSICAL = "PHYSICAL"
    INFERRED = "INFERRED"
    DISPUTED = "DISPUTED"


class RelationType(str, Enum):
    """Typed spatial relations between entities (v1.0 spec section 49)."""

    PART_OF = "PART_OF"
    HAS_PART = "HAS_PART"
    BELONGS_TO = "BELONGS_TO"
    HAS_ENTRANCE = "HAS_ENTRANCE"
    HAS_GATE = "HAS_GATE"
    BOUNDED_BY = "BOUNDED_BY"
    SEPARATED_BY = "SEPARATED_BY"
    CONNECTED_BY = "CONNECTED_BY"
    ADJACENT_TO = "ADJACENT_TO"
    CONTAINS = "CONTAINS"
    WITHIN = "WITHIN"
    OVERLAPS = "OVERLAPS"
    SAME_AS = "SAME_AS"
    UNKNOWN = "UNKNOWN"


class AssertionType(str, Enum):
    BOUNDARY = "BOUNDARY"
    NAME = "NAME"
    TYPE = "TYPE"
    RELATION = "RELATION"
    EVIDENCE = "EVIDENCE"


class EvidenceType(str, Enum):
    GEOMETRY = "GEOMETRY"
    NAME = "NAME"
    RELATION = "RELATION"
    DOCUMENT = "DOCUMENT"
    IMAGE = "IMAGE"
    OTHER = "OTHER"


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    TRUSTED = "TRUSTED"


class ValidationStatus(str, Enum):
    PASSED = "PASSED"
    WARNED = "WARNED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ProviderStatus(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    ERROR = "ERROR"


class MorphologyType(str, Enum):
    """Residential morphology profile (v1.0 spec section 17). Not core ontology. Multi-label allowed."""

    MODERN_GATED = "MODERN_GATED"
    MULTI_PHASE = "MULTI_PHASE"
    OLD_GATED = "OLD_GATED"
    OLD_OPEN = "OLD_OPEN"
    DANWEI_COURTYARD = "DANWEI_COURTYARD"
    VILLA = "VILLA"
    ROAD_SPLIT = "ROAD_SPLIT"
    MIXED_USE = "MIXED_USE"
    SUPER_COMPOUND = "SUPER_COMPOUND"
    SMALL_COURTYARD = "SMALL_COURTYARD"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    UNKNOWN = "UNKNOWN"


class RoadRole(str, Enum):
    """Road role in compound boundary context (v1.0 spec section 15)."""

    PUBLIC_ROAD = "PUBLIC_ROAD"
    INTERNAL_ROAD = "INTERNAL_ROAD"
    SERVICE_ROAD = "SERVICE_ROAD"
    PEDESTRIAN_PATH = "PEDESTRIAN_PATH"
    UNKNOWN_ROAD_ROLE = "UNKNOWN_ROAD_ROLE"


class BuildingFunction(str, Enum):
    """Building function (v1.0 spec section 13). Separated from BuildingMembership."""

    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    OFFICE = "OFFICE"
    SCHOOL = "SCHOOL"
    HOSPITAL = "HOSPITAL"
    COMMUNITY_SERVICE = "COMMUNITY_SERVICE"
    PARKING = "PARKING"
    OTHER = "OTHER"


class BuildingMembershipState(str, Enum):
    """Building membership (v1.0 spec section 12.1)."""

    MEMBER = "MEMBER"
    NON_MEMBER = "NON_MEMBER"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class SeparatorType(str, Enum):
    """Feature that separates compounds (v1.0 spec section 36)."""

    PUBLIC_ROAD = "PUBLIC_ROAD"
    RIVER = "RIVER"
    RAILWAY = "RAILWAY"
    WALL = "WALL"
    FENCE = "FENCE"
    GREEN_BUFFER = "GREEN_BUFFER"
    SCHOOL = "SCHOOL"
    HOSPITAL = "HOSPITAL"
    COMMERCIAL = "COMMERCIAL"
    OTHER = "OTHER"


class ConnectorType(str, Enum):
    """Feature that connects compound parts (v1.0 spec section 37)."""

    INTERNAL_ROAD = "INTERNAL_ROAD"
    PRIVATE_PASSAGE = "PRIVATE_PASSAGE"
    PEDESTRIAN_GATE = "PEDESTRIAN_GATE"
    SHARED_COURTYARD = "SHARED_COURTYARD"
    PEDESTRIAN_BRIDGE = "PEDESTRIAN_BRIDGE"
    UNDERGROUND_ACCESS = "UNDERGROUND_ACCESS"
    OTHER = "OTHER"


class GoldState(str, Enum):
    """Gold adjudication state (v1.0 spec section 9)."""

    GOLD_RESOLVED = "GOLD_RESOLVED"
    GOLD_PARTIAL = "GOLD_PARTIAL"
    GOLD_UNRESOLVED = "GOLD_UNRESOLVED"


class EvidenceSufficiency(str, Enum):
    """Evidence sufficiency level (v1.0 spec section 10)."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ErrorAttribution(str, Enum):
    """Error attribution for failure analysis (v1.0 spec section 30)."""

    DATA_LIMIT = "DATA_LIMIT"
    ENTITY_MODEL = "ENTITY_MODEL"
    ONTOLOGY = "ONTOLOGY"
    PROVIDER = "PROVIDER"
    GIS = "GIS"
    SEMANTIC_REASONING = "SEMANTIC_REASONING"
    VALIDATION = "VALIDATION"
    CALIBRATION = "CALIBRATION"
    GOLD_LIMITATION = "GOLD_LIMITATION"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Core Contracts ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Observation:
    id: str = field(default_factory=_new_id)
    source: str = ""
    source_record_id: str = ""
    observed_features: tuple[str, ...] = ()
    raw_geometry: Optional[str] = None
    observed_at: str = ""
    provenance: str = ""


@dataclass(frozen=True)
class SpatialRepresentation:
    id: str = field(default_factory=_new_id)
    entity_id: str = ""
    geometry: str = ""
    origin: RepresentationOrigin = RepresentationOrigin.OTHER
    crs: str = "WGS84"
    confidence: float = 0.0
    observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BoundaryRepresentation:
    id: str = field(default_factory=_new_id)
    entity_id: str = ""
    geometry: str = ""
    origin: RepresentationOrigin = RepresentationOrigin.OTHER
    boundary_type: BoundaryType = BoundaryType.INFERRED
    crs: str = "WGS84"
    confidence: float = 0.0
    observation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationMeasurement:
    iou: Optional[float] = None
    distance: Optional[float] = None
    semantic_score: Optional[float] = None
    cross_encoder_score: Optional[float] = None


@dataclass(frozen=True)
class SpatialRelation:
    id: str = field(default_factory=_new_id)
    source_entity_id: str = ""
    target_entity_id: str = ""
    relation_type: RelationType = RelationType.UNKNOWN
    measurements: Optional[RelationMeasurement] = None


@dataclass(frozen=True)
class AuthorityAssertion:
    id: str = field(default_factory=_new_id)
    entity_id: str = ""
    authority: str = ""
    assertion_type: AssertionType = AssertionType.BOUNDARY
    confidence: float = 0.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    id: str = field(default_factory=_new_id)
    source: str = ""
    evidence_type: EvidenceType = EvidenceType.OTHER
    content: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class BoundaryHypothesis:
    id: str = field(default_factory=_new_id)
    entity_id: str = ""
    geometry: str = ""
    generator: str = ""
    confidence: float = 0.0
    evidence: tuple[Evidence, ...] = ()
    status: HypothesisStatus = HypothesisStatus.PROPOSED


@dataclass(frozen=True)
class ValidationResult:
    id: str = field(default_factory=_new_id)
    entity_id: str = ""
    validator: str = ""
    status: ValidationStatus = ValidationStatus.PASSED
    findings: tuple[str, ...] = ()
    decision_ready: bool = False


@dataclass(frozen=True)
class SpatialEntity:
    id: str = field(default_factory=_new_id)
    ontology_type: OntologyType = OntologyType.RESIDENTIAL_COMPOUND
    name: str = ""
    observations: tuple[Observation, ...] = ()
    representations: tuple[SpatialRepresentation, ...] = ()
    relations: tuple[SpatialRelation, ...] = ()
    authority_assertions: tuple[AuthorityAssertion, ...] = ()


@dataclass(frozen=True)
class TrustedSpatialState:
    entities: dict[str, SpatialEntity] = field(default_factory=dict)
    trusted_projections: dict[str, SpatialRepresentation] = field(default_factory=dict)
    unresolved: tuple[str, ...] = ()
    created_at: str = field(default_factory=_now_iso)


# ── Provider Contract ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProviderResult:
    status: ProviderStatus = ProviderStatus.NOT_APPLICABLE
    hypotheses: tuple[BoundaryHypothesis, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    provenance: str = ""


# ── Gold Adjudication (v1.0 spec sections 8-11) ────────────────────────────────


@dataclass(frozen=True)
class SeparatorFeature:
    """Feature that separates compounds (v1.0 spec section 36)."""
    separator_type: SeparatorType = SeparatorType.OTHER
    geometry_wkt: str = ""
    strength: float = 1.0
    evidence: str = ""


@dataclass(frozen=True)
class ConnectorFeature:
    """Feature that connects compound parts (v1.0 spec section 37)."""
    connector_type: ConnectorType = ConnectorType.OTHER
    geometry_wkt: str = ""
    strength: float = 1.0
    evidence: str = ""


@dataclass(frozen=True)
class BoundaryUncertaintyZone:
    """Zone where boundary position is uncertain (v1.0 spec section 41)."""
    geometry_wkt: str = ""
    uncertainty_range_m: float = 0.0
    evidence: str = ""


@dataclass(frozen=True)
class GoldCorrectionRecord:
    """Record of a Gold correction (v1.0 spec section 43)."""
    case_id: str = ""
    old_state: str = ""
    new_state: str = ""
    reason: str = ""
    new_evidence: str = ""
    reviewer: str = ""
    date: str = ""


@dataclass(frozen=True)
class GoldAdjudication:
    """Gold adjudication result (v1.0 spec sections 8-11, 8-step protocol).

    Step 1-4: Collection & Construction
    Step 5: Independent Evidence Review
    Step 6: Adjudication
    Step 7: Sufficiency Decision
    Step 8: Evidence Bundle Freeze
    """
    gold_entity: str = ""
    ontology_type: OntologyType = OntologyType.RESIDENTIAL_COMPOUND
    entity_hierarchy: str = ""
    aliases: tuple[str, ...] = ()
    physical_boundary: Optional[str] = None
    building_membership: dict[str, BuildingMembershipState] = field(default_factory=dict)
    important_entrances: tuple[str, ...] = ()
    neighbor_relations: tuple[str, ...] = ()
    evidence_bundle: str = ""
    evidence_sufficiency: EvidenceSufficiency = EvidenceSufficiency.INSUFFICIENT
    gold_state: GoldState = GoldState.GOLD_UNRESOLVED
    gold_confidence: float = 0.0
    uncertainty_zones: tuple[BoundaryUncertaintyZone, ...] = ()
    temporal_reference: str = ""
    adjudication_notes: str = ""
    corrections: tuple[GoldCorrectionRecord, ...] = ()


# ── Reproducibility Contract (v1.0 spec section 41) ──────────────────────────


@dataclass(frozen=True)
class BenchmarkRunRecord:
    """Record of a single benchmark run (v1.0 spec section 41)."""
    benchmark_version: str = ""
    case_ids: tuple[str, ...] = ()
    dataset_versions: str = ""
    source_manifest: str = ""
    ontology_version: str = ""
    provider_versions: str = ""
    model_versions: str = ""
    validation_policy_version: str = ""
    trust_threshold: float = 0.0
    run_time: str = ""


# ── Adapter Functions (v1 ↔ Contracts) ───────────────────────────────────────


def observation_from_source_record(record: "SourceRecord") -> Observation:
    return Observation(
        source="excel_import",
        source_record_id=str(id(record)),
        observed_features=(record.name, record.address),
        raw_geometry=record.geometry_wkt,
        provenance=f"excel:{record.city}/{record.district}",
    )


def representation_from_geometry_version(gv: "GeometryVersion", entity_id: str) -> SpatialRepresentation:
    return SpatialRepresentation(
        entity_id=entity_id,
        geometry=gv.wkt,
        crs=gv.crs,
        confidence=gv.qa_score if hasattr(gv, "qa_score") else 0.0,
    )


def spatial_relation_from_entity_relation(er: "EntityRelation") -> SpatialRelation:
    from src.domain.models import RelationType as V1RelationType
    type_map = {
        V1RelationType.SAME_ENTITY: RelationType.SAME_AS,
        V1RelationType.SAME_ENTITY_ALT_BOUNDARY: RelationType.SAME_AS,
        V1RelationType.RELATED_ENTITY: RelationType.OVERLAPS,
        V1RelationType.POSSIBLE_MERGE_ERROR: RelationType.OVERLAPS,
        V1RelationType.POSSIBLE_DUPLICATE: RelationType.SAME_AS,
    }
    mapped = type_map.get(er.relation_type, RelationType.UNKNOWN)
    return SpatialRelation(
        source_entity_id=er.source_id or "",
        target_entity_id=er.target_id or "",
        relation_type=mapped,
        measurements=RelationMeasurement(
            iou=er.iou if hasattr(er, "iou") else None,
            distance=er.distance if hasattr(er, "distance") else None,
            semantic_score=er.semantic_similarity if hasattr(er, "semantic_similarity") else None,
            cross_encoder_score=er.cross_encoder_score if hasattr(er, "cross_encoder_score") else None,
        ),
    )