"""
Core Domain Models for Residential Spatial Entity Platform (v2.0 Spec).
Adheres strictly to Data-Model-First, Semantic-Disambiguation and Non-Residential Entity Classification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum


class EntityType(str, Enum):
    RESIDENTIAL_COMMUNITY = "RESIDENTIAL_COMMUNITY"          # 标准住宅小区 / 花园 / 家园 / 苑
    RESIDENTIAL_COURTYARD = "RESIDENTIAL_COURTYARD"          # 独栋号院 / 大院 / 胡同院落 (如: X号院)
    RESIDENTIAL_DORMITORY = "RESIDENTIAL_DORMITORY"          # 单位家属院 / 职工宿舍
    MIXED_COMMERCIAL_RESIDENTIAL = "MIXED_COMMERCIAL_RESIDENTIAL"  # 商住两用 / 商业广场公寓 / 商住大厦
    NON_RESIDENTIAL_COMMERCIAL = "NON_RESIDENTIAL_COMMERCIAL"      # 纯商业街 / 商场 / 市场 / 纯写字楼
    NON_RESIDENTIAL_FACILITY = "NON_RESIDENTIAL_FACILITY"          # 企事业单位 / 研究所 / 医院 / 学校 / 厂区


class CoordinateStatus(str, Enum):
    CONFIRMED_WGS84 = "CONFIRMED_WGS84"
    CONFIRMED_GCJ02 = "CONFIRMED_GCJ02"
    CONFIRMED_BD09 = "CONFIRMED_BD09"
    CRS_UNKNOWN = "CRS_UNKNOWN"
    MIXED_CRS = "MIXED_CRS"
    PARTIAL_TRANSFORM = "PARTIAL_TRANSFORM"
    SYSTEMATIC_OFFSET = "SYSTEMATIC_OFFSET"
    POINT_POLYGON_CRS_CONFLICT = "POINT_POLYGON_CRS_CONFLICT"


class RelationType(str, Enum):
    SAME_ENTITY = "SAME_ENTITY"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SAME_ENTITY_ALT_BOUNDARY = "SAME_ENTITY_ALT_BOUNDARY"
    SIBLING_PHASE = "SIBLING_PHASE"              # 兄弟分期 (一期 vs 二期)
    SIBLING_SUBAREA = "SIBLING_SUBAREA"          # 兄弟分区 (南区 vs 北区, A区 vs B区)
    SIBLING_COURTYARD = "SIBLING_COURTYARD"      # 兄弟号院 (9号院 vs 5号院, 23号 vs 21号)
    WHOLE_TO_PHASE = "WHOLE_TO_PHASE"            # 整区到分期
    PHASE_TO_WHOLE = "PHASE_TO_WHOLE"            # 分期到整区
    RELATED_ENTITY = "RELATED_ENTITY"            # 临近关联 (待人工复核)
    POSSIBLE_MERGE_ERROR = "POSSIBLE_MERGE_ERROR" # 空间碰撞重叠
    NOT_SAME_ENTITY = "NOT_SAME_ENTITY"
    UNCERTAIN = "UNCERTAIN"


class GeometrySourceType(str, Enum):
    SOURCE_RAW = "SOURCE_RAW"
    SOURCE_NORMALIZED = "SOURCE_NORMALIZED"
    OSM_BOUNDARY = "OSM_BOUNDARY"
    BUILDING_DERIVED = "BUILDING_DERIVED"
    ROAD_CONSTRAINED = "ROAD_CONSTRAINED"
    IMAGE_SEGMENTATION = "IMAGE_SEGMENTATION"
    HUMAN_DRAWN = "HUMAN_DRAWN"
    SYSTEM_REPAIR = "SYSTEM_REPAIR"


class QADomain(str, Enum):
    COORDINATE_QA = "COORDINATE_QA"
    GEOMETRY_VALIDITY = "GEOMETRY_VALIDITY"
    ENTITY_QA = "ENTITY_QA"
    FENCE_QA = "FENCE_QA"
    REPAIR_QA = "REPAIR_QA"


@dataclass(frozen=True)
class SourceRecord:
    """Immutable Source Record - Never overwritten or mutated."""
    source_record_id: str
    source_system: str
    source_batch_id: str
    source_business_id: Optional[str]
    name_raw: str
    address_raw: str
    province_raw: str
    city_raw: str
    district_raw: str
    street_raw: str
    point_raw_lng: Optional[float]
    point_raw_lat: Optional[float]
    geometry_raw_wkt: Optional[str]
    area_raw: Optional[float] = None
    attributes_raw: Dict[str, Any] = field(default_factory=dict)
    ingested_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CoordinateAssessment:
    """Diagnostic assessment for coordinate system of a SourceRecord."""
    source_record_id: str
    coordinate_status: CoordinateStatus
    point_crs: str
    polygon_crs: str
    selected_transform: Optional[str]
    delta_lng: float
    delta_lat: float
    confidence: float
    notes: List[str] = field(default_factory=list)


@dataclass
class GeometryVersion:
    """Versioned geometric representation attached to a Canonical Entity."""
    geometry_version_id: str
    canonical_entity_id: str
    geometry_wkt: str
    geometry_source: GeometrySourceType
    source_record_id: Optional[str]
    coordinate_reference: str = "WGS84"
    geometry_status: str = "ACTIVE"
    geometry_confidence: float = 1.0
    parent_geometry_version_id: Optional[str] = None
    created_by: str = "SYSTEM"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CanonicalEntity:
    """Canonical Community Entity representing a unique real-world community."""
    canonical_entity_id: str
    canonical_name: str
    province: str
    city: str
    district: str
    street: str
    entity_type: EntityType = EntityType.RESIDENTIAL_COMMUNITY
    entity_status: str = "ACTIVE"
    canonical_geometry_version_id: Optional[str] = None
    identity_confidence: float = 1.0
    member_source_record_ids: List[str] = field(default_factory=list)
    semantic_attributes: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class EntityRelation:
    """Relation between two SourceRecords, or SourceRecord and CanonicalEntity."""
    relation_id: str
    subject_id: str
    object_id: str
    relation_type: RelationType
    same_entity_probability: float
    relation_confidence: float
    directional: bool = False
    explain_codes: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    decision_status: str = "AUTO_DECIDED"
    model_version: str = "semantic_rule_v2"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class QAResult:
    """Quality assessment output from Geometry QA or Fence QA."""
    qa_result_id: str
    target_id: str
    qa_domain: QADomain
    score: float
    issues: List[str] = field(default_factory=list)
    features: Dict[str, Any] = field(default_factory=dict)
    decision: str = "PASS"
    qa_model_version: str = "qa_v2"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
