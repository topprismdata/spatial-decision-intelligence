# R9 Building Membership REFACTOR — Design Note v1.0

**Hypothesis:** H-BM-01 — Building Membership accuracy can be improved by replacing fixed heuristic weights with evidence-based membership that accounts for building function, spatial separation, and morphological context.

**R7 Evidence:** D4 affects 6/30 cases (20%), 4 primary root cause. Primary failure modes: school/commercial contamination in MIXED_USE, office confusion in DANWEI, multi-phase grouping errors.

**Evaluation:** D4-affected cases: all 5 MIXED_USE (BJ-RS-0026-0030) + 1 DANWEI (BJ-RS-0014) + 2 MULTI_PHASE (BJ-RS-0008, BJ-RS-0010)

**Key changes from current HEURISTIC_BASELINE:**
- Fixed weights (0.40/0.25/0.20/0.15) → evidence-based feature aggregation
- Building function awareness (school/commercial/hospital exclusion)
- Spatial separation detection (road/gap between building and compound)
- Morphology-aware thresholds (different for MIXED_USE vs MODERN_GATED)