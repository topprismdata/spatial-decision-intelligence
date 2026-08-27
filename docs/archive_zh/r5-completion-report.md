# R5 Source Manifest & Gold Adjudication — Completion Report

**阶段：** R5 — Source Manifest + Gold Adjudication  
**契约状态：** G01–G16 验收测试全部 100% 通过，R5 正式 `ACCEPTED`

---

## 1. 核心交付物

| 交付项 | 文件路径 | 说明 |
|:---|:---|:---|
| 设计规范 | `docs/r5-source-manifest-and-gold-adjudication-design-note.md` | 八步裁决协议 (G1–G8)、认识论、Entity/Boundary 分离、Gold Independence |
| Gold 契约与枚举 | `src/gold/__init__.py` | `GoldState`, `EvidenceSufficiency`, `SegmentStatus`, `BuildingMembershipState`, `DependencyType`, `SourceFamily`, `SourceSemanticRole`, `AuthorityScope`, `CueType` |
| Gold 数据模型 | `src/gold/models.py` | `SourceManifestEntry`, `CaseSourceManifest`, `SourceDependency`, `EvidenceBundle`, `GoldAssertion`, `GoldEntityState`, `GoldBoundaryState`, `GoldBoundarySegment`, `BoundaryUncertaintyZone`, `GoldReviewConflict`, `GoldCaseVersion`, `GoldCorrectionRecord`, `MetricEligibility`, `GoldCase` |
| 裁决引擎 | `src/gold/adjudicator.py` | `GoldAdjudicator` (G1–G8), `CeilingReportGenerator` |
| 验收测试 | `tests/test_r5_gold_adjudication.py` | G01–G16 全部通过 |

---

## 2. 验收核查表 (G1–G16)

```text
[✓] G01: 30 Case 全部拥有冻结 Source Manifest (版本/许可证/访问时间)
[✓] G02: 每个 Source 具有版本/许可证/访问时间
[✓] G03: 所有 Gold Assertion 可追溯到 Evidence Bundle
[✓] G04: Source Dependency 已显式记录 (INDEPENDENT/PARTIALLY_DEPENDENT/DERIVED/UNKNOWN)
[✓] G05: Entity Gold 与 Boundary Gold 分离
[✓] G06: Estate / Phase / Compound 结构完成或显式 UNRESOLVED
[✓] G07: Physical Boundary Role 与其他 Boundary Role 分离
[✓] G08: Building Membership 有 MEMBER/NON_MEMBER/AMBIGUOUS/UNKNOWN 四态
[✓] G09: Boundary 支持 Segment-level uncertainty
[✓] G10: Gold Reviewer 未看到 Provider/Ranking/Validation 输出 (Gold Independence)
[✓] G11: GOLD_UNRESOLVED 是有效状态，不被删除或替换
[✓] G12: Gold Freeze 可复现 (版本化 + 内容哈希)
[✓] G13: 每个 Case 已标 Metric Eligibility
[✓] G14: Observation Ceiling Report 已生成
[✓] G15: Independent Review 完成 (冲突记录)
[✓] G16: Gold Assertion 本体类型丰富
```

---

## 3. Gold Independence 验证

通过静态代码分析确认 `GoldAdjudicator` 中**零引用**以下系统模块：

- `ProviderHypothesis`
- `CandidateRankingEngine`
- `BoundaryHypothesis`
- `ProviderResult`
- `ValidationResult`

Gold 裁决无法接触到任何 Provider、Ranking 或 Validation 输出，确保 Gold Independence 硬性隔离。

---

## 4. 关键技术决策

1. **Gold 不是单一 Polygon**：`GoldEntityState` 与 `GoldBoundaryState` 完全分离，`GoldBoundaryState` 内支持 `BoundaryUncertaintyZone` 表达线性不确定区域。
2. **Assertion-first 裁决**：所有 Gold 结论以 `GoldAssertion` 为单位，每个 Assertion 绑定 `EvidenceBundle`，支持局部冲突与局部 `GOLD_UNRESOLVED`。
3. **Source Manifest 版本化**：每个 Case 的 `SourceManifestEntry` 包含 `source_url`、`license`、`license_version`、`retrieved_at`、`content_hash`，确保可追溯。
4. **Evidence Independence**：`SourceDependency` 数据结构支持 `INDEPENDENT` / `PARTIALLY_DEPENDENT` / `DERIVED` / `UNKNOWN` 四类依赖关系，防止混合来源重复计算证据。

---

**R5 正式闭环。建议放行 R6 B0–B7 Open-Data Benchmark。**