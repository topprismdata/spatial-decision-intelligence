"""P0-10 / v1.0 Baseline Experiment Matrix (B0-B9), Ablation (A1-A5), Failure Taxonomy (F01-F20).

Each experiment must report its incremental value over the previous baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ExperimentID(str, Enum):
    """Eight baseline experiments (B0-B9) + five ablation experiments (A1-A5)."""

    B0 = "B0"  # Point + Area Prior
    B1 = "B1"  # Existing Open Polygon
    B2 = "B2"  # Road only
    B3 = "B3"  # Building only
    B4 = "B4"  # Road + Building
    B5 = "B5"  # Multi-source Buildings
    B6 = "B6"  # Open Vector Fusion
    B7 = "B7"  # + Semantic Public Data
    B8 = "B8"  # + VLM (only after P1 start)
    B9 = "B9"  # Minimal World Model (+ Evidence Validation, Trust Calibration, Abstention)
    A1 = "A1"  # Full System - Road
    A2 = "A2"  # Full System - Building
    A3 = "A3"  # Full System - Semantic Evidence
    A4 = "A4"  # Full System - Multi-source Fusion
    A5 = "A5"  # Full System - VLM


@dataclass
class ExperimentResult:
    experiment_id: ExperimentID
    accuracy: float = 0.0
    trusted_coverage: float = 0.0
    false_trusted_rate: float = 0.0
    incremental_data: str = ""
    resolved_cases: list[str] = field(default_factory=list)
    new_errors: list[str] = field(default_factory=list)
    incremental_cost: str = ""


@dataclass
class CategoryBreakdown:
    modern_gated: float = 0.0
    multi_phase: float = 0.0
    danwei_courtyard: float = 0.0
    old_open: float = 0.0
    road_split: float = 0.0
    mixed_use: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "Modern Gated": self.modern_gated,
            "Multi-phase": self.multi_phase,
            "Danwei Courtyard": self.danwei_courtyard,
            "Old Open": self.old_open,
            "Road-split": self.road_split,
            "Mixed-use": self.mixed_use,
        }


# ── Accuracy-Coverage Curve (v1.0 spec section 24.3) ─────────────────────────


@dataclass
class AccuracyCoveragePoint:
    """A single point on the accuracy-coverage curve."""
    trust_threshold: float
    accuracy: float
    coverage: float


@dataclass
class AccuracyCoverageCurve:
    """Accuracy-Coverage curve at multiple trust thresholds."""
    points: list[AccuracyCoveragePoint] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["Accuracy-Coverage Curve:"]
        for p in self.points:
            lines.append(f"  >= {p.trust_threshold:.0%} confidence: "
                         f"accuracy={p.accuracy:.1%}, coverage={p.coverage:.1%}")
        return "\n".join(lines)


# ── Source Complementarity Matrix (v1.0 spec section 28) ──────────────────────


@dataclass
class SourceComplementarityEntry:
    """Single entry in the source complementarity matrix."""
    entity_recall: float = 0.0
    building_coverage: float = 0.0
    road_coverage: float = 0.0
    boundary_coverage: float = 0.0
    semantic_coverage: float = 0.0


@dataclass
class SourceComplementarityMatrix:
    """Source complementarity matrix (v1.0 spec section 28)."""
    osm: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)
    overture: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)
    microsoft: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)
    osm_overture: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)
    osm_microsoft: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)
    full_open: SourceComplementarityEntry = field(default_factory=SourceComplementarityEntry)

    def summary(self) -> str:
        rows = [
            ("Source", "Entity", "Building", "Road", "Boundary", "Semantic"),
            ("OSM", self.osm.entity_recall, self.osm.building_coverage, self.osm.road_coverage, self.osm.boundary_coverage, self.osm.semantic_coverage),
            ("Overture", self.overture.entity_recall, self.overture.building_coverage, self.overture.road_coverage, self.overture.boundary_coverage, self.overture.semantic_coverage),
            ("Microsoft", self.microsoft.entity_recall, self.microsoft.building_coverage, "-", "-", "-"),
            ("OSM+Overture", self.osm_overture.entity_recall, self.osm_overture.building_coverage, self.osm_overture.road_coverage, self.osm_overture.boundary_coverage, self.osm_overture.semantic_coverage),
            ("OSM+MS", self.osm_microsoft.entity_recall, self.osm_microsoft.building_coverage, "-", "-", "-"),
            ("Full Open", self.full_open.entity_recall, self.full_open.building_coverage, self.full_open.road_coverage, self.full_open.boundary_coverage, self.full_open.semantic_coverage),
        ]
        lines = ["Source Complementarity Matrix:"]
        for row in rows:
            fmt = "  {:20s} " + " ".join(["{:>8.1%}" if isinstance(v, float) else "{:>8}" for v in row[1:]])
            lines.append(fmt.format(row[0], *row[1:]))
        return "\n".join(lines)


# ── Failure Taxonomy (F01-F20, v1.0 spec section 29) ─────────────────────────


class FailureCode(str, Enum):
    F01 = "F01"  # ENTITY_NOT_FOUND
    F02 = "F02"  # ENTITY_DUPLICATE
    F03 = "F03"  # ENTITY_FALSE_MERGE
    F04 = "F04"  # ENTITY_FALSE_SPLIT
    F05 = "F05"  # PHASE_COMPOUND_AMBIGUITY
    F06 = "F06"  # BUILDING_DATA_MISSING
    F07 = "F07"  # BUILDING_SOURCE_CONFLICT
    F08 = "F08"  # ROAD_DATA_MISSING
    F09 = "F09"  # ROAD_SEMANTIC_AMBIGUITY
    F10 = "F10"  # OPEN_BOUNDARY_MISSING
    F11 = "F11"  # MIXED_USE_CONTAMINATION
    F12 = "F12"  # SCHOOL_HOSPITAL_CONTAMINATION
    F13 = "F13"  # MULTIPLE_PLAUSIBLE_BOUNDARIES
    F14 = "F14"  # GEOMETRY_INVALID
    F15 = "F15"  # TOPOLOGY_CONFLICT
    F16 = "F16"  # EVIDENCE_INSUFFICIENT
    F17 = "F17"  # SOURCE_STALE
    F18 = "F18"  # SOURCE_DEPENDENCY
    F19 = "F19"  # HIGH_CONFIDENCE_WRONG
    F20 = "F20"  # GOLD_UNRESOLVED


FAILURE_DESCRIPTIONS = {
    FailureCode.F01: "Entity not found",
    FailureCode.F02: "Entity duplicate",
    FailureCode.F03: "Entity false merge",
    FailureCode.F04: "Entity false split",
    FailureCode.F05: "Phase/compound ambiguity",
    FailureCode.F06: "Building data missing",
    FailureCode.F07: "Building source conflict",
    FailureCode.F08: "Road data missing",
    FailureCode.F09: "Road semantic ambiguity",
    FailureCode.F10: "Open boundary missing",
    FailureCode.F11: "Mixed-use contamination",
    FailureCode.F12: "School/hospital contamination",
    FailureCode.F13: "Multiple plausible boundaries",
    FailureCode.F14: "Geometry invalid",
    FailureCode.F15: "Topology conflict",
    FailureCode.F16: "Evidence insufficient",
    FailureCode.F17: "Source stale",
    FailureCode.F18: "Source dependency (non-independent evidence)",
    FailureCode.F19: "High confidence but wrong",
    FailureCode.F20: "Gold unresolved",
}


@dataclass
class FailureRecord:
    case_id: str
    experiment_id: ExperimentID
    failure_code: FailureCode
    attribution: str = ""  # ErrorAttribution from spec section 30
    description: str = ""
    impact: str = ""


@dataclass
class FailureReport:
    total_cases: int = 0
    failures_by_code: dict[FailureCode, int] = field(default_factory=dict)
    failures_by_category: dict[str, int] = field(default_factory=dict)
    failures_by_attribution: dict[str, int] = field(default_factory=dict)
    records: list[FailureRecord] = field(default_factory=list)

    @property
    def top_failures(self) -> list[tuple[FailureCode, int]]:
        return sorted(self.failures_by_code.items(), key=lambda x: -x[1])

    def summary(self) -> str:
        lines = [f"=== Failure Report ({self.total_cases} cases) ==="]
        for code, count in self.top_failures:
            pct = count / max(self.total_cases, 1) * 100
            lines.append(f"  {code.value} {FAILURE_DESCRIPTIONS[code]:35s} {count:3d} ({pct:5.1f}%)")
        return "\n".join(lines)