"""P0-05 / v1.0 Minimal Ontology: Beijing Residential Ontology Profile.

Defines the 14 frozen ontology types and morphology profile.
See: 北京住宅开放数据与本体定义规范 v1.0
"""

from __future__ import annotations

from src.domain.contracts import OntologyType, MorphologyType


# All 14 valid ontology types (frozen per spec)
VALID_ONTOLOGY_TYPES: frozenset[OntologyType] = frozenset(OntologyType)


def is_valid_ontology_type(t: str | OntologyType) -> bool:
    if isinstance(t, OntologyType):
        return t in VALID_ONTOLOGY_TYPES
    return any(t == v.value for v in OntologyType)


def ontology_type_from_name(name: str) -> OntologyType | None:
    """Resolve a Chinese/common name to an OntologyType."""
    mappings = {
        "小区": OntologyType.RESIDENTIAL_COMPOUND,
        "社区": OntologyType.ADMINISTRATIVE_COMMUNITY,
        "住宅小区": OntologyType.RESIDENTIAL_COMPOUND,
        "期": OntologyType.RESIDENTIAL_PHASE,
        "栋": OntologyType.BUILDING,
        "楼": OntologyType.BUILDING,
        "路": OntologyType.ROAD,
        "街": OntologyType.ROAD,
        "道": OntologyType.ROAD,
        "门": OntologyType.ENTRANCE,
        "入口": OntologyType.ENTRANCE,
        "地块": OntologyType.LAND_PARCEL,
        "大院": OntologyType.RESIDENTIAL_COMPOUND,
        "住宅区": OntologyType.RESIDENTIAL_ESTATE,
        "园区": OntologyType.RESIDENTIAL_ESTATE,
        "物业": OntologyType.PROPERTY_MANAGEMENT_AREA,
        "管委会": OntologyType.ADMINISTRATIVE_COMMUNITY,
        "居委会": OntologyType.ADMINISTRATIVE_COMMUNITY,
        "大门": OntologyType.GATE,
        "围墙": OntologyType.BARRIER,
        "栅栏": OntologyType.BARRIER,
    }
    for key, value in mappings.items():
        if key in name:
            return value
    return None