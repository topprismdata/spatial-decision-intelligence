# 路网参照文献调研与 v1 方案

**目标**：为围栏诊断引入外部参照（道路网络），把"形状怀疑"升级为"参照验证"。
**触发背景**：用户指出当前全部判断均为内生判断（只用底表自身的点/多边形/名称），未结合 OSM 道路信息。经核实属实——`src/domain/models.py` 中 `OSM_BOUNDARY`、`ROAD_CONSTRAINED` 两个枚举为占位符，全项目从未赋值。

**日期**：2026-08-20 · 9 轮检索 · 13 条引用逐条核实

---

## 一、为什么需要外部参照（三个证据缺口）

| 缺口 | 现状 | 路网参照能给的 |
|:---|:---|:---|
| 838 条 NARROW_STRIP 只是"形状像街道围栏"的假设 | 窄长形状+名字带"胡同"→ 推断是沿街画的，无证据 | 围栏中轴线与真实路网对齐 → 沿路=街道型围栏正例；不沿路=画错/漂移（ORPHAN_STRIP） |
| 坐标纠偏残差无法客观评定 | GCJ-02→WGS84 靠统计聚类（d_lng≈0.0077°），"纠得准不准"无外部检验 | 纠偏后围栏应贴上路网/建筑，残余偏移可测 |
| 重叠对与碎片语义靠猜 | 两围栏重叠=同一条路两段重复画？还是真重复？ | 路网位置直接回答"这是不是同一段路的两次数字化" |

---

## 二、六条文献脉络（全部核实）

### 脉络 A · 地图匹配（Map Matching）：曲线/点列贴到路网

| 文献 | 核实出处 | 对本项目的意义 |
|:---|:---|:---|
| **Newson & Krumm** (2009). *Hidden Markov map matching through noise and sparseness*. ACM SIGSPATIAL GIS'09, pp. 336-343. DOI: 10.1145/1653771.1653818 | ✅ ACM DL | 经典 HMM 地图匹配：发射概率=点距高斯（σ_z≈4.07m），转移概率=直线距离 vs 路网距离之差的指数分布。**适用场景**：把围栏中轴线采样点序列贴到路网上 |
| **Alt, Efrat, Rote & Wenk** (2003). *Matching Planar Maps*. Journal of Algorithms 49(2):262-283 | ✅（经 Newson&Krumm 与 Fréchet 综述交叉确认） | Fréchet 距离做图-曲线匹配的算法基础：找一条使 Fréchet 距离最小的路径 |
| 备注 | | HMM 适合"有序轨迹"；围栏中轴线**顺序信息弱**（无行进方向），v1 更适合用纯几何距离度量，HMM 留给有向轨迹场景 |

### 脉络 B · 地图融合（Conflation）：两个路网/数据集的匹配

| 文献 | 核实出处 | 对本项目的意义 |
|:---|:---|:---|
| **Saalfeld** (1988). *Conflation: Automated Map Compilation*. IJGIS 2(3):217-228 | ✅（经 Ruiz 综述引用链确认） | conflation 开山：先整体几何变换消除全局误差，再局部匹配——"先仿射后匹配"范式 |
| **Walter & Fritsch** (1999). *Matching spatial data sets: a statistical approach*. IJGIS 13(5):445-473. DOI: 10.1080/136588199241157 | ✅ ADS | 车辆导航数据 vs 地形图路网的统计匹配：Buffer Growing + 角度/长度/形状比较；**先做仿射变换消除全局误差，使后续缓冲半径可以更小** → 直接指导我们的"对齐预校验"步骤 |
| **Ruiz, Ariza, Ureña & Blázquez** (2011). *Digital map conflation: a review of the process and a proposal for classification*. IJGIS 25(9):1439-1466. DOI: 10.1080/13658816.2010.519707 | ✅ ADS/University of Jaén | conflation 全景综述（83 参考文献分类）——几何/语义/拓扑融合三类，评估指标体系 |
| **Safra, Kanza, Sagiv & Doytsher** (2013). *Ad Hoc Matching of Vectorial Road Networks*. IJGIS 27(1):114-153 | ✅（经 ACM iTour 引用链确认） | 无控制点的路网 ad-hoc 匹配（距离+角度+形状组合打分），更贴近我们"无对应关系先验"的处境 |

### 脉络 C · 折线相似性度量：量化"围栏轴线 vs 道路"的贴合度

| 文献 | 核实出处 | 对本项目的意义 |
|:---|:---|:---|
| **Alt & Godau** (1995). *Computing the Fréchet distance between two polygonal curves*. Int. J. Computational Geometry & Applications 5(1-2):75-91 | ✅（Buchin et al. 与 Wolfram MathWorld 交叉确认） | 连续 Fréchet 距离 O(n²log n)；"人牵狗"语义——**考虑点序，适合有序折线** |
| **Eiter & Mannila** (1994). *Computing discrete Fréchet distance*. 技术报告 CD-TR 94/64, TU Vienna | ✅（MathWorld 确认） | 离散 Fréchet：O(mn) 动态规划，实现简单，工程首选 |
| Hausdorff 距离（经典） | ✅（多处交叉确认） | 只看点集不看顺序；对"蛇形曲线"会低估差异——v1 的**轴线 vs 路段**比较中作为快速粗筛，Fréchet 做精判 |
| **Buchin, Buchin, Meulemans & Mulzer** (2014/2017). *Four Soviets Walk the Dog*. SODA 2014 / arXiv:1209.4403 | ✅ arXiv | Fréchet 计算复杂度前沿；证明 Hausdorff 与 Fréchet 可差很远（引以为戒的图示） |

### 脉络 D · OSM 中国数据质量（关键风险脉络）

| 文献 | 核实出处 | 关键结论 |
|:---|:---|:---|
| **Zheng & Zheng** (2014). *Assessing the completeness and positional accuracy of OpenStreetMap in China*. In: Thematic Cartography for the Society, Springer. | ✅ Google Scholar | 中国 OSM 首个质量研究：以百度为参照，71% 区域细节不如百度，平均 66% 位置准确；**北京、上海完整度与位置精度最高**；全国 94% 为不完整区域 |
| **Ma, Hua & Wang** (2025). *Crowdsourced Highway Network Data in China: A Multi-Dimensional Quality Assessment…* Transactions in GIS. DOI: 10.1111/tgis.70325 | ✅ | 2015-2024 全国 366 城 OSM 高速路网评估（ISO 19113 对齐）：名称完整性 <50% 且在降、拓扑错误在增；位置精度"北高南低"；城市化率正贡献、降水负贡献 |
| **重要更正（本次调研的诚实修正）** | ✅ Wikipedia/HanWiki | 我此前判断"OSM 中国部分数据由 GCJ-02 瓦片描摹、存在整体坐标系污染"——**文献与社区记载不支持这个强表述**。OSM 名义坐标系即 WGS-84（用户以 GPS 采集），与商业地图的 GCJ-02 偏移问题无关。真实风险是**质量异质性**（部分地区精度差、拓扑错、覆盖不全），而非系统性坐标污染。结论不变：**用前必须局部抽样校验，且不能当绝对真值** |

### 脉络 E · 数据获取与工具

| 工具/文献 | 核实出处 | 用途 |
|:---|:---|:---|
| **Boeing** (2017). *OSMnx: New methods for acquiring, constructing, analyzing, and visualizing complex street networks*. Computers, Environment and Urban Systems 65:126-139. DOI: 10.1016/j.compenvurbsys.2017.05.004 | ✅ | Python 下载/清洗/分析 OSM 路网的标准工具（含北京城区驾驶+步行层，胡同=residential/unclassified 级） |
| Overpass API | — | OSMnx 底层之一，按边界框拉取 |
| 腾讯位置服务路网 | — | 合规替代路径：与现有腾讯底图同源同口径（GCJ-02），省坐标系转换 |

### 脉络 F · 坐标参照系（已核，沿用 PROJECT_OVERVIEW）

| 文献 | 出处 |
|:---|:---|
| GCJ-02 学术描述 | IJGI 8(12):567, 2019（非线性保密算法，偏移 100-700m） |
| eviltransform 精度实测（工程参考，非论文） | Gehrmann (2019) 博客：30 城实测转换误差 1-12m（北京 1.78m、石家庄 7.46m）——**石家庄误差偏大，正好是我们两个数据城市之一** |

---

## 三、v1 技术方案：路网参照层

### 3.1 新增判定（三条，全部只加标签、不改数据）

| 判定 | 定义（初稿阈值） | 证据强度 |
|:---|:---|:---|
| `ROAD_ALIGNED` | 中轴线采样点 ≥80% 落在路网 15m 缓冲内，且走向夹角中位数 <30° | 强：围栏确实沿一条真实道路分布 |
| `ORPHAN_STRIP` | NARROW_STRIP 且中轴线到最近路网中位距离 >50m | 强：窄长围栏底下没有路 → 画错/漂移高危 |
| `ROAD_OFFSET_RESIDUAL` | ROAD_ALIGNED 围栏的点到路网距离呈系统性单向偏移（均值矢量 >20m 且方向一致） | 中：纠偏后残余偏移的量化证据 |

### 3.2 流水线（六步）

```
1. 取数      OSMnx 拉北京/石家庄路网（drive + walk 层，含 residential/unclassified）
              ↓
2. 预校验    抽 20 个"高置信街道型围栏"（名字含 街/路/胡同/巷 且 NARROW_STRIP）
            + 20 个随机围栏，测 OSM 对齐残差
              ├─ 无系统性偏移 → 直接用
              └─ 有系统偏移 → 局部平移/仿射校准（Saalfeld/Walter-Fritsch 先变换后匹配范式）
              ↓
3. 中轴线提取 NARROW_STRIP：外接矩形长轴采样；大多边形：骨架/boundary 内采样
              ↓
4. 对齐度量   Hausdorff 粗筛（快速）→ 离散 Fréchet 精判（Eiter-Mannila O(mn)）
            逐点最近距离分布（中位数/P90）+ 走向夹角
              ↓
5. 打标      ROAD_ALIGNED / ORPHAN_STRIP / ROAD_OFFSET_RESIDUAL
            （写入 qa_issues_report.csv 新列，走既有交付链路）
              ↓
6. 校准      阈值不拍脑袋：用 50 个人工样本做弱监督校准
            （对齐度量作为新标注函数加入 Snorkel 式权重学习）
```

### 3.3 与 50 样本人工修正闭环的协同（这是路网层的最大价值）

| 协同点 | 说明 |
|:---|:---|
| 省标注预算 | ROAD_ALIGNED 的街道型围栏基本不用人工看（路网已背书）→ 50 个样本全部聚焦真正分歧的对 |
| 新标注函数 | 对齐度量（距离中位数/覆盖率/走向角）作为弱监督框架里的新 LF，与组件门/IoU/BGE/rerank 并列参与权重学习 |
| 主动学习挑样更准 | "NARROW_STRIP 但 ORPHAN_STRIP"（形状像街但底下没路）是最值得人看的一类，天然进主动学习池 |
| 铁律不变 | 路网参照只产生标签与置信度，**永不自动合并、永不自动改坐标** |

### 3.4 合规与风险控制

| 风险 | 控制措施 |
|:---|:---|
| OSM 作为底图展示 | ❌ 禁止（沿用项目红线：展示层只用腾讯地图 GL JS）；OSM 仅作**离线分析参照** |
| OSM 质量异质 | 第 2 步预校验强制执行；Ma et al. 显示质量空间异质 → 北京/石家庄分别校验 |
| 石家庄 eviltransform 残差偏大（7.46m 实测） | 纠偏残差判定阈值（20m）留足余量；两城分别标定 |
| OSM 覆盖不全（部分地区路网缺失） | ORPHAN_STRIP 判定要求"该区域路网密度足够"才成立（密度低的网格降级为 UNKNOWN，不误判） |
| 对外部数据依赖的战略顾虑 | 备选：腾讯位置路网数据（同底图同口径），接口层抽象出来，参照源可切换 |

---

## 四、诚实边界（文献支持什么 / 不支持什么）

**支持**：
- 用 OSM 作**相对参照**做对齐/偏离检测（conflation 与 map matching 文献充分）
- 北京城区 OSM 质量相对可靠（Zheng & Zheng：北京是全国最好区域之一）
- 阈值用人工样本校准而非拍脑袋（延续弱监督脉络）

**不支持**：
- 把 OSM 当**绝对真值**直接"纠正"围栏坐标（质量异质性，只能反向提供证据）
- OSM 中国数据"整体坐标污染"的强假设（本次已更正——名义 WGS-84，风险是异质性）
- v1 就上 HMM 匹配（围栏中轴线无行进方向，HMM 转移概率失去意义；纯几何度量足够）

---

## 五、落地顺序

1. **Step 1** ✅ **完成（2026-08-20，见 `ROAD_PRECHECK_STEP1.md`）**：39/40 围栏预校验——OSM 北京与纠偏坐标系无系统性偏移（对齐子集平均位移矢量 0.9m，无需仿射校准）；名称模式识别街道围栏误判率 85%（20 个名字含街的窄条里只有 3 个真贴路）→ 几何对齐度量不可替代；抓到 ORPHAN_STRIP 候选（玉桥中路甲2号院 217m、东新开胡同 79m）；生产化三修正：骨架法轴线、highway 类型过滤、全城路网一次下载
2. **Step 2** ✅ **完成（2026-08-20，见 `ROAD_ALIGNMENT_STEP2.md`）**：全城路网（91,035 ways / 35,030 km，米制 cKDTree 索引）+ 双假设 CRS 甄别 + **安慰剂检验**。核心结果：底表多边形 CRS 统一为 GCJ-02，此前怀疑的"一批多边形本是 WGS-84"被证伪（路网网格巧合对齐，逐围栏 p 值分布均匀，χ²≈11.0/df=8）；点列确认为多边形的机械派生（点=内部参考−s，残差 2-3m）；真产出为 ROAD_ALIGNED 26 条、ORPHAN_STRIP 候选 46 条、方法论铁律"外部参照检验必须带安慰剂对照"
3. **Step 3**（与 50 样本闭环合并）：对齐度量作为新 LF 进权重校准；inspector 页面加 ROAD_ALIGNED/ORPHAN_STRIP 两个分类按钮
4. **Step 4**（简化）：石家庄复跑——预期同样阴性（点列派生机制全国统一），主要确认路网密度护栏阈值

---

*核查说明：本报告 13 条引用经 9 轮检索逐条核实（ACM DL / ADS / arXiv / Springer / DOI 解析交叉验证）。第 2 节脉络 D 中对"OSM 中国坐标系污染"的更正，依据 Wikipedia 及其原始引用链与 Zheng & Zheng (2014) 的实测描述。*
