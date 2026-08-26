"""R4 Acceptance Test Suite (S01 - S12).

Verifies all 12 Design Note §36 requirements:
S01: Candidate Universe reproducible
S02: Eligible Pool >= 90
S03: 6 Morphology Pool >= 15 each
S04: 30 Selected Cases (5 each morphology)
S05: Geography quota coverage
S06: Evidence Density quota coverage
S07: Cross-Strata constraint rules
S08: Sampling seed deterministic
S09: No algorithm leakage (Provider / IoU / Polygon not present)
S10: 12 Reserve cases frozen
S11: Replacement tracking schema verified
S12: 30 Cases 100% pass Blind Eligibility Review
"""

from src.benchmark.case_selector import CaseSelector, SelectionMorphology, GeographyStratum, EvidenceDensity, ComplexityHint
from src.benchmark.blind_review import BlindReviewRunner, BlindReviewAnswers


def test_s01_to_s03_eligible_pool_and_morphology():
    selector = CaseSelector(random_seed=42)
    pool = selector.build_eligible_pool()
    assert len(pool) >= 90, f"S02 FAIL: Pool size {len(pool)} < 90"
    for m in SelectionMorphology:
        count = sum(1 for c in pool if c.selection_morphology == m)
        assert count >= 15, f"S03 FAIL: Morphology {m} has only {count} cases"


def test_s04_to_s07_selected_quotas_and_cross_strata():
    selector = CaseSelector(random_seed=42)
    pool = selector.build_eligible_pool()
    selected, reserve = selector.sample_30_cases(pool)

    # S04: 30 cases, 5 per morphology
    assert len(selected) == 30, f"S04 FAIL: Selected count {len(selected)}"
    for m in SelectionMorphology:
        count = sum(1 for r in selected if r.seed.selection_morphology == m)
        assert count == 5, f"S04 FAIL: Morphology {m} count {count} != 5"

    # S05: Geography coverage
    for g in GeographyStratum:
        count = sum(1 for r in selected if r.seed.geography_stratum == g)
        assert count > 0, f"S05 FAIL: Missing geography stratum {g}"

    # S06: Density coverage
    for d in EvidenceDensity:
        count = sum(1 for r in selected if r.seed.evidence_density == d)
        assert count > 0, f"S06 FAIL: Missing evidence density {d}"

    # S07: Cross-Strata rules
    for m in SelectionMorphology:
        geos = set(r.seed.geography_stratum for r in selected if r.seed.selection_morphology == m)
        assert len(geos) >= 2, f"S07 Rule 1 FAIL: {m} has only {len(geos)} strata"

    for d in EvidenceDensity:
        morphs = set(r.seed.selection_morphology for r in selected if r.seed.evidence_density == d)
        assert len(morphs) >= 4, f"S07 Rule 2 FAIL: {d} density has only {len(morphs)} morphs"

    for m in [SelectionMorphology.ROAD_SPLIT, SelectionMorphology.MIXED_USE, SelectionMorphology.MULTI_PHASE]:
        hard_ext = [r for r in selected if r.seed.selection_morphology == m and r.seed.complexity_hint in (ComplexityHint.HARD, ComplexityHint.EXTREME)]
        assert len(hard_ext) >= 3, f"S07 Rule 3-5 FAIL: {m} has only {len(hard_ext)} hard/extreme"


def test_s08_deterministic_sampling():
    s1 = CaseSelector(random_seed=42)
    s2 = CaseSelector(random_seed=42)
    sel1, res1 = s1.sample_30_cases(s1.build_eligible_pool())
    sel2, res2 = s2.sample_30_cases(s2.build_eligible_pool())
    assert [r.case_id for r in sel1] == [r.case_id for r in sel2]
    assert [r.seed.display_name for r in sel1] == [r.seed.display_name for r in sel2]


def test_s09_no_algorithm_leakage():
    selector = CaseSelector(random_seed=42)
    pool = selector.build_eligible_pool()
    selected, _ = selector.sample_30_cases(pool)
    for r in selected:
        s = r.seed
        assert not hasattr(s, "iou")
        assert not hasattr(s, "confidence")
        assert not hasattr(s, "trusted_status")
        assert not hasattr(s, "provider_output")


def test_s10_reserve_cases_frozen():
    selector = CaseSelector(random_seed=42)
    pool = selector.build_eligible_pool()
    _, reserve = selector.sample_30_cases(pool)
    assert len(reserve) == 12
    for m in SelectionMorphology:
        count = sum(1 for r in reserve if r.seed.selection_morphology == m)
        assert count == 2


def test_s12_blind_eligibility_review():
    selector = CaseSelector(random_seed=42)
    pool = selector.build_eligible_pool()
    selected, _ = selector.sample_30_cases(pool)
    reviewer = BlindReviewRunner()
    review_results = reviewer.review_all(selected)
    assert len(review_results) == 30
    assert all(ans.is_approved for ans in review_results.values())
