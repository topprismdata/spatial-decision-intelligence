# R2 Baseline Boundary Provider Design Note v1.1

**项目：** Spatial Decision Intelligence
**阶段：** R2 — Baseline Provider Implementation
**上游：** R1 Metric CRS（ACCEPTED_WITH_FINDINGS）
**v1.1 修正：** 8 项 Benchmark Isolation 修复（见 §12）

---

## 1. R2 目标

R2 不是：

- 实现所有可能的边界生成算法
- 引入 VLM 或 ML
- 扩展 Ontology
- 进入 P2

R2 是：

> **实现 4 个可真实运行的 Baseline Provider，使 B0-B7 实验可以启动。**

R2 的核心约束是 Benchmark Isolation：

> B0-B7 每升一级，到底增加了什么信息，必须能够被严格归因。

---

## 2. Provider Contract

### ProviderRequest

```text
ProviderRequest
  target_entity_id: str
  target_boundary_role: BoundaryRole  # PHYSICAL_BOUNDARY / MANAGEMENT_BOUNDARY / ...
  seed_observations: list[SeedObservation]
  context: ProviderContext
  optional_priors: Optional[Priors]
```

### SeedObservation

```text
SeedObservation
  point: (lng, lat)
  source: str
  observed_at: str
  positional_quality: str  # HIGH / MEDIUM / LOW
  uncertainty_radius_m: float
```

Provider 可用 Seed 做搜索锚点，但**不得普遍要求 Polygon 必须包含 Seed**。合法的空间关系包括：

- `candidate intersects seed uncertainty region`
- `candidate is within search tolerance`

### Priors

```text
Priors
  area_prior: Optional[AreaPrior]

AreaPrior
  value_m2: float
  source_observation_id: str
  provenance: str
  allowed_experiments: tuple[str, ...]  # e.g. ("B0",)
```

**B1-B7 默认禁止使用 Gold / existing target area prior。** AreaPrior 仅限 B0 AreaPriorBaseline 使用。如需单独测试面积先验增量，应作为独立 Ablation 运行。

### ProviderResult

```text
ProviderResult
  status: ProviderStatus  # APPLICABLE / NOT_APPLICABLE / ERROR
  hypotheses: tuple[BoundaryHypothesis, ...]
  evidence: tuple[Evidence, ...]
  provenance: ProviderProvenance
```

### ProviderProvenance

```text
ProviderProvenance
  provider_id: str
  provider_version: str
  algorithm_version: str
  source_observation_ids: tuple[str, ...]
  source_dataset_releases: tuple[str, ...]
  parameter_profile: str
  metric_crs: str
  transform_chain: str
  generated_at: str
```

### 规则

- Provider 在无数据时必须返回 `NOT_APPLICABLE`
- Provider **不得直接宣布 `TRUSTED`**（`HypothesisStatus.PROPOSED` 止步）
- Provider **只负责生成，不负责排序**
- Provider 不得使用 `confidence` 字段；改用 `generation_score` / `provider_features`

---

## 3. 四个 Baseline Provider

### 3.1 ExistingOpenBoundaryProvider

**允许使用的证据：**

- OSM `landuse=residential`（**不要求 `name` 存在**）— 所有开放 Polygon 均可进入候选池
- 已知来源语义标注的 Polygon（保留 `source_semantic_role`：`RESIDENTIAL_LANDUSE` / `PROPERTY_MANAGEMENT_AREA` / `KNOWN_RESIDENTIAL_BOUNDARY` / `PARCEL` / `OTHER`）

**provider_features：**
- `name_present: bool` — 是否存在 `name` 标签（用于后续 Ranking，不用于决定候选资格）
- `source_semantic_role: str`
- `seed_distance_m: float`
- `polygon_area_m2: float`

**算法：**

```
1. 在 seed point 搜索半径内加载开放 Polygon
2. 筛选：空间上与 seed uncertainty region 相交
3. 生成所有候选，保留来源语义角色
4. 输出 list[BoundaryHypothesis]（全部 PROPOSED）
```

**不适用时：** 无匹配开放 Polygon → `NOT_APPLICABLE`

### 3.2 RoadBlockProvider

**允许使用的证据：**

- OSM road network
- 使用 versioned Baseline Road Profile（见 §7）

**Road 语义角色（RoadBlockBaselineProfile v1）：**

```text
strong_separator: primary, secondary, tertiary, trunk, motorway
weak_separator: primary_link, secondary_link, tertiary_link, service
excluded: footway, path, cycleway, bridleway, track, pedestrian, steps
```

参数版本化，不承诺 Road Role Truth。

**算法：**

生成两个 Candidate Family：

```
Family A: ROAD_STRONG_ONLY
1. 在 seed point 搜索半径内加载 road network
2. 仅使用 strong_separator
3. 构建道路封闭街区
4. 筛选与 seed uncertainty region 相交的街区
5. 输出候选（PROPOSED）

Family B: ROAD_STRONG_PLUS_WEAK
1. 相同 road network
2. 使用 strong_separator + weak_separator
3. 构建道路封闭街区
4. 筛选与 seed uncertainty region 相交的街区
5. 输出候选（PROPOSED）
```

**provider_features：**
- `road_profile_variant: str` — "STRONG_ONLY" 或 "STRONG_PLUS_WEAK"
- `strong_edge_count: int`
- `weak_edge_count: int`
- `seed_distance_m: float`
- `block_area_m2: float`

**不适用时：** 无 road data → `NOT_APPLICABLE`

### 3.3 BuildingClusterProvider

**允许使用的证据：**

- 由 `BuildingSourcePolicy` 控制

**BuildingSourcePolicy：**

```text
OSM_ONLY
OVERTURE_ONLY
MICROSOFT_ONLY
MULTI_SOURCE
```

**Multi-source duplicate policy（方案 A — 推荐）：**

```
Per-source clustering
→ per-source hypotheses
→ later fusion/ranking
```

禁止将三源 footprint 直接 union 到同一池子聚类。

**算法：**

```
1. 根据 BuildingSourcePolicy 加载指定源
2. 在 seed 搜索半径内聚类（米制距离阈值）
3. 筛选与 seed uncertainty region 相交的 cluster
4. 对每个 cluster 构建 concave hull
5. 输出所有候选（全部 PROPOSED）
```

**不适用时：** 无 building data → `NOT_APPLICABLE`

### 3.4 AreaPriorBaseline

**允许使用的证据：**

- 仅 seed point + AreaPrior（来自 Priors）
- 无任何外部数据

**算法：**

```
1. 以 seed point 为中心
2. 以 area_prior 计算等效半径
3. 生成圆形缓冲区
4. 标记为 EXPERIMENTAL BASELINE
5. 输出 1 个候选（PROPOSED）
```

**始终适用：** 只要有 seed point 和 AreaPrior 即可生成

---

## 4. BaselineExperimentProfile — B0-B7 组成契约

B0-B7 由 Provider 按以下规则组成。**不进行 Geometry Fusion**，只做 Candidate Pool Fusion（候选集合合并）。

```text
B0
AreaPriorBaseline only

B1
ExistingOpenBoundary only

B2
RoadBlock only (both STRONG_ONLY and STRONG_PLUS_WEAK families)

B3
BuildingCluster single-source runs (per BuildingSourcePolicy)

B4
RoadBlock candidates
+
BuildingCluster candidates
→ candidate pool
→ geometric ranking

B5
Per-source BuildingCluster candidates
→ multi-source candidate pool
→ geometric ranking

B6
ExistingOpenBoundary candidates
+
RoadBlock candidates
+
BuildingCluster candidates
→ candidate pool
→ geometric ranking

B7
Same candidate pool as B6
+
public semantic evidence features
→ semantic ranking
```

### BaselineExperimentProfile

```text
BaselineExperimentProfile

experiment_id: str
enabled_providers: list[str]
provider_profiles: dict
building_source_policy: str
ranking_policy: str
semantic_features_enabled: bool
area_prior_enabled: bool
```

原则冻结：

- B4/B5/B6 不做 Geometry Fusion（union / intersection / weighted fusion）
- 真正的 Geometry Fusion 须待 Benchmark 证明需要后再启动
- AreaPrior 仅限 B0


## 5. Provider 使用 MetricGeometryService

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
list[BoundaryHypothesis]  (all PROPOSED, generation_score set)
  ↓
CandidateRankingEngine.rank(candidates, semantic_evidence)
  ↓
list[CandidateRankRecord]
  hypothesis_id
  ranking_score
  ranking_features
  ranking_policy_version
```

- Provider **只负责生成**，不负责排序、不筛选最高匹配
- Provider 输出 `generation_score`（或 `provider_features`），**不得使用 `confidence`**
- `CandidateRankingEngine` 独立于 Provider
- B7 是 Semantic Ranking 增量，**不是新增 Provider**

### B7 设计

```
B6: Open Vector Candidate Generation
        ↓
CandidateRankingEngine (geometric features only)

B7: same candidates
        ↓
CandidateRankingEngine (geometric + public semantic evidence features)
```

B7 不新建 Provider，只扩展 Ranking 特征。

---

## 6. BoundaryHypothesis Provenance

```text
BoundaryHypothesis
  id: str
  entity_id: str
  geometry: str  # WKT
  generator: str  # provider name
  generation_score: float  # NOT confidence
  provider_features: dict[str, float]  # e.g. seed_distance_m, area_m2, building_count
  evidence: tuple[Evidence, ...]
  status: HypothesisStatus  # PROPOSED
  metadata: {
    "metric_crs": "EPSG:32650",
    "transform_chain": "...",
    "algorithm_version": "v1.0",
    "parameters": {...}
  }
```

`confidence` 字段从 R2 Provider 输出中移除。真正 `confidence` 留给 Evidence Validation + Calibration 阶段。

---

## 7. RoadBlockBaselineProfile v1

| 类别 | 标签 | 说明 |
|:---|:---|:---|
| `strong_separator` | `primary`, `secondary`, `tertiary`, `trunk`, `motorway` | 形成强边界证据 |
| `weak_separator` | `primary_link`, `secondary_link`, `tertiary_link`, `service` | 弱边界证据 |
| `excluded` | `footway`, `path`, `cycleway`, `bridleway`, `track`, `pedestrian`, `steps` | 不参与街区构建 |

参数版本化，不承诺 Road Role Truth。后续可被 Road Semantic Reasoning 替代。

---

## 8. R2 验收场景

| 场景 | 条件 | 预期 |
|:---|:---|:---|
| P1 | ExistingOpenBoundary — seed 在已知 OSM Polygon 内 | 返回该 Polygon + 来源语义角色 |
| P2 | ExistingOpenBoundary — 无数据 | `NOT_APPLICABLE` |
| P3 | RoadBlock — seed 在道路封闭街区中 | 返回街区 Polygon |
| P4 | BuildingCluster — seed 在 building cluster 中 | 返回 cluster hull |
| P5 | AreaPriorBaseline | 返回圆形缓冲区，标注 `EXPERIMENTAL BASELINE` |
| P6 | 全部 Provider 使用 MetricGeometryService | 不直接调用 legacy `metric_crs.py` |
| P7 | Legacy Allowlist 清零 | `candidate_fusion.py` / `ai_fence_guard.py` / `boundary_reasoning_agent.py` 不再引用 legacy metric |
| P8 | 全部 Provider 输出 `PROPOSED`，不使用 `confidence` | `HypothesisStatus.PROPOSED`，使用 `generation_score` |
| P9 | BuildingCluster 支持 SourcePolicy | `OSM_ONLY` / `OVERTURE_ONLY` / `MICROSOFT_ONLY` / `MULTI_SOURCE` |
| P10 | RoadBlock 使用 versioned Road Profile | 明确 strong/weak/excluded 三类 |

---

## 9. R2 Acceptance Gate

| Gate | 条件 | 验证 |
|:---|:---|:---|
| Gate 1 | 4 个 Provider 全部实现 | P1-P5 |
| Gate 2 | 全部使用 MetricGeometryService | P6 |
| Gate 3 | Legacy Allowlist 清零 | P7 |
| Gate 4 | 无 Provider 自宣布 TRUSTED 或使用 confidence | P8 |
| Gate 5 | BuildingCluster 支持 SourcePolicy | P9 |
| Gate 6 | RoadBlock 使用 versioned Road Profile | P10 |
| Gate 7 | 无新增 legacy metric 调用 | Regression Guard |

---

## 10. 禁止

- 新增任何 Provider 类型（仅限 4 个 Baseline）
- 在 Provider 中引入 VLM / ML
- 修改 Ontology
- 实现 Evidence Fusion 学习化
- 进入 P2
- Provider 自己宣布 TRUSTED
- B1-B7 使用 AreaPrior（除非显式标注 Ablation）
- 三源 Building 直接 union 聚类
- Provider 内使用 `confidence` 字段

---

## 11. Legacy Metric Allowlist

```text
LegacyMetricGuard

Existing Allowlist:
- candidate_fusion.py
- ai_fence_guard.py
- boundary_reasoning_agent.py

Policy:
- 不允许新增 legacy caller
- R2 每迁移一个旧 caller，从 allowlist 删除
- R2 完成时 allowlist 必须为 0

R2 Acceptance requires legacy_metric_allowlist == empty
```

---

## 12. v1.1 修正清单

| # | 问题 | 修正 |
|:---|:---|:---|
| 1 | `target_area_m2` 是公共必填，导致 Benchmark Leakage | 改为 `AreaPrior`，显式可追溯，B1-B7 默认禁用 |
| 2 | `seed_point` 被当作 Ground Truth | 改为 `SeedObservation` + `uncertainty_radius_m`，不要求 Polygon 必须包含 Seed |
| 3 | Provider 内含 ranking / highest-match 逻辑 | 全部删除，Provider 只生成，Ranking 独立 |
| 4 | `confidence: 0-1` 在 Hypothesis 中 | 改为 `generation_score` + `provider_features`，`confidence` 留给 Calibration 阶段 |
| 5 | 缺少 `target_boundary_role` | 加入 `ProviderRequest.target_boundary_role` |
| 6 | Building 三源无 Source Policy 和 duplicate 处理 | 增加 `BuildingSourcePolicy` + per-source clustering |
| 7 | RoadBlock 使用所有 highway 类型 | 增加 versioned `RoadBlockBaselineProfile v1`（strong/weak/excluded） |
| 8 | `provenance: str` 太弱 | 改为结构化 `ProviderProvenance`；B7 明确为 Semantic Ranking 增量 |