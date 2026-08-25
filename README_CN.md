# 空间决策智能（Spatial Decision Intelligence）

**面向企业决策引擎的可信空间世界模型与决策就绪引擎。**

`可信世界状态` · `决策就绪` · `可解释诊断` · `人工治理` · `MIT 开源`

> **核心问题：** 在优化辖区、拜访路线、门店覆盖或配送网络之前，系统首先回答一个更基础的问题：  
> **数据所描述的空间世界，是否足够可信，足以支持下一步决策？**

Spatial Decision Intelligence 将坐标不一致、围栏损坏和空间实体歧义，转换成经过验证、可追溯、可供下游决策引擎安全使用的**空间事实（Trusted Spatial Facts）**。

当前经过真实数据验证的首个落地场景是 **Geofence Integrity（围栏完整性诊断）**：9,039 条真实围栏已全量跑通（见[真实证据](#真实证据9039-条真实围栏验证)）。

---

## 一、 产品定位与体系架构

本项目采用双层品牌定位：

```text
Spatial Decision Intelligence (平台愿景)
└── Spatial World Model Integrity Engine (当前核心产品：空间世界模型可信层)
    └── Geofence Integrity (场景 #1：围栏完整性诊断，已验证落地)
```

### 在 TopPrism 决策操作系统中的位置

在 TopPrism（SVDE 架构）体系中，**Agent 是接口，协议是运行时**。本项目作为空间底座，处于决策语义层与求解器之前：

```text
企业现实数据 (Enterprise Spatial Reality)
门店、围栏、坐标、道路、辖区、历史底表
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ Spatial World Model Integrity Layer (本项目当前能力)     │
│ 空间世界模型可信层 · 决策前诊断闸门                     │
│                                                         │
│ · 坐标系统一：WGS-84 / GCJ-02 漂移自动校正与点重构      │
│ · 几何体检与自愈：自相交拓扑闭合、MIC 工业级窄条检测    │
│ · 空间实体解析：空间重叠 (IoU) + 组件硬门 + 交叉编码重排│
│ · 决策就绪闸门：Fail-Closed 拦截阻断，生成三级复核工单  │
└────────────────────────────┬────────────────────────────┘
                             │ Trusted Spatial State (可信空间状态)
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Decision Semantic Layer                                 │
│ 将业务目标编译为带有显式空间约束的决策对象               │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Decision Compiler & Solver (决策求解器)                 │
│                                                         │
│ · 拜访排程 visit-scheduling-optimizer                   │
│ · 辖区规划 market-partition                             │
│ · 配送调度 open-dispatch                                │
│ · 门店潜力 themed-street-engine                         │
└────────────────────────────┬────────────────────────────┘
                             ▼
                  执行 → 结果 → 决策记忆 (Decision Memory)
```

这意味着本项目解决的不是 *“围栏应该怎么画”*，而是：  
**“决策引擎看到的空间世界是否真实、统一、无冲突，并且足以支持下一步决策？”**

---

## 二、 它不是什么（What It Is NOT）

为建立严谨的工程与学术边界，明确本项目**不是**：

1. **不是通用 GIS 可视化软件**：展示空间不是终点，输出带证据的诊断事实才是核心；
2. **不是自动合并的黑盒 MDM**：坚守 **0 自动静默合并** 铁律，所有疑似实体冲突均推入可追溯的人工工单队列；
3. **不是下游策略优化求解器**：不替代辖区规划（`market-partition`）或排程算法（`visit-scheduling-optimizer`），而是充当它们的**前置质量闸门（Fail-Closed Gate）**；
4. **不是所有空间场景都已验证完毕**：目前仅在 **Geofence Integrity** 场景完成真实数据闭环，其余场景（如渠道冲突、空白网格）属于演进路线图。

---

## 三、 决策就绪契约（Decision-Readiness Contract）

下游决策引擎消费空间数据前，必须满足以下六维契约：

| 契约维度 | 决策前必须回答的问题 | 本项目当前能力 | Fail-Closed 处置策略 |
| :--- | :--- | :---: | :--- |
| **坐标可信** | 点、面、路网是否处于统一无偏的空间参考系？ | ✅ 已实现 | 自动七参数校正；无法对齐者**隔离** |
| **几何可信** | 围栏是否拓扑有效、无自相交、无窄条退化？ | ✅ 已实现 | `make_valid` 自动自愈；严重畸形者**拦截** |
| **实体可信** | 相似记录是同一实体、兄弟分期还是独立实体？ | ✅ 已实现 | 组件硬门 + Cross-Encoder 精排判定 |
| **关系可信** | 是否存在地面重复计数、异常重叠或辖区碰撞？ | ✅ 已实现 | 空间 IoU 结合语义重排，分流为三级工单 |
| **决策适用** | 是否满足下游特定求解器的输入契约？ | ✅ 已实现 | 专用 Adapters（Territory / Visit / Coverage） |
| **时效可信** | 空间数据是否依然代表最新的客观现实？ | 路线图 | 规划中（结合遥感时相更新） |

---

## 四、 诊断推理与证据链闭环

引擎输出严格遵循 **Finding $\rightarrow$ Evidence $\rightarrow$ Impact $\rightarrow$ Recommended Review $\rightarrow$ Disposition** 标准：

```text
Finding (发现了什么)
  └─ 示例: 围栏 SRC_0042 为严重窄条退化 (MIC 直径仅 7m，长度 340m)
Evidence (客观证据)
  └─ 规则: MAXIMUM_INSCRIBED_CIRCLE < 50m; 测算指标: max_w=7.1m, mean_w=4.2m, len=340m
Impact (下游决策污染风险)
  └─ 阻断: [market-partition, open-dispatch]；后果: 导致辖区边界严重扭曲、送货可达性失效
Recommended Review (人工复核建议)
  └─ 建议核查是否为沿街带状商铺，建议在源头重新按建筑轮廓核定
Disposition (人工处置与回流)
  └─ 审核员选择: [CONFIRM_REPAIR / SPLIT / QUARANTINE] ──► 回流至 Decision Memory
```

---

## 五、 真实证据（9,039 条真实围栏验证）

在 9,039 条真实业务围栏（北京 7,431 + 石家庄 1,608）上完成全量实证：

| 检验主张 (Claim) | 实测证据 (Evidence) | 状态 |
| :--- | :--- | :---: |
| **坐标系系统性漂移纠正** | 8,332 条 WGS-84 点 vs GCJ-02 面完成空间纠偏；505 条零点从质心重构 | **已实证** |
| **拓扑打结自愈** | 539 个自相交/蝴蝶结多边形 100% 自动自愈闭合 | **已实证** |
| **工业级窄条检测** | 基于最大内切圆（MIC）检出 838 条窄条退化围栏（淘汰误报率 70% 的旧长宽比规则） | **已实证** |
| **语义与空间消歧** | 4,931 对软关联完成全量 BGE Cross-Encoder 精排（MPS GPU 加速 410 秒完成） | **已实证** |
| **三级工单智能分流** | Tier 1 高危待复核 1,311 对 / Tier 2 常规 2,808 对 / Tier 3 安全归档 8,907 对 | **已实证** |
| **零误合并红线** | 自动合并数恒为 0，杜绝主数据污染 | **已实证** |

> **证据不支持什么（反证声明）：**  
> 1. 本证据证明了空间数据体检、纠偏与工单分流的有效性，**不代表下游辖区方案已经自动最优**；  
> 2. 弱监督自绘围栏目前处于数据准备（7,630 瓦片切片）与初步验证阶段，尚未在生产中替代采购围栏。

---

## 六、 快速开始（Quick Start）

本项目支持干净机器开箱即用，无需配置外部私有数据：

### 1. 安装环境

```bash
git clone https://github.com/topprismdata/spatial-decision-intelligence.git
cd spatial-decision-intelligence

# 创建 Python 3.10 虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -e .
```

### 2. 运行合成基准诊断

```bash
# 使用内置 30 条合成典型退化围栏快速体检
spatial-di diagnose examples/sample_fences.geojson

# 或指定自定义 Excel / GeoJSON / CSV 文件
spatial-di diagnose /path/to/your/fences.xlsx --output-dir outputs/
```

### 3. 启动多城市交互式抽检器

```bash
# 启动本地案例抽检器（支持北京/石家庄/工单导出）
open outputs/interactive_inspector.html
```

---

## 七、 许可证与代码结构

* **代码许可证**：[MIT License](LICENSE)
* **核心模块**：
  * `src/domain/world_model.py`：空间世界模型核心数据契约（Entities, Findings, Impact, TrustedState）；
  * `src/adapters/decision_adapters.py`：下游决策引擎（Territory, Visit, Coverage）Fail-Closed 适配器；
  * `src/geometry/ai_fence_guard.py`：AI 围栏质检拦截与防御性降级网关；
  * `src/cli.py`：统一 `spatial-di` 命令行工具。
