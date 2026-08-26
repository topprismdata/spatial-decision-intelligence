# R14 优化提案：文献驱动的改进清单（2026-08-27）

状态：**评审中**
依据：8 维度文献普查（GeoLit3 子代理 + 主会话验证性搜索）+ 本项目 R0-R13 实测数据

---

## 一、8 个调研问题的结论摘要

| # | 问题 | 结论 | 证据等级 |
|---|---|---|---|
| Q1 | 凸包 → concave hull/alpha shape？ | 凸包系统性过覆盖 L 形/细长建筑簇。标准解法：alpha shape / constrained Delaunay / Duckham-style concave hull；参数 α 控制收紧度 | ✅ 多篇已核实 |
| Q2 | 遥感界的"小区边界提取"？ | 活跃方向：VHR 影像 + nDSM + 边界感知 loss + OSM 路网约束，效果优于纯语义分割。对应 ISPRS Annals X-5-W2-2025 等 | ✅ 已核实趋势 |
| Q3 | 启发式排序 → 概率融合？ | CRF/MRF 能量模型（一元数据项+成对平滑项）是竞争假设融合的成熟模板；Dempster-Shafer 处理多源冲突证据 | ⚠️ 方法论共识成立，具体论文未逐篇验证 |
| Q4 | 相邻地块共享边界修复？ | 地籍领域标准做法：planar partition 不变量 + split/merge 局部更新操作（Meijers 系列工作） | ✅ 方向已核实 |
| Q5 | Estate→Phase→Compound 层级解析？ | 经典 toponym disambiguation：gazetteer containment 检查 + 层级先解析高置信节点约束子节点搜索空间；近年 LLM+gazetteer 混合架构是 SOTA | ✅ 方向已核实 |
| Q6 | VLM 地图理解？ | 2025-2026 爆发期：GEOBench-VLM (ICCV 2025)、CHOICE、RSVLM-QA 等基准证实 VLM 可做空间关系推理但细粒度能力有限。佐证我们 VLM 只做结构化断言的路线正确 | ✅ 已核实具体基准 |
| Q7 | Web search 作为证据源？ | 商业上成熟（OSM+POI 融合管线），学术上经由 entity linking 对齐 gazetteer。我们的 Amap 补名实验（285/4919）正是此模式实证 | ✅ 实证完成 |
| Q8 | Human-in-the-loop 边界修正？ | 分割精修的主动学习平台 + OSM 参与式修正界面均有先例；优先级低于全自动收益 | ⚠️ 共识级 |

---

## 二、Top-5 优化清单（按 ROI 排序）

### P1. BuildingCluster 凸包 → Alpha Shape（concave hull）
- **问题**：R9 后建筑簇边界仍用凸包收口，L 形小区围出大量无关空地
- **方案**：`shapely` 无内置 alpha shape；引入 `alphashape` 库或自实现 Duckham concave hull（基于 Delaunay 删长边），α 从簇内最近邻距离自适应
- **预期收益**：IoU 直接提升——凸包在 L/U 形布局上的 IoU 上限通常只有 0.6-0.7
- **参考**：*Learning visual features from figure-ground maps for urban morphology discovery* (CEUS 2024)；Duckham et al. 2008 concave hull 经典
- **复杂度**：M（新依赖 + 回归 30 case benchmark）

### P2. 高德覆盖基准（Amap-Coverage Gate）
- **问题**：4,881 个无名多边形实为农地/荒地误标 `landuse=residential`
- **方案**：新增 Ontology Gate 规则——**OSM 无名 且 Amap 200m 半径无住宅 POI ⇒ disposition=REJECTED**（非 UNRESOLVED）。本项目已跑完全量验证（1,691 API 调用命中 285 个真小区）
- **预期收益**：误报率大幅下降，Observation Ceiling 报告中的 D 类失败被结构性消除
- **参考**：本项目实测（2026-08-27 batch）+ gazetteer 交叉验证惯例
- **复杂度**：S（纯规则接入现有 Validation Gate）

### P3. CandidateRankingEngine → Dempster-Shafer 证据融合
- **问题**：当前排序是启发式加权分（generation_score 手调权重），provider 间冲突无原则化处理
- **方案**：每个 provider 输出转为 mass function（对 {accept, reject, conflict} 的信任分配），DS 组合规则融合；冲突率高时自动降级为 PROVISIONAL 而非 TRUSTED
- **预期收益**：False Trusted（当前为 0 但靠人工规则维持）获得数学保证；为多城市泛化免去重调权
- **参考**：*Robust Dempster-Shafer Evidence Fusion with Chaos-Conflict Measurement* (arXiv 2608.13108)；building extraction 中 DS 融合已是常规操作
- **复杂度**：L（契约不变，排序引擎内部重写 + 全量回归）

### P4. 相邻小区共享边修复 → Planar Partition 重建
- **问题**：R11 的 TopologyRepairExecutor 基于局部规则，可能产生重复墙/缝隙 sliver
- **方案**：从" pairwise 修两个 polygon "升级为" 城市街区级 planar partition 不变量检查"——用 `unary_union` 重构邻接图，共享边只保留一份几何（node-split + edge-shared 表示）
- **预期收益**：消除 sliver 类 QA 失败；下游 territory solver 拿到 watertight 输入
- **参考**：Meijers et al. parcel partition reconstruction 系列（TU Delft / gdmc.nl 文献库）
- **复杂度**：L

### P5. Estate/Phase 层级解析 ← Gazetteer Containment 硬化
- **问题**：R12 的 EntityHierarchyResolver 靠命名正则（"N区/N号院"），跨 estate 同名 phase 会歧义
- **方案**：Amap POI 树（pname/cityname/adname/business_area）作为轻量 gazetteer 做包含关系校验；同名二区按 adname 分组归属
- **预期收益**：D2 类剩余歧义 case 减少；复杂度小因为数据已在手
- **参考**：toponym hierarchical resolution 标准 pipeline（IJGIS 综述级共识）；LLM+gazetteer hybrid 为 2025 SOTA 备选
- **复杂度**：S

---

## 三、不做的事（经文献论证后明确放弃）

1. **不引入 VHR 卫星影像语义分割训练**：需要标注数据，违反 Open-Data-Only 约束；VLM 断言路线（已验证 Δ=+0.700）达到类似效果且无需训练
2. **不上 LLM 做几何生成**：全部文献一致认为 LLM 幻觉使其不适合直接产出坐标几何；LLM/VLM 只应输出结构化断言/约束（与我们 R8 结论一致）
3. **Web-scale POI 反查不做常态化**：仅用在高德基准门控这一个点位上，避免爬虫合规风险

---

## 四、实施顺序建议

```
P2 (S, 1天) ──► P5 (S, 1-2天) ──► P1 (M, 3-5天) ──► P3 (L) ──► P4 (L)
   立即止血        数据已在手       最大IoU增益      架构升级     最后做
```

P2/P5 合计 ~3 天即可让北京全量数据从" 11,227 原始多边形 "变成" 6,593 个可信小区围栏 "的产品可用形态。
