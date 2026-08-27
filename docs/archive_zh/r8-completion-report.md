# R8 Road Semantic Interpretation Experiment — Completion Report

**Hypothesis:** H-RS-01 — Road Semantic Interpretation improves Ranking Regret without increasing False Trusted.

**Evaluation:** BJ-RS-0021 ~ BJ-RS-0025 (5 ROAD_SPLIT cases)

**Data:** 500 real Beijing residential polygons (Geofabrik OSM)

---

## 1. Three-Arm Results (Top1 Quality)

| Case | Name | N | B6 | B8-D | B8-V | B8-D Δ | B8-V Δ |
|------|------|:-:|:--:|:----:|:----:|:------:|:------:|
| BJ-RS-0021 | 劲松五区 | 5 | 0.30 | 0.750 | 1.000 | +0.450 | +0.700 |
| BJ-RS-0022 | 昌平松园小区 | 2 | 0.30 | 0.600 | 1.000 | +0.300 | +0.700 |
| BJ-RS-0023 | 青年路国美第一城 | 5 | 0.30 | 0.750 | 1.000 | +0.450 | +0.700 |
| BJ-RS-0024 | 亦庄天华园三里 | 5 | 0.30 | 0.750 | 1.000 | +0.450 | +0.700 |
| BJ-RS-0025 | 回龙观龙泽苑 | 5 | 0.30 | 0.750 | 1.000 | +0.450 | +0.700 |

## 2. Aggregate Metrics

| Metric | B6 | B8-D | B8-V |
|--------|:--:|:----:|:----:|
| Avg Top1 Quality | 0.300 | 0.720 | 1.000 |
| Δ vs B6 | — | **+0.420** | **+0.700** |
| B8-V Δ vs B8-D | — | — | **+0.280** |
| Win/Tie/Loss vs B6 | — | 5/0/0 | 5/0/0 |
| FalseTrusted | 0 | 0 | 0 |

## 3. Decision Analysis

| Rule | Threshold | Result | Status |
|------|:---------:|:------:|:------:|
| B8-D ≥ δ (δ=0.10) | Δ ≥ 0.10 | Δ = 0.420 | **PASS** |
| B8-V ≥ δ (δ=0.10) | Δ ≥ 0.10 | Δ = 0.700 | **PASS** |
| B8-V ≥ B8-D + ε (ε=0.03) | Δ ≥ 0.03 | Δ = 0.280 | **PASS** |
| FalseTrusted = 0 | = 0 | 0 | **PASS** |

## 4. Verdict

**Road semantics valuable, VLM has independent increment over deterministic.**

**Decision:** VLM eligible for external validation.

## 5. Next Step

1. **External Validation** — Run B8-V on unseen ROAD_SPLIT / MULTI_PHASE cases (e.g., BJ-RS-0006, BJ-RS-0010, plus reserve cases)
2. If external validation replicates the improvement → VLM upgrade to `KEEP / INTEGRATE`
3. If not → revert to B8-D deterministic only

## 6. Safety

FalseTrusted remained 0 across all three arms. The safety baseline is preserved.