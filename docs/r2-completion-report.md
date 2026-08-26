# R2 Baseline Boundary Providers — Final Completion Report

**阶段：** R2 — Baseline Provider Implementation
**状态：** R2.0–R2.5 全部通过，Level 1 & Level 2 测试通过，Legacy Allowlist 归零

---

## 1. 交付物矩阵与成熟度状态

| 模块 / Provider | 实现状态 | 验证状态 | 架构状态 | 说明 |
|:---|:---|:---|:---|:---|
| `ProviderRequest` / `ProviderContext` | `IMPLEMENTED` | `UNIT_TESTED` | `ACCEPTED` | 包含 `SeedObservation` (带不确定度半径) 及显式 `AreaPrior` |
| `ExistingOpenBoundaryProvider` | `IMPLEMENTED` | `BENCHMARKED` | `ACCEPTED` | 经受真实北京 OSM 住宅多边形验证（上地东里等），`name` 作为特征输出 |
| `RoadBlockProvider` | `IMPLEMENTED` | `BENCHMARKED` | `ACCEPTED` | 分离为 `STRONG_ONLY` 与 `STRONG_PLUS_WEAK` 两个 Candidate Family |
| `BuildingClusterProvider` | `IMPLEMENTED` | `BENCHMARKED` | `ACCEPTED` | 支持 `BuildingSourcePolicy` (OSM/Overture/MS/Multi-source) 与单源聚类隔离 |
| `AreaPriorBaseline` | `IMPLEMENTED` | `BENCHMARKED` | `ACCEPTED` | 仅限 B0 试验，严格隔离先验污染，标记 `EXPERIMENTAL` |
| `CandidateRankingEngine` | `IMPLEMENTED` | `UNIT_TESTED` | `ACCEPTED` | 独立排序，支持 B6 几何特征与 B7 语义特征增量 |
| `BaselineExperimentProfile` | `IMPLEMENTED` | `UNIT_TESTED` | `ACCEPTED` | 冻结 B0–B7 候选池合并（Candidate Pool Fusion）规则 |
| `MetricGeometryService` | `IMPLEMENTED` | `UNIT_TESTED` | `ACCEPTED` | 统一米制服务入口，EPSG:32650 投影与 Shapely 深度集成 |

---

## 2. Legacy Metric Allowlist 归零审计

```text
Production Callers (legacy metric_crs):    0  ✅ [CLEARED]
Search Approximation Callers (allowed):    4  ✅ [STRICTLY ISOLATED]
  - src/providers/baselines.py:74 (bbox_from_center for spatial search window)
  - src/providers/baselines.py:161 (bbox_from_center for spatial search window)
  - src/providers/baselines.py:258 (bbox_from_center for spatial search window)
  - src/agents/boundary_reasoning_agent.py:14 (degree_offset_for_meters for search bbox)
```

所有生产级面积、距离、缓冲、吸附与拓扑容差计算全部迁移至 `MetricGeometryService`（基于 EPSG:32650 投影 CRS 计算），杜绝了伪米制与度量混淆。

---

## 3. 测试与验证结果

### Level 1: Deterministic Fixture Integration
- **测试文件：** `tests/test_r2_integration.py`
- **结果：** 7/7 用例全部通过，验证了 Provider 接口隔离、生成与排序解耦、无自宣布 TRUSTED。

### Level 2: Real Beijing OSM Snapshot Smoke Test
- **数据源：** 北京真实 Geofabrik/OSM 空间数据快照（`data/beijing_fixtures/`）
  - `residential_500.json` (500 个真实住宅多边形)
  - `roads_strong_500.json` (500 条主干路网)
  - `buildings_500.json` (500 栋建筑轮廓)
- **测试文件：** `tests/test_r2_real_osm_smoke.py`
- **验证通过链路：**
  `真实北京 OSM 数据 -> Observation -> Baseline Provider -> MetricGeometryService -> ProviderHypothesis -> CandidateRankingEngine`
- **结论：** 数据链路全部走通，所有输出候选保持 `PROPOSED`，无硬编码与先验泄漏。

---

## 4. 关键原则落实核对

1. **先验隔离：** `AreaPrior` 仅对 B0 开放，B1–B7 默认禁用。
2. **种子容差：** `SeedObservation` 引入 `uncertainty_radius_m`，取代强硬点包含过滤。
3. **分群隔离：** 多源建筑聚类采用“按源独立聚类生成假设 -> 外部排序组合”方案，避免多源重叠污染。
4. **生成与排序分离：** Provider 仅负责提出假设与提取空间特征，不决定最终信任与权重。
5. **真实数据验证：** 真实北京数据通过快照冻结，保证 CI/CD 确定性与现实贴合度。

---

**建议结论：** R2 (Baseline Boundary Provider Implementation) 全部验收通过，正式闭环，可以进入 **R3 Validation Gate 完整性验证**。
