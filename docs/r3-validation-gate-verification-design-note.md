# R3 Validation Gate Verification Design Note v1.0

**项目：** Spatial Decision Intelligence
**阶段：** R3 — Validation Contract Verification Gate
**性质：** 契约校验与门控语义冻结（不新增算法，不扩大开发）
**上游：** R2 Baseline Provider Implementation (`ACCEPTED`)
**下游：** R4 30-Case Real Beijing Benchmark

---

## 1. R3 目标与范围

R3 是进入真实数据 Benchmark (R4–R6) 之前的**门控语义闭环验证**。
R3 不做新的校验算法开发，仅严格验证：
1. **四大 Gate 语义稳定性**：`OntologyGate`、`GeometryGate`、`EvidenceGate`、`DecisionReadinessGate`。
2. **状态与处置判定规则**：`ValidationStatus` (PASSED / WARNED / FAILED / BLOCKED) 与组合规则。
3. **分权机制**：`FinalDisposition` (TRUSTED / PROVISIONAL / UNRESOLVED / REJECTED) 与 `DecisionReadiness` (Consumer-Aware READY 状态) 严格解耦。
4. **组合测试矩阵**：通过 12–16 个覆盖各种边界与异常组合的单元测试，确保 R4 的所有判决确定且可复现。

---

## 2. 四大 Gate 契约与输入输出

每个 Gate 遵循统一接口：
```python
def validate(context, hypothesis) -> ValidationResult
```

### 2.1 Ontology Gate
- **输入**：`target_entity_type: OntologyType`, `target_boundary_role: BoundaryRole`, `hypothesis: BoundaryHypothesis`
- **规则**：
  - 非法/未定义本体类型 -> `FAILED`
  - 角色冲突（如将 `ResidentialEstate` 的粗大区域作为 `PHYSICAL_BOUNDARY` 且无子实体划分） -> `WARNED` / `BLOCKED`
- **输出**：`ValidationResult(validator="OntologyGate", status=...)`

### 2.2 Geometry Gate
- **输入**：`hypothesis: BoundaryHypothesis`, `metric_service: MetricGeometryService`
- **规则**：
  - 空几何、非多边形、解析异常 -> `BLOCKED`
  - 拓扑自相交、非法环 -> `BLOCKED`
  - 面积异常 (< 100 m² 或 > 5,000,000 m²，基于 EPSG:32650 投影计算) -> `FAILED`
  - 狭长碎屑、极低紧凑度 -> `WARNED`
- **输出**：`ValidationResult(validator="GeometryGate", status=...)`

### 2.3 Evidence Gate
- **输入**：`hypothesis: BoundaryHypothesis`, `evidence_list: list[Evidence]`
- **规则**：
  - 0 证据支持 -> `FAILED` (导致 UNRESOLVED)
  - 仅单一弱先验证据 (如仅 B0 面积圆) -> `WARNED` (最多进入 PROVISIONAL)
  - 存在明确排除证据/矛盾证据 -> `BLOCKED`
  - 多源独立证据支撑 -> `PASSED`
- **输出**：`ValidationResult(validator="EvidenceGate", status=...)`

### 2.4 Decision Readiness Gate (Consumer-Aware)
- **输入**：`previous_gate_results: list[ValidationResult]`, `hypothesis: BoundaryHypothesis`, `consumer: ConsumerProfile`
- **规则**：
  - 前序 Gate 存在 `BLOCKED` -> 对所有 Consumer `NOT_READY`
  - 满足特定业务场景门槛（如 `VisitCheckIn` 仅需大致范围且容忍警告 -> `READY`；`TerritoryOptimization` 要求极高几何完整与拓扑一致 -> `NOT_READY`）
- **输出**：`ValidationResult(validator="DecisionReadinessGate/{consumer.name}", status=...)`

---

## 3. FinalDisposition 与 DecisionReadiness 严格分离

```text
[四大 Gate 验证结果]
         │
         ├───► FinalDisposition 判定 (客观空间世界信任状态)
         │       ├── TRUSTED      (所有前序 Gate 均 PASSED，多源证据充分)
         │       ├── PROVISIONAL  (存在非致命 WARNING，如单源数据或紧凑度较低)
         │       ├── UNRESOLVED   (证据不足或存在歧义，系统主动弃权 Abstain)
         │       └── REJECTED     (存在硬性 BLOCKED，如几何损坏、严重越界)
         │
         └───► DecisionReadiness 评估 (下游特定消费者使用就绪度)
                 ├── Consumer A (VisitCheckIn)          ──► READY
                 └── Consumer B (TerritoryOptimization)  ──► NOT_READY
```

**铁律**：`DecisionReadiness` 不得篡改 `FinalDisposition`；下游消费系统只能消费通过 `FinalDisposition` 准入后的 `Trusted / Provisional Projection`。

---

## 4. 组合验证测试矩阵 (14 Cases)

| 用例 ID | Ontology | Geometry | Evidence | 预期 FinalDisposition | 预期 Consumer A (Visit) | 预期 Consumer B (Territory) | 说明 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **V01** | PASSED | PASSED | PASSED | `TRUSTED` | `READY` | `READY` | 完美黄金样本 |
| **V02** | PASSED | **BLOCKED** | PASSED | `REJECTED` | `NOT_READY` | `NOT_READY` | 几何自交/空几何直接否决 |
| **V03** | **FAILED** | PASSED | PASSED | `REJECTED` | `NOT_READY` | `NOT_READY` | 本体类型未定义/非法 |
| **V04** | PASSED | PASSED | **FAILED** | `UNRESOLVED` | `NOT_READY` | `NOT_READY` | 0 证据支撑，主动弃权 |
| **V05** | PASSED | PASSED | **WARNED** | `PROVISIONAL` | `READY` | `NOT_READY` | 单一弱证据，宽容业务可用，严苛业务禁用 |
| **V06** | PASSED | **WARNED** | PASSED | `PROVISIONAL` | `READY` | `NOT_READY` | 几何微瑕（紧凑度低/略小），降级入库 |
| **V07** | **WARNED** | PASSED | PASSED | `PROVISIONAL` | `READY` | `READY_WITH_WARNING` | 角色存在层级模糊但物理明确 |
| **V08** | PASSED | **FAILED** | PASSED | `REJECTED` | `NOT_READY` | `NOT_READY` | 面积超界（> 5km² 孤立错误多边形） |
| **V09** | PASSED | PASSED | **BLOCKED** | `REJECTED` | `NOT_READY` | `NOT_READY` | 存在致命排除冲突证据 |
| **V10** | **BLOCKED** | **BLOCKED** | **FAILED** | `REJECTED` | `NOT_READY` | `NOT_READY` | 全面崩塌，严格阻断 |
| **V11** | PASSED | PASSED | PASSED | `TRUSTED` | `READY` | `NOT_READY` | 消费者置信度阈值过滤测试（Hypothesis 分数 0.75，Territory 需 0.90） |
| **V12** | PASSED | **WARNED** | **WARNED** | `PROVISIONAL` | `READY_WITH_WARNING` | `NOT_READY` | 多重非致命告警累加 |
| **V13** | PASSED | PASSED | PASSED | `TRUSTED` | `READY` | `NOT_READY` | 消费者要求拓扑一致性检查但未提供拓扑证明 |
| **V14** | PASSED | PASSED | PASSED | `TRUSTED` | `READY` | `READY` | 高分独立双源证据确认 |

---

## 5. R3 验收标准 (Acceptance Gate)

- [ ] 四大 Gate 接口定义确定，无单一 `qa_score` 绕过硬门控。
- [ ] 实现了独立的 `FinalDisposition` 计算器与 `DecisionReadinessGate`。
- [ ] 14 个组合矩阵测试全部在真实 `MetricGeometryService` 与 Domain 契约下 100% 通过。
- [ ] 门控判定全过程完整输出结构化 `findings` 与 `provenance`。
- [ ] 验收通过后直接放行 R4（30 个真实北京 Case 选取与标注）。
