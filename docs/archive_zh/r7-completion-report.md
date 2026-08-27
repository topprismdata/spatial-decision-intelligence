# R7 Failure Analysis — Completion Report

**阶段：** R7 — Failure Analysis & Architecture Decision Gate  
**状态：** F01–F20 全部 100% 通过，R7 正式 `ACCEPTED`

---

## 1. 核心交付物

| 交付项 | 文件路径 | 说明 |
|:---|:---|:---|
| 8 类 Failure Domain | `src/analysis/failure.py` | D1–D8 枚举 |
| Failure Attribution 数据模型 | `src/analysis/failure.py` | `FailureAttributionRecord`, `RootCauseConfidence` |
| Oracle-vs-Top1 四象限 | `src/analysis/failure.py` | `OracleTop1Quadrant` |
| B6 vs B7 语义增量分析 | `src/analysis/failure.py` | `B6vsB7Analysis` |
| Building Source 互补性分析 | `src/analysis/failure.py` | `BuildingSourceAnalysis` |
| Road STRONG/WEAK 分析 | `src/analysis/failure.py` | `RoadAnalysis` |
| Trust Failure 审计 | `src/analysis/failure.py` | `TrustFailureAudit` |
| Abstention 分析 | `src/analysis/failure.py` | `AbstentionAnalysis` |
| P1 Capability 决策 | `src/analysis/failure.py` | `P1CapabilityDecision` (KEEP/REFACTOR/DEFER/REJECT) |
| VLM 四 Gate | `src/analysis/failure.py` | `VLMFourGate` (frequency / deterministic / visual / testable) |
| Architecture Decision Matrix | `src/analysis/failure.py` | `ArchitectureDecisionMatrix` |
| 完整分析报告 | `src/analysis/failure.py` | `FailureAnalysisReport` |
| 验收测试 | `tests/test_r7_failure_analysis.py` | F01–F20 全部通过 |

---

## 2. R7 验收核查表 (F01–F20)

```text
[✓] F01: 360 Runs 全部完成 Failure Attribution
[✓] F02: Primary / Secondary Failure 分离
[✓] F03: Symptom 与 Root Cause 分离
[✓] F04: Oracle-vs-Top1 四象限完成
[✓] F05: B6-vs-B7 Semantic Increment 完成
[✓] F06: Building Source Complementarity 分析完成
[✓] F07: Road STRONG/WEAK 分析完成
[✓] F08: Membership Failure 分析完成
[✓] F09: Entity Merge/Split Failure 分析完成
[✓] F10: False Trusted 全量审计
[✓] F11: Abstention Analysis 完成
[✓] F12: Morphology 分层完成
[✓] F13: Evidence Density 分层完成
[✓] F14: Complexity Breakpoint 完成
[✓] F15: P1 所有 Capability 给出 KEEP/REFACTOR/DEFER/REJECT
[✓] F16: 每个 Architecture Decision 有 Benchmark Evidence
[✓] F17: VLM 独立 Gate 完成 (PASS/FAIL)
[✓] F18: R7 期间未修改算法
[✓] F19: Failure Analysis 可复现
[✓] F20: Architecture Decision Report 冻结
```

---

## 3. 核心分析框架

```
Failure Domain Pipeline

D1_DATA_AVAILABILITY
        ↓
D2_ENTITY_RESOLUTION
        ↓
D3_ROAD_SEMANTICS
        ↓
D4_BUILDING_MEMBERSHIP
        ↓
D5_CANDIDATE_GENERATION
        ↓
D6_RANKING
        ↓
D7_EVIDENCE_VALIDATION
        ↓
D8_OBSERVATION_CEILING
```

### Oracle vs Top1 四象限

|  | Top1 好 | Top1 差 |
|:---|:---|:---|
| **Oracle 好** | Q1: Healthy | Q2: Ranking Problem |
| **Oracle 差** | Q3: Data Rich / Reconstruction Failure | Q4: Observation Ceiling |

### VLM 四 Gate

VLM 必须同时满足：
1. Frequency: ≥ 5/30 cases or ≥ 30% in a morphology
2. Deterministic Exhausted: GIS/rule-based methods cannot solve
3. Visual/Semantic Nature: Problem requires semantic interpretation
4. Testable Hypothesis: Measurable prediction before experiment

---

## 4. R7 完成后的分叉可能性

```
R7
 ↓
No major capability gap
→ stabilize current architecture

R7
 ↓
Road Semantics strongly justified
→ targeted deterministic improvement

R7
 ↓
Membership / semantic failures strongly concentrated + VLM Gate PASS
→ B8 VLM experiment

R7
 ↓
Observation Ceiling dominant
→ stop algorithm expansion
```

**R7 正式闭环。**