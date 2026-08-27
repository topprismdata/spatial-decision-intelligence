"""
Evidence Algebra (Proposal 2: Semantic Layer).

Lifts evidence combination from ad-hoc ranking into a formal algebra. The
world model and the disposition ledger consume evidence only through the
`EvidenceAlgebra` interface; concrete fusion strategies are interchangeable
implementations with identical interfaces:

  HeuristicCategoryAlgebra  - vote counting + category coverage (today's
                              default; equivalent to `disposition.evaluate`).
  DempsterShaferAlgebra     - mass functions over Theta = {HOLD, NOT_HOLD},
                              Dempster's rule with a Yager fallback when
                              conflict K = 1. Yields belief/plausibility
                              intervals and a conflict measure K that
                              operationalizes review triage.

Algebra contract (tested):
  A1  (Opinion, combine, 1)  - combine is commutative and associative,
                               with identity `identity()`.
  A2  arbitrate              - idempotent, commutative authority selection.
  A3  bounds                 - 0 <= belief <= plausibility <= 1.
  A4  monotone belief        - appending SUPPORTING mass never lowers belief.
  A5  conflict               - K in [0, 1]; K = 1 handled without division
                               errors (Yager: conflict mass goes to Theta).

Disposition rule under an algebra (INV-8 generalization):
  refute-dominant            -> REJECTED
  conflict >= cap_threshold  -> at most PROVISIONAL (high-conflict evidence
                                never earns TRUSTED; triage to human review)
  coverage complete AND belief >= trust_threshold -> TRUSTED
  some supporting evidence   -> PROVISIONAL
  otherwise                  -> UNRESOLVED

Domain-agnostic: opinions carry no geometry and no ontology.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple

from src.domain.disposition import (
    Disposition,
    EvidenceItem,
    EvidenceKind,
    evaluate,
)


# ---------------------------------------------------------------------------
# DS opinion: a mass function over Theta = {HOLD, NOT_HOLD}.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MassOpinion:
    """Mass assignment m: {HOLD, NOT_HOLD, Theta} -> [0, 1], summing to 1."""

    m_hold: float = 0.0
    m_not_hold: float = 0.0
    m_uncertain: float = 1.0  # vacuous opinion: m(Theta) = 1

    def __post_init__(self) -> None:
        total = self.m_hold + self.m_not_hold + self.m_uncertain
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"masses must sum to 1, got {total}")
        if min(self.m_hold, self.m_not_hold, self.m_uncertain) < 0:
            raise ValueError("masses must be non-negative")

    @property
    def is_vacuous(self) -> bool:
        return self.m_uncertain >= 1.0 - 1e-9

    def belief(self) -> float:
        """Belief the boundary claim holds: Bel(HOLD) = m({HOLD})."""
        return self.m_hold

    def plausibility(self) -> float:
        """Plausibility: Pl(HOLD) = m({HOLD}) + m(Theta)."""
        return self.m_hold + self.m_uncertain

    def conflict_with(self, other: "MassOpinion") -> float:
        """Dempster conflict for this pair: mass assigned to empty intersections.
        With singleton masses plus Theta, only HOLD x NOT_HOLD conflicts."""
        return (
            self.m_hold * other.m_not_hold
            + self.m_not_hold * other.m_hold
        )


@dataclass(frozen=True)
class HeuristicOpinion:
    """Vote-count opinion: support vs refute mass plus category coverage."""

    support: float = 0.0
    refute: float = 0.0
    categories: FrozenSet[str] = frozenset()
    required: FrozenSet[str] = frozenset()


# Per-item mass contributions for the DS algebra.
DS_SUPPORTING_MASS = MassOpinion(m_hold=0.6, m_uncertain=0.4)
DS_REFUTING_MASS = MassOpinion(m_not_hold=0.6, m_uncertain=0.4)
def ds_combine(
    a: MassOpinion, b: MassOpinion
) -> Tuple[MassOpinion, float]:
    """Dempster's rule over {HOLD, NOT_HOLD, Theta}; Yager fallback when
    K = 1 (total disagreement: all mass to Theta). Returns (joint, K).

    Intersections: HxH->H, NxN->N, HxTheta/ThetaxH->H, NxTheta/ThetaxN->N,
    ThetaxTheta->Theta, HxN/NxH -> conflict K. The cross terms with Theta
    therefore belong to the *singleton* masses, not to Theta.
    """
    k = a.m_hold * b.m_not_hold + a.m_not_hold * b.m_hold
    raw_hold = (
        a.m_hold * b.m_hold
        + a.m_hold * b.m_uncertain
        + a.m_uncertain * b.m_hold
    )
    raw_not = (
        a.m_not_hold * b.m_not_hold
        + a.m_not_hold * b.m_uncertain
        + a.m_uncertain * b.m_not_hold
    )
    raw_theta = a.m_uncertain * b.m_uncertain
    if k >= 1.0 - 1e-12:
        # Total disagreement: Yager - all mass to Theta, K reported as 1.
        return MassOpinion(m_hold=0.0, m_not_hold=0.0, m_uncertain=1.0), 1.0
    denom = 1.0 - k
    return (
        MassOpinion(
            m_hold=raw_hold / denom,
            m_not_hold=raw_not / denom,
            m_uncertain=raw_theta / denom,
        ),
        k,
    )


# ---------------------------------------------------------------------------
# Algebra interface and implementations.
# ---------------------------------------------------------------------------

class EvidenceAlgebra(ABC):
    """The only way the world model touches evidence semantics."""

    @abstractmethod
    def identity(self):
        """Neutral element for combine (A1)."""

    @abstractmethod
    def from_item(self, item: EvidenceItem):
        """Embed one evidence item as an opinion."""

    @abstractmethod
    def combine(self, a, b):
        """⊗: commutative, associative aggregation (A1)."""

    @abstractmethod
    def arbitrate(self, a, b):
        """⊔: authority arbitration; idempotent and commutative (A2)."""

    @abstractmethod
    def belief(self, op) -> float:
        """Degree of belief the claim holds (A3 lower bound)."""

    @abstractmethod
    def plausibility(self, op) -> float:
        """Plausibility upper bound (A3)."""

    @abstractmethod
    def conflict(self, ops) -> float:
        """Pairwise-summed conflict measure K in [0, 1] (A5)."""

    @abstractmethod
    def disposition(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> Disposition:
        """INV-8 generalized: derive the disposition from evidence."""

    @abstractmethod
    def trust_earned(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> bool:
        """Whether TRUSTED is justified (used by verify_zero_false_trust)."""


class HeuristicCategoryAlgebra(EvidenceAlgebra):
    """Vote counting + coverage; exactly `disposition.evaluate` semantics."""

    def identity(self) -> HeuristicOpinion:
        return HeuristicOpinion()

    def from_item(self, item: EvidenceItem) -> HeuristicOpinion:
        if item.kind is EvidenceKind.SUPPORTING:
            return HeuristicOpinion(
                support=1.0,
                categories=frozenset({item.category}),
            )
        return HeuristicOpinion(refute=1.0)

    def combine(self, a: HeuristicOpinion, b: HeuristicOpinion) -> HeuristicOpinion:
        return HeuristicOpinion(
            support=a.support + b.support,
            refute=a.refute + b.refute,
            categories=a.categories | b.categories,
            required=a.required | b.required,
        )

    def arbitrate(
        self, a: HeuristicOpinion, b: HeuristicOpinion
    ) -> HeuristicOpinion:
        """Keep the opinion with strictly more support; ties -> union."""
        if a.support != b.support:
            return a if a.support > b.support else b
        return HeuristicOpinion(
            support=max(a.support, b.support),
            refute=min(a.refute, b.refute),
            categories=a.categories | b.categories,
            required=a.required | b.required,
        )

    def belief(self, op: HeuristicOpinion) -> float:
        total = op.support + op.refute
        return op.support / total if total > 0 else 0.0

    def plausibility(self, op: HeuristicOpinion) -> float:
        total = op.support + op.refute
        return 1.0 - op.refute / total if total > 0 else 1.0

    def conflict(self, ops) -> float:
        support = sum(o.support for o in ops)
        refute = sum(o.refute for o in ops)
        total = support + refute
        if total <= 0:
            return 0.0
        return 2.0 * min(support, refute) / total

    def disposition(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> Disposition:
        return evaluate(items, required_categories)

    def trust_earned(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> bool:
        return (
            evaluate(items, required_categories) is Disposition.TRUSTED
        )


class DempsterShaferAlgebra(EvidenceAlgebra):
    """DS belief functions over {HOLD, NOT_HOLD} with Yager total-conflict
    fallback. belief/plausibility give the interval; conflict K drives
    abstention: high-conflict evidence sets can never earn TRUSTED."""

    def __init__(
        self,
        trust_belief_threshold: float = 0.60,
        conflict_cap: float = 0.50,
    ) -> None:
        self.trust_belief_threshold = trust_belief_threshold
        self.conflict_cap = conflict_cap

    def identity(self) -> MassOpinion:
        return MassOpinion()  # vacuous: m(Theta) = 1

    def from_item(self, item: EvidenceItem) -> MassOpinion:
        return (
            DS_SUPPORTING_MASS
            if item.kind is EvidenceKind.SUPPORTING
            else DS_REFUTING_MASS
        )

    def combine(self, a: MassOpinion, b: MassOpinion) -> MassOpinion:
        joint, _ = ds_combine(a, b)
        return joint

    def arbitrate(self, a: MassOpinion, b: MassOpinion) -> MassOpinion:
        """Authority selection: the more committed opinion wins (larger
        singleton mass total); idempotent since a vs a keeps a."""
        commit_a = a.m_hold + a.m_not_hold
        commit_b = b.m_hold + b.m_not_hold
        if commit_a == commit_b:
            return a
        return a if commit_a > commit_b else b

    def belief(self, op: MassOpinion) -> float:
        return op.belief()

    def plausibility(self, op: MassOpinion) -> float:
        return op.plausibility()

    def conflict(self, ops) -> float:
        """Cumulative conflict across the evidence set: sum of pairwise K
        clipped to [0, 1]."""
        k = 0.0
        for i in range(len(ops)):
            for j in range(i + 1, len(ops)):
                k += ops[i].conflict_with(ops[j])
        return min(k, 1.0)

    # -- INV-8 generalized --------------------------------------------------

    def disposition(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> Disposition:
        opinions = [self.from_item(it) for it in items]
        if not opinions:
            return Disposition.UNRESOLVED
        joint = opinions[0]
        for op in opinions[1:]:
            joint = self.combine(joint, op)
        k = self.conflict(opinions)

        if joint.m_not_hold > joint.m_hold and joint.m_not_hold > 0:
            return Disposition.REJECTED
        supporting = {
            it.category
            for it in items
            if it.kind is EvidenceKind.SUPPORTING
        }
        coverage = bool(required_categories) and (
            supporting >= required_categories
        )
        if k >= self.conflict_cap:
            # Conflicting evidence: abstain from trust regardless of coverage.
            return Disposition.PROVISIONAL if supporting else Disposition.UNRESOLVED
        if coverage and joint.belief() >= self.trust_belief_threshold:
            return Disposition.TRUSTED
        if supporting:
            return Disposition.PROVISIONAL
        return Disposition.UNRESOLVED

    def trust_earned(
        self, items: List[EvidenceItem], required_categories: FrozenSet[str]
    ) -> bool:
        return (
            self.disposition(items, required_categories) is Disposition.TRUSTED
        )

    def opinion_of(
        self, items: List[EvidenceItem]
    ) -> MassOpinion:
        opinions = [self.from_item(it) for it in items]
        if not opinions:
            return self.identity()
        joint = opinions[0]
        for op in opinions[1:]:
            joint = self.combine(joint, op)
        return joint
