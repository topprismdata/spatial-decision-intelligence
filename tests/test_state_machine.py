"""
Tests for the World-Model Verified State Machine (src/domain/state_machine.py)
and its integration in the orchestrator.

Covers the four formal invariants:
  INV-1 legality      - only table-listed transitions occur.
  INV-2 chain integrity - append-only hash chain detects any tampering.
  INV-3 publish gate  - PUBLISHED requires a complete evidence chain.
  INV-4 replayability - re-execution reproduces recorded digests exactly.
"""

import pytest

from src.domain.state_machine import (
    ChainIntegrityError,
    IllegalTransitionError,
    LiveClock,
    PublishGateError,
    ReplayClock,
    ReplayMismatchError,
    RunState,
    Transition,
    TransitionLog,
    artifact_digest,
)
from src.agents.orchestrator import SpatialIntelligencePlatform


BRIEF_OK = {
    "name": "龙泽苑西区",
    "address": "北京市昌平区回龙观",
    "lng": 116.321,
    "lat": 40.075,
}
# 2 km² prior -> generated circle area exceeds the guard's 800,000 m² cap
# -> AREA_TOO_LARGE -> no fallback -> REJECTED_UNRECOVERABLE (fail-closed).
BRIEF_OVERSIZED = {
    "name": "巨型假想地块",
    "address": "北京市昌平区",
    "lng": 116.35,
    "lat": 40.08,
    "prior_area_m2": 2_000_000,
}

# Key translation for the batch surface, which reads "area_m2".
BRIEF_OVERSIZED_BATCH = dict(BRIEF_OVERSIZED, area_m2=BRIEF_OVERSIZED["prior_area_m2"])


@pytest.fixture(scope="module")
def platform() -> SpatialIntelligencePlatform:
    return SpatialIntelligencePlatform()


# ---------------------------------------------------------------------------
# Happy path: full chain, publish gate satisfied by construction.
# ---------------------------------------------------------------------------

def test_publish_path_full_chain(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    log = res.transition_log
    assert log is not None
    assert log.state is RunState.PUBLISHED

    transitions = [ev.transition for ev in log.events]
    assert transitions == [
        Transition.RESOLVE,
        Transition.REASON,
        Transition.GENERATE,
        Transition.AUDIT,
        Transition.PUBLISH,
    ]
    assert len(log.events) == 5

    # INV-2: chain verifies end to end.
    log.verify_chain()

    # INV-3: the publish event carries a complete evidence chain.
    publish_ev = log.events[-1]
    assert publish_ev.evidence_refs, "publish must carry evidence refs"
    assert any(r.startswith("OBS:") for r in publish_ev.evidence_refs)
    assert any(r.startswith("QA:") for r in publish_ev.evidence_refs)


def test_fail_closed_path_never_published(platform):
    res = platform.generate_single_fence(**BRIEF_OVERSIZED)
    log = res.transition_log
    assert log is not None
    assert log.state is RunState.REJECTED
    assert log.events[-1].transition is Transition.FAIL_CLOSE
    assert res.qa_audit.entity.is_decision_ready is False
    # Chain still complete and verifiable on the rejection path.
    log.verify_chain()


def test_batch_excludes_fail_closed_runs(platform):
    state = platform.batch_generate_and_govern([BRIEF_OK, BRIEF_OVERSIZED_BATCH])
    names = [e.canonical_name for e in state.entities.values()]
    assert any("龙泽苑" in n for n in names)  # resolver may normalize spacing
    assert all(n != "巨型假想地块" for n in names)


# ---------------------------------------------------------------------------
# INV-1: legality.
# ---------------------------------------------------------------------------

def test_inv1_illegal_transition_from_start():
    log = TransitionLog("RUN_TEST")
    with pytest.raises(IllegalTransitionError):
        log.append(
            transition=Transition.GENERATE,  # skip resolve+reason: illegal
            agent="GeometryGenerationAgent",
            to_state=RunState.HYPOTHESES_GENERATED,
        )


def test_inv1_no_transitions_after_terminal(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    log = res.transition_log
    assert log.state in (RunState.PUBLISHED, RunState.REJECTED)
    with pytest.raises(IllegalTransitionError):
        log.append(
            transition=Transition.RESOLVE,
            agent="EntityResolutionAgent",
            to_state=RunState.ENTITY_RESOLVED,
        )


def test_inv1_illegal_target_rejected():
    log = TransitionLog("RUN_TEST")
    log.append(transition=Transition.RESOLVE, agent="EntityResolutionAgent",
               to_state=RunState.ENTITY_RESOLVED)
    # REASON from ENTITY_RESOLVED may only target CONSTRAINTS_REASONED.
    with pytest.raises(IllegalTransitionError):
        log.append(transition=Transition.REASON, agent="BoundaryReasoningAgent",
                   to_state=RunState.QA_PASSED)


# ---------------------------------------------------------------------------
# INV-2: tamper-evident chain.
# ---------------------------------------------------------------------------

def test_inv2_tampered_payload_detected(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    records = res.transition_log.to_records()

    # Tamper with a payload metric deep in the chain.
    tampered = [dict(r) for r in records]
    tampered[2]["payload"] = dict(tampered[2]["payload"])
    tampered[2]["payload"]["area_m2"] = 42.0  # falsified metric

    with pytest.raises(ChainIntegrityError):
        TransitionLog.from_records(tampered)


def test_inv2_tampered_hash_link_detected(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    tampered = [dict(r) for r in res.transition_log.to_records()]
    tampered[3]["prev_event_hash"] = "0" * 64

    with pytest.raises(ChainIntegrityError):
        TransitionLog.from_records(tampered)


def test_inv2_rehydration_preserves_verifiability(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    records = res.transition_log.to_records()
    reborn = TransitionLog.from_records(records)
    reborn.verify_chain()  # no exception
    assert reborn.state is RunState.PUBLISHED
    assert [e.event_hash for e in reborn.events] == [
        e.event_hash for e in res.transition_log.events
    ]


# ---------------------------------------------------------------------------
# INV-3: publish gate.
# ---------------------------------------------------------------------------

def test_inv3_publish_requires_evidence_refs(platform):
    res = platform.generate_single_fence(**BRIEF_OK)
    log = res.transition_log
    # Rebuild a log parked at QA_PASSED: replay every event in order,
    # stopping after AUDIT (governance events are dropped).
    parked = TransitionLog(log.run_id)
    for ev in log.events:
        parked.append(
            transition=ev.transition,
            agent=ev.agent,
            to_state=ev.to_state,
            inputs_digest=ev.inputs_digest,
            outputs_digest=ev.outputs_digest,
            evidence_refs=ev.evidence_refs,
            payload=ev.payload,
            clock=ev.occurred_at,
        )
        if ev.to_state is RunState.QA_PASSED:
            break
    assert parked.state is RunState.QA_PASSED
    with pytest.raises(PublishGateError):
        parked.append(
            transition=Transition.PUBLISH,
            agent="Governor",
            to_state=RunState.PUBLISHED,
            evidence_refs=(),  # no evidence: must be refused
            outputs_digest="abc",
        )


def test_inv3_publish_requires_outputs_digest():
    # Drive a minimal legal chain to QA_PASSED directly at FSM level.
    log = TransitionLog("RUN_FSM")
    log.append(transition=Transition.RESOLVE, agent="A1", to_state=RunState.ENTITY_RESOLVED)
    log.append(transition=Transition.REASON, agent="A2", to_state=RunState.CONSTRAINTS_REASONED)
    log.append(transition=Transition.GENERATE, agent="A3", to_state=RunState.HYPOTHESES_GENERATED)
    log.append(transition=Transition.AUDIT, agent="A4", to_state=RunState.QA_PASSED,
               evidence_refs=("OBS:x",))
    with pytest.raises(PublishGateError):
        log.append(transition=Transition.PUBLISH, agent="Governor",
                   to_state=RunState.PUBLISHED,
                   evidence_refs=("OBS:x",), outputs_digest="")


# ---------------------------------------------------------------------------
# INV-4: determinism and replay.
# ---------------------------------------------------------------------------

def test_inv4_identical_runs_produce_identical_chains(platform):
    res1 = platform.generate_single_fence(**BRIEF_OK)
    res2 = platform.generate_single_fence(**BRIEF_OK)
    hashes1 = [e.event_hash for e in res1.transition_log.events]
    hashes2 = [e.event_hash for e in res2.transition_log.events]
    assert hashes1 == hashes2, "wall-clock must not enter the chain"
    # occurred_at may differ; digests must not.
    at1 = [e.occurred_at for e in res1.transition_log.events]
    at2 = [e.occurred_at for e in res2.transition_log.events]
    assert at1 != at2  # LiveClock ticks; proves time is recorded but not hashed


def test_inv4_replay_against_recorded_chain(platform):
    recorded_res = platform.generate_single_fence(**BRIEF_OK)
    replay_res = platform.generate_single_fence(**BRIEF_OK,
                                                recorded=recorded_res.transition_log)
    assert replay_res.transition_log.state is RunState.PUBLISHED
    assert [e.event_hash for e in replay_res.transition_log.events] == [
        e.event_hash for e in recorded_res.transition_log.events
    ]


def test_inv4_replay_detects_input_divergence(platform):
    recorded_res = platform.generate_single_fence(**BRIEF_OK)
    drifted = dict(BRIEF_OK, lng=BRIEF_OK["lng"] + 0.01)  # different input
    with pytest.raises(ReplayMismatchError):
        platform.generate_single_fence(**drifted, recorded=recorded_res.transition_log)


def test_inv4_replay_clock_reproduces_artifacts(platform):
    first = platform.generate_single_fence(**BRIEF_OK)
    ats = [e.occurred_at for e in first.transition_log.events]
    state_version = "2026.08.27.v1"

    replay_platform = SpatialIntelligencePlatform(
        clock=ReplayClock(ats, state_version)
    )
    second = replay_platform.generate_single_fence(**BRIEF_OK)

    # Same digests, same recorded times, deterministic batch metadata.
    assert [e.event_hash for e in second.transition_log.events] == [
        e.event_hash for e in first.transition_log.events
    ]
    state = replay_platform.batch_generate_and_govern([BRIEF_OK])
    assert state.state_version == state_version
    # published_at is the tick AFTER the 5 events; ReplayClock clamps to the
    # last recorded timestamp once the list is exhausted.
    assert state.published_at == ats[-1]


# ---------------------------------------------------------------------------
# Digest hygiene: wall-clock stripping.
# ---------------------------------------------------------------------------

def test_strip_clock_removes_temporal_fields():
    artifact = {
        "finding_id": "F1",
        "created_at": "2026-01-01T00:00:00",
        "metrics": {"qa_score": 0.9, "observed_at": "NOW"},
        "nested": [{"published_at": "x", "keep": 1}],
    }
    d1 = artifact_digest(artifact)
    d2 = artifact_digest(dict(artifact, created_at="2099-12-31T23:59:59"))
    assert d1 == d2, "timestamp changes must not change the digest"
    assert artifact_digest(dict(artifact, metrics={"qa_score": 0.8})) != d1


def test_run_id_binds_to_inputs(platform):
    r1 = platform.generate_single_fence(**BRIEF_OK)
    r2 = platform.generate_single_fence(
        name=BRIEF_OK["name"], address=BRIEF_OK["address"],
        lng=BRIEF_OK["lng"] + 0.5, lat=BRIEF_OK["lat"],
    )
    assert r1.transition_log.run_id != r2.transition_log.run_id
