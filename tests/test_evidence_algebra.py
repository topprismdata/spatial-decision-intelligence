"""
Tests for the Evidence Algebra (src/domain/evidence_algebra.py).

Covers the algebra contract:
  A1  combine: commutative, associative (float-tolerance), identity
  A2  arbitrate: idempotent, commutative
  A3  bounds: 0 <= belief <= plausibility <= 1
  A4  monotone belief: SUPPORTING-flavored mass never lowers belief
  A5  conflict: K in [0,1]; K=1 (total disagreement) handled by Yager rule
and the ledger integration: swapping the algebra swaps fusion semantics
without touching gates (default behavior identical to pre-algebra).
"""

import itertools

import pytest

from src.domain.disposition import (
    Disposition,
    DispositionLedger,
    EvidenceItem,
    EvidenceKind,
)
from src.domain.evidence_algebra import (
    DS_SUPPORTING_MASS,
    DempsterShaferAlgebra,
    HeuristicCategoryAlgebra,
    HeuristicOpinion,
    MassOpinion,
    ds_combine,
)

DS = DempsterShaferAlgebra()
HEUR = HeuristicCategoryAlgebra()

HARD_HOLD = MassOpinion(m_hold=1.0, m_uncertain=0.0)
HARD_NOT = MassOpinion(m_not_hold=1.0, m_uncertain=0.0)
SOFT_HOLD = MassOpinion(m_hold=0.6, m_uncertain=0.4)
SOFT_NOT = MassOpinion(m_not_hold=0.6, m_uncertain=0.4)
MIXED = MassOpinion(m_hold=0.3, m_not_hold=0.3, m_uncertain=0.4)
VACUOUS = MassOpinion()  # m(Theta) = 1

DS_CASES = [HARD_HOLD, HARD_NOT, SOFT_HOLD, SOFT_NOT, MIXED, VACUOUS]
SUPPORTING_FLAVORED = [HARD_HOLD, SOFT_HOLD, MIXED, VACUOUS]

ITEMS = [
    EvidenceItem("e1", EvidenceKind.SUPPORTING, "GEOMETRY"),
    EvidenceItem("e2", EvidenceKind.SUPPORTING, "AUDIT"),
]
REQUIRED = frozenset({"GEOMETRY", "AUDIT"})


# ---------------------------------------------------------------------------
# A1: combine is a commutative associative monoid (DS + heuristic).
# ---------------------------------------------------------------------------

def test_ds_combine_commutative():
    for a, b in itertools.product(DS_CASES, repeat=2):
        ab, k_ab = ds_combine(a, b)
        ba, k_ba = ds_combine(b, a)
        assert ab == ba
        assert abs(k_ab - k_ba) < 1e-12


def test_ds_combine_associative():
    # Dempster's rule is exactly associative; equality here is float-tolerance.
    for a, b, c in itertools.product(DS_CASES[::2], repeat=3):
        left, _ = ds_combine(ds_combine(a, b)[0], c)
        right, _ = ds_combine(a, ds_combine(b, c)[0])
        assert left.m_hold == pytest.approx(right.m_hold, abs=1e-9)
        assert left.m_not_hold == pytest.approx(right.m_not_hold, abs=1e-9)
        assert left.m_uncertain == pytest.approx(right.m_uncertain, abs=1e-9)


def test_ds_identity_is_vacuous():
    vac = DS.identity()
    assert vac.is_vacuous
    for a in DS_CASES:
        assert DS.combine(a, vac) == a


def test_heuristic_combine_monoid():
    a = HeuristicOpinion(support=1.0, categories=frozenset({"GEOMETRY"}))
    b = HeuristicOpinion(support=1.0, categories=frozenset({"AUDIT"}))
    c = HeuristicOpinion(refute=1.0)
    assert HEUR.combine(a, b) == HEUR.combine(b, a)
    assert HEUR.combine(HEUR.combine(a, b), c) == HEUR.combine(a, HEUR.combine(b, c))
    assert HEUR.combine(a, HEUR.identity()) == a


def test_heuristic_arbitrate_idempotent_commutative():
    a = HeuristicOpinion(support=2.0, categories=frozenset({"GEOMETRY"}))
    b = HeuristicOpinion(support=1.0, categories=frozenset({"AUDIT"}))
    assert HEUR.arbitrate(a, a) == a
    assert HEUR.arbitrate(a, b) == HEUR.arbitrate(b, a)


def test_ds_arbitrate_picks_more_committed():
    assert DS.arbitrate(HARD_HOLD, VACUOUS) == HARD_HOLD
    assert DS.arbitrate(HARD_HOLD, HARD_HOLD) == HARD_HOLD


# ---------------------------------------------------------------------------
# A3/A4: bounds and monotone belief.
# ---------------------------------------------------------------------------

def test_ds_bounds_hold_across_case_matrix():
    for a, b in itertools.product(DS_CASES, repeat=2):
        joint, _ = ds_combine(a, b)
        assert 0.0 <= joint.belief() <= joint.plausibility() <= 1.0 + 1e-9


def test_ds_supporting_mass_never_lowers_belief():
    base = DS_SUPPORTING_MASS
    # A4 holds for SUPPORTING-flavored additions (hold or uncertainty mass);
    # refuting mass is exactly the demotion path, not covered by this law.
    for extra in SUPPORTING_FLAVORED:
        joint, _ = ds_combine(base, extra)
        assert joint.belief() >= base.belief() - 1e-9


# ---------------------------------------------------------------------------
# A5: conflict semantics.
# ---------------------------------------------------------------------------

def test_ds_agreeing_evidence_has_zero_conflict():
    assert ds_combine(SOFT_HOLD, SOFT_HOLD)[1] == 0.0


def test_ds_total_conflict_uses_yager_no_crash():
    joint, k = ds_combine(HARD_HOLD, HARD_NOT)
    assert k == 1.0
    assert joint.is_vacuous  # all mass to Theta, nothing asserted


def test_ds_conflict_in_unit_range():
    for a, b in itertools.product(DS_CASES, repeat=2):
        _, k = ds_combine(a, b)
        assert 0.0 <= k <= 1.0 + 1e-9


def test_ds_set_conflict_sums_pairwise_clipped():
    ops = [DS.from_item(EvidenceItem(f"e{i}", EvidenceKind.SUPPORTING, "GEOMETRY"))
           for i in range(3)]
    ops.append(DS.from_item(EvidenceItem("eN", EvidenceKind.REFUTING, "GEOMETRY")))
    k = DS.conflict(ops)
    assert 0.0 < k <= 1.0


# ---------------------------------------------------------------------------
# Disposition semantics: fusion strategy swaps, gates do not.
# ---------------------------------------------------------------------------

def test_both_algebras_agree_on_clear_cut_cases():
    assert DS.disposition(ITEMS, REQUIRED) is Disposition.TRUSTED
    assert HEUR.disposition(ITEMS, REQUIRED) is Disposition.TRUSTED
    assert DS.disposition([], REQUIRED) is Disposition.UNRESOLVED
    assert HEUR.disposition([], REQUIRED) is Disposition.UNRESOLVED
    lone_refuting = [EvidenceItem("e3", EvidenceKind.REFUTING, "GEOMETRY")]
    assert DS.disposition(lone_refuting, REQUIRED) is Disposition.REJECTED
    assert HEUR.disposition(lone_refuting, REQUIRED) is Disposition.REJECTED


def test_supported_refutation_diverges_by_design():
    """Two supports vs one refutation: the heuristic algebra hard-rejects
    (categorical rule); the DS algebra weighs the evidence - belief in HOLD
    survives (raw 0.84 vs 0.6), but conflict K = 0.504 breaches the cap, so
    it abstains to PROVISIONAL and flags for human triage. This divergence
    is the intended value of swappable fusion strategies."""
    mixed = ITEMS + [EvidenceItem("e3", EvidenceKind.REFUTING, "GEOMETRY")]
    assert HEUR.disposition(mixed, REQUIRED) is Disposition.REJECTED
    assert DS.disposition(mixed, REQUIRED) is Disposition.PROVISIONAL
    ops = [DS.from_item(it) for it in mixed]
    assert DS.conflict(ops) >= 0.5


def test_ds_belief_threshold_blocks_weak_trust():
    strict = DempsterShaferAlgebra(trust_belief_threshold=0.99)
    # Coverage complete but soft evidence cannot reach 0.99 belief.
    assert strict.disposition(ITEMS, REQUIRED) is Disposition.PROVISIONAL


# ---------------------------------------------------------------------------
# Ledger integration: algebra injection swaps semantics in place.
# ---------------------------------------------------------------------------

def _fed_ledger(algebra=None) -> DispositionLedger:
    led = DispositionLedger("E1", REQUIRED, algebra=algebra)
    for it in ITEMS:
        led.append(it)
    return led


def test_default_ledger_matches_pre_algebra_behavior():
    # No algebra injected: exactly the legacy category-coverage result.
    assert _fed_ledger().disposition is Disposition.TRUSTED


def test_heuristic_algebra_equivalent_to_default():
    assert _fed_ledger(HEUR).disposition is _fed_ledger().disposition


def test_ds_ledger_reports_opinion_and_trust():
    led = _fed_ledger(DS)
    assert led.disposition is Disposition.TRUSTED
    op = led.opinion()
    assert isinstance(op, MassOpinion)
    assert 0.0 <= op.belief() <= op.plausibility() <= 1.0
    led.verify_monotone()
    led.verify_zero_false_trust()


def test_ds_ledger_abstains_on_conflict():
    led = DispositionLedger("E2", REQUIRED, algebra=DS)
    for it in ITEMS:
        led.append(it)
    led.append(EvidenceItem("eX", EvidenceKind.REFUTING, "FINDING",
                            note="contradicting survey"))
    assert led.disposition in (Disposition.PROVISIONAL, Disposition.REJECTED)
    # Conflict K is directly readable for review triage.
    ops = [DS.from_item(it) for it in led.items]
    assert DS.conflict(ops) > 0.0
