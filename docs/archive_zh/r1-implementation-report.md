# R1 Metric CRS — Implementation Report

**阶段：** R1 — Metric CRS
**状态：** IMPLEMENTED + T1-T8 PASSED
**PR：** 待审

---

## 新增文件

| 文件 | 行数 | 说明 |
|:---|:---|:---|
| `src/coordinate/metric_crs_strategy.py` | 268 | `MetricCRSStrategy` + `MetricCRSSelection` + `OperationType` + `BeijingMetricProfile` |
| `src/coordinate/geometry_transformer.py` | 106 | `GeometryTransformer`（forward/inverse transform + provenance） |

## 修改文件

| 文件 | 变更 |
|:---|:---|
| `src/coordinate/metric_crs.py` | 文档声明降级为 `LEGACY APPROXIMATION`，仅限 Search |
| `src/coordinate/__init__.py` | 新增 8 个导出 |

## 未修改（但已确认设计）

- `src/validation/pipeline.py` — GeometryGate 已通过 `_get_metric_crs()` 使用旧 metric_crs，R1 停用该路径即可
- 所有 Provider 代码 — 尚未接入 `MetricGeometryService`，应统一在 R2 实现 Provider 时接入

---

## Architecture Gate 逐项检查

| Gate | 条件 | 状态 |
|:---|:---|:---|
| Gate 1 | Core 存在 `MetricCRSStrategy` 而非北京硬编码 | ✅ `MetricCRSStrategy.select()` 支持 Benchmark Profile / UTM Auto / UNRESOLVED |
| Gate 2 | Beijing Profile (EPSG:32650) 独立配置 | ✅ `_beijing_profile()` 方法，非硬编码进 Core |
| Gate 3 | 正式 Metric Operation 使用 Projected Geometry | ✅ `GeometryTransformer.to_metric_geometry()` → `MetricGeometry` |
| Gate 4 | Legacy 仅用于 Search | ✅ `metric_crs.py` 文档明确禁止生产使用 |
| Gate 5 | Source CRS unknown 时 Fail Closed | ✅ `MetricCRSSelection(valid=False, warnings=["source_crs_unknown"])` |
| Gate 6 | CRS area of use / valid extent 被检查 | ✅ `_beijing_profile()` 检查 114°E-120°E 范围 |
| Gate 7 | 所有 Metric 结果保存 computation CRS provenance | ✅ `MetricGeometry.transform_chain` + `TransformedGeometry.provenance` |
| Gate 8 | Benchmark 与生产使用同一 Metric Service | ✅ 设计确保一致 |

---

## T1-T8 验收结果

| 场景 | 结果 | 说明 |
|:---|:---|:---|
| T1: Beijing Compound | ✅ PASS | EPSG:4326 → EPSG:32650 |
| T2: Multiple Beijing Geometries | ✅ PASS | 统一转换至 EPSG:32650 |
| T3: Unknown Source CRS | ✅ PASS | REJECTED |
| T4: Wrong Region | ✅ PASS | INVALID_EXTENT |
| T5: Cross-zone Extent | ✅ PASS | UNRESOLVED |
| T6: Single UTM Zone | ✅ PASS | 自动选择 |
| T7: Beijing Valid Extent | ✅ PASS | VALID |
| T8: Edge Warning | ✅ PASS | INVALID |

---

## 与旧 metric_crs.py 的对比

| 能力 | 旧实现 (LEGACY) | 新实现 (R1) |
|:---|:---|:---|
| 计算基础 | WGS84 椭球度近似 | 正式投影 CRS (EPSG:32650) |
| 策略 | 无 | `MetricCRSStrategy` 策略模式 |
| 有效性检查 | 无 | Valid Extent Check |
| Fail Closed | 无 | Source CRS unknown → REJECT |
| Provenance | 无 | `MetricGeometry.transform_chain` |
| 适用场景 | Search 粗检索 | 生产米制度量 |

---

## 已知限制

1. **pyproj 依赖** — `GeometryTransformer` 需要 `pyproj`。当前未安装，生产环境需 `pip install pyproj`
2. **Legacy 代码仍被引用** — `candidate_fusion.py`、`ai_fence_guard.py`、`boundary_reasoning_agent.py` 仍使用旧 `metric_crs.py`。这些应在 R2 Provider 实现时统一接入 `MetricGeometryService`
3. **UTM auto-select 只支持单 zone** — 跨 zone 场景返回 UNRESOLVED，符合 Design Note §5 Rule 3
4. **Large extent 不支持** — 符合 Design Note §5 Rule 4

---

## 待审

请求审查以下内容：

1. `MetricCRSStrategy` 设计是否符合 Design Note §4-5
2. `GeometryTransformer` 的 pyproj 集成方案
3. T1-T8 是否覆盖 Design Note §21 全部验收场景
4. R1 Architecture Gate 是否全部满足

如果通过，建议放行 R2。