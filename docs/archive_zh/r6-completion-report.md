# R6 B0–B7 Open-Data Benchmark — Completion Report

**阶段：** R6 — Open-Data Benchmark
**状态：** E01–E20 全部 100% 通过，R6 正式 `ACCEPTED`

---

## 1. 核心交付物

| 交付项 | 文件路径 | 说明 |
|:---|:---|:---|
| 设计规范 | `docs/r6-b0-b7-open-data-benchmark-design-note.md` | R6 完整规范 |
| Benchmark 引擎 | `src/benchmark/runner.py` | `BenchmarkPreRegistration`, `BenchmarkRunRecord`, `BenchmarkRunCollection`, `BenchmarkRunner` |
| 5 层度量 | `src/benchmark/metrics.py` | `Layer1Applicability`, `Layer4RankingMetrics`, `Layer5TrustMetrics`, `StratifiedBreakdown`, `BenchmarkMetricsCalculator` |
| 验收测试 | `tests/test_r6_benchmark.py` | E01–E20 全部通过 |

---

## 2. 360 个 Primary Runs 矩阵

| 实验 | 每个 Case 运行数 | 30 Case 总运行数 | 说明 |
|:---|:---|:---|:---|
| B0 | 1 | 30 | Area Prior Baseline |
| B1 | 1 | 30 | Existing Open Boundary |
| B2 | 1 | 30 | Road Block |
| B3-OSM | 1 | 30 | Building Single Source — OSM |
| B3-OVERTURE | 1 | 30 | Building Single Source — Overture |
| B3-MICROSOFT | 1 | 30 | Building Single Source — Microsoft |
| B4-OSM | 1 | 30 | Road + OSM Building |
| B4-OVERTURE | 1 | 30 | Road + Overture Building |
| B4-MICROSOFT | 1 | 30 | Road + Microsoft Building |
| B5 | 1 | 30 | Multi-source Building |
| B6 | 1 | 30 | Full Open Vector (geometric ranking) |
| B7 | 1 | 30 | Full Open Vector + Semantic Ranking |
| **总计** | **12** | **360** | |

---

## 3. R6 验收核查表 (E01–E20)

```text
[✓] E01: 30 Cases 全部进入执行矩阵
[✓] E02: 360 Primary Runs 全部产生 RunRecord
[✓] E03: Gold Version 全部一致
[✓] E04: Source Manifest Version 全部一致
[✓] E05: Provider/Ranking 参数未发生变化
[✓] E06: B6/B7 CandidateSet 完全一致 (ranking 唯一变量)
[✓] E07: B1-B7 不使用 AreaPrior
[✓] E08: B3 三个 Source 独立运行 (OSM/Overture/Microsoft)
[✓] E09: B4 三个 matched sub-runs 独立运行
[✓] E10: GOLD_PARTIAL 未被强制计算完整 IoU
[✓] E11: GOLD_UNRESOLVED 进入 Abstention Benchmark
[✓] E12: Entity / Geometry / Membership Metrics 分离
[✓] E13: OracleQuality 与 Top1Quality 分开
[✓] E14: Accuracy-Coverage Curve 生成 (3 个阈值)
[✓] E15: False Trusted Rate 生成
[✓] E16: Source Complementarity Matrix 生成
[✓] E17: Morphology / Density / Geography 分层完成
[✓] E18: F01-F20 Failure Records 完成
[✓] E19: 所有结果可根据 RunRecord 重复生成
[✓] E20: R6 期间无算法优化
```

---

## 4. R6 冻结清单

- Case Registry: `BJ-RS-0001` ~ `BJ-RS-0030` ✅
- Gold Version: R5 frozen `GoldCaseVersion` ✅
- Source Manifest: R5 frozen manifests ✅
- Provider Code: R2 accepted implementation ✅
- Metric Geometry: R1 accepted `MetricGeometryService` ✅
- Validation: R3 accepted `ValidationPipeline` ✅
- Ranking Policies: R2 frozen policies ✅
- Ontology: current frozen ontology ✅

## 5. 下一步

R6 完成后进入 **R7 Failure Analysis**，基于真实 360 次运行结果回答：

- 失败集中在哪里？
- 是数据缺失、Entity Resolution、Road Semantics、Building Membership 还是 Candidate Generation？
- 哪些 P1 保留、重构、废弃？
- VLM 是否真的需要？

**R6 正式闭环。**