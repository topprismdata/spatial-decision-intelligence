# R7 Architecture Decision Report v1.1

## 1. Executive Verdict

**Next Phase:** R8 Road Semantic Interpretation Experiment (3-arm: Control / B8-D / B8-V)

**Core finding:** 7/30 cases (23%) are Observation Ceiling. 6/30 (20%) are D3 Road Semantics — the largest actionable failure cluster. D6 Ranking Algorithm itself is not failing (0 cases); the problem is missing Road Semantic features.

## 2. Failure Landscape (D1-D8)

| Domain | Primary Cases | % | Notes |
|--------|:------------:|:-:|-------|
| D1 DATA_AVAILABILITY | 5 | 17% | Data ceiling |
| D2 ENTITY_RESOLUTION | 4 | 13% | Entity confusion |
| **D3 ROAD_SEMANTICS** | **6** | **20%** | **Largest actionable cluster** |
| D4 BUILDING_MEMBERSHIP | 6 | 20% | Primary root cause: 4/6 cases |
| D5 CANDIDATE_GENERATION | 4 | 13% | Generation gap |
| **D6 RANKING_ALGORITHM** | **0** | **0%** | **No ranking algorithm failure** |
| D7 EVIDENCE_VALIDATION | 0 | 0% | Validation gates working |
| D8 OBSERVATION_CEILING | 5 | 17% | Genuine limit |

### Morphology × Failure Domain

| Morphology | D1 | D2 | D3 | D4 | D5 | D8 |
|------------|:--:|:--:|:--:|:--:|:--:|:--:|
| MODERN_GATED | · | · | · | · | ■ | ■ |
| MULTI_PHASE | ■ | ■ | ■ | · | · | · |
| DANWEI_COURTYARD | ■ | ■ | · | ■ | · | · |
| OLD_OPEN | ■ | · | · | · | · | ■ |
| **ROAD_SPLIT** | · | · | **■** | · | · | · |
| MIXED_USE | · | · | · | ■ | · | · |

## 3. Generation vs Ranking (Oracle vs Top1)

| Quadrant | Count | Interpretation |
|----------|:-----:|----------------|
| Q1 Healthy | 18 | MODERN_GATED, OSM polygon available |
| **Q2 Ranking Problem** | **5** | **Oracle good, Top1 low — D3 root cause** |
| Q3 Reconstruction Fail | 0 | No data-rich generation failures |
| Q4 Observation Ceiling | 7 | OLD_OPEN x4, DANWEI x2, LOW density x1 |

**Critical clarification:** Q2 (5 Ranking Problem cases) is a **symptom**. The **root cause** is D3 Road Semantics (5/5). The ranking algorithm itself (D6) is not failing — it lacks the correct Road Semantic feature signal. Do not optimize the ranking engine; add Road Semantic features.

## 4. B6 vs B7 Semantic Increment

| Metric | B6 | B7 | Δ |
|--------|:--:|:--:|:-:|
| Top1 OK | 18/30 (60%) | 22/30 (73%) | +13% |
| Win/Tie/Loss | — | — | 4/24/2 |
| ΔRankingRegret | — | — | -0.08 |

**Verdict:** Semantic ranking has measurable but modest effect. B7 uses non-specific semantic features. R8 will test whether targeted Road Semantic features produce larger gains.

## 5. Building Source Complementarity

| Source | Coverage | Verdict |
|--------|:--------:|---------|
| OSM | 83% (25/30) | Best single source |
| Overture | 77% (23/30) | Comparable |
| Microsoft | 60% (18/30) | Lower, no unique wins |
| B5 Multi | 83% (25/30) | **No improvement over best single source** |

**Decision:** Stop multi-source building expansion. OSM alone is sufficient.

## 6. Road Analysis

| Metric | Result |
|--------|:------:|
| ROAD_SPLIT affected | 5/5 (100%) |
| STRONG_ONLY | Under-splits (public roads not cutting compound) |
| STRONG_PLUS_WEAK | Over-splits (service roads cutting too aggressively) |
| MULTI_PHASE affected | 2/5 (secondary) |

**Decision:** R8 focused on 5 ROAD_SPLIT cases only. MULTI_PHASE held as external validation set.

## 7. Trust & Abstention

| Metric | Count | Notes |
|--------|:-----:|-------|
| False Trusted | 0 | **Safety baseline** |
| Observation Ceiling cases | 7 | OLD_OPEN x4, DANWEI x2, LOW density x1 |
| Correct Abstention | 5/7 | System correctly UNRESOLVED |
| False Certainty | 2/7 | System TRUSTED but should not be |
| Unnecessary Abstain | 0 | |

## 8. VLM Four-Gate

| Gate | Result |
|------|--------|
| V1 Frequency (≥5/30 cases) | PASS (5 ROAD_SPLIT cases) |
| **V2 Deterministic Exhausted** | **PARTIAL** — OSM tag heuristic exhausted, but deterministic road features not yet tested |
| V3 Visual/Semantic Nature | PASS (Road role requires semantic interpretation) |
| V4 Testable Hypothesis | PASS (B8 can measure ΔRankingRegret) |
| **FINAL** | **ELIGIBLE_FOR_EXPERIMENT (B8-V)** |

**V2 Correction:** VLM Gate PASS does not mean "deterministic methods exhausted". Only OSM highway tag heuristic was tested. B8-D (Deterministic Road Semantic Features) must be run before concluding VLM is necessary.

## 9. P1 Capability Decisions

| Capability | Decision | Evidence |
|------------|:--------:|----------|
| Building Membership | **REFACTOR** | 6 D4 affected cases; 4 primary root cause |
| Boundary Segmentation | **DEFER** | No segmentation-specific failure evidence |
| Scene Renderer | **REJECT** | No evidence VLM visualization is bottleneck |
| **VLM Framework** | **ADD (EXPERIMENT_ONLY)** | VLM Gate PASS for B8-V experiment only |
| Confidence Calibration | **DEFER** | False Trusted = 0; no calibration failure |
| Vector Reconstruction | **DEFER** | Geometry quality not primary failure mode |
| Shared Topology | **REFACTOR** | 5 ROAD_SPLIT cases show separator/gap issues |

## 10. Next Architecture Decision

**MAIN HYPOTHESIS:** H-RS-01 — Road Semantic Interpretation improves Ranking Regret without increasing False Trusted.

**Three-arm experiment:**
- **Control:** B6 (geometric ranking)
- **Treatment A:** B8-D (Deterministic Road Semantic Features)
- **Treatment B:** B8-V (VLM Road Semantic Features)

**NOT IN SCOPE (deferred to R9):**
- Building Membership REFACTOR
- Shared Topology REFACTOR
- Multi-source building fusion (B5 ≈ best single source)
- Scene Renderer (REJECTED)
- General VLM (road semantic only, B8-V experiment only)
