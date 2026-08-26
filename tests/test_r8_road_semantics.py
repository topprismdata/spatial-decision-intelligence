"""R8 Road Semantic Experiment tests: contract, interpreters, ranking adapter, experiment runner."""

from src.road_semantics import (
    RoadRole,
    RoadContinuity,
    CompoundSplitSupport,
    Producer,
    RoadSemanticAssertion,
    VLMExperimentManifest,
)
from src.road_semantics.deterministic import DeterministicRoadInterpreter
from src.road_semantics.vlm import VLMRoadInterpreter
from src.road_semantics.ranking import RoadSemanticRankingAdapter
from src.road_semantics.experiment import R8ExperimentRunner, R8ExperimentResult, ArmResult


def test_contract_road_semantic_assertion():
    """RoadSemanticAssertion is the common contract for B8-D and B8-V."""
    a = RoadSemanticAssertion(
        road_segment_id="road_1",
        road_role=RoadRole.PUBLIC_SEPARATOR,
        continuity=RoadContinuity.THROUGH,
        compound_split_support=CompoundSplitSupport.SUPPORT,
        producer=Producer.DETERMINISTIC,
    )
    assert a.road_role == RoadRole.PUBLIC_SEPARATOR
    assert a.continuity == RoadContinuity.THROUGH
    assert a.producer == Producer.DETERMINISTIC


def test_deterministic_interpreter():
    """B8-D: Deterministic interpreter produces RoadSemanticAssertion."""
    interp = DeterministicRoadInterpreter()
    road_wkt = "LINESTRING(116.44 39.87, 116.46 39.89)"
    result = interp.interpret(road_wkt, "primary", [], [])
    assert isinstance(result, RoadSemanticAssertion)
    assert result.producer == Producer.DETERMINISTIC
    assert result.road_role in (RoadRole.PUBLIC_SEPARATOR, RoadRole.WEAK_SEPARATOR, RoadRole.AMBIGUOUS)


def test_vlm_interpreter():
    """B8-V: VLM interpreter produces RoadSemanticAssertion list."""
    interp = VLMRoadInterpreter()
    results = interp.interpret("<svg>mock</svg>", ["road_1", "road_2"])
    assert len(results) >= 1
    for r in results:
        assert isinstance(r, RoadSemanticAssertion)
        assert r.producer == Producer.VLM


def test_vlm_manifest():
    """VLMExperimentManifest is frozen before execution."""
    m = VLMExperimentManifest(
        model_name="gpt-4o",
        model_version="2026-08",
        temperature=0.0,
        seed=42,
    )
    assert m.model_name == "gpt-4o"
    assert m.temperature == 0.0


def test_ranking_adapter_accepts_both():
    """Common Ranking Adapter accepts assertions from both B8-D and B8-V."""
    adapter = RoadSemanticRankingAdapter()
    det_assertions = [
        RoadSemanticAssertion(road_segment_id="r1", road_role=RoadRole.PUBLIC_SEPARATOR, producer=Producer.DETERMINISTIC),
        RoadSemanticAssertion(road_segment_id="r2", road_role=RoadRole.INTERNAL_ACCESS, producer=Producer.DETERMINISTIC),
    ]
    vlm_assertions = [
        RoadSemanticAssertion(road_segment_id="r1", road_role=RoadRole.PUBLIC_SEPARATOR, producer=Producer.VLM),
        RoadSemanticAssertion(road_segment_id="r2", road_role=RoadRole.INTERNAL_ACCESS, producer=Producer.VLM),
    ]
    from src.domain.contracts import BoundaryHypothesis, HypothesisStatus
    hyps = [
        BoundaryHypothesis(entity_id="test", geometry="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", status=HypothesisStatus.PROPOSED),
    ]
    det_ranked = adapter.rank(hyps, det_assertions)
    vlm_ranked = adapter.rank(hyps, vlm_assertions)
    assert len(det_ranked) == 1
    assert len(vlm_ranked) == 1


def test_experiment_runner():
    """R8 experiment runner executes 3 arms on 5 ROAD_SPLIT cases."""
    runner = R8ExperimentRunner()
    result = runner.run_all()
    assert len(result.case_results) == 15  # 5 cases × 3 arms
    assert len(result.by_arm) == 3  # B6, B8-D, B8-V
    for arm in ["B6", "B8-D", "B8-V"]:
        assert arm in result.by_arm
        assert len(result.by_arm[arm]) == 5


def test_arm_result():
    """ArmResult tracks all required metrics."""
    r = ArmResult(arm="B8-D", case_id="BJ-RS-0021", top1_quality=0.85, oracle_quality=0.92, ranking_regret=0.07)
    assert r.arm == "B8-D"
    assert r.ranking_regret == 0.07


def test_false_trusted_safety_gate():
    """Safety gate: FalseTrusted must remain 0."""
    runner = R8ExperimentRunner()
    result = runner.run_all()
    for case in result.case_results:
        assert not case.false_trusted, f"FalseTrusted in {case.arm}/{case.case_id}"