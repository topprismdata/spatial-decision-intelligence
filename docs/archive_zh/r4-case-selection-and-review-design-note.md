# Spatial Decision Intelligence — R4 北京住宅 30-Case Selection & Review Design Note v1.0

**项目：** Spatial Decision Intelligence
**阶段：** R4 — 30 个真实北京住宅 Case 选取与评审
**上游：** R3 Validation Gate Verification (`ACCEPTED`)
**下游：** R5 Source Manifest + Gold Adjudication
**核心原则：** Case Selection 必须独立于算法表现（Selection Blindness），杜绝便利抽样与先验泄漏。

---

## 1. 核心流程与防作弊规则 (Anti-Bias Pipeline)

```text
真实北京开放数据 (OSM / Geofabrik / Overture)
              │
              ▼
   Candidate Universe 发现池构建
              │
              ▼
   粗去重与合格性初筛 (Eligibility Screening)
              │
              ▼
   90-Case Eligible Pool (6 大形态 × 15)
              │
              ▼
   受约束抽样 (Constrained Sampling, 固定 seed=42)
              │
              ├───► 30 个正式 Benchmark Cases (6 形态 × 5)
              └───► 12 个备用 Reserve Cases (6 形态 × 2)
              │
              ▼
   盲审评审 (Blind Review, 仅看观测与空间事实，零算法/Polygon)
              │
              ▼
   BeijingResidentialCaseRegistry v0.1 最终冻结
```

---

## 2. 分层与配额要求 (Quotas & Strata)

1. **Morphology 配额 (严格 6 × 5 = 30)**:
   - `MODERN_GATED` (现代封闭社区): 5
   - `MULTI_PHASE` (多期住宅): 5
   - `DANWEI_COURTYARD` (单位大院): 5
   - `OLD_OPEN` (开放老旧社区): 5
   - `ROAD_SPLIT` (公共道路切割): 5
   - `MIXED_USE` (商住/学校混合): 5

2. **Geography 配额 (全域覆盖)**:
   - `CORE_URBAN` (核心城区，东西城/朝阳海淀核心): 10
   - `INNER_SUBURB` (近郊城区，丰台/石景山/昌平顺义核心): 8
   - `URBAN_FRINGE` (城乡结合部): 7
   - `OUTER_NEWTOWN` (远郊新城，房山/通州/怀柔密云平谷大兴): 5

3. **Evidence Density 配额**:
   - `HIGH` (≥3 类独立证据家族): 8
   - `MEDIUM` (2 类有效证据): 14
   - `LOW` (仅基本身份或结构残缺，用于测定天花板): 8

4. **Complexity 预期分布**:
   - `SIMPLE`: 6 | `MODERATE`: 8 | `HARD`: 10 | `EXTREME`: 6

5. **Cross-Strata 交叉规则**:
   - 每种 Morphology 至少跨越 2 个地理区位。
   - HIGH / MEDIUM / LOW 各至少覆盖 4 种 Morphology。
   - `ROAD_SPLIT`、`MIXED_USE`、`MULTI_PHASE` 每组至少含 3 个 HARD/EXTREME 案例。
