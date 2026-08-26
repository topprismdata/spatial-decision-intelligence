"""R7 Failure Analysis: root cause attribution, Oracle-vs-Top1, P1 review, VLM Gate.

Design Note v1.0 §§1-26.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FailureDomain(str, Enum):
    D1_DATA_AVAILABILITY = "D1_DATA_AVAILABILITY"
    D2_ENTITY_RESOLUTION = "D2_ENTITY_RESOLUTION"
    D3_ROAD_SEMANTICS = "D3_ROAD_SEMANTICS"
    D4_BUILDING_MEMBERSHIP = "D4_BUILDING_MEMBERSHIP"
    D5_CANDIDATE_GENERATION = "D5_CANDIDATE_GENERATION"
    D6_RANKING = "D6_RANKING"
    D7_EVIDENCE_VALIDATION = "D7_EVIDENCE_VALIDATION"
    D8_OBSERVATION_CEILING = "D8_OBSERVATION_CEILING"


class RootCauseConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DecisionClass(str, Enum):
    KEEP = "KEEP"
    REFACTOR = "REFACTOR"
    ADD = "ADD"
    DEFER = "DEFER"
    REJECT = "REJECT"


class VLMVerdict(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"
    ELIGIBLE_FOR_B8 = "ELIGIBLE_FOR_B8"


@dataclass
class FailureAttributionRecord:
    case_id: str = ""
    experiment_id: str = ""
    run_id: str = ""
    primary_domain: FailureDomain = FailureDomain.D8_OBSERVATION_CEILING
    secondary_domains: tuple[str, ...] = ()
    failure_codes: tuple[str, ...] = ()
    observed_symptom: str = ""
    gold_reference: str = ""
    metric_evidence: str = ""
    source_evidence: str = ""
    root_cause_hypothesis: str = ""
    root_cause_confidence: RootCauseConfidence = RootCauseConfidence.LOW
    actionability: str = ""


@dataclass
class OracleTop1Quadrant:
    oracle_high_top1_high: int = 0  # Q1: Healthy
    oracle_high_top1_low: int = 0  # Q2: Ranking Problem
    oracle_low_data_rich: int = 0  # Q3: Reconstruction Failure
    oracle_low_data_poor: int = 0  # Q4: Observation Ceiling


@dataclass
class B6vsB7Analysis:
    improves_top1: int = 0
    unchanged: int = 0
    harms_top1: int = 0
    by_morphology: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class BuildingSourceAnalysis:
    osm_coverage: float = 0.0
    overture_coverage: float = 0.0
    microsoft_coverage: float = 0.0
    osm_oracle_quality: float = 0.0
    overture_oracle_quality: float = 0.0
    microsoft_oracle_quality: float = 0.0
    multi_source_improvement_over_best: float = 0.0


@dataclass
class RoadAnalysis:
    strong_only_correct_split: int = 0
    strong_only_over_split: int = 0
    strong_only_under_split: int = 0
    strong_plus_weak_correct: int = 0
    strong_plus_weak_over_split: int = 0
    strong_plus_weak_under_split: int = 0


@dataclass
class TrustFailureAudit:
    total_trusted: int = 0
    true_trusted: int = 0
    false_trusted: int = 0
    borderline_trusted: int = 0
    false_trusted_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class AbstentionAnalysis:
    gold_unresolved: int = 0
    correct_abstain: int = 0
    false_certainty: int = 0
    gold_resolved: int = 0
    unnecessary_abstain: int = 0


@dataclass
class P1CapabilityDecision:
    capability: str = ""
    observed_failure: str = ""
    affected_cases: list[str] = field(default_factory=list)
    affected_morphologies: list[str] = field(default_factory=list)
    failure_frequency: int = 0
    current_baseline: str = ""
    root_cause_confidence: RootCauseConfidence = RootCauseConfidence.LOW
    proposed_action: DecisionClass = DecisionClass.DEFER
    expected_metric: str = ""
    decision: str = "DEFER"


@dataclass
class VLMFourGate:
    frequency: bool = False
    deterministic_exhausted: bool = False
    visual_semantic_nature: bool = False
    testable_hypothesis: bool = False

    @property
    def passed(self) -> bool:
        return all([self.frequency, self.deterministic_exhausted, self.visual_semantic_nature, self.testable_hypothesis])


@dataclass
class ArchitectureDecisionMatrix:
    capability: str = ""
    empirical_problem: str = ""
    affected_cases: list[str] = field(default_factory=list)
    affected_morphologies: list[str] = field(default_factory=list)
    failure_frequency: int = 0
    current_baseline: str = ""
    root_cause_confidence: RootCauseConfidence = RootCauseConfidence.LOW
    proposed_action: DecisionClass = DecisionClass.DEFER
    expected_metric: str = ""
    decision: str = "DEFER"


@dataclass
class FailureAnalysisReport:
    n_runs: int = 0
    n_cases: int = 0
    records: list[FailureAttributionRecord] = field(default_factory=list)
    oracle_top1: OracleTop1Quadrant = field(default_factory=OracleTop1Quadrant)
    b6_vs_b7: B6vsB7Analysis = field(default_factory=B6vsB7Analysis)
    building_source: BuildingSourceAnalysis = field(default_factory=BuildingSourceAnalysis)
    road: RoadAnalysis = field(default_factory=RoadAnalysis)
    trust: TrustFailureAudit = field(default_factory=TrustFailureAudit)
    abstention: AbstentionAnalysis = field(default_factory=AbstentionAnalysis)
    p1_decisions: list[P1CapabilityDecision] = field(default_factory=list)
    vlm_gate: VLMFourGate = field(default_factory=VLMFourGate)
    architecture_decisions: list[ArchitectureDecisionMatrix] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"=== R7 Failure Analysis Report ===\n"
            f"  Runs Analyzed: {self.n_runs}\n"
            f"  Q1 Healthy: {self.oracle_top1.oracle_high_top1_high}\n"
            f"  Q2 Ranking Problem: {self.oracle_top1.oracle_high_top1_low}\n"
            f"  Q3 Reconstruction Failure: {self.oracle_top1.oracle_low_data_rich}\n"
            f"  Q4 Observation Ceiling: {self.oracle_top1.oracle_low_data_poor}\n"
            f"  False Trusted: {self.trust.false_trusted}\n"
            f"  P1 Decisions: {len(self.p1_decisions)} capabilities\n"
            f"  VLM Gate: {'PASS' if self.vlm_gate.passed else 'NOT_PASSED'}\n"
        )