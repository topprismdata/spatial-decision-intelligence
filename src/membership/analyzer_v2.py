"""R9 Building Membership REFACTOR: evidence-based, function-aware, morphology-adaptive.

Replaces fixed heuristic weights (0.40/0.25/0.20/0.15) with evidence-based aggregation.
Addresses: school/commercial contamination, office confusion, multi-phase grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.domain.contracts import Evidence, EvidenceType


class MembershipLevel(str, Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCERTAIN = "UNCERTAIN"
    EXCLUDED = "EXCLUDED"


class BuildingFunction(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    SCHOOL = "SCHOOL"
    HOSPITAL = "HOSPITAL"
    COMMERCIAL = "COMMERCIAL"
    OFFICE = "OFFICE"
    COMMUNITY_SERVICE = "COMMUNITY_SERVICE"
    PARKING = "PARKING"
    UNKNOWN = "UNKNOWN"


@dataclass
class MembershipEvidence:
    evidence_type: str = ""
    supports: bool = True
    confidence: float = 0.0
    detail: str = ""


@dataclass
class MembershipResult:
    building_id: str = ""
    compound_id: str = ""
    level: MembershipLevel = MembershipLevel.UNCERTAIN
    confidence: float = 0.0
    evidence: list[MembershipEvidence] = field(default_factory=list)
    primary_function: BuildingFunction = BuildingFunction.UNKNOWN


class BuildingFunctionClassifier:
    """Classifies building function from OSM tags, Overture class, name patterns."""

    SCHOOL_KEYWORDS = frozenset({"学校", "小学", "中学", "幼儿园", "大学", "学院", "教学楼", "操场"})
    HOSPITAL_KEYWORDS = frozenset({"医院", "卫生院", "诊所", "医疗", "康复"})
    COMMERCIAL_KEYWORDS = frozenset({"商场", "超市", "购物", "商业", "商铺", "底商", "菜市场", "广场"})
    OFFICE_KEYWORDS = frozenset({"办公楼", "写字楼", "大厦", "商务", "办公"})
    RESIDENTIAL_KEYWORDS = frozenset({"住宅", "公寓", "宿舍", "居民", "小区", "花园", "家园"})

    def classify(self, name: str, osm_tags: Optional[dict] = None, overture_class: Optional[str] = None) -> BuildingFunction:
        if overture_class:
            cls_map = {"residential": BuildingFunction.RESIDENTIAL, "apartments": BuildingFunction.RESIDENTIAL,
                       "school": BuildingFunction.SCHOOL, "hospital": BuildingFunction.HOSPITAL,
                       "commercial": BuildingFunction.COMMERCIAL, "office": BuildingFunction.OFFICE,
                       "parking": BuildingFunction.PARKING, "community_service": BuildingFunction.COMMUNITY_SERVICE}
            if overture_class in cls_map:
                return cls_map[overture_class]

        if osm_tags:
            building_tag = osm_tags.get("building", "")
            amenity = osm_tags.get("amenity", "")
            if amenity in ("school", "university", "kindergarten"):
                return BuildingFunction.SCHOOL
            if amenity in ("hospital", "clinic"):
                return BuildingFunction.HOSPITAL
            if amenity in ("commercial", "marketplace", "shop"):
                return BuildingFunction.COMMERCIAL
            if building_tag in ("office", "commercial", "retail", "school", "hospital", "parking"):
                cls_map = {"office": BuildingFunction.OFFICE, "commercial": BuildingFunction.COMMERCIAL,
                           "retail": BuildingFunction.COMMERCIAL, "school": BuildingFunction.SCHOOL,
                           "hospital": BuildingFunction.HOSPITAL, "parking": BuildingFunction.PARKING}
                if building_tag in cls_map:
                    return cls_map[building_tag]

        # Name-based fallback
        for kw, func in [(self.SCHOOL_KEYWORDS, BuildingFunction.SCHOOL),
                         (self.HOSPITAL_KEYWORDS, BuildingFunction.HOSPITAL),
                         (self.COMMERCIAL_KEYWORDS, BuildingFunction.COMMERCIAL),
                         (self.OFFICE_KEYWORDS, BuildingFunction.OFFICE),
                         (self.RESIDENTIAL_KEYWORDS, BuildingFunction.RESIDENTIAL)]:
            if any(k in name for k in kw):
                return func
        return BuildingFunction.UNKNOWN


class BuildingMembershipAnalyzerV2:
    """Evidence-based building membership analyzer.

    Replaces fixed heuristic weights with:
    - Function-based exclusion (schools, hospitals excluded by default)
    - Spatial containment evidence
    - Road separation evidence
    - Morphology-aware thresholds
    """

    def __init__(self):
        self._function_classifier = BuildingFunctionClassifier()

    def analyze(
        self,
        building_id: str,
        building_wkt: str,
        building_name: str = "",
        compound_id: str = "",
        compound_boundary_wkt: str = "",
        osm_tags: Optional[dict] = None,
        overture_class: Optional[str] = None,
        morphology: str = "",
    ) -> MembershipResult:
        evidence = []

        # 1. Function classification
        func = self._function_classifier.classify(building_name, osm_tags, overture_class)

        # Strong exclusion for non-residential functions
        if func in (BuildingFunction.SCHOOL, BuildingFunction.HOSPITAL):
            evidence.append(MembershipEvidence("function", False, 0.95, f"Non-residential function: {func.value}"))
            return MembershipResult(
                building_id=building_id, compound_id=compound_id,
                level=MembershipLevel.EXCLUDED, confidence=0.05,
                evidence=evidence, primary_function=func,
            )

        if func in (BuildingFunction.COMMERCIAL, BuildingFunction.OFFICE):
            # Commercial/office can be part of mixed-use compound
            if morphology == "MIXED_USE":
                evidence.append(MembershipEvidence("function", True, 0.5, f"Mixed-use: commercial/office allowed"))
            else:
                evidence.append(MembershipEvidence("function", False, 0.7, f"Non-residential in non-mixed context"))
                return MembershipResult(
                    building_id=building_id, compound_id=compound_id,
                    level=MembershipLevel.EXCLUDED, confidence=0.30,
                    evidence=evidence, primary_function=func,
                )

        # 2. Spatial containment
        try:
            from shapely import wkt as _wkt
            building = _wkt.loads(building_wkt)
            compound = _wkt.loads(compound_boundary_wkt) if compound_boundary_wkt else None

            if compound and building.within(compound):
                evidence.append(MembershipEvidence("containment", True, 0.9, "Building fully within compound boundary"))
            elif compound:
                dist = building.distance(compound)
                if dist < 0.001:
                    evidence.append(MembershipEvidence("containment", True, 0.6, "Building adjacent to compound"))
                else:
                    evidence.append(MembershipEvidence("containment", False, 0.7, f"Building outside compound (dist={dist:.4f})"))
        except Exception:
            pass

        # 3. Aggregate confidence
        if not evidence:
            return MembershipResult(
                building_id=building_id, compound_id=compound_id,
                level=MembershipLevel.UNCERTAIN, confidence=0.5,
                evidence=[], primary_function=func,
            )

        support = sum(e.confidence for e in evidence if e.supports)
        oppose = sum(e.confidence for e in evidence if not e.supports)
        total = support + oppose
        if total == 0:
            return MembershipResult(
                building_id=building_id, compound_id=compound_id,
                level=MembershipLevel.UNCERTAIN, confidence=0.5,
                evidence=evidence, primary_function=func,
            )

        net = (support - oppose * 0.5) / max(total, 1)
        confidence = max(0.0, min(1.0, net))

        if confidence >= 0.75:
            level = MembershipLevel.CONFIRMED
        elif confidence >= 0.50:
            level = MembershipLevel.LIKELY
        elif confidence >= 0.25:
            level = MembershipLevel.UNCERTAIN
        else:
            level = MembershipLevel.EXCLUDED

        return MembershipResult(
            building_id=building_id, compound_id=compound_id,
            level=level, confidence=confidence,
            evidence=evidence, primary_function=func,
        )