"""
Disposition Lattice and Monotonicity Theorem (Proposal 1: Semantic Layer).

Formalizes entity trustworthiness as a bounded lattice and proves - by
mechanized checking - the evidence-gating invariants:

  INV-5  Lattice semantics  - dispositions form a total order (chain lattice)
        REJECTED < UNRESOLVED < PROVISIONAL < TRUSTED with join = max,
        meet = min.
  INV-6  No evidence, no upgrade - a ledger snapshot's disposition may rise
        only when the newly appended evidence contains a SUPPORTING item that
        survives the active set. Silent upgrades are structurally impossible.
  INV-7  Refutation-gated demotion - the disposition may fall only when the
        delta appends a REFUTING item or supersedes previously active
        supporting evidence. Downgrades are always evidence-carrying events.
  INV-8  Zero-false-trust - TRUSTED requires active supporting evidence
        covering EVERY required category. Checked, not assumed: any snapshot
        claiming TRUSTED without full category coverage fails verification.

The module is domain-agnostic: evidence categories are free-form strings; the
caller supplies `required_categories` (e.g. the gate contract). Evidence items
are algebra elements (category, kind) so a future evidence algebra (Proposal 2)
can replace the evaluation rule without changing this interface.

Dispositions are *derived*, never stored as mutable state: the ledger stores
evidence; `evaluate()` recomputes. History is append-only in both senses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Tuple


class Disposition(str, Enum):
    """Trust disposition of an entity (INV-5 chain lattice, bottom to top)."""

    REJECTED = "REJECTED"        # bottom: refuting evidence active
    UNRESOLVED = "UNRESOLVED"    # no evidence either way
    PROVISIONAL = "PROVISIONAL"  # some supporting evidence, coverage incomplete
    TRUSTED = "TRUSTED"          # top: full required-category coverage

    @property
    def rank(self) -> int:
        return _ORDER.index(self)

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Disposition):
            return NotImplemented
        return self.rank <= other.rank

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Disposition):
            return NotImplemented
        return self.rank < other.rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Disposition):
            return NotImplemented
        return self.rank >= other.rank

    def __gt__(self, other: object) -> bool:
        # NOTE: str.Enum inherits str.__gt__ (lexicographic); without this
        # override, "REJECTED" > "PROVISIONAL" is True and demotions read as
        # upgrades. Rank-based comparison is the only safe order here.
        if not isinstance(other, Disposition):
            return NotImplemented
        return self.rank > other.rank

    @staticmethod
    def join(a: "Disposition", b: "Disposition") -> "Disposition":
        """Least upper bound (max in the chain)."""
        return a if a.rank >= b.rank else b

    @staticmethod
    def meet(a: "Disposition", b: "Disposition") -> "Disposition":
        """Greatest lower bound (min in the chain)."""
        return a if a.rank <= b.rank else b


# Chain order, bottom to top (INV-5).
_ORDER: Tuple[Disposition, ...] = (
    Disposition.REJECTED,
    Disposition.UNRESOLVED,
    Disposition.PROVISIONAL,
    Disposition.TRUSTED,
)


class EvidenceKind(str, Enum):
    SUPPORTING = "SUPPORTING"
    REFUTING = "REFUTING"


@dataclass(frozen=True)
class EvidenceItem:
    """One algebra-element piece of evidence in a ledger.

    `overrides` lists evidence ids this item supersedes (e.g. a repair
    superseding an earlier refutation). Supersession is itself evidence and
    stays in the ledger forever - nothing is ever deleted.
    """

    evidence_id: str
    kind: EvidenceKind
    category: str
    note: str = ""
    overrides: Tuple[str, ...] = ()
    recorded_at: str = ""  # clock stamp; excluded from digest semantics


@dataclass(frozen=True)
class DispositionSnapshot:
    """Disposition of the ledger after the n-th evidence append."""

    index: int                 # evidence count at snapshot time
    disposition: Disposition
    evidence_ids: Tuple[str, ...]
    new_item: Optional[EvidenceItem] = None  # item appended at this step


class MonotonicityError(Exception):
    """INV-6/INV-7 violation: an upgrade or demotion lacks its evidence."""


class ZeroFalseTrustError(Exception):
    """INV-8 violation: TRUSTED without full required-category coverage."""


def _active_items(items: List[EvidenceItem]) -> List[EvidenceItem]:
    """Items not superseded by any later item's overrides."""
    superseded = {oid for it in items for oid in it.overrides}
    return [it for it in items if it.evidence_id not in superseded]


def evaluate(
    items: List[EvidenceItem], required_categories: FrozenSet[str]
) -> Disposition:
    """Derive the disposition from an evidence set (INV-8 rule)."""
    active = _active_items(items)
    if any(it.kind is EvidenceKind.REFUTING for it in active):
        return Disposition.REJECTED
    supporting = {it.category for it in active if it.kind is EvidenceKind.SUPPORTING}
    if required_categories and supporting >= required_categories:
        return Disposition.TRUSTED
    if supporting:
        return Disposition.PROVISIONAL
    return Disposition.UNRESOLVED


class DispositionLedger:
    """Append-only evidence ledger for one entity, with snapshot history."""

    def __init__(
        self,
        entity_id: str,
        required_categories: FrozenSet[str],
        clock: Optional[object] = None,
        algebra: Optional[object] = None,
    ) -> None:
        """`algebra` is any object implementing the EvidenceAlgebra protocol
        (duck-typed to avoid a circular import). None = the built-in
        category-coverage rule (`evaluate`), the historical default."""
        self.entity_id = entity_id
        self.required_categories = frozenset(required_categories)
        self._clock = clock
        self._algebra = algebra
        self.items: List[EvidenceItem] = []
        self.snapshots: List[DispositionSnapshot] = [
            DispositionSnapshot(
                index=0,
                disposition=Disposition.UNRESOLVED,
                evidence_ids=(),
            )
        ]

    # -- append --------------------------------------------------------------

    def append(self, item: EvidenceItem) -> Disposition:
        """Append evidence; recompute; record snapshot. Returns new disposition."""
        if any(it.evidence_id == item.evidence_id for it in self.items):
            raise ValueError(
                f"evidence {item.evidence_id} already in ledger "
                f"{self.entity_id} (append-only)"
            )
        stamped = item
        if self._clock is not None and not item.recorded_at:
            stamped = EvidenceItem(
                **{**item.__dict__, "recorded_at": self._clock.now_iso()}
            )
        self.items.append(stamped)
        disp = self._compute(self.items)
        self.snapshots.append(
            DispositionSnapshot(
                index=len(self.items),
                disposition=disp,
                evidence_ids=tuple(it.evidence_id for it in self.items),
                new_item=stamped,
            )
        )
        return disp

    def _compute(self, items: List[EvidenceItem]) -> Disposition:
        """Disposition via the injected algebra, or the built-in rule."""
        if self._algebra is not None:
            return self._algebra.disposition(items, self.required_categories)
        return evaluate(items, self.required_categories)

    @property
    def disposition(self) -> Disposition:
        return self._compute(self.items)

    def opinion(self):
        """Current algebra opinion (DS: MassOpinion; heuristic: votes).
        None when no algebra is injected and no notion of opinion exists."""
        if self._algebra is None:
            return None
        return self._algebra.opinion_of(self.items) \
            if hasattr(self._algebra, "opinion_of") else None

    def active_items(self) -> List[EvidenceItem]:
        return _active_items(self.items)

    # -- verification ---------------------------------------------------------

    def verify_monotone(self) -> None:
        """Check INV-6/INV-7 over the recorded snapshot history."""
        for prev, curr in zip(self.snapshots, self.snapshots[1:]):
            delta = curr.new_item
            if delta is None:  # snapshots beyond appends: consistent
                continue
            if curr.disposition > prev.disposition:
                if delta.kind is not EvidenceKind.SUPPORTING:
                    raise MonotonicityError(
                        f"{self.entity_id}: upgrade {prev.disposition.value} -> "
                        f"{curr.disposition.value} carried "
                        f"{delta.kind.value} evidence {delta.evidence_id}"
                    )
            elif curr.disposition < prev.disposition:
                superseded_support = any(
                    oid in {p.evidence_id for p in self.items[: curr.index]}
                    and _was_supporting(self.items, oid)
                    for oid in delta.overrides
                )
                if (
                    delta.kind is not EvidenceKind.REFUTING
                    and not superseded_support
                ):
                    raise MonotonicityError(
                        f"{self.entity_id}: demotion {prev.disposition.value} -> "
                        f"{curr.disposition.value} carried no refuting or "
                        f"superseding evidence ({delta.evidence_id})"
                    )




    def verify_zero_false_trust(self) -> None:
        """Check INV-8: every snapshot claiming TRUSTED must be derivable
        from its own evidence prefix, and the live set must cover all
        required categories."""
        for snap in self.snapshots:
            if snap.disposition is Disposition.TRUSTED:
                recomputed = self._compute(self.items[: snap.index])
                if recomputed is not Disposition.TRUSTED:
                    raise ZeroFalseTrustError(
                        f"{self.entity_id}: snapshot @{snap.index} claims "
                        f"TRUSTED but evidence prefix yields {recomputed.value}"
                    )
        disp = self.disposition
        if disp is not Disposition.TRUSTED:
            return
        supporting = {
            it.category
            for it in self.active_items()
            if it.kind is EvidenceKind.SUPPORTING
        }
        missing = self.required_categories - supporting
        if missing:
            raise ZeroFalseTrustError(
                f"{self.entity_id}: TRUSTED but missing categories "
                f"{sorted(missing)}"
            )

    def to_records(self) -> List[dict]:
        return [dict(it.__dict__) for it in self.items]


def disposition_from_validation(
    validation_status: str,
    decision_ready: bool,
    finding_severities: Tuple[str, ...] = (),
) -> Disposition:
    """Map a GeometryObservation/SpatialEntity state onto the lattice.

    REJECTED/QUARANTINED or blocked findings  -> REJECTED
    RECONSTRUCTED (unconfirmed constructed)   -> PROVISIONAL
    VERIFIED_VALID / REPAIRED_AUTO            -> TRUSTED
    anything else                             -> UNRESOLVED
    """
    if (
        validation_status in ("REJECTED", "QUARANTINED")
        or not decision_ready
        or "CRITICAL" in finding_severities
    ):
        return Disposition.REJECTED
    if validation_status == "RECONSTRUCTED":
        return Disposition.PROVISIONAL
    if validation_status in ("VERIFIED_VALID", "REPAIRED_AUTO"):
        return Disposition.TRUSTED
    return Disposition.UNRESOLVED
