# R8 Road Semantic Interpretation Experiment Design Note v1.1

**Main Hypothesis:** H-RS-01 — ROAD_SPLIT 的主要瓶颈不是 Candidate Generation，而是无法正确识别道路的空间分隔语义；更好的 Road Semantic Interpretation 可以降低 Ranking Regret，而不增加 False Trusted。

**Evaluation Subset:** BJ-RS-0021 ~ BJ-RS-0025 (5 ROAD_SPLIT cases)

**Anti-overfitting:** These 5 cases are the **one-shot evaluation set**. No tuning on evaluation cases during development. Use synthetic fixtures or non-Benchmark OSM data for feature engineering.

---

## 1. Three-arm Experiment

| Arm | Description | Road Semantics |
|-----|------------|----------------|
| **Control (B6)** | Geometric ranking only | Existing coarse OSM-tag heuristic (highway=primary/secondary/tertiary) |
| **Treatment A (B8-D)** | B6 candidates + DeterministicRoadInterpreter | Deterministic road semantic features (class, width, continuity, building connectivity) |
| **Treatment B (B8-V)** | B6 candidates + VLMRoadInterpreter | VLM outputs: structured road-role assertions only |

**Frozen across all arms:**
- Candidate Set: identical to B6
- Gold: R5 frozen
- Case: BJ-RS-0021 ~ BJ-RS-0025 (5 ROAD_SPLIT cases)
- Ranking base: identical
- **Common downstream:** same Ranking Adapter, same Validation Pipeline

---

## 2. Common Semantic Output Contract

Both B8-D and B8-V must produce the same `RoadSemanticAssertion` schema, consumed by the same Ranking Adapter. This ensures the only variable is the **Road Semantic Interpreter**.

```text
RoadSemanticAssertion

road_segment_id: str
road_role:
  PUBLIC_SEPARATOR     # 公共城市道路构成强分隔
  INTERNAL_ACCESS      # 小区内部道路
  WEAK_SEPARATOR       # 服务道路/消防通道/模糊边界
  AMBIGUOUS            # 无法判断
continuity:
  THROUGH              # 贯穿整片区域
  TERMINATING          # 在区域内终止
  LOCAL                # 局部短连接
compound_split_support:
  SUPPORT              # 支持将两侧分为不同 Compound
  AGAINST              # 不支持分割
  UNKNOWN              # 证据不足
evidence_features: dict
producer:
  DETERMINISTIC        # B8-D
  VLM                  # B8-V
```

---

## 3. Pre-registered Metrics & Thresholds

### Primary Metric
- **ΔRankingRegret** (OracleQuality - Top1Quality), normalized 0–1

### Secondary Metrics
- ΔTop1Quality
- Correct Split Rate
- Over-Split Rate
- Under-Split Rate

### Safety Gate
- **FalseTrusted must remain 0.** If any Treatment increases FalseTrusted > 0, it cannot be ACCEPTED.

### Decision Thresholds (pre-registered)

| Threshold | Value | Meaning |
|-----------|-------|---------|
| ε (equivalence) | ΔRegret ≤ 0.03 | Treatments are equivalent |
| δ (material improvement) | ΔRegret ≥ 0.10 | Treatment materially improves over Control |

### Decision Rules

| Result | Decision |
|--------|----------|
| B8-D - B6 ≥ δ, B8-V - B8-D ≤ ε | VLM not needed; keep deterministic |
| B8-D - B6 ≥ δ, B8-V - B8-D ≥ δ | VLM has independent increment |
| B8-D - B6 ≤ ε, B8-V - B6 ≥ δ | VLM route validated |
| B8-D - B6 ≤ ε, B8-V - B6 ≤ ε | H-RS-01 not supported |
| Any Treatment FalseTrusted > 0 | Rejected from Trusted Path |

### Statistical approach (5 cases only)
- Paired per-case comparison
- Win / Tie / Loss count
- Median ΔRankingRegret
- Effect threshold (ε, δ) — not p-value

---

## 4. VLM Experiment Manifest

Pre-registered before B8-V execution:

```text
VLMExperimentManifest

model_name: str
model_version: str
prompt_version: str
system_prompt_hash: str
input_schema: str
visual_input_spec: str
context_window: int
temperature: float
top_p: float
seed: int
max_tokens: int
retry_policy: str
structured_output_schema: str
inference_runtime: str
```

### Visual Input

B8-V requires a minimal vector-to-image renderer for VLM consumption. This is strictly an **experimental input adapter**, not a restoration of the P1 Scene Renderer capability. It must be:

- Deterministic: same input → same image
- Minimal: roads, buildings, candidate boundaries only
- No styling configurability
- Not integrated into the production pipeline

---

## 5. Corrected Trust & Abstention Baseline

| Metric | Value | Definition |
|--------|:-----:|------------|
| False Trusted | 0 | System output `TRUSTED` but Gold ≠ GOLD_RESOLVED |
| Failure to Abstain | 2/7 | System output ≠ `UNRESOLVED` but Gold = GOLD_UNRESOLVED (e.g. PROVISIONAL, READY_WITH_WARNING) |
| Correct Abstention | 5/7 | System output `UNRESOLVED` and Gold = GOLD_UNRESOLVED |
| Observation Ceiling cases | 7 | OLD_OPEN x4, DANWEI x2, LOW density x1 |

**Clarification:** `False Certainty` renamed to `FailureToAbstain`. The 2 cases produced `PROVISIONAL` or `READY_WITH_WARNING`, not `TRUSTED`. False Trusted remains 0 — the safety baseline for R8.

---

## 6. R8 Acceptance Gate

```text
[ ] 5 ROAD_SPLIT cases all execute 3 arms
[ ] B8-D and B8-V produce identical RoadSemanticAssertion schema
[ ] Common Ranking Adapter consumes both output types
[ ] VLMExperimentManifest frozen before execution
[ ] ε and δ thresholds pre-registered
[ ] No tuning on evaluation cases during development
[ ] FalseTrusted tracked per arm
[ ] Paired per-case results reported
[ ] Decision rules applied post-hoc
[ ] External validation set identified (if VLM wins)
```

---

## 7. R8 Completion Decision Tree

```
B8-D > B6, B8-V ≈ B8-D
  → Road semantics valuable, VLM no independent value
  → KEEP deterministic, REJECT VLM integration

B8-D > B6, B8-V > B8-D
  → Road semantics valuable, VLM has independent increment
  → VLM eligible for external validation

B8-D ≈ B6, B8-V > B6
  → VLM provides semantic capability deterministic cannot
  → Strongest evidence for VLM

B8-D ≈ B8-V ≈ B6
  → H-RS-01 not supported
  → Stop Road Semantic architecture expansion
```

Even if B8-V wins, the next step is **External Validation** on unseen ROAD_SPLIT / MULTI_PHASE cases, not production integration.