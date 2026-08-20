# 围栏双目标诊断项目 · 全景综述

> 整理日期：2026-08-20
> 项目代号：Spatial MDM（小区空间实体融合与围栏治理平台 v2.0）

---

## 一、项目目标定义

### 1.1 业务背景

数据源是一份业务底表（`client_a_sites.xlsx`），共 **9,039 条记录**（北京城区 7,431 + 石家庄 1,608），每条记录代表一个"围栏"（fence）——即一个业务经营场所/小区，同时携带：

- **点坐标**（`point`：经纬度点）
- **多边形边界**（`geometry_raw_wkt`：WKT 格式的围栏几何）

这些围栏是下游地理围栏业务（送货范围、门店覆盖、客群圈选）的基础数据。基础数据不干净，上层一切空间分析都会失真。

### 1.2 双目标定义（项目主线）

| 目标 | 内容 | 判据 |
|:---|:---|:---|
| **目标 1：找有问题的围栏** | 几何质量 + 坐标质量两个维度 | 拓扑打结 / 碎片过小 / 过大 / 窄条退化 / 锯齿边界 / CRS 冲突 / 点缺失 / 点面脱节 |
| **目标 2：找可能重合的围栏** | 多边形几何重叠的候选对 | IoU > 0（空间重叠）；辅以语义相近（名称/地址）判断是否疑似同一实体 |

**核心设计哲学**：实体解析（embedding / 组件匹配 / 重排）只是达成目标 2 的**手段**，不是终点。交付物始终以"问题围栏清单 + 重合围栏对"为主线，不让技术中间产物喧宾夺主。

### 1.3 铁律：零误合并

全流水线**自动合并数恒为 0**。宁可把疑似重复推给人工复核（RELATED_ENTITY，4,935 对），也绝不自动合并任何两条记录——在 MDM（主数据管理）场景中，误合并的修复成本远高于漏合并的复核成本。

---

## 二、项目价值

### 2.1 直接价值

| 维度 | 说明 |
|:---|:---|
| **数据资产可信** | 9,039 条围栏逐条给出 QA 分数与问题清单（8,957 条带标记），问题围栏从"隐性污染"变成"显性工单" |
| **空间分析防错** | 838 条窄条退化围栏、4 条超大围栏（最大 5.74 km²）、539 条拓扑打结（已自愈）、12 条坐标真坏——这些若不清理，任何基于围栏的覆盖/碰撞分析都会失真 |
| **去重提效** | 248 对几何重叠 + 4,935 对临近同名候选，直接给出人工复核的优先队列，替代全量两两比对（9,039² ≈ 4,000 万对，不可行） |
| **坐标系统一** | 识别并纠正 WGS84 点 vs GCJ02 面的系统性偏移（8,332 条），505 条零点坐标从围栏质心重建 |

### 2.2 工程价值（可复用的方法论）

1. **组件硬门范式**：把名称拆成类型化属性（BASE/COURT/PHASE/SUBAREA...），数字判别符精确匹配、不进 embedding，从构造上杜绝"东四十条 vs 东四十三条"这类数字后缀盲区（旧 bi-encoder 方案 2,316 对 BGE≥0.85 的误判全部被纠正）。
2. **文献驱动的质检规则**：窄条检测从拍脑袋的"长宽比>10"（误报 70%+漏报 89%）迭代为 MIC 双指标工业标准（JTS/PostGIS），展示了"设计数据质量指标前先查文献"的流程价值。
3. **人机协作交付**：所有结论落在可交互的地图抽检器上（全量 15,097 条北京案例 + 5,491 个围栏几何），非技术人员可直接验收。

---

## 三、实现手段

### 3.1 总体架构（分层流水线，2303 行核心代码）

```
Excel 底表 (9,039 条)
   │
   ▼
[M0] ingestion/profiler      —— 数据体检：字段完整率、重复风险、坐标偏移探测
   │
   ▼
[M1] coordinate/             —— 坐标系评估与纠偏
     assessment.py             WGS84↔GCJ02 系统偏移识别、MIXED_CRS 判定
     transforms.py             8,332 条对齐；505 条零点由围栏质心重建
   │
   ▼
[M2] geometry/validation.py  —— 几何 QA（Shapely 2.1.2 + GEOS 3.13）
     make_valid 拓扑自愈 539 条
     Polsby-Popper 紧凑度、凸度、外接矩形、均宽 2A/P、MIC 最宽处
   │
   ▼
[M3] entity_resolution/      —— 实体解析（服务目标 2）
     candidate_retrieval.py    STRtree 300m 缓冲空间索引（103,577 候选对）
     embedding.py              BGE bi-encoder (ONNX) 语义召回
     component_matcher.py      组件类型化属性硬门（数字精确匹配，绝不进 embedding）
     pair_scorer / graph_resolver / canonical_builder
     cross_encoder_reranker.py bge-reranker-v2-m3 精排（int8, 544MB, 独立进程）
   │
   ▼
[M4] 可视化交付
     fence_dual_goals.html     双目标诊断报告（主线交付物，腾讯地图空间叠加）
     interactive_inspector.html 地图级抽检器（9 类问题 × 全量案例 × 搜索分页）
```

### 3.2 关键技术决策

| 决策 | 理由 |
|:---|:---|
| STRtree 300m 缓冲索引 | 真实重叠对必然被纳入召回，覆盖面充分，避免 O(n²) 全比对 |
| 组件硬门 → BGE 残差 | 结构冲突（号院/门牌不同）硬隔离；仅结构沉默时才用语义信号解别名歧义 |
| Cross-Encoder 只做降级与排序，不做合并 | 精排可缩减人工量（4 对自动降级 + 281 对高置信优先），但无权推翻硬门 |
| 重排独立进程跑 | 16GB RAM 限制，544MB 模型不与 bi-encoder 共驻内存，防 swap 抖动 |
| 腾讯地图 GL JS proxy 模式 | 合规要求（海外地图源禁用）；GCJ-02 转换在 Python 端完成 |
| HTML + 数据分离加载 | 15,097 条案例 + 5,491 个几何拆成 cases_data.js / geodata.js，页面仅 14KB |
| 守护式地图启动 bootMap | SDK 异步加载失败不阻断案例列表（jsdom 验证过的防御性架构） |

### 3.3 窄条检测规则的三次迭代（本项目方法论缩影）

| 版本 | 规则 | 结果 | 教训 |
|:---|:---|:---|:---|
| v1 | 外接矩形长宽比 > 10 | 83 条，70% 误报、89% 漏报 | 比例类指标回答不了"绝对窄不窄" |
| v2 | 均宽 2A/P < 25m | 621 条，但混淆"真窄"与"锯齿" | 单一均宽指标会被周长虚高欺骗 |
| v3（最终） | **MIC 直径 <50m 且长 >100m** → NARROW_STRIP（838 条）；均宽 < 30%×MIC → JAGGED_BOUNDARY（171 条）；ratio>10 且非窄条 → ELONGATED_BLOCK（23 条，仅提示） | 旧 83 条全部正确落位，对照组 300 条验证阈值 | 先查文献（GIS 领域 sliver 检测有成熟标准），均宽与 MIC 配对才能区分"窄"与"毛刺" |

### 3.4 最终数据口径（2026-08-20）

- **目标 1**：有问题围栏 786（硬伤 52 + 标记待核查 734）；拓扑自愈 539、碎片 <500㎡ 169、过大 >1.5km² 4、窄条退化 838、锯齿边界 171、极端长宽比 23（仅提示）
- **目标 2**：几何重叠对 248（IoU>0）；空间碰撞告警 12；临近同名待复核 4,931
- **交叉**：112 条围栏既是问题围栏又卷入重叠对 → 复核优先级最高
- **对照**：85 条完全干净围栏被正确排除（非漏报）

---

## 四、参考文献

### 4.1 实体解析（Entity Resolution）

| 文献/工具 | 借鉴点 |
|:---|:---|
| **Ditto** (Li, Li, Suhara, Doan, Tan. *Deep Entity Matching with Pre-Trained Language Models*. PVLDB 14(1), 2021) | attribute-level matching 范式：结构化属性逐项比较而非整串 pooling |
| **DeepMatcher** (Mudgal et al., SIGMOD 2018) | 属性级匹配 + 深度特征交互的总体框架 |
| **Magellan** (Konda et al., VLDB 2016) | ER 流水线分阶段（blocking→matching→decision）的工程范式 |
| **C-Pack / BGE** (Xiao et al., SIGIR 2024, arXiv:2309.07597) | bge-large-zh bi-encoder 召回的底座模型与训练语料 |
| **BGE M3-Embedding** (Chen et al., ACL 2024, arXiv:2402.03216) | bge-reranker-v2-m3 精排模型的底座（multi-functionality 多语料架构） |

### 4.2 几何质量 / 窄多边形检测（GIS 数据质量）

| 文献/标准 | 借鉴点 |
|:---|:---|
| **Polsby-Popper** (1991) | 薄度比率/等周商 4πA/P²——紧凑度与 sliver 的经典度量 |
| **ArcGIS Data Reviewer "Polygon Sliver" check** | 工业界 sliver 检查的标准实现（薄度比率 + 面积阈值组合） |
| **Kratochvílová & Cajthaml** (*Accuracy assessment of old large-scale maps and reducing positional error in land use change analyses*, Sci Rep 2025, DOI: 10.1038/s41598-025-12235-9) | 叠置分析（overlay）中 sliver 多边形的影响与剔除——证明 sliver 清理是地图叠加类业务的前置质量要求 |
| **Mestetskiy** (*Circular axis-based shape analysis*, VISAPP 2015, pp. 379-386, DOI: 10.5220/0005261903790386) | 中轴宽度函数——宽度"每点取值"的严格定义；本项目的 2A/P 均宽仅在带状形状下收敛于真实宽度，对紧凑形状低估（圆的 2A/P = 半径），这正是必须与 MIC 配对使用的原因 |
| **Stojmenović & Žunić** (*Measuring elongation from shape centroid*, JMIV 30(1):73-85, 2008) | 伸长度（elongation）度量——尺度不变，但证实其回答不了"绝对窄不窄" |
| **Žunić & Rosin** (*Measuring Shapes with Desired Convex Polygons*, IEEE TPAMI 42(6), 2020, DOI: 10.1109/TPAMI.2019.2898830) | 预定义凸多边形相似度的形状度量族——佐证形状度量需按"待回答的问题"选择，比例类指标与绝对宽度指标各司其职 |
| **JTS `MaximumInscribedCircle`** / **PostGIS `ST_MaximumInscribedCircle`** | 最大内切圆 = 最宽通道宽度，非凸/蜿蜒形状稳健——窄多边形检测的工业标准 |

### 4.3 坐标系与空间索引

| 工具/标准 | 借鉴点 |
|:---|:---|
| **GCJ-02 偏移的学术分析** (IJGI 8(12):567, 2019, DOI: 10.3390/ijgi8120567) | GCJ-02 系"WGS-84 基础上的地形图非线性保密算法"，偏移量级 100-700m、无官方逆向工具——本项目识别的系统性 d_lng≈0.0077° 均值与该文献口径一致 |
| **GEOS STRtree**（经 Shapely 2.x 暴露；R-tree: Guttman, SIGMOD 1984, pp. 47-57, DOI: 10.1145/602259.602266；STR packing: Leutenegger, Edgington, Lopez, ICDE 1997, pp. 497-506, DOI: 10.1109/ICDE.1997.582015） | R-tree 空间索引做候选对召回，300m 缓冲保证重叠对零漏召 |

### 4.4 流水线其他方法步骤的基础文献

| 方法步骤 | 文献依据 |
|:---|:---|
| 候选对召回 = blocking（空间分块代替全量 O(n²) 比对） | **Christen**, *Data Matching: Concepts and Techniques for Record Linkage, Entity Resolution, and Duplicate Detection*, Springer 2012（Indexing 章, pp. 69-100, DOI: 10.1007/978-3-642-31164-2_4） |
| 重合判据 IoU = Jaccard 系数（交集/并集） | **Jaccard**, *The distribution of the flora in the alpine zone*, New Phytologist 11(2):37-50, 1912, DOI: 10.1111/j.1469-8137.1912.tb05611.x |
| Cross-Encoder 精排范式（查询-文档拼接后单模型打分） | **Nogueira & Cho**, *Passage Re-ranking with BERT*, arXiv:1901.04085, 2019 |
| 几何顶点抽稀（地图渲染前降负载） | **Douglas & Peucker**, *Algorithms for the reduction of the number of points required to represent a digitized line or its caricature*, The Canadian Cartographer 10(2):112-122, 1973, DOI: 10.3138/FM57-6770-U75U-7727 |

> 文献核查说明（2026-08-20，三轮自检）：以上所有条目均经逐条检索核实——出处（会议/期刊/卷期页码/DOI）与本文描述的对应关系均已确认；原稿中 Ditto 误标为 KDD 2021（实为 PVLDB 14(1)）、Žunić & Rosin 2020 误描述为"伸长度度量族"、2A/P 误标为"中轴宽度一阶近似"（数学上圆的 2A/P=半径而非直径，与中轴宽度不等价），已全部修正。

---

## 五、交付物清单（outputs/）

| 文件 | 内容 | 角色 |
|:---|:---|:---|
| `fence_dual_goals.html` | 双目标诊断报告：问题围栏分级 + 重叠对地图叠加（248 对，IoU 降序） | **主线交付物** |
| `interactive_inspector.html` + `cases_data.js` + `geodata.js` | 地图抽检器：9 类问题 × 全量北京案例（15,097 条），搜索 + 分页 + 腾讯地图 | **验收工具** |
| `qa_issues_report.csv` | 逐围栏几何/坐标诊断（8,957 行，含 max_width_m 等特征列） | 数据底账 |
| `entity_relations.csv` | 13,026 对关系（iou / distance / bge_sim / cross_encoder_score） | 数据底账 |
| `canonical_entities.csv` | 9,039 个标准实体主数据 | MDM 产出 |
| `EXECUTIVE_REPORT.md` / `pipeline_summary.json` / `dataset_health_report.json` | 汇总指标 | 管理视图 |

---

## 六、遗留事项与后续方向

1. **全量 Cross-Encoder rerank**：受 16GB 内存限制仅抽样 600 对验证，腾出 ~1GB 后跑 `rerank_stage.py` 即可全量（预期把 4,935 对软判定进一步分流）。
2. **12 条空间碰撞告警中含"假碰撞"**：超大异常围栏（最大 5.74 km²）包住小围栏所致，建议先清理超大围栏再复核碰撞对。
3. **MIXED_CRS 12 条坐标真坏**：点面脱节无法自动对齐，需回源核对。
4. **石家庄数据**：抽检器当前锁定北京城区；石家庄 1,608 条已在双目标报告中覆盖，如需地图抽检可复用同一架构。
