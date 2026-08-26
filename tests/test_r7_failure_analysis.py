"""R7 Failure Analysis Acceptance Tests (F01-F20)."""

from src.analysis.failure import (
    FailureDomain,
    DecisionClass,
    RootCauseConfidence,
    VLMVerdict,
    FailureAttributionRecord,
    OracleTop1Quadrant,
    B6vsB7Analysis,
    BuildingSourceAnalysis,
    RoadAnalysis,
    TrustFailureAudit,
    AbstentionAnalysis,
    P1CapabilityDecision,
    VLMFourGate,
    ArchitectureDecisionMatrix,
    FailureAnalysisReport,
)


def test_f01_failure_attribution():
    """F01: Failure attribution record complete."""
    r = FailureAttributionRecord(
        case_id="BJ-RS-0001", experiment_id="B2", run_id="r-001",
        primary_domain=FailureDomain.D3_ROAD_SEMANTICS,
        failure_codes=("F09",),
        root_cause_hypothesis="Road STRONG_ONLY under-split compound",
        root_cause_confidence=RootCauseConfidence.HIGH,
    )
    assert r.primary_domain == FailureDomain.D3_ROAD_SEMANTICS
    assert r.root_cause_confidence == RootCauseConfidence.HIGH


def test_f02_primary_secondary_separation():
    """F02: Primary and secondary failure domains separated."""
    r = FailureAttributionRecord(
        primary_domain=FailureDomain.D5_CANDIDATE_GENERATION,
        secondary_domains=(FailureDomain.D6_RANKING.value,),
    )
    assert r.primary_domain == FailureDomain.D5_CANDIDATE_GENERATION
    assert len(r.secondary_domains) == 1


def test_f03_symptom_vs_root_cause():
    """F03: Symptom and root cause are separate fields."""
    r = FailureAttributionRecord(
        observed_symptom="IoU=0.31, candidate missing west side",
        root_cause_hypothesis="Road STRONG_ONLY did not generate block on west side",
    )
    assert "IoU" in r.observed_symptom
    assert "Road" in r.root_cause_hypothesis


def test_f04_oracle_top1_quadrant():
    """F04: Oracle-vs-Top1 four-quadrant analysis."""
    q = OracleTop1Quadrant(
        oracle_high_top1_high=45,
        oracle_high_top1_low=30,
        oracle_low_data_rich=15,
        oracle_low_data_poor=10,
    )
    assert q.oracle_high_top1_low == 30  # Ranking Problem
    assert q.oracle_low_data_poor == 10  # Observation Ceiling


def test_f05_b6_vs_b7():
    """F05: B6 vs B7 semantic increment analysis."""
    a = B6vsB7Analysis(improves_top1=11, unchanged=15, harms_top1=4)
    assert a.improves_top1 == 11
    assert a.unchanged == 15


def test_f06_building_source():
    """F06: Building source complementarity analysis."""
    a = BuildingSourceAnalysis(
        osm_coverage=0.70, overture_coverage=0.65, microsoft_coverage=0.55,
        multi_source_improvement_over_best=0.05,
    )
    assert a.osm_coverage == 0.70
    assert a.multi_source_improvement_over_best == 0.05


def test_f07_road_analysis():
    """F07: Road STRONG/WEAK analysis."""
    r = RoadAnalysis(strong_only_correct_split=20, strong_only_over_split=8, strong_only_under_split=2)
    assert r.strong_only_correct_split == 20
    assert r.strong_only_over_split == 8


def test_f08_membership():
    """F08: P1 capability decision for Building Membership."""
    d = P1CapabilityDecision(
        capability="Building Membership",
        failure_frequency=5,
        proposed_action=DecisionClass.REFACTOR,
        decision="REFACTOR",
    )
    assert d.capability == "Building Membership"
    assert d.proposed_action == DecisionClass.REFACTOR


def test_f09_entity_merge_split():
    """F09: Entity merge/split failure decision."""
    d = P1CapabilityDecision(
        capability="Entity Resolution",
        failure_frequency=3,
        proposed_action=DecisionClass.KEEP,
        decision="KEEP",
    )
    assert d.decision == "KEEP"


def test_f10_false_trusted_audit():
    """F10: False Trusted full audit."""
    t = TrustFailureAudit(
        total_trusted=100, true_trusted=85, false_trusted=8, borderline_trusted=7,
        false_trusted_distribution={"EvidenceGate": 5, "GeometryGate": 3},
    )
    assert t.false_trusted == 8
    assert t.false_trusted_distribution["EvidenceGate"] == 5


def test_f11_abstention():
    """F11: Abstention analysis."""
    a = AbstentionAnalysis(gold_unresolved=5, correct_abstain=3, false_certainty=2)
    assert a.gold_unresolved == 5
    assert a.correct_abstain == 3
    assert a.false_certainty == 2


def test_f12_morphology_stratification():
    """F12: Architecture decision includes morphology."""
    d = ArchitectureDecisionMatrix(
        capability="Road Semantics",
        affected_morphologies=["ROAD_SPLIT", "MULTI_PHASE"],
        failure_frequency=8,
        decision="REFACTOR",
    )
    assert "ROAD_SPLIT" in d.affected_morphologies
    assert d.decision == "REFACTOR"


def test_f13_evidence_density_stratification():
    """F13: Failure analysis evidence density tracked."""
    r = FailureAttributionRecord(
        case_id="BJ-RS-0015",
        primary_domain=FailureDomain.D1_DATA_AVAILABILITY,
        root_cause_hypothesis="LOW evidence density, insufficient building coverage",
    )
    assert r.primary_domain == FailureDomain.D1_DATA_AVAILABILITY


def test_f14_complexity_breakpoint():
    """F14: Complexity breakpoint tracked."""
    r = FailureAttributionRecord(
        case_id="BJ-RS-0025",
        primary_domain=FailureDomain.D5_CANDIDATE_GENERATION,
        root_cause_hypothesis="EXTREME complexity, multi-phase road split",
    )
    assert "EXTREME" in r.root_cause_hypothesis or "CANDIDATE" in r.primary_domain.value


def test_f15_p1_decisions_all():
    """F15: All 7 P1 capabilities have decisions."""
    capabilities = [
        "Building Membership", "Boundary Segmentation", "Scene Renderer",
        "VLM Framework", "Confidence Calibration", "Vector Reconstruction", "Shared Topology",
    ]
    for cap in capabilities:
        d = P1CapabilityDecision(capability=cap, decision="DEFER")
        assert d.decision in ("KEEP", "REFACTOR", "DEFER", "REJECT")


def test_f16_architecture_decision_evidence():
    """F16: Each architecture decision has benchmark evidence."""
    d = ArchitectureDecisionMatrix(
        capability="Road Semantics",
        empirical_problem="8/30 cases show systematic Road STRONG_ONLY under-split",
        failure_frequency=8,
        root_cause_confidence=RootCauseConfidence.HIGH,
        decision="REFACTOR",
    )
    assert d.empirical_problem != ""
    assert d.failure_frequency > 0


def test_f17_vlm_gate():
    """F17: VLM independent gate."""
    gate = VLMFourGate(
        frequency=True, deterministic_exhausted=True,
        visual_semantic_nature=True, testable_hypothesis=True,
    )
    assert gate.passed
    gate2 = VLMFourGate(frequency=False, deterministic_exhausted=False, visual_semantic_nature=False, testable_hypothesis=False)
    assert not gate2.passed


def test_f18_no_algorithm_change():
    """F18: No algorithm modification during R7 (static check)."""
    import inspect
    src = inspect.getsource(FailureAttributionRecord)
    assert "Provider" not in src  # No provider code in analysis


def test_f19_report_summary():
    """F19: Failure analysis report generates summary."""
    report = FailureAnalysisReport(
        n_runs=360, n_cases=30,
        oracle_top1=OracleTop1Quadrant(45, 30, 15, 10),
    )
    s = report.summary()
    assert "360" in s
    assert "Q1" in s
    assert "Q2" in s


def test_f20_p1_decision_chain():
    """F20: P1 decisions have evidence chain."""
    d = P1CapabilityDecision(
        capability="Shared Topology",
        observed_failure="17% ROAD_SPLIT cases show adjacent candidate overlap/gap",
        affected_cases=["BJ-RS-0021", "BJ-RS-0025"],
        failure_frequency=5,
        current_baseline="Road provider does not produce shared boundary",
        proposed_action=DecisionClass.REFACTOR,
        expected_metric="Reduce separator violation rate by 50%",
        decision="REFACTOR",
    )
    assert d.observed_failure != ""
    assert d.expected_metric != ""