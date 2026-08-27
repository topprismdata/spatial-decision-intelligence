# Spatial Decision Intelligence — 实施纠偏与 Benchmark Gate 指令 v1.0

**项目：** Spatial Decision Intelligence
**日期：** 2026-08-26
**依据：** 实施纠偏审查（2026-08-26）

---

## 0. 为什么需要这份文档

前序开发快速搭建了基础架构骨架，但混淆了"实现了能力"与"能力已被验证"。本项目核心原则是 **Architecture is evidence-gated**。因此必须冻结当前开发节奏，转向真实数据驱动的验证循环。

---

## 1. 能力成熟度定义

所有 Capability 必须使用双维度状态：

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

---

## 2. 当前真实成熟度评估

| 能力 | 实现状态 | 验证状态 | 判定 |
|:---|:---|:---|:---|
| Domain Contract | `IMPLEMENTED` | `UNIT_TESTED` | P0 可继续 |
| Minimal Ontology | `IMPLEMENTED` | `UNIT_TESTED` | 待真实 Gold 压测 |
| Observation Adapter (3 源) | `IMPLEMENTED` | `UNIT_TESTED` | 未做北京覆盖实验 |
| Metric CRS | `IMPLEMENTED` | **DESIGN_REJECTED** | **P0 BLOCKER** — 须返工 |
| Provider Contract | `IMPLEMENTED` | — | 通过 |
| Baseline Provider | `INTERFACE_ONLY` | — | **未完成** |
| Validation: Ontology | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Geometry | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Evidence | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Decision Readiness | `IMPLEMENTED` | `UNIT_TESTED` | 通过 |
| Validation: Authority | `NOT_STARTED` | — | — |
| Validation: Temporal | `NOT_STARTED` | — | — |
| Benchmark Framework | `IMPLEMENTED` | — | 通过 |
| 30 Case Benchmark | `NOT_STARTED` | — | **未开始** |
| Failure Analysis | `NOT_STARTED` | — | **未开始** |
| Building Membership | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — HEURISTIC_BASELINE |
| Boundary Segment | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| Scene Renderer | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** |
| VLM Framework | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — DISABLED_BY_DEFAULT |
| Confidence Calibration | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — 无 Gold 无法校准 |
| Vector Reconstruction | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — GEOMETRIC_SNAPPING_BASELINE |
| Shared Topology | `IMPLEMENTED` | `NOT_BENCHMARKED` | **EXPERIMENTAL** — 阈值未校准 |

---

## 3. STOP 指令

### 立即停止

- P2 任何任务（Active Evidence Acquisition / Learned Provider / Learned Fusion / Temporal Change / VLM Fine-tuning / Graph DB / KG Reasoner / Predictive World Model）
- 更多 VLM Prompt 开发
- 训练任何模型
- 增加新 Ontology Type

### 允许（仅限 R2 明确定义的 4 个 Baseline Provider）

- `ExistingOpenBoundaryProvider`
- `RoadBlockProvider`
- `BuildingClusterProvider`
- `AreaPriorBaseline`

**除 R2 明确定义的 4 个 Baseline Provider 外，禁止新增任何 Provider 类型或扩展 Provider 能力。** 不允许在 R2 之外自己再增加路由、缓存、调度、编排等 Provider 基础设施。4 个 Baseline 全部实现、全部通过 B0-B7 验证后，Provider 能力才视为 R2 完成。

### 条件启动

P1 所有能力（Building Membership / Boundary Segment / Renderer / VLM / Calibration / Reconstruction / Topology）**保留为实验资产**，但：

- 不进入主生产架构
- 不得被任何 Benchmark 以外的代码调用
- 必须等 R8 决定去留

---

## 4. 唯一正确的下一阶段 (R0-R9)

```
R0
修正实施状态报告
        ↓
R1
修复真正的 Metric CRS
        ↓
R2
完成 Baseline Provider 实体实现
        ↓
R3
验证 Validation Gate 完整性
        ↓
R4
选取 30 个真实北京 Case
        ↓
R5
冻结 Source Manifest + Gold Protocol
        ↓
R6
只跑 B0-B7
        ↓
R7
Failure Analysis
        ↓
R8
决定哪些 P1 代码值得保留/重构/废弃
        ↓
R9
必要时才运行 B8 VLM
```

### R0 — 修正实施状态报告

更新所有文档，使用双维度状态标注。确保团队对真实成熟度无歧义。

### R1 — 修复 Metric CRS（P0 BLOCKER）

当前实现是改进的经纬度近似，不是真正的投影 CRS。必须：

1. 选择适合北京的目标投影 CRS（如 UTM 50N / Lambert 等）
2. 实现 `WGS84 → Projected → WGS84` 转换管线
3. 所有 `area()` / `buffer()` / `distance()` / `snapping()` / `topology tolerance()` 改用投影坐标
4. `meters_per_degree_*` 保留用于 bbox 粗检索 / query radius / 搜索窗口

### R2 — 完成 Baseline Provider 实体实现

至少实现可真实运行的：

| Provider | 输入 | 输出 |
|:---|:---|:---|
| `ExistingOpenBoundaryProvider` | OSM landuse=residential 等 | `BoundaryHypothesis[]` |
| `RoadBlockProvider` | OSM road network | `BoundaryHypothesis[]` |
| `BuildingClusterProvider` | OSM/Overture/MS Buildings | `BoundaryHypothesis[]` |
| `AreaPriorBaseline` | Point + Area | `BoundaryHypothesis` |

### R3 — 验证 Validation Gate 完整性

- 确认 Decision Readiness Gate 已实现并可通过真实 Case 测试
- Authority / Temporal Gate 标记为 `NOT_STARTED`，不做假实现

### R4 — 选取 30 个真实北京 Case

按规范分层：

| 类型 | 数量 |
|:---|:---|
| 现代封闭社区 | 5 |
| 多期社区 | 5 |
| 单位大院 | 5 |
| 开放老旧社区 | 5 |
| 道路切割社区 | 5 |
| 商住混合 | 5 |

地理分布：核心城区 ≥ 10，近郊 ≥ 6，城乡结合部 ≥ 6，远郊新城 ≥ 4。
证据密度：HIGH ≥ 5，MEDIUM ≥ 12，LOW ≥ 8。

### R5 — 冻结 Source Manifest + Gold Protocol

- 每个 Case 记录 Source Manifest（来源 / 版本 / 许可证 / URL / 查询 / 下载日期）
- 按 8 步 Gold Adjudication Protocol 裁决
- 输出 `GOLD_RESOLVED` / `GOLD_PARTIAL` / `GOLD_UNRESOLVED`

### R6 — 只跑 B0-B7

只跑 B0-B7（B8 VLM 和 B9 Minimal World Model 暂不跑）：

| 实验 | 数据/能力 | 目的 |
|:---|:---|:---|
| B0 | Point + Area Prior | 最弱基线 |
| B1 | Existing Open Polygon | 开放现成边界 |
| B2 | Road only | 道路贡献 |
| B3 | Building only | 建筑贡献 |
| B4 | Road + Building | 基础结构融合 |
| B5 | Multi-source Building | 多源建筑增量 |
| B6 | Full Open Vector | 完整开放矢量基线 |
| B7 | + Public Semantic Data | 实体语义增量 |

### R7 — Failure Analysis

基于 B0-B7 结果，输出：

- 20 故障码分布
- 按场景/地理/证据密度分层
- 归因分析（DATA_LIMIT / ENTITY_MODEL / ONTOLOGY / PROVIDER / GIS / VALIDATION 等）

### R8 — 决定 P1 去留

基于 Failure Analysis 证据：

- 哪些 P1 能力值得保留 → 进入主架构
- 哪些 P1 能力需要重构 → 重新设计
- 哪些 P1 能力可以废弃 → 删除或归档

### R9 — 必要时才运行 B8 VLM

启动条件：

```
某 Failure Type 数量足够大
+
传统方法显著不足
+
问题具有视觉/语义性质
```

例如：

- F09 ROAD_SEMANTIC_AMBIGUITY 是主要瓶颈 → 启动 VLM Road Semantic Experiment
- F08 ROAD_DATA_MISSING 是主要瓶颈 → VLM 可能解决不了，不启动

---

## 5. 冻结规则

1. P1 所有能力标记为 `EXPERIMENTAL`，不进入主路径
2. VLM 默认 `DISABLED_BY_DEFAULT`
3. Building Membership 固定权重为 `HEURISTIC_BASELINE`，参数版本化、可配置
4. Topology 阈值（5m / 10m²）为 `EXPERIMENTAL_DEFAULT`，须 Benchmark 校准
5. Vector Reconstruction snapping 为 `GEOMETRIC_SNAPPING_BASELINE`，非语义吸附
6. Graph DB 启动条件删除"10K 关系"阈值，改为 `multi-hop reasoning / query complexity / relational DB bottleneck`
7. B9 不直接跑，等 B1-B7 结果决定
8. 所有 Capability 必须保持双维度状态（Implementation / Validation）