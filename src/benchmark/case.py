"""P0-10 / v1.0 30-Case Data Reality Benchmark: case definitions.

Each case represents a real Beijing residential compound with gold-standard data.
v1.0 alignment: complexity labels, geographic distribution, evidence density, morphology multi-label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.domain.contracts import (
    GoldAdjudication,
    GoldState,
    EvidenceSufficiency,
    MorphologyType,
)


class CaseCategory(str, Enum):
    MODERN_GATED = "modern_gated"
    MULTI_PHASE = "multi_phase"
    DANWEI_COURTYARD = "danwei_courtyard"
    OLD_OPEN = "old_open"
    ROAD_SPLIT = "road_split"
    MIXED_USE = "mixed_use"


class ComplexityLevel(str, Enum):
    """Case complexity (v1.0 spec section 15)."""
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    HARD = "HARD"
    EXTREME = "EXTREME"


class GeographyRegion(str, Enum):
    """Geographic region (v1.0 spec section 13.2)."""
    CORE_URBAN = "core_urban"  # 核心城区
    SUBURBAN = "suburban"  # 近郊城区
    URBAN_FRINGE = "urban_fringe"  # 城乡结合部
    REMOTE_NEW_TOWN = "remote_new_town"  # 远郊新城


class EvidenceDensity(str, Enum):
    """Evidence density (v1.0 spec section 14.2)."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class CaseData:
    osm: bool = False
    overture_buildings: bool = False
    overture_transportation: bool = False
    overture_places: bool = False
    overture_base: bool = False
    microsoft_buildings: bool = False
    government_public: bool = False
    sentinel_context: bool = False

    def missing(self) -> list[str]:
        return [k for k, v in self._asdict().items() if not v]

    def _asdict(self):
        return {
            "OSM": self.osm,
            "Overture Buildings": self.overture_buildings,
            "Overture Transportation": self.overture_transportation,
            "Overture Places": self.overture_places,
            "Overture Base": self.overture_base,
            "Microsoft Buildings": self.microsoft_buildings,
            "Government Public": self.government_public,
            "Sentinel": self.sentinel_context,
        }


@dataclass(frozen=True)
class CaseAnswers:
    """Answers to the 12 questions for each case."""
    q1_entity_found: Optional[bool] = None
    q2_estate_phase_compound_distinguished: Optional[bool] = None
    q3_osm_has_boundary: Optional[bool] = None
    q4_building_source_coverage_consistent: Optional[bool] = None
    q5_road_forms_enclosure: Optional[bool] = None
    q6_road_semantic_ambiguity: Optional[str] = None
    q7_building_cluster_multi_explanation: Optional[bool] = None
    q8_school_commercial_contamination: Optional[bool] = None
    q9_trusted_candidate_possible: Optional[bool] = None
    q10_main_evidence_gap: Optional[str] = None
    q11_should_abstain: Optional[bool] = None
    q12_vlm_actionable_problem: Optional[str] = None


@dataclass
class BenchmarkCase:
    """A single case in the 30-Case Data Reality Benchmark (v1.0)."""
    case_id: str
    name: str
    category: CaseCategory
    morphology: tuple[MorphologyType, ...] = ()  # Multi-label morphology
    complexity: ComplexityLevel = ComplexityLevel.MODERATE
    geography: GeographyRegion = GeographyRegion.CORE_URBAN
    evidence_density: EvidenceDensity = EvidenceDensity.MEDIUM
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0
    data: CaseData = field(default_factory=CaseData)
    answers: CaseAnswers = field(default_factory=CaseAnswers)
    gold: GoldAdjudication = field(default_factory=GoldAdjudication)
    notes: str = ""


# ── 30 Case Templates ─────────────────────────────────────────────────────────


def create_30_case_templates() -> list[BenchmarkCase]:
    """Create the 30-case template structure with geographic diversity.

    6 categories × 5 = 30 cases.
    Geographic distribution: core_urban (12), suburban (8), urban_fringe (6), remote_new_town (4).
    Evidence density: HIGH (10), MEDIUM (12), LOW (8).
    """
    cases = []
    category_map = {
        CaseCategory.MODERN_GATED: [
            ("BJ-001", "现代封闭社区1", ComplexityLevel.SIMPLE, GeographyRegion.CORE_URBAN, EvidenceDensity.HIGH),
            ("BJ-002", "现代封闭社区2", ComplexityLevel.SIMPLE, GeographyRegion.CORE_URBAN, EvidenceDensity.HIGH),
            ("BJ-003", "现代封闭社区3", ComplexityLevel.MODERATE, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-004", "现代封闭社区4", ComplexityLevel.MODERATE, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-005", "现代封闭社区5", ComplexityLevel.HARD, GeographyRegion.REMOTE_NEW_TOWN, EvidenceDensity.LOW),
        ],
        CaseCategory.MULTI_PHASE: [
            ("BJ-006", "多期社区1", ComplexityLevel.MODERATE, GeographyRegion.CORE_URBAN, EvidenceDensity.HIGH),
            ("BJ-007", "多期社区2", ComplexityLevel.HARD, GeographyRegion.CORE_URBAN, EvidenceDensity.MEDIUM),
            ("BJ-008", "多期社区3", ComplexityLevel.MODERATE, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-009", "多期社区4", ComplexityLevel.HARD, GeographyRegion.URBAN_FRINGE, EvidenceDensity.MEDIUM),
            ("BJ-010", "多期社区5", ComplexityLevel.EXTREME, GeographyRegion.REMOTE_NEW_TOWN, EvidenceDensity.LOW),
        ],
        CaseCategory.DANWEI_COURTYARD: [
            ("BJ-011", "单位大院1", ComplexityLevel.MODERATE, GeographyRegion.CORE_URBAN, EvidenceDensity.HIGH),
            ("BJ-012", "单位大院2", ComplexityLevel.HARD, GeographyRegion.CORE_URBAN, EvidenceDensity.MEDIUM),
            ("BJ-013", "单位大院3", ComplexityLevel.HARD, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-014", "单位大院4", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
            ("BJ-015", "单位大院5", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
        ],
        CaseCategory.OLD_OPEN: [
            ("BJ-016", "开放老旧社区1", ComplexityLevel.MODERATE, GeographyRegion.CORE_URBAN, EvidenceDensity.HIGH),
            ("BJ-017", "开放老旧社区2", ComplexityLevel.HARD, GeographyRegion.CORE_URBAN, EvidenceDensity.MEDIUM),
            ("BJ-018", "开放老旧社区3", ComplexityLevel.HARD, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-019", "开放老旧社区4", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
            ("BJ-020", "开放老旧社区5", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
        ],
        CaseCategory.ROAD_SPLIT: [
            ("BJ-021", "道路切割社区1", ComplexityLevel.HARD, GeographyRegion.CORE_URBAN, EvidenceDensity.MEDIUM),
            ("BJ-022", "道路切割社区2", ComplexityLevel.HARD, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-023", "道路切割社区3", ComplexityLevel.EXTREME, GeographyRegion.SUBURBAN, EvidenceDensity.LOW),
            ("BJ-024", "道路切割社区4", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
            ("BJ-025", "道路切割社区5", ComplexityLevel.EXTREME, GeographyRegion.REMOTE_NEW_TOWN, EvidenceDensity.LOW),
        ],
        CaseCategory.MIXED_USE: [
            ("BJ-026", "商住混合1", ComplexityLevel.HARD, GeographyRegion.CORE_URBAN, EvidenceDensity.MEDIUM),
            ("BJ-027", "商住混合2", ComplexityLevel.HARD, GeographyRegion.SUBURBAN, EvidenceDensity.MEDIUM),
            ("BJ-028", "商住混合3", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
            ("BJ-029", "商住混合4", ComplexityLevel.EXTREME, GeographyRegion.URBAN_FRINGE, EvidenceDensity.LOW),
            ("BJ-030", "商住混合5", ComplexityLevel.EXTREME, GeographyRegion.REMOTE_NEW_TOWN, EvidenceDensity.LOW),
        ],
    }
    for category, entries in category_map.items():
        for case_id, name, complexity, geography, evidence in entries:
            cases.append(BenchmarkCase(
                case_id=case_id, name=name, category=category,
                complexity=complexity, geography=geography,
                evidence_density=evidence,
            ))
    return cases