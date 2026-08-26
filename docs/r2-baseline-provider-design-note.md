# R2 Baseline Boundary Provider Design Note v1.0

**项目：** Spatial Decision Intelligence
**阶段：** R2 — Baseline Provider Implementation
**上游：** R1 Metric CRS（ACCEPTED_WITH_FINDINGS）
**目标：** 实现 4 个 Baseline Provider，清零 LegacyMetric Allowlist

---

## 1. R2 目标

R2 不是：

- 实现所有可能的边界生成算法
- 引入 VLM 或 ML
- 扩展 Ontology
- 进入 P2

R2 是：

> **实现 4 个可真实运行的 Baseline Provider，使 B0-B7 实验可以启动。**

---

## 2. Provider Contract

### 输入

每个 Provider 接收：

```text
entity_id: str
seed_point: (lng, lat)
target_area_m2: float
context: ProviderContext
```

其中 `ProviderContext` 包含：

```text
observations: list[Observation]  # 可用数据源
metric_service: MetricGeometryService  # 统一米制计算
```

### 输出

```text
ProviderResult
  status: APPLICABLE / NOT_APPLICABLE / ERROR
  hypotheses: list[BoundaryHypothesis]
  evidence: list[Evidence]
  provenance: str
```

### 规则

- Provider 在无数据时必须返回 `NOT_APPLICABLE`
- Provider 不得直接宣布 `TRUSTED`（`HypothesisStatus.PROPOSED` 止步）
- Candidate Generation 与 Candidate Ranking 严格分离

---

## 3. 四个 Baseline Provider

### 3.1 ExistingOpenBoundaryProvider

**允许使用的证据：**

- OSM `landuse=residential` 且存在 `name` 且边界与 seed point 空间一致
- 任何其他开放数据源中已存在的闭合 Polygon

**算法：**

```
1. 在 seed point 附近搜索开放 Polygon
2. 筛选：包含 seed point、面积在 target_area 合理范围内
3. 返回最高匹配的 Polygon 作为候选
```

**不适用时：** 无匹配开放 Polygon → `NOT_APPLICABLE`

### 3.2 RoadBlockProvider

**允许使用的证据：**

- OSM road network（所有 `highway` 类型）
- 仅用于形成道路封闭街区

**算法：**

```
1. 在 seed point 周围加载 road network
2. 构建道路封闭街区（road-enclosed block）
3. 筛选包含 seed point 的街区
4. 按面积匹配度排序
```

**不适用时：** 无 road data → `NOT_APPLICABLE`

### 3.3 BuildingClusterProvider

**允许使用的证据：**

- OSM Buildings
- Overture Buildings
- Microsoft Buildings

**算法：**

```
1. 在 seed point 周围加载 building footprints
2. 聚类（距离阈值，米制）
3. 对每个 cluster 构建 concave hull
4. 筛选包含 seed point 的 cluster
5. 按面积匹配度排序
```

**不适用时：** 无 building data → `NOT_APPLICABLE`

### 3.4 AreaPriorBaseline

**允许使用的证据：**

- 仅 seed point + target area
- 无任何外部数据

**算法：**

```
1. 以 seed point 为中心
2. 以 target_area 计算等效半径
3. 生成圆形缓冲区
4. 标记为 EXPERIMENTAL BASELINE
```

**始终适用：** 只要有 seed point 即可生成

---

## 4. Provider 如何使用 MetricGeometryService

所有 Provider 的几何操作必须通过 `MetricGeometryService`：

```
Provider
  ↓
MetricCRSStrategy.select(extent, centroid, operation_type, benchmark_profile="Beijing")
  ↓
GeometryTransformer.to_metric_geometry(wkt, selection, operation_type)
  ↓
MetricGeometry (projected CRS)
  ↓
shapely operation (buffer / area / distance / cluster)
  ↓
GeometryTransformer.inverse_transform → EPSG:4326
  ↓
BoundaryHypothesis
```

禁止：

- Provider 内直接使用 `meters_per_degree_*`
- Provider 内直接调用 `shapely.buffer(degree_value)`
- Provider 自己选择 CRS

---

## 5. Candidate Generation 与 Ranking 严格分离

```
Provider.generate_candidates()
  ↓
list[BoundaryHypothesis]  (all PROPOSED)
  ↓
CandidateRankingEngine.rank(candidates)
  ↓
list[BoundaryHypothesis]  (sorted by score, still PROPOSED)
  ↓
ValidationPipeline.run()
  ↓
list[ValidationResult]
```

- Provider 只负责生成，不负责排序
- `CandidateRankingEngine` 独立于 Provider
- 排序结果不改变 `HypothesisStatus`

---

## 6. BoundaryHypothesis Provenance

每个 `BoundaryHypothesis` 必须包含：

```text
generator: "ExistingOpenBoundaryProvider" / "RoadBlockProvider" / ...
confidence: 0.0-1.0
evidence: list[Evidence]  # 引用了哪些 Observation
metadata: {
  "metric_crs": "EPSG:32650",
  "transform_chain": "...",
  "algorithm_version": "v1.0",
  "parameters": {...}
}
```

---

## 7. R2 验收场景

### P1 — ExistingOpenBoundaryProvider

seed point 在已知 OSM residential Polygon 内 → 返回该 Polygon

### P2 — ExistingOpenBoundaryProvider 无数据

seed point 不在任何开放 Polygon 内 → `NOT_APPLICABLE`

### P3 — RoadBlockProvider

seed point 在道路封闭街区中 → 返回街区 Polygon

### P4 — BuildingClusterProvider

seed point 在 building cluster 中 → 返回 cluster hull

### P5 — AreaPriorBaseline

始终返回圆形缓冲区，标注 `EXPERIMENTAL BASELINE`

### P6 — Metric CRS 集成

所有 Provider 的几何操作使用 `MetricGeometryService`，不直接调用 legacy `metric_crs.py`

### P7 — Legacy Allowlist 清零

R2 完成时，`candidate_fusion.py`、`ai_fence_guard.py`、`boundary_reasoning_agent.py` 不再引用 legacy metric 模块

### P8 — 不允许 Provider 自宣布 TRUSTED

所有 Provider 输出的 `HypothesisStatus` 必须为 `PROPOSED`

---

## 8. R2 Acceptance Gate

| Gate | 条件 | 验证方法 |
|:---|:---|:---|
| Gate 1 | 4 个 Provider 全部实现 | P1-P5 验收 |
| Gate 2 | 全部使用 MetricGeometryService | P6 验收 |
| Gate 3 | Legacy Allowlist 清零 | P7 验收 |
| Gate 4 | 无 Provider 自宣布 TRUSTED | P8 验收 |
| Gate 5 | 无新增 legacy metric 调用 | Regression Guard 通过 |

---

## 9. 禁止

- 新增任何 Provider 类型（仅限 4 个 Baseline）
- 在 Provider 中引入 VLM / ML
- 修改 Ontology
- 实现 Evidence Fusion 学习化
- 进入 P2
- Provider 自己宣布 TRUSTED