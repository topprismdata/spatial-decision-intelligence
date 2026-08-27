"""
World-Model Verified State Machine (Proposal 5: Formal Container).

Formalizes the implicit 4-agent pipeline (resolve -> reason -> generate -> audit
-> publish) as an explicit finite state machine with:

  INV-1  Legality        - only transitions listed in TRANSITIONS may occur.
  INV-2  Chain integrity - append-only, hash-chained event log; tamper-evident.
  INV-3  Publish gate    - -> PUBLISHED requires non-empty evidence refs and
                           input/output digests. A TRUSTED (published) state
                           carries a complete evidence chain by construction.
  INV-4  Replayability   - deterministic re-execution must reproduce recorded
                           input/output digests. Wall-clock time is recorded on
                           events but NEVER enters digests or control flow.

The FSM is domain-agnostic: it knows states, transitions, digests, and hashes.
It holds no geometry, no ontology, and no agent references.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Tuple


class RunState(str, Enum):
    """States of a single entity reconstruction run."""

    BRIEF_RECEIVED = "BRIEF_RECEIVED"
    ENTITY_RESOLVED = "ENTITY_RESOLVED"            # after Agent 1
    CONSTRAINTS_REASONED = "CONSTRAINTS_REASONED"  # after Agent 2
    HYPOTHESES_GENERATED = "HYPOTHESES_GENERATED"  # after Agent 3
    QA_PASSED = "QA_PASSED"                        # after Agent 4 (approved)
    QA_REJECTED = "QA_REJECTED"                    # after Agent 4 (fail-closed)
    PUBLISHED = "PUBLISHED"                        # terminal: in TrustedSpatialState
    REJECTED = "REJECTED"                          # terminal: fail-closed, never published


class Transition(str, Enum):
    """Named transitions (one agent step or governance decision each)."""

    RESOLVE = "RESOLVE"          # Agent 1
    REASON = "REASON"            # Agent 2
    GENERATE = "GENERATE"        # Agent 3
    AUDIT = "AUDIT"              # Agent 4
    PUBLISH = "PUBLISH"          # governance: QA-passed -> world model
    FAIL_CLOSE = "FAIL_CLOSE"    # governance: QA-rejected -> terminal rejection


#: INV-1 legality table: (state, transition) -> allowed target states.
#: AUDIT has two targets, resolved by the runtime audit outcome.
TRANSITIONS: Dict[Tuple[RunState, Transition], FrozenSet[RunState]] = {
    (RunState.BRIEF_RECEIVED, Transition.RESOLVE): frozenset({RunState.ENTITY_RESOLVED}),
    (RunState.ENTITY_RESOLVED, Transition.REASON): frozenset({RunState.CONSTRAINTS_REASONED}),
    (RunState.CONSTRAINTS_REASONED, Transition.GENERATE): frozenset({RunState.HYPOTHESES_GENERATED}),
    (RunState.HYPOTHESES_GENERATED, Transition.AUDIT): frozenset({
        RunState.QA_PASSED,
        RunState.QA_REJECTED,
    }),
    (RunState.QA_PASSED, Transition.PUBLISH): frozenset({RunState.PUBLISHED}),
    (RunState.QA_REJECTED, Transition.FAIL_CLOSE): frozenset({RunState.REJECTED}),
}

#: Validation statuses an audit may emit for the run to count as approved.
APPROVED_STATUSES = frozenset({"VERIFIED_VALID", "REPAIRED_AUTO"})

#: Terminal states - no outgoing transitions by construction.
TERMINAL_STATES = frozenset({RunState.PUBLISHED, RunState.REJECTED})


class StateMachineError(Exception):
    """Base class for FSM violations."""


class IllegalTransitionError(StateMachineError):
    """INV-1 violation: transition not permitted from the current state."""


class ChainIntegrityError(StateMachineError):
    """INV-2 violation: event hash chain broken or tampered."""


class PublishGateError(StateMachineError):
    """INV-3 violation: publish attempted without a complete evidence chain."""


class ReplayMismatchError(StateMachineError):
    """INV-4 violation: re-execution digests differ from recorded digests."""


# ---------------------------------------------------------------------------
# Canonical digests: stable across processes; wall-clock never enters.
# ---------------------------------------------------------------------------

CLOCK_FIELDS = frozenset({
    "created_at", "published_at", "observed_at", "occurred_at",
    "state_version", "disposed_at",
})


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialization (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(obj: Any) -> str:
    """SHA-256 over canonical JSON of computation-relevant data only."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def strip_clock(obj: Any) -> Any:
    """Recursively remove wall-clock fields so artifacts that embed timestamps
    (QualityFinding.created_at, GeometryObservation.observed_at, ...) digest
    deterministically."""
    if isinstance(obj, dict):
        return {
            k: strip_clock(v)
            for k, v in obj.items()
            if k not in CLOCK_FIELDS
        }
    if isinstance(obj, (list, tuple)):
        return [strip_clock(v) for v in obj]
    return obj


def artifact_digest(obj: Any) -> str:
    """Digest of a world-model artifact with wall-clock fields stripped."""
    return digest(strip_clock(obj))


# ---------------------------------------------------------------------------
# Events and the append-only log.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TransitionEvent:
    """One typed, hash-chained state transition.

    `payload` carries a compact structured record (digests, status, evidence
    refs, key metrics) - NOT full data blobs. Full input/output snapshots live
    in the caller's replay store keyed by (run_id, seq) when needed.

    `occurred_at` is recorded for audit but excluded from `event_hash`, so
    identical computations produce identical chains regardless of when run.
    """

    seq: int
    run_id: str
    from_state: RunState
    transition: Transition
    to_state: RunState
    agent: str
    inputs_digest: str
    outputs_digest: str
    evidence_refs: Tuple[str, ...] = ()
    payload: Dict[str, Any] = field(default_factory=dict)
    occurred_at: str = ""          # recorded clock; excluded from event_hash
    prev_event_hash: str = ""
    event_hash: str = ""

    def compute_hash(self) -> str:
        """Hash over every field except occurred_at and the hash fields."""
        body = {
            "seq": self.seq,
            "run_id": self.run_id,
            "from_state": self.from_state.value,
            "transition": self.transition.value,
            "to_state": self.to_state.value,
            "agent": self.agent,
            "inputs_digest": self.inputs_digest,
            "outputs_digest": self.outputs_digest,
            "evidence_refs": list(self.evidence_refs),
            "payload": strip_clock(self.payload),
            "prev_event_hash": self.prev_event_hash,
        }
        return digest(body)


class TransitionLog:
    """Append-only, hash-chained log of transitions for one run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: List[TransitionEvent] = []
        self.state: RunState = RunState.BRIEF_RECEIVED

    # -- append (INV-1, INV-3) ------------------------------------------------

    def append(
        self,
        transition: Transition,
        agent: str,
        to_state: RunState,
        inputs_digest: str = "",
        outputs_digest: str = "",
        evidence_refs: Tuple[str, ...] = (),
        payload: Optional[Dict[str, Any]] = None,
        clock: str = "",
    ) -> TransitionEvent:
        """Append one event after enforcing legality (INV-1) and, for PUBLISH,
        the complete-evidence-chain gate (INV-3)."""
        if self.state in TERMINAL_STATES:
            raise IllegalTransitionError(
                f"run={self.run_id}: terminal state {self.state.value} has no "
                f"outgoing transitions"
            )
        allowed = TRANSITIONS.get((self.state, transition))
        if allowed is None:
            raise IllegalTransitionError(
                f"run={self.run_id}: {transition.value} from {self.state.value} "
                f"is not in the transition table"
            )
        if to_state not in allowed:
            raise IllegalTransitionError(
                f"run={self.run_id}: {transition.value} from {self.state.value} "
                f"allows {[s.value for s in sorted(allowed)]}, got {to_state.value}"
            )
        if transition is Transition.PUBLISH:
            self._enforce_publish_gate(evidence_refs, outputs_digest)

        draft = TransitionEvent(
            seq=len(self.events),
            run_id=self.run_id,
            from_state=self.state,
            transition=transition,
            to_state=to_state,
            agent=agent,
            inputs_digest=inputs_digest,
            outputs_digest=outputs_digest,
            evidence_refs=tuple(evidence_refs),
            payload=payload or {},
            occurred_at=clock,
            prev_event_hash=self.events[-1].event_hash if self.events else "",
        )
        event = TransitionEvent(
            **{**draft.__dict__, "event_hash": draft.compute_hash()}
        )
        self.events.append(event)
        self.state = to_state
        return event

    # -- INV-3: publish gate ---------------------------------------------------

    @staticmethod
    def _enforce_publish_gate(
        evidence_refs: Tuple[str, ...], outputs_digest: str
    ) -> None:
        """A state may enter PUBLISHED only with a complete evidence chain."""
        if not evidence_refs:
            raise PublishGateError(
                "PUBLISH requires non-empty evidence_refs (INV-3)"
            )
        if not outputs_digest:
            raise PublishGateError(
                "PUBLISH requires an outputs_digest (INV-3)"
            )

    # -- INV-2: chain verification ----------------------------------------------

    def verify_chain(self) -> None:
        """Re-hash every event; check seq, linkage, legality, state closure."""
        prev_hash = ""
        prev_state = RunState.BRIEF_RECEIVED
        for i, ev in enumerate(self.events):
            if ev.seq != i:
                raise ChainIntegrityError(
                    f"run={self.run_id}: seq gap at position {i}"
                )
            if ev.from_state is not prev_state:
                raise ChainIntegrityError(
                    f"run={self.run_id} seq={ev.seq}: from_state does not chain"
                )
            allowed = TRANSITIONS.get((ev.from_state, ev.transition))
            if allowed is None or ev.to_state not in allowed:
                raise ChainIntegrityError(
                    f"run={self.run_id} seq={ev.seq}: illegal recorded transition "
                    f"{ev.transition.value} "
                    f"{ev.from_state.value}->{ev.to_state.value}"
                )
            if ev.prev_event_hash != prev_hash:
                raise ChainIntegrityError(
                    f"run={self.run_id} seq={ev.seq}: broken prev hash link"
                )
            if ev.event_hash != ev.compute_hash():
                raise ChainIntegrityError(
                    f"run={self.run_id} seq={ev.seq}: event hash mismatch "
                    f"(payload tampered)"
                )
            prev_hash = ev.event_hash
            prev_state = ev.to_state
        if self.state is not prev_state:
            raise ChainIntegrityError(f"run={self.run_id}: log state out of sync")

    # -- export / rehydrate -------------------------------------------------------

    def to_records(self) -> List[Dict[str, Any]]:
        """Serialize events (chain remains verifiable after rehydration)."""
        records = []
        for ev in self.events:
            r = dict(ev.__dict__)
            r["from_state"] = ev.from_state.value
            r["transition"] = ev.transition.value
            r["to_state"] = ev.to_state.value
            r["evidence_refs"] = list(ev.evidence_refs)
            records.append(r)
        return records

    @classmethod
    def from_records(cls, records: List[Dict[str, Any]]) -> "TransitionLog":
        """Rehydrate a log from serialized records (INV-2 still enforced)."""
        if not records:
            raise ChainIntegrityError("cannot rehydrate an empty log")
        log = cls(run_id=records[0]["run_id"])
        for r in records:
            ev = TransitionEvent(
                seq=r["seq"],
                run_id=r["run_id"],
                from_state=RunState(r["from_state"]),
                transition=Transition(r["transition"]),
                to_state=RunState(r["to_state"]),
                agent=r["agent"],
                inputs_digest=r["inputs_digest"],
                outputs_digest=r["outputs_digest"],
                evidence_refs=tuple(r.get("evidence_refs", ())),
                payload=r.get("payload", {}),
                occurred_at=r.get("occurred_at", ""),
                prev_event_hash=r.get("prev_event_hash", ""),
                event_hash=r.get("event_hash", ""),
            )
            if ev.event_hash != ev.compute_hash():
                raise ChainIntegrityError(
                    f"run={log.run_id} seq={ev.seq}: record hash mismatch"
                )
            log.events.append(ev)
            log.state = ev.to_state
        return log


# ---------------------------------------------------------------------------
# Clocks: wall time recorded, never digested, injectable for replay.
# ---------------------------------------------------------------------------

class LiveClock:
    """Production clock: real wall time."""

    def now_iso(self) -> str:
        return datetime.now().isoformat()

    def version(self) -> str:
        return datetime.now().strftime("%Y.%m.%d.v1")


class ReplayClock:
    """Replay clock: returns the recorded values from the original run."""

    def __init__(self, occurred_ats: List[str], state_version: str) -> None:
        self._ats = list(occurred_ats)
        self._i = 0
        self._version = state_version

    def now_iso(self) -> str:
        val = self._ats[min(self._i, len(self._ats) - 1)]
        self._i += 1
        return val

    def version(self) -> str:
        return self._version
