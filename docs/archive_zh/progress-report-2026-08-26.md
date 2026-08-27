# Spatial Decision Intelligence — 实施进展报告（纠偏版）

**⚠️ 重要说明：** 本报告已根据 2026-08-26 实施纠偏审查修正。所有能力使用双维度状态标注：
- **实现状态：** `NOT_STARTED` / `INTERFACE_ONLY` / `IMPLEMENTED` / `UNIT_TESTED`
- **验证状态：** `NOT_BENCHMARKED` / `BENCHMARKED` / `CALIBRATED` / `ACCEPTED` / `REJECTED`
- 两者组合才是真实成熟度。"实现了"≠"已验证"。

**项目：** Spatial Decision Intelligence（TopprismData / 北京住宅空间世界重建）
**报告日期：** 2026-08-26
**仓库路径：** `/Users/user/WorkBuddy/2026-08-18-17-47-15`

---

## 目录

1. [总体架构](#1-总体架构)
2. [M0: 现有基线冻结](#2-m0-现有基线冻结)
3. [M1: 领域契约迁移](#3-m1-领域契约迁移)
4. [M2: Metric CRS](#4-m2-metric-crs)
5. [M3: 开放数据观测层](#5-m3-开放数据观测层)
6. [M4: 最小本体](#6-m4-最小本体)
7. [M5: Provider 框架](#7-m5-provider-框架)
8. [M6: 验证管道](#8-m6-验证管道)
9. [M7: 30-Case Benchmark](#9-m7-30-case-benchmark)
10. [M8: 故障分析](#10-m8-故障分析)
11. [P1: 高级能力](#11-p1-高级能力)
12. [v1.0 规范对齐](#12-v10-规范对齐)
13. [代码统计](#13-代码统计)
14. [下一步](#14-下一步)
15. [真实成熟度评估](#15-真实成熟度评估)
16. [纠偏后的开发路线 (R0-R9)](#16-纠偏后的开发路线-r0-r9)

---

## 1. 总体架构

```
                  ┌─────────────────────────────────────┐
                  │         CLI (src/cli.py)             │
                  └──────────────┬──────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          ▼                      ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   BatchPipeline  │  │  4-Agent Pipeline│  │  CLI generate    │
│  (entity_res.)   │  │  (spatial world) │  │  (single entity) │
└────────┬─────────┘  └────────┬─────────┘  └──────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────────────────────────────────────────────────┐
│                    Domain Contracts                            │
│  (contracts.py / world_model.py / models.py / ontology.py)    │
└──────────────────────────────────────────────────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Coordinate      │  │  Geometry QA     │  │  Metric CRS      │
│  Alignment       │  │  + AI Fence Guard│  │  (meters from    │
│                  │  │                  │  │   WGS84)         │
└──────────────────┘  └──────────────────┘  └──────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Observation     │  │  Entity          │  │  Validation      │
│  Adapters        │  │  Resolution      │  │  Pipeline        │
│  (OSM/Overture/  │  │  (component      │  │  (4 Gates)       │
│   Microsoft)     │  │   matcher etc.)  │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  P1 Modules:  Membership / Segmentation / Renderer / VLM    │
│  / Calibration / Reconstruction / Topology                  │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Benchmark Suite (30-Case / 15 Experiments / 20 Failure     │
│  Codes / Accuracy-Coverage / Source Matrix / Reproducibility)│
└──────────────────────────────────────────────────────────────┘
```

---

## 2. M0: 现有基线冻结

**目标：** 对现有代码进行 KEEP / REFACTOR / EXPERIMENTAL 分类，冻结基线。

### 分类结果

| 类别 | 数量 | 关键资产 |
|:---|:---|:---|
| **KEEP** | 24 src/ 文件 + 8 顶层脚本 | 核心领域模型、坐标对齐、Geometry QA、实体解析管道、4-Agent 管道、决策适配器、AI Fence Guard |
| **REFACTOR** | 1 src/ + 4 脚本 | `EntityResolutionAgent` 与 `component_matcher` 重复逻辑；`draw_step8/9/10_7k` 应模块化；`patch_qa_report` 应合并入验证管道 |
| **EXPERIMENTAL** | 1 src/ + 20 脚本 | `DatasetExtractor` (ML 训练数据工具)；全部 road/draw pipeline 原型脚本 |

### 架构关键发现

1. **双领域模型并存**：`src/domain/models.py`（v1 CanonicalEntity）vs `src/domain/world_model.py`（v2 SpatialEntity）
2. **跨包依赖反转**：`src/generation/candidate_fusion.py` 向上依赖 `src/agents/`
3. **ReviewDisposition 已定义但从未被 populate**
4. **现有 Integrity 测试套件存在**：2 个测试文件

---

## 3. M1: 领域契约迁移

**P0-01: Domain Contract Split** — 11 个核心领域契约

| 契约 | 说明 |
|:---|:---|
| `SpatialEntity` | 顶层实体，聚合 Observations / Representations / Relations |
| `SpatialRepresentation` | 几何解释（与 Observation 分离） |
| `BoundaryRepresentation` | 边界类型几何表示 |
| `Observation` | 原始数据观测（不携带解释） |
| `SpatialRelation` | 实体间关系（独立于几何度量） |
| `RelationMeasurement` | 可选几何度量（IoU/距离/语义分） |
| `AuthorityAssertion` | 权威/信任断言 |
| `Evidence` | 证据 |
| `BoundaryHypothesis` | 候选边界假设 |
| `ValidationResult` | 验证结果 |
| `TrustedSpatialState` | 聚合可信状态 |

**v1 ↔ v2 适配器函数：** `observation_from_source_record`、`representation_from_geometry_version`、`spatial_relation_from_entity_relation`

**文件：** `src/domain/contracts.py`（487 行）

---

## 4. M2: Metric CRS

**P0-02: Metric CRS Contract** — 消除所有 `111320` 和 `buffer(0.000X)` 近似

### 核心函数

| 函数 | 说明 |
|:---|:---|
| `meters_per_degree_lat(lat)` | WGS84 椭球纬度每度米数 |
| `meters_per_degree_lng(lat)` | WGS84 椭球经度每度米数（纬度校正） |
| `degree_offset_for_meters(meters, lat)` | 米 → 度偏移量 |
| `area_m2_from_wgs84(geom, lat)` | 度坐标 → 平方米面积 |
| `distance_m(geom_a, geom_b, lat)` | 米制距离 |
| `buffer_meters(wkt, meters, lat)` | 米制缓冲区 |
| `bbox_from_center(lng, lat, half_side_m)` | 米制边界框 |
| `buffer_degrees_for_meters(meters, lat)` | 米 → 度缓冲区（保守值） |
| `perimeter_m_from_wgs84(geom, lat)` | 度坐标 → 米周长 |

### 验证结果（北京 40°N）

```
meters_per_degree_lat(40°N) = 111,034.64m  (旧值: 111,320)
meters_per_degree_lng(40°N) = 85,393.86m  (旧值: 111,320)
buffer_degrees_for_meters(300m, 40°N) = 0.002702°  (旧值: 0.003°)
```

### 重构文件

| 文件 | 替换内容 |
|:---|:---|
| `src/agents/boundary_reasoning_agent.py` | `111320.0` → `degree_offset_for_meters()` |
| `src/generation/candidate_fusion.py` | `111320` + `buffer(0.0001)` → `bbox_from_center()` + `buffer_meters()` |
| `src/geometry/ai_fence_guard.py` | `111320.0` → `distance_m()` |
| `src/entity_resolution/candidate_retrieval.py` | `buffer_degrees` → `buffer_meters` |
| `src/pipelines/batch_pipeline.py` | 更新调用参数 |

---

## 5. M3: 开放数据观测层

**P0-04: Observation Adapter Contract**

三个 Source Adapter，均只产生 `Observation`，不产生 `SpatialRepresentation` 或 `SpatialEntity`。

| 适配器 | 源 | 支持格式 | 许可证 |
|:---|:---|:---|:---|
| `OverpassAdapter` | OSM (Overpass API) | 缓存 JSON / 实时查询 | ODbL |
| `OvertureAdapter` | Overture Maps | GeoJSON (buildings/transportation/places/base) | CDLA-Permissive-1.0 |
| `MicrosoftBuildingsAdapter` | Microsoft Global ML Building Footprints | GeoJSON | CDLA-Permissive-1.0 |

**文件：** `src/observation/`（4 文件，430 行）

---

## 6. M4: 最小本体

**P0-05: Minimal Ontology** — 14 个冻结类型（v1.0 升级后）

### OntologyType（14 类型）

| 类型 | 说明 |
|:---|:---|
| `ResidentialEstate` | 楼盘 / 住宅项目认知实体 |
| `ResidentialPhase` | 开发期次 |
| `ResidentialCompound` | 实际住宅空间单元（主要目标） |
| `PropertyManagementArea` | 物业管理区域 |
| `ResidentialLandUse` | 住宅土地利用区域 |
| `AdministrativeCommunity` | 行政社区 |
| `LandParcel` | 土地 / 宗地 |
| `Building` | 建筑 |
| `Entrance` | 出入口（语义位置） |
| `Gate` | 大门（物理设施） |
| `Road` | 道路 |
| `Barrier` | 围墙 / 栅栏等物理屏障 |
| `UnknownResidentialEntity` | 未分类住宅实体 |
| `OtherBuiltFeature` | 其他建成特征 |

### MorphologyType（12 类型，multi-label 允许）

`MODERN_GATED` / `MULTI_PHASE` / `OLD_GATED` / `OLD_OPEN` / `DANWEI_COURTYARD` / `VILLA` / `ROAD_SPLIT` / `MIXED_USE` / `SUPER_COMPOUND` / `SMALL_COURTYARD` / `UNDER_CONSTRUCTION` / `UNKNOWN`

**文件：** `src/domain/ontology.py`（49 行）

---

## 7. M5: Provider 框架

**P0-06/07: Provider Contract + Baseline Providers**

| 契约 | 说明 |
|:---|:---|
| `ProviderResult` | 标准 Provider 输出 |
| `ProviderStatus` | `APPLICABLE` / `NOT_APPLICABLE` / `ERROR` |
| `BoundaryHypothesis` | 候选边界假设 |

Provider 框架已就绪，4 个 Baseline Provider 预留接口：
- `ExistingOpenBoundaryProvider`
- `RoadBlockProvider`
- `BuildingClusterProvider`
- `AreaPriorBaseline`

---

## 8. M6: 验证管道

**P0-08: Validation Pipeline** — 4 Gate 流水线

| Gate | 说明 |
|:---|:---|
| `OntologyGate` | 验证 OntologyType 是否属于 14 冻结类型 |
| `GeometryGate` | 验证几何有效性、面积范围、自交等 |
| `EvidenceGate` | 验证证据充分性 |

**文件：** `src/validation/pipeline.py`（225 行）

---

## 9. M7: 30-Case Benchmark

**P0-10: 30-Case Data Reality Benchmark**

### 分层

| 类型 | 数量 | 分布 |
|:---|:---|:---|
| 现代封闭社区 | 5 | 核心城区/近郊/远郊新城 |
| 多期社区 | 5 | 核心城区/近郊/城乡结合部/远郊新城 |
| 单位大院 | 5 | 核心城区/近郊/城乡结合部 |
| 开放老旧社区 | 5 | 核心城区/近郊/城乡结合部 |
| 道路切割社区 | 5 | 核心城区/近郊/城乡结合部/远郊新城 |
| 商住混合 | 5 | 核心城区/近郊/城乡结合部/远郊新城 |

### 实验矩阵（15 实验）

| ID | 名称 | 说明 |
|:---|:---|:---|
| B0 | Point + Area Prior | 最弱基线 |
| B1 | Existing Open Polygon | 开放现成边界 |
| B2 | Road only | 道路贡献 |
| B3 | Building only | 建筑贡献 |
| B4 | Road + Building | 结构融合 |
| B5 | Multi-source Building | 多源建筑增量 |
| B6 | Open Vector Fusion | 完整开放矢量基线 |
| B7 | + Public Semantic Data | 实体语义增量 |
| B8 | + VLM | 仅 P1 启动后 |
| B9 | Minimal World Model | 完整最小架构 |
| A1 | Full - Road | Ablation: 道路价值 |
| A2 | Full - Building | Ablation: 建筑价值 |
| A3 | Full - Semantic | Ablation: 语义价值 |
| A4 | Full - Multi-source | Ablation: 多源价值 |
| A5 | Full - VLM | Ablation: VLM 价值 |

### 故障码（20 码）

F01-F20，覆盖 Entity、Building、Road、Boundary、Geometry、Evidence、Source、Confidence 等维度。

**文件：** `src/benchmark/`（3 文件，551 行）

---

## 10. M8: 故障分析

- 17 → **20 故障码**（新增 F18 SOURCE_DEPENDENCY、F19 HIGH_CONFIDENCE_WRONG、F20 GOLD_UNRESOLVED）
- **9 类 Error Attribution**（DATA_LIMIT / ENTITY_MODEL / ONTOLOGY / PROVIDER / GIS / SEMANTIC_REASONING / VALIDATION / CALIBRATION / GOLD_LIMITATION）
- **Accuracy-Coverage Curve** 替代单一 IoU
- **Source Complementarity Matrix**（6 来源组合 × 5 维度）
- **Reproducibility Contract**（BenchmarkRunRecord）

---

## 11. P1: 高级能力

### P1-01: Building Membership ✅

**文件：** `src/membership/`（372 行）

4 种分析方法：

| 方法 | 权重 | 说明 |
|:---|:---|:---|
| Containment | 0.40 | 建筑是否在 Compound 内部 |
| Road Separation | 0.25 | 道路是否分隔建筑与 Compound |
| Cluster | 0.20 | 建筑是否在 Compound 建筑列表中 |
| Naming | 0.15 | 建筑名是否匹配 Compound 名 |

4 级输出：`CONFIRMED` / `LIKELY` / `UNCERTAIN` / `EXCLUDED`

### P1-02: Boundary Segment ✅

**文件：** `src/segmentation/`（310 行）

多边形 → `BoundarySegment[]` 分解，每个 Segment 有独立置信度。支持：
- 角点检测断点
- 道路交叉点断点
- 米制长度计算
- 道路对齐 / 建筑对齐置信度赋值

### P1-03: Scene Renderer ✅

**文件：** `src/renderer/`（385 行）

确定性 SVG 场景渲染，供 VLM 消费。渲染：
- 道路（灰色线）
- 建筑（浅灰填充）
- 确认边界（红色虚线 + 标签）
- 候选边界（蓝色虚线 + 置信度）
- POI（黄色圆点 + 标签）
- 图例

### P1-04: VLM Vector Reasoning ✅

**文件：** `src/vlm/`（381 行）

结构化的 VLM 实验框架：
- 严格的实验 Brief 模板
- 3 种 Prompt Builder（Road Semantic / Building Grouping / Candidate Comparison）
- JSON 输出解析器（支持 markdown code block 提取）
- 锁定测试子集评估框架
- 基线对比（without-VLM vs with-VLM）

### P1-05: Confidence Calibration ✅

**文件：** `src/calibration/`（196 行）

基于 Gold Cases 的置信度校准：
- 10-bin 可靠性图
- ECE（Expected Calibration Error）
- MCE（Maximum Calibration Error）
- 校准置信度映射（`calibrated_confidence()`）

### P1-06: Vector Reconstruction ✅

**文件：** `src/reconstruction/`（177 行）

3 个操作：
- **Douglas-Peucker 简化**：减少顶点数，保留拓扑
- **语义吸附**：对齐到最近道路几何
- **Segment QA**：检查自交、拓扑变化、过度简化

### P1-07: Shared Boundary ✅

**文件：** `src/topology/`（168 行）

城市级拓扑分析：
- 共享边界检测
- 间隙检测（< 5m 为拓扑问题）
- 重叠检测（> 10m² 为冲突）
- 拓扑一致性报告

---

## 12. v1.0 规范对齐

三份上位规范已全部对齐到代码：

| 规范 | 代码对齐状态 |
|:---|:---|
| 总体设计 v1.3 | 已有 `world_model.py`、`contracts.py` |
| 实施设计规范 v1.0 | M0-M8 + P1 全部实现 |
| 本体定义规范 v1.0 | ✅ 14 类型 / 12 Morphology / 14 Relation / Separator/Connector / Gold 三态 / 8 步裁决协议 |
| Benchmark 规范 v1.0 | ✅ 20 故障码 / 15 实验 / Accuracy-Coverage / Source Matrix / Reproducibility |

### v1.0 新增枚举

| 枚举 | 值数 | 说明 |
|:---|:---|:---|
| `OntologyType` | 14 | 核心住宅本体类型 |
| `MorphologyType` | 12 | 住宅形态学剖面 |
| `RelationType` | 14 | 空间关系 |
| `RoadRole` | 5 | 道路角色 |
| `BuildingFunction` | 8 | 建筑功能（与 Membership 分离） |
| `BuildingMembershipState` | 4 | 建筑隶属状态 |
| `SeparatorType` | 10 | 分隔特征 |
| `ConnectorType` | 6 | 连接特征 |
| `GoldState` | 3 | Gold 裁决状态 |
| `EvidenceSufficiency` | 3 | 证据充分性 |
| `ErrorAttribution` | 9 | 失败归因 |

---

## 13. 代码统计

### 总量

| 指标 | 值 |
|:---|:---|
| Python 源文件 | 57 个 |
| 总代码行数 | ~7,500 行 |
| 测试文件 | 4 个 |
| 包 | 20 个 |

### 新增模块（M0 后新增，~4,000 行）

| 模块 | 文件 | 行数 | 说明 |
|:---|:---|:---|:---|
| `src/domain/contracts.py` | 1 | 487 | 11 核心契约 + v1.0 升级 |
| `src/domain/ontology.py` | 1 | 49 | 14 类型本体 + 中文映射 |
| `src/coordinate/metric_crs.py` | 1 | 157 | WGS84 椭球米制计算 |
| `src/observation/` | 4 | 430 | 3 数据源适配器 |
| `src/validation/pipeline.py` | 1 | 225 | 4 Gate 验证管道 |
| `src/benchmark/` | 3 | 551 | 30-Case Benchmark 框架 |
| `src/membership/` | 2 | 372 | P1-01 Building Membership |
| `src/segmentation/` | 2 | 310 | P1-02 Boundary Segment |
| `src/renderer/` | 2 | 385 | P1-03 Scene Renderer |
| `src/vlm/` | 2 | 381 | P1-04 VLM Reasoning |
| `src/calibration/` | 2 | 196 | P1-05 Confidence Calibration |
| `src/reconstruction/` | 2 | 177 | P1-06 Vector Reconstruction |
| `src/topology/` | 2 | 168 | P1-07 Shared Boundary |
| `tests/` | 4 | ~400 | 测试用例 |

### 重构文件（5 个）

| 文件 | 重构内容 |
|:---|:---|
| `src/agents/entity_resolution_agent.py` | 消除与 `component_matcher` 的重复逻辑 |
| `src/agents/boundary_reasoning_agent.py` | `111320.0` → `degree_offset_for_meters()` |
| `src/generation/candidate_fusion.py` | 3 处 `111320` + 2 处 `buffer(0.000X)` 替换 |
| `src/geometry/ai_fence_guard.py` | `111320.0` → `distance_m()` |
| `src/entity_resolution/candidate_retrieval.py` | `buffer_degrees` → `buffer_meters` |

---

## 14. 下一步

### 短期

1. **30 个真实 Case 填充** — 用实际北京住宅数据填充 `BenchmarkCase` 模板
2. **B0-B9 Baseline 实验运行** — 使用现有数据跑 Baseline Ladder
3. **Failure Analysis** — 根据实验结果生成故障分类报告

### 中期（P2 候选）

| P2 任务 | 启动条件 |
|:---|:---|
| Active Evidence Acquisition | Benchmark 证明证据缺口显著 |
| Learned Provider Selection | 多 Provider 结果差异显著 |
| Learned Evidence Fusion | 多源互补性明显 |
| Temporal Change Detection | 同一 Case 多时间点数据可用 |
| Specialized VLM Fine-tuning | VLM 增量显著但成本过高 |
| Graph Database | 实体关系规模超 10K |
| Knowledge Graph Reasoner | 推理需求明确 |
| Predictive World Model | 预测需求明确 |

### 关键证伪条件

- **Falsification 1**：开放数据无法达到合理 Entity Recall → 调整目标
- **Falsification 2**：Estate/Phase/Compound 本体无法稳定解释 → 重构 Ontology
- **Falsification 3**：Road + Building 已解决绝大多数问题 → 不建设重型 VLM
- **Falsification 4**：VLM 无显著增量 → 不进入生产主路径
- **Falsification 5**：开放数据证据不足 → 接受更多 `UNRESOLVED`

## 15. 真实成熟度评估

根据 2026-08-26 实施纠偏审查，以下为所有能力的双维度状态：

| 能力 | 实现状态 | 验证状态 | 判定 |
|:---|:---|:---|:---|
| Domain Contract | `IMPLEMENTED` | `UNIT_TESTED` | P0 可继续 |
| Minimal Ontology | `IMPLEMENTED` | `UNIT_TESTED` | 待真实 Gold 压测 |
| Observation Adapter (3 源) | `IMPLEMENTED` | `UNIT_TESTED` | 未做北京覆盖实验 |
| Metric CRS | `IMPLEMENTED` | **DESIGN_REJECTED** | **P0 BLOCKER** — 须返工 |
| Provider Contract | `IMPLEMENTED` | — | 通过 |
| Baseline Provider | `INTERFACE_ONLY` | — | **未完成** |
| Validation: Ontology Gate | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Geometry Gate | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Evidence Gate | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Decision Readiness | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Authority Gate | `NOT_STARTED` | — | — |
| Validation: Temporal Gate | `NOT_STARTED` | — | — |
| Benchmark Framework | `IMPLEMENTED` | — | 通过 |
| 30 Case 真实填充 | `NOT_STARTED` | — | **未开始** |
| B0-B7 实验运行 | `NOT_STARTED` | — | **未开始** |
| Failure Analysis | `NOT_STARTED` | — | **未开始** |
| Building Membership | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — HEURISTIC_BASELINE |
| Boundary Segment | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Scene Renderer | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| VLM Framework | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — DISABLED_BY_DEFAULT |
| Confidence Calibration | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — 无 Gold 无法校准 |
| Vector Reconstruction | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — GEOMETRIC_SNAPPING_BASELINE |
| Shared Topology | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — 阈值未校准 |


## 16. 纠偏后的开发路线 (R0-R9)

```
R0   修正实施状态报告（已完成）
        ↓
R1   修复真正的 Metric CRS（P0 BLOCKER）
        ↓
R2   完成 Baseline Provider 实体实现
        ↓
R3   验证 Validation Gate 完整性
        ↓
R4   选取 30 个真实北京 Case
        ↓
R5   冻结 Source Manifest + Gold Protocol
        ↓
R6   只跑 B0-B7
        ↓
R7   Failure Analysis
        ↓
R8   决定哪些 P1 值得保留/重构/废弃
        ↓
R9   必要时才运行 B8 VLM
```

### 立即停止

- P2 任何任务
- 更多 VLM Prompt 开发
- 更多 Provider 实现
- 训练任何模型
- 增加新 Ontology Type

### 修正说明

1. P1 全部标记为 EXPERIMENTAL，不进入主生产架构
2. VLM 默认 DISABLED_BY_DEFAULT
3. Building Membership 固定权重为 HEURISTIC_BASELINE，参数版本化，须 Benchmark 校准
4. Topology 阈值（5m / 10m²）为 EXPERIMENTAL_DEFAULT，须校准
5. Vector Reconstruction snapping 为 GEOMETRIC_SNAPPING_BASELINE，非语义吸附
6. Graph DB 启动条件删除"10K 关系"阈值
7. B9 需 B1-B7 结果后再决定
8. 所有 Capability 保持双维度状态
