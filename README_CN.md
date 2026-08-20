# 空间决策智能引擎（Spatial Decision Intelligence Engine）

**用可解释的诊断推理，识别业务目标与空间约束之间的冲突。**

`WORLD MODEL` · `FOUNDATION LAYER` · `REAL-DATA VALIDATED` · `ANONYMIZED OPERATIONAL DATA` · `MIT`

> **决策问题：** 空间策略失效时——覆盖缺口、重复投入、辖区悄然重叠——是方案错了，还是方案所依赖的空间数据坏了？优化之前，必须先诊断。

三项核心能力：

- ✓ **空间约束分析**——几何、坐标、拓扑是业务决策的一等约束，不是数据清洗的细节。
- ✓ **双目标冲突诊断**——两个目标同时联合体检（数据可信 **且** 同一块地不重复计数），任一失效都会悄悄腐蚀其上的所有决策。
- ✓ **可解释、可执行的输出**——每条发现都带具体可查的原因；引擎只提议，人拍板（**零自动合并**）。

**首个应用场景：围栏诊断**（本仓库初版名为 `fence-dual-goal-diagnosis`，围栏场景现在是引擎的场景 #1）。9,039 条真实围栏已全量跑通，见[证据](README.md#evidence-real-data-validated-fence-scenario)。

## 为什么存在

企业空间决策永远处于张力之中：增长目标 vs 成本纪律、覆盖范围 vs 服务效率、渠道扩张 vs 经销商冲突——每个权衡都是空间的，每个都算在一张围栏地图上。

- **传统 GIS** 回答"哪里有什么"——展示空间，不判断方案。
- **优化算法** 回答"怎么优化"——但前提是目标、约束、数据可信；坏围栏进，自信的坏辖区出。
- **企业首先需要的是**："现在的空间体系为什么不可靠"——哪些围栏坏了、哪些地被数了两次、各自怎么办。

这就是**诊断**。围栏底表是诊断的起点，因为一份围栏导出表看起来没问题，直到你打开看：

- 多边形自相交；几米宽却几百米长的碎片条带；一条围栏 5.74 km²，邻居们只有 3 万 m²。
- 一半行是 WGS84、一半是 GCJ-02——系统性 ~500 m 偏移，悄悄腐蚀每一次空间连接。
- 同一个小区以近似名字（"XX小区""XX小区(一期)""XX小區"）出现多行，多边形部分重叠。

任何下游决策引擎——辖区设计、拜访规划、覆盖分析——都会继承这三种失效。本引擎是跑在这些引擎**之前**的诊断闸门。

## 双目标诊断框架

```
              业务目标
         目标 A              目标 B
            \                 /
            冲突空间（两目标必须同时成立，
             单独优化一个会掩盖另一个的失效）
                    |
              诊断引擎
                    |
            根因定位（逐围栏/逐对，带证据）
                    |
        优化建议（排序复核队列——人来决定）
```

应用到围栏：**目标 A** = 围栏层可信（几何+坐标质量）；**目标 B** = 地面不重复计数。两目标不可分：既坏又有重复的围栏是最高优先级发现（参考运行中有 112 条恰好处于该交集）。

## 演示：Before → 诊断 → After

```
BEFORE（原始导出，"在 GIS 里看起来挺好"）
  8,332 行坐标系错误（~500 m 系统性偏移）｜539 个自相交多边形｜同一小区重复多行

诊断（199 秒）
  目标A：786 条围栏带原因标记，如"窄条——最宽通道 7 m，绵延 340 m"
  目标B：248 个重叠对按 IoU 排序，如某小区两期工程 IoU 0.48、地址相同
  12 条碰撞告警｜4,935 对近似名待复核

AFTER（人工复核处置队列）
  坐标先纠偏再进空间连接｜异常大围栏在源头修复｜重复逐条人工确认——0 次静默合并
  效果：下游引擎跑在可信围栏层上，不再继承三种失效模式。
```

## 与传统 GIS / 优化的差异

| | GIS | 优化 | **TopPrism 诊断** |
|:---|:---:|:---:|:---:|
| 展示空间 | ✓ | △ | ✓ |
| 发现异常 | △ | ✓ | ✓ |
| 解释原因 | × | × | ✓ |
| 业务目标理解 | × | △ | ✓ |
| 生成行动建议 | × | △ | ✓（路线图） |

## 在 TopPrism 能力体系中的位置

```
        TopPrism AI Decision OS
                 |
          Geo Intelligence
                 |
        Spatial Foundation ← 本仓库
  ┌────────┬────────┬────────┬────────┐
围栏诊断    路线优化    门店潜力   辖区规划
(本仓库)   (open-dispatch (themed-  (visit-scheduling-
           logistics-    street-   optimizer,
           dispatch-     engine)   market-partition)
           clustering)
```

姊妹仓库 [`bge-entity-match`](https://github.com/topprismdata/bge-entity-match) 按**名称**做实体解析；本引擎**几何+名称**联合解析，以空间重叠作为召回真值。两者共同构成决策引擎之下的可信空间+实体基础层。

## 扩展场景（路线图）

同一套"先诊断后优化"循环可推广到：渠道电子围栏诊断、经销商辖区冲突诊断、门店覆盖诊断、配送网络诊断、市场空白诊断。框架不变，只换空间模型与业务规则。

## 证据（围栏场景，真实数据验证）

9,039 条围栏全量运行：8,332 坐标纠偏、539 拓扑自愈、786 问题围栏（52 硬伤）、248 重叠对（IoU>0）、4,935 待复核关系对、12 条碰撞告警、**0 自动合并**，耗时 199 秒（另 19 分钟抽样精排）。

完整证据表与"证据不支持什么"反证说明见英文版 [README](README.md#evidence-real-data-validated-fence-scenario)。完整方法论与三轮文献核查记录见 [`outputs/PROJECT_OVERVIEW.md`](outputs/PROJECT_OVERVIEW.md)、[`docs/methodology.md`](docs/methodology.md)、[`docs/architecture.md`](docs/architecture.md)、[`docs/examples.md`](docs/examples.md)。

## 快速开始

```bash
pip install shapely pandas openpyxl fastembed onnxruntime torch
export FASTEMBED_CACHE_DIR=~/.cache/fastembed
export OMP_NUM_THREADS=4
export KMP_DUPLICATE_LIB_OK=TRUE

python run.py                       # 全量流水线 M0 → M3
python generate_fence_dual_goals.py # 双目标 HTML 报告（含地图）
python generate_inspector.py        # 交互式案例抽检器
python rerank_stage.py              # 全量精排（需 ~1 GB 空闲内存）
```

## 边界与限制

精排在 16 GB 参考机上为抽样模式（600/4,935 对）；无法确信对齐的 MIXED_CRS 围栏隔离而非静默纠正；无几何重叠的纯名称重复不在本引擎范围；名称解析规则针对中文居住区命名调优；目前仅围栏一个场景落地，扩展场景为路线图而非结果。

## License

MIT — 见 [`LICENSE`](LICENSE)。
