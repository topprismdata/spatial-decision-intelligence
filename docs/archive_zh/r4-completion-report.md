# R4 30-Case Selection & Review — Completion Report

**阶段：** R4 — 30 个真实北京住宅 Case 选取与盲审  
**状态：** S01–S12 验收测试全部 100% 通过，Case Registry v0.1 已正式冻结并提交  

---

## 1. 核心执行结论

1. **严格坚持选择盲目性 (Selection Blindness)**：
   - 候选池构建与抽样逻辑完全基于实体名称、真实空间位置与开放数据粗分类，**零 Provider 输出、零 Gold Polygon、零 IoU/评分先验泄漏**。
2. **>=90 个 Eligible Pool 规模验证**：
   - 从北京全域真实候选池中遴选出 90 个有效种子样本（6 大形态各 15 个）。
3. **受约束抽样机制 (Constrained Sampling)**：
   - 固定随机种子 `random_seed=42`，完全可复现生成 30 个正式 Benchmark Cases（`BJ-RS-0001` ~ `BJ-RS-0030`）以及 12 个备用 Reserve Cases（`BJ-RS-RES-0001` ~ `BJ-RS-RES-0012`）。
4. **配额与交叉约束 100% 达标**：
   - **形态**：6 大形态严格各 5 个。
   - **地理**：核心城区 9 / 近郊 5 / 城乡结合部 8 / 远郊新城 8（远郊不缺席）。
   - **证据密度**：HIGH 12 / MEDIUM 11 / LOW 7（LOW 案例有效保留以测定天花板）。
   - **复杂度**：HARD/EXTREME 达 21 个（70%），杜绝挑选容易样本。
5. **盲审全通过**：
   - 30 个正式案例通过 7 项非几何盲审（`BlindReviewRunner`），无数据损坏、无跨组重复实体。

---

## 2. 交付物一览

| 交付文件 | 说明 |
|:---|:---|
| `docs/r4-case-selection-and-review-design-note.md` | R4 选样与盲审设计规范 |
| `src/benchmark/case_selector.py` | 90-Case Eligible Pool 构建与约束抽样引擎 |
| `src/benchmark/blind_review.py` | 盲审检查器与替换记录器 |
| `tests/test_r4_case_selection.py` | S01–S12 验收测试集 |
| `docs/beijing-residential-case-registry-v0.1.md` | 30 正式案例 + 12 备用案例冻结花名册 |

---

## 3. R4 验收标准核查表

```text
[X] S01: Candidate Universe 可重复生成
[X] S02: Eligible Pool >= 90 (实际 90)
[X] S03: 六类 Morphology 每类 Pool >= 15 (实际各 15)
[X] S04: 最终 30 Case 每类 Morphology = 5
[X] S05: Geography 配额覆盖 (Core/Inner/Fringe/Outer 均覆盖)
[X] S06: Evidence Density 配额覆盖 (High/Med/Low 均覆盖)
[X] S07: Cross-Strata 跨层约束全满足 (每形态跨>=2地理层，Density跨>=4形态)
[X] S08: Sampling Seed 固定后 100% 确定性复现
[X] S09: 零算法/Polygon 泄漏
[X] S10: 12 个 Reserve Case 冻结 (每形态 2 个)
[X] S11: 替换记录模式就绪 (R01-R05)
[X] S12: 30 Cases 盲审 100% 通过
```

**建议结论：** R4 (30-Case Selection & Review) 验收全部通过，正式闭环，放行进入 **R5 Source Manifest + Gold Adjudication**。
