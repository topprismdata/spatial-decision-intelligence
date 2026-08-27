# Spatial Decision Intelligence — 实施进展报告 v1.1

**项目：** Spatial Decision Intelligence（TopprismData / 北京住宅空间世界重建）
**报告日期：** 2026-08-26（v1.1 纠偏版）
**仓库路径：** `/Users/user/WorkBuddy/2026-08-18-17-47-15`
**状态：** 本报告为项目当前唯一状态源。v1.0 已归档至 `progress-report-2026-08-26-v1.0.md`。

---

## 核心原则

本报告所有 Capability 使用双维度状态标注：

| 状态 | 含义 |
|:---|:---|
| `NOT_STARTED` | 尚未建设 |
| `INTERFACE_ONLY` | 只有 Contract / Skeleton |
| `IMPLEMENTED` | 有可运行实现 |
| `UNIT_TESTED` | 基础测试通过 |
| `BENCHMARKED` | 在真实 Benchmark 上运行 |
| `CALIBRATED` | 参数经过 Calibration Set |
| `ACCEPTED` | 通过 Gate，可进入主架构 |
| `REJECTED` | Benchmark 证伪 |
| `EXPERIMENTAL` | 保留研究，不进入主路径 |

**"实现了" ≠ "已验证"。** 两者组合才是真实成熟度。

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
9. [M7: Benchmark 框架](#9-m7-benchmark-框架)
10. [M8: 故障分析框架](#10-m8-故障分析框架)
11. [P1: 实验性能力](#11-p1-实验性能力)
12. [v1.0 规范对齐](#12-v10-规范对齐)
13. [代码统计](#13-代码统计)
14. [真实成熟度评估](#14-真实成熟度评估)
15. [当前唯一开发路线：R0-R9](#15-当前唯一开发路线r0-r9)

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
│  Alignment       │  │  + AI Fence Guard│  │  (LEGACY_APPROX)  │
│  (KEEP)          │  │  (KEEP)          │  │  (P0 BLOCKER)     │
└──────────────────┘  └──────────────────┘  └──────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Observation     │  │  Entity          │  │  Validation      │
│  Adapters        │  │  Resolution      │  │  Pipeline        │
│  (IMPLEMENTED)   │  │  (KEEP)          │  │  (4 Gates)       │
└──────────────────┘  └──────────────────┘  └──────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  P1 Modules (全部 EXPERIMENTAL / NOT_BENCHMARKED)            │
│  Membership / Segmentation / Renderer / VLM / Calibration   │
│  / Reconstruction / Topology — 不进入生产路径                 │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  Benchmark Suite (Framework 已实现，真实实验未开始)            │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. M0: 现有基线冻结

**实现状态：** `IMPLEMENTED` | **验证状态：** `ACCEPTED`

对现有代码进行 KEEP / REFACTOR / EXPERIMENTAL 分类，冻结基线。

| 类别 | 数量 | 关键资产 |
|:---|:---|:---|
| **KEEP** | 24 src/ 文件 + 8 顶层脚本 | 核心领域模型、坐标对齐、Geometry QA、实体解析管道、4-Agent 管道、决策适配器、AI Fence Guard |
| **REFACTOR** | 1 src/ + 4 脚本 | `EntityResolutionAgent` 与 `component_matcher` 重复逻辑（已重构）；`draw_step8/9/10_7k` 应模块化；`patch_qa_report` 应合并入验证管道 |
| **EXPERIMENTAL** | 1 src/ + 20 脚本 | `DatasetExtractor`；全部 road/draw pipeline 原型脚本 |

---

## 3. M1: 领域契约迁移

**实现状态：** `IMPLEMENTED` | **验证状态：** `UNIT_TESTED`

11 个核心领域契约（`src/domain/contracts.py`，487 行）：

| 契约 | 说明 |
|:---|:---|
| `SpatialEntity` | 顶层实体，聚合 Observations / Representations / Relations |
| `SpatialRepresentation` | 几何解释（与 Observation 分离） |
| `BoundaryRepresentation` | 边界类型几何表示 |
| `Observation` | 原始数据观测（不携带解释） |
| `SpatialRelation` | 实体间关系（独立于几何度量） |
| `RelationMeasurement` | 可选几何度量 |
| `AuthorityAssertion` | 权威/信任断言 |
| `Evidence` | 证据 |
| `BoundaryHypothesis` | 候选边界假设 |
| `ValidationResult` | 验证结果 |
| `TrustedSpatialState` | 聚合可信状态 |

适配器函数：`observation_from_source_record`、`representation_from_geometry_version`、`spatial_relation_from_entity_relation`

---

## 4. M2: Metric CRS

**实现状态：** `IMPLEMENTED` | **验证状态：** `DESIGN_REJECTED` | **判定：P0 BLOCKER**

### 当前实现

`src/coordinate/metric_crs.py` 提供基于 WGS84 椭球的经纬度换算函数：

| 函数 | 说明 |
|:---|:---|
| `meters_per_degree_lat(lat)` | 纬度每度米数（WGS84 椭球） |
| `meters_per_degree_lng(lat)` | 经度每度米数（纬度校正） |
| `degree_offset_for_meters(meters, lat)` | 米 → 度偏移量 |
| `area_m2_from_wgs84(geom, lat)` | 度坐标 → 平方米 |
| `distance_m(geom_a, geom_b, lat)` | 米制距离 |
| `buffer_meters(wkt, meters, lat)` | 米制缓冲区 |
| `bbox_from_center(lng, lat, half_side_m)` | 米制边界框 |

### 为什么被拒

这是**更精确的经纬度近似**，不是真正的**投影 CRS**。真实要求是：

```
WGS84
  ↓
选择适合目标区域的投影 CRS
  ↓
Projected Coordinates
  ↓
buffer / area / distance / snapping
  ↓
WGS84
```

### 保留范围

`meters_per_degree_*` 可继续用于：

- bbox 粗检索
- query radius
- 搜索窗口

**不可用于：**

- polygon area（正式计算）
- buffer（正式计算）
- boundary distance
- snapping
- topology tolerance

### 修复方向（R1）

设计 `MetricCRSStrategy` 策略接口：

```
MetricCRSStrategy
  ↓
输入：geometry extent / centroid / source CRS / operation type
  ↓
输出：metric computation CRS / selection reason / valid extent
```

北京 Benchmark Profile → `EPSG:32650 (UTM 50N)`
未来其他城市 → 根据地理范围自动选择

---

## 5. M3: 开放数据观测层

**实现状态：** `IMPLEMENTED` | **验证状态：** `UNIT_TESTED` — 未做北京覆盖实验

三个 Source Adapter (`src/observation/`)，均只产生 `Observation`，不产生 `SpatialRepresentation`：

| 适配器 | 源 | 许可证 |
|:---|:---|:---|
| `OverpassAdapter` | OSM (Overpass API) | ODbL |
| `OvertureAdapter` | Overture Maps | CDLA-Permissive-1.0 |
| `MicrosoftBuildingsAdapter` | Microsoft Global ML Building Footprints | CDLA-Permissive-1.0 |

---

## 6. M4: 最小本体

**实现状态：** `IMPLEMENTED` | **验证状态：** `UNIT_TESTED` — 待真实 Gold 压测

### OntologyType（14 类型）

`ResidentialEstate` / `ResidentialPhase` / `ResidentialCompound` / `PropertyManagementArea` / `ResidentialLandUse` / `AdministrativeCommunity` / `LandParcel` / `Building` / `Entrance` / `Gate` / `Road` / `Barrier` / `UnknownResidentialEntity` / `OtherBuiltFeature`

### MorphologyType（12 类型，multi-label 允许）

`MODERN_GATED` / `MULTI_PHASE` / `OLD_GATED` / `OLD_OPEN` / `DANWEI_COURTYARD` / `VILLA` / `ROAD_SPLIT` / `MIXED_USE` / `SUPER_COMPOUND` / `SMALL_COURTYARD` / `UNDER_CONSTRUCTION` / `UNKNOWN`

---

## 7. M5: Provider 框架

### Provider Contract

**实现状态：** `IMPLEMENTED`

| 契约 | 说明 |
|:---|:---|
| `ProviderResult` | 标准 Provider 输出 |
| `ProviderStatus` | `APPLICABLE` / `NOT_APPLICABLE` / `ERROR` |
| `BoundaryHypothesis` | 候选边界假设 |

### Baseline Providers

**实现状态：** `INTERFACE_ONLY` | **判定：未完成**

以下 4 个 Provider 只有接口预留，尚未实现可真实运行的版本：

| Provider | 状态 |
|:---|:---|
| `ExistingOpenBoundaryProvider` | `INTERFACE_ONLY` |
| `RoadBlockProvider` | `INTERFACE_ONLY` |
| `BuildingClusterProvider` | `INTERFACE_ONLY` |
| `AreaPriorBaseline` | `INTERFACE_ONLY` |

---

## 8. M6: 验证管道

**实现状态：** `PARTIAL` | **验证状态：** `UNIT_TESTED`

| Gate | 状态 | 说明 |
|:---|:---|:---|
| Ontology Gate | `IMPLEMENTED` | 验证 OntologyType 是否属于 14 冻结类型 |
| Geometry Gate | `IMPLEMENTED` | 验证几何有效性、面积范围 |
| Evidence Gate | `IMPLEMENTED` | 验证证据充分性 |
| Decision Readiness Gate | `IMPLEMENTED` | Consumer-aware：同一状态对 Visit 可能 READY，对 Territory 可能 NOT_READY |
| Authority Gate | `NOT_STARTED` | 长期体系 |
| Temporal Gate | `NOT_STARTED` | 长期体系 |

---

## 9. M7: Benchmark 框架

**实现状态：** `IMPLEMENTED`（框架） | **真实实验：** `NOT_STARTED`

### 框架已实现

- 30 Case 模板（6 类型 × 5）
- 15 实验定义（B0-B9 + A1-A5）
- 20 故障码（F01-F20）
- Accuracy-Coverage Curve
- Source Complementarity Matrix
- Reproducibility Contract (`BenchmarkRunRecord`)

### 未开始

- 30 个真实北京 Case 填充
- B0-B7 实验运行
- 任何实际 Benchmark 结果

---

## 10. M8: 故障分析框架

**实现状态：** `IMPLEMENTED`（框架） | **真实分析：** `NOT_STARTED`

### 框架已实现

- 20 故障码（F01-F20）
- 9 类 Error Attribution
- 按场景/地理/证据密度分层

### 未开始

- 基于真实 B0-B7 结果的故障分析
- 任何实际 Failure Report

---

## 11. P1: 实验性能力

**全部标记为：** `IMPLEMENTED` / `EXPERIMENTAL` / `NOT_BENCHMARKED`

**规则：** P1 能力在 Benchmark 给出证据之前，不得进入 `Trusted Production Path`。允许被测试、Benchmark 和明确标记的 Experimental Pipeline 调用。

| 能力 | 实现状态 | 验证状态 | 备注 |
|:---|:---|:---|:---|
| Building Membership | `IMPLEMENTED` | `NOT_BENCHMARKED` | HEURISTIC_BASELINE（固定权重 0.40/0.25/0.20/0.15，参数版本化，须 Benchmark 校准） |
| Boundary Segment | `IMPLEMENTED` | `NOT_BENCHMARKED` | — |
| Scene Renderer | `IMPLEMENTED` | `NOT_BENCHMARKED` | — |
| VLM Framework | `IMPLEMENTED` | `NOT_BENCHMARKED` | **DISABLED_BY_DEFAULT**，需 R7 Failure Analysis 证明必要性 |
| Confidence Calibration | `IMPLEMENTED` | `NOT_BENCHMARKED` | 无 Gold 无法真正校准 |
| Vector Reconstruction | `IMPLEMENTED` | `NOT_BENCHMARKED` | GEOMETRIC_SNAPPING_BASELINE（非语义吸附） |
| Shared Topology | `IMPLEMENTED` | `NOT_BENCHMARKED` | 阈值（5m / 10m²）为 EXPERIMENTAL_DEFAULT，须校准 |

---

## 12. v1.0 规范对齐

四份上位规范在代码中的对齐状态：

| 规范 | 代码对齐状态 |
|:---|:---|
| 总体设计 v1.3 | 已有 `world_model.py`、`contracts.py` |
| 实施设计规范 v1.0 | M0 基线 + M1 契约 + M2-M6 部分实现（见 §14 成熟度评估） |
| 本体定义规范 v1.0 | 14 类型 / 12 Morphology / 14 Relation / Separator/Connector / Gold 三态 / 8 步裁决协议 |
| Benchmark 规范 v1.0 | 20 故障码 / 15 实验 / Accuracy-Coverage / Source Matrix / Reproducibility |

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

| 模块 | 行数 | 当前状态 |
|:---|:---|:---|
| `src/domain/contracts.py` | 487 | `IMPLEMENTED` |
| `src/domain/ontology.py` | 49 | `IMPLEMENTED` |
| `src/coordinate/metric_crs.py` | 157 | `LEGACY_APPROXIMATION` — 待返工 |
| `src/observation/` | 430 | `IMPLEMENTED` |
| `src/validation/pipeline.py` | 225 | `PARTIAL` |
| `src/benchmark/` | 551 | `IMPLEMENTED`（框架） |
| `src/membership/` | 372 | `EXPERIMENTAL` |
| `src/segmentation/` | 310 | `EXPERIMENTAL` |
| `src/renderer/` | 385 | `EXPERIMENTAL` |
| `src/vlm/` | 381 | `EXPERIMENTAL` — DISABLED_BY_DEFAULT |
| `src/calibration/` | 196 | `EXPERIMENTAL` |
| `src/reconstruction/` | 177 | `EXPERIMENTAL` |
| `src/topology/` | 168 | `EXPERIMENTAL` |

---

## 14. 真实成熟度评估

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
| Building Membership | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Boundary Segment | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Scene Renderer | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| VLM Framework | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — DISABLED_BY_DEFAULT |
| Confidence Calibration | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Vector Reconstruction | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Shared Topology | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |

---

## 15. 当前唯一开发路线：R0-R9

暂停 P2 任何开发。唯一有效的下一阶段路线：

```
R0   ✅ 修正实施状态报告（v1.1 已完成，v1.0 已归档）
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

### R0 已完成内容

- 文档修正为双维度状态标注
- 旧版 v1.0 归档，v1.1 为唯一状态源
- 所有 P1 降级为 `EXPERIMENTAL`
- Metric CRS 标记为 `DESIGN_REJECTED` / `P0 BLOCKER`
- Baseline Provider 标记为 `INTERFACE_ONLY`
- Validation Gate 逐 Gate 标注
- VLM 默认 `DISABLED_BY_DEFAULT`
- Graph DB 启动条件删除"10K 关系"阈值
- B9 暂不跑，需 B1-B7 结果后再决定

### 立即停止

- P2 任何任务
- 更多 VLM Prompt 开发
- 训练任何模型
- 增加新 Ontology Type

### 允许（仅限 R2 明确定义的 4 个 Baseline Provider）

- `ExistingOpenBoundaryProvider`
- `RoadBlockProvider`
- `BuildingClusterProvider`
- `AreaPriorBaseline`

**除 R2 明确定义的 4 个 Baseline Provider 外，禁止新增任何 Provider 类型或扩展 Provider 能力。** 4 个 Baseline 全部实现、全部通过 B0-B7 验证后，Provider 能力才视为 R2 完成。

### 冻结规则

1. P1 全部标记为 `EXPERIMENTAL`，不进入主生产架构
2. VLM 默认 `DISABLED_BY_DEFAULT`
3. Building Membership 固定权重为 `HEURISTIC_BASELINE`，参数版本化
4. Topology 阈值（5m / 10m²）为 `EXPERIMENTAL_DEFAULT`
5. Vector Reconstruction snapping 为 `GEOMETRIC_SNAPPING_BASELINE`
6. 所有 Capability 保持双维度状态