# Spatial Decision Intelligence — R5 Source Manifest & Gold Adjudication Design Note v1.0

**项目：** Spatial Decision Intelligence  
**阶段：** R5 — Source Manifest + Gold Adjudication  
**上游：** R4 30-Case Selection & Review (`ACCEPTED`)  
**下游：** R6 B0–B7 Open-Data Benchmark  
**核心原则：** Gold 必须独立于评测系统（Gold Independence），诚实记录现实证据支持边界，允许明确的 `GOLD_UNRESOLVED`。

---

## 1. 核心流程与 8 步裁决协议 (G1–G8 Protocol)

```text
G1: Source Freeze (冻结每个 Case 的所有开放数据源元数据)
         │
         ▼
G2: Entity Candidate Review (实体候选池初步审查，不碰几何)
         │
         ▼
G3: Estate / Phase / Compound 结构裁决 (确立社会认知与物理单元层级)
         │
         ▼
G4: Structural Evidence Review (建筑、道路、出入口、物理分隔物审查)
         │
         ▼
G5: Boundary Segment Adjudication (边界逐段裁决 + 不确定性带标记)
         │
         ▼
G6: Evidence Sufficiency Decision (独立判定证据充分性与 GoldState)
         │
         ▼
G7: Independent Review & Conflict Resolution (双盲复审与冲突裁定)
         │
         ▼
G8: Gold Freeze (生成防篡改版本哈希与 Gold World State 冻结文件)
```

---

## 2. 认识论与状态矩阵

| 状态类型 | 取值枚举 | 核心语义 |
|:---|:---|:---|
| **GoldState** | `GOLD_RESOLVED` / `GOLD_PARTIAL` / `GOLD_UNRESOLVED` | 最终世界解释能被开放证据确定到什么程度 |
| **EvidenceSufficiency** | `SUFFICIENT` / `PARTIAL` / `INSUFFICIENT` | 当前开放证据在数量与独立性上是否充足 |
| **SegmentStatus** | `CONFIRMED` / `SUPPORTED` / `UNCERTAIN` / `UNRESOLVED` / `CONFLICTED` | 边界线段局部的微观可信度 |
| **BuildingMembership** | `MEMBER` / `NON_MEMBER` / `AMBIGUOUS` / `UNKNOWN` | 建筑物理隶属关系裁定 |
| **DependencyType** | `INDEPENDENT` / `PARTIALLY_DEPENDENT` / `DERIVED` / `UNKNOWN` | 数据源间的派生依赖关系 |
