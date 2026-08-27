"""Ontology v2: 双层本体 — 用途层(LandUseClass) + 实体层(v1 frozen).

升级动机 (2026-08-27 三次自检 + 用户质询"本体是否需要升级"):
  v1 本体冻结在住宅域, 无医院/学校/公园概念. R15 分类器另造 GB50137 十码,
  与本体平行运行 — 同一地块有两个互不相通的身份. 这是框架级裂缝.

v2 设计:
  1. v1 实体枚举原样保留 (frozen 兼容);
  2. LandUseClass 枚举承载规划用途 — 与"实体是什么"正交的属性;
  3. OntologyProfile 声明应用域: 合法实体集 × 合法用途集 × 组合约束.
"""

from __future__ import annotations

from enum import Enum

from src.domain.contracts import OntologyType as V1EntityType


class LandUseClass(str, Enum):
    """GB50137 用途大类 (+军事/农业/未分类). 地块的用途属性."""

    RESIDENTIAL = "R"
    COMMERCIAL_RETAIL = "B1"
    BUSINESS_OFFICE = "B2"
    INDUSTRIAL = "M"
    TRANSPORT_HUB = "S"
    EDUCATION_RESEARCH = "A3"
    SPORTS_CULTURE = "A4"
    HEALTHCARE = "A5"
    PARK_GREEN = "G"
    MILITARY = "MIL"
    AGRICULTURAL = "AGR"
    UNCLASSIFIED = "U"


class OntologyProfile(str, Enum):
    RESIDENTIAL_V1 = "residential-v1"
    URBAN_LANDUSE_V2 = "urban-landuse-v2"


_PROFILE_ENTITY_TYPES: dict[OntologyProfile, set[V1EntityType]] = {
    OntologyProfile.RESIDENTIAL_V1: set(V1EntityType),
    OntologyProfile.URBAN_LANDUSE_V2: {
        V1EntityType.LAND_PARCEL,
        V1EntityType.BUILDING,
        V1EntityType.ROAD,
        V1EntityType.RESIDENTIAL_COMPOUND,
        V1EntityType.RESIDENTIAL_ESTATE,
        V1EntityType.ADMINISTRATIVE_COMMUNITY,
        V1EntityType.UNKNOWN_RESIDENTIAL_ENTITY,
    },
}

_PROFILE_LANDUSE: dict[OntologyProfile, set[LandUseClass]] = {
    OntologyProfile.RESIDENTIAL_V1: {LandUseClass.RESIDENTIAL},
    OntologyProfile.URBAN_LANDUSE_V2: set(LandUseClass),
}

# 非法组合 (zero false-merge 精神延伸到用途-实体对)
_ILLEGAL_PAIRS: set[tuple[V1EntityType, LandUseClass]] = {
    (V1EntityType.RESIDENTIAL_COMPOUND, LandUseClass.MILITARY),
    (V1EntityType.RESIDENTIAL_COMPOUND, LandUseClass.AGRICULTURAL),
    (V1EntityType.RESIDENTIAL_ESTATE, LandUseClass.INDUSTRIAL),
}


def validate_pair(entity_type: V1EntityType, landuse: LandUseClass,
                  profile: OntologyProfile) -> tuple[bool, str]:
    if entity_type not in _PROFILE_ENTITY_TYPES.get(profile, set()):
        return False, f"{entity_type.value} 不在 {profile.value} 实体集"
    if landuse not in _PROFILE_LANDUSE.get(profile, set()):
        return False, f"{landuse.value} 不在 {profile.value} 用途集"
    if (entity_type, landuse) in _ILLEGAL_PAIRS:
        return False, f"非法组合 {entity_type.value}×{landuse.value}"
    return True, ""
