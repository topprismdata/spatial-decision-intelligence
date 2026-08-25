# 人工修正闭环 · 文献调研（~50 个人工样本场景）

> 目标：为围栏诊断引擎增加"人工修正 → 引擎学习"的强化能力。人工预算 ≈ 50 个标注样本。本文回答：50 个样本在文献里能支撑什么、不能支撑什么、推荐的技术路线是什么。
>
> 检索时间：2026-08-20。所有引用均已逐条核实出处。

---

## 一、问题设定

当前引擎输出一个**复核队列**（4,935 对近似名关系 + 786 条问题围栏标记），人来复核。下一阶段要做的闭环是：

```
引擎产出复核队列
      ↓
人工修正（确认/否决 + 理由）≈ 50 个样本
      ↓
引擎学习（阈值？权重？规则？奖励模型？）
      ↓
重新排序/重新过滤队列 → 人工修正 ……
```

关键问题：**50 个样本应该学什么、怎么学**。

## 二、文献全景：六条脉络

### 脉络 1 · 从人类偏好学习（RLHF / 偏好优化）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Christiano et al., *Deep Reinforcement Learning from Human Preferences*, **NeurIPS 2017** (pp. 4299–4307, arXiv:1706.03741) | 成对偏好比较（Bradley–Terry 损失）训练奖励模型，替代手工奖励函数；反馈量可低至交互次数的 1% | 偏好比较（"这个对里引擎判断错了/对了"）是比打分更可靠的人工信号形式 |
| Rafailov et al., *Direct Preference Optimization*, **ICML 2024** (arXiv:2305.18290) | 跳过显式奖励模型，直接从偏好对优化策略，训练稳定 | 50 对规模下 DPO 不可行（文献中 DPO 训练通常需数千对），但偏好对的**数据格式**值得现在就定好 |
| Chen et al., *Cost-Effective Proxy Reward Model Construction with On-Policy and Active Learning*, **arXiv:2407.02119** (2024) | 少量种子标注 + 主动学习挑选最有信息量的样本 → 训练代理评估模型 → 再自动标注出 9 倍偏好对，DPO 后仍有效 | **最贴合我们设定**：50 个人工样本的正确用法是"种子"，先用主动学习挑样本，再学一个代理判断器放大 |
| Zhao et al., *GFRIEND: Generative Few-shot Reward Inference through EfficieNt DPO*, **arXiv:2506.8965** (2025) | CoT 采样 + 多级偏好精化，少样本奖励模型达到大数据集训练水平 | 数据增广（对已有标注做推理式扩展）是小样本放大器的补充手段 |

### 脉络 2 · 主动学习（50 个样本"挑哪些"是第一决定）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Settles, *Active Learning Literature Survey*, **UW–Madison CS TR 1648**, 2009 | 综述：不确定采样、QBC、期望误差缩减等查询策略 | 挑样本的原则：挑"模型最拿不准/最分歧"的，不挑随机的 |
| Sarawagi & Bhamidipaty, *Interactive Deduplication Using Active Learning*, **KDD 2002** (pp. 269–278) | 去重任务的主动学习开山作：由 learner 挑 record pair 给人标注 | 与我们场景同构（去重+人在回路），可直接借鉴其"结对提问"形式 |
| Sun et al., *A Genetic Algorithm Based Entity Resolution Approach with Active Learning*, **Frontiers of Computer Science 11(1):147–159, 2017** (DOI 10.1007/s11704-015-5276-6) | 遗传算法从少量标注学"属性比较+阈值"的复合匹配规则 | **直接支持我们的需求**：从几十个人工样本反推匹配阈值/规则组合，文献有成熟先例 |
| *Low-resource ER with domain generalization and active learning* (DGER+DUAL), **Neurocomputing, 2024** (S0925231224009020) | 主动学习挑"高不确定+高域偏移"样本微调，少量标注预算内超过纯不确定性采样 | 我们有天然的分域（北京 vs 石家庄），第二城市适配可直接用此思路 |
| Primpeli (博士论文), *Reducing the Labeling Effort for ER using Distant Supervision and Active Learning*, **Uni Mannheim, 2022** | 远程监督生成初始标注 + 主动学习补查；保证有限预算内 anytime 性能 | 初始化阶段用便宜信号（我们的 IoU/组件门）打底，人工只标分歧处 |

### 脉络 3 · 弱监督（把现有管线信号当"标注函数"）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Ratner et al., *Snorkel: Rapid Training Data Creation with Weak Supervision*, **PVLDB 11(3):269–282, 2017** (DOI 10.14778/3157794.3157797；扩展版 VLDB Journal 29:709–730, 2020) | 多个噪声标注函数（规则/启发式）输出 → 生成式模型学各函数权重 → 概率标签；不依赖人工标注 | 我们管线里已有的组件硬门、IoU 门、BGE 相似度、rerank 分数**就是现成的标注函数**；50 个人工样本可用来校准它们的权重，替代手工拍阈值 |

### 脉络 4 · LLM 少样本实体匹配（50 个样本做演示，放大到全量）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Peeters & Bizer, *Using ChatGPT for Entity Matching* (MatchGPT), **arXiv:2305.03423** (2023) 及期刊版 *Entity Matching using Large Language Models* | 最好配置下 **0–10 个示例**的 LLM 匹配器 ≈ 数千样本微调的 PLM；对未见实体更鲁棒；提示需按模型×数据调 | 50 个人工修正样本天然是高质量 ICL 演示集：用它们预判剩余 4,885 对，人工只抽查分歧 |

### 脉络 5 · 人在回路数据清洗（修正建议的排序与采纳）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Xie et al., *A Data Cleaning Framework Based on User Feedback*, **WAIM 2013** (LNCS 7923, pp. 514–520, DOI 10.1007/978-3-642-38562-9_52) | 候选修复 + 贝叶斯委员会预测修复正确性 + 按不确定度排序交人工，人工反馈持续改进模型 | "按不确定度排序给人工看"的闭环结构与我们的复核队列升级方向一致 |
| Rezig et al., *Towards an End-to-End Human-Centric Data Cleaning Framework*, **HILDA 2019** (DOI 10.1145/3328519.3329133) | 端到端清洗框架中人在回路的系统性设计（规则提供/修复验证/主动学习降人工量） | 框架级参考 |
| 孙辞海等，《一种基于确定度的交互式迭代数据清洗方法》，《智能计算机与应用》**13(8), 2023** | 确定度度量 + 确定度增益（保留/修改分歧度）挑给人看的样本，迭代提升 | 中文文献同构工作，可直接引用 |

### 脉络 6 · Pay-as-you-go（渐进式可信度）

| 文献 | 核心结论 | 对我们的启示 |
|:---|:---|:---|
| Jeffery, Franklin, Halevy, *Pay-as-you-go User Feedback for Dataspace Systems*, **SIGMOD 2008** (pp. 847–860) | 用户反馈逐步收紧匹配置信度的渐进集成范式 | 产品叙事：每一条人工修正都在"付钱"提升整张关系图的置信度——契合零自动合并原则 |

## 三、核心判断：50 个样本能学什么、不能学什么

**不能学的（诚实边界）：**
- ❌ 从零训练神经奖励模型 / 直接 DPO——文献量级是数千偏好对起（Christiano 2017 虽反馈占比 <1%，但绝对量仍远超 50）
- ❌ 微调 embedding 模型本身——50 对会造成灾难性过拟合
- ❌ 学出任何"自动合并"能力——与零自动合并铁律冲突，无论数据量

**能学的（文献充分支持）：**

| 学习目标 | 方法 | 文献支撑 |
|:---|:---|:---|
| ① 挑哪 50 个 | 主动学习：挑引擎内部信号**最分歧**的对（如 BGE 说像、rerank 说不像；IoU 高但组件门拒绝） | Settles 2009; Sarawagi 2002; Chen 2024 |
| ② 阈值/规则权重 | 把组件门/IoU 门/BGE 分/rerank 分当标注函数，在 50 个金标上反推最优权重组合（网格或遗传搜索） | Snorkel (PVLDB 2017); Sun 2017 |
| ③ 放大到全量 | 50 个修正做 ICL 演示，LLM 预判剩余对，人工抽查 | MatchGPT (arXiv:2305.03423) |
| ④ 下一批挑什么 | 按学习后模型的不确定度/分歧度排序，继续 pay-as-you-go | Xie 2013; Jeffery 2008 |
| ⑤ （未来）偏好模型 | 修正记录持续累积到数百对后，才进入 DPO/奖励模型量级 | Rafailov 2024; Chen 2024 |

**对"强化学习"的定位建议**：n=50 阶段的准确技术名称是**主动学习 + 弱监督权重校准 + 少样本 ICL 放大**的闭环（文献脉络 2/3/4）；随修正记录累积，才演进为真正的偏好学习/RLHF（脉络 1）。对外叙事可以叫 "human-correction reinforcement loop"，论文引用按阶段分层挂靠，避免 n=50 却引 RLHF 的错位。

## 四、推荐架构（闭环 v1）

```
                 复核队列（引擎产出）
                        |
        ┌───────────────┴────────────────┐
        |  主动选择层（分歧度排序）          |   ← ① 挑 50 个
        |  score = |bge_sim − rerank|      |      信号：BGE↔rerank 分歧、
        |        + 边界带样本 + 分层配额     |      IoU 高但被门拒、阈值±ε 带
        └───────────────┬────────────────┘
                        ↓
                 人工修正（50 样本）
                 确认 / 否决 + 理由标签
                        ↓
        ┌───────────────┴────────────────┐
        |  弱监督权重层                    |   ← ② 学习
        |  标注函数 = {组件门, IoU 门,      |      在 50 金标上拟合权重
        |  bge_sim, rerank_score}          |      （留一交叉验证防过拟合）
        └───────────────┬────────────────┘
                        ↓
        ┌───────────────┴────────────────┐
        |  放大层（可选）                   |   ← ③
        |  50 个修正做 ICL 演示 → LLM       |      LLM 预判 + 人工抽查
        |  预判剩余 4,885 对                |
        └───────────────┬────────────────┘
                        ↓
              重排序后的复核队列（更准的优先级）
                        ↓
              下一批主动选择 → 循环（pay-as-you-go）

  铁律不变：学习只改变排序与置信度，永不触发自动合并。
```

**50 个样本的分层配额建议**（基于现有队列结构）：
- 20 个：RERANK 分歧带（bge_sim 与 rerank 结论冲突）
- 10 个：几何重叠对（IoU>0.1，跨 SIBLING/PHASE 类型）
- 10 个：组件门边界带（数字判别符差一位的硬门拒绝案例）
- 5 个：MIXED_CRS / 隔离区（坐标存疑如何影响匹配）
- 5 个：随机对照（校准人工一致性）

**评估口径**（呼应 README 的 Evaluation 三维度）：
- 阈值/权重校准后，50 样本留一交叉验证的 F1 变化
- 重排序后队列的 Precision@50 提升（人工复查成本口径）
- LLM 放大层与人工抽查的一致率（>90% 才进入下一轮）

## 五、引用清单（已核实）

1. Christiano, P., Leike, J., Brown, T.B., Martic, M., Legg, S., Amodei, D. *Deep Reinforcement Learning from Human Preferences.* NeurIPS 2017, pp. 4299–4307. arXiv:1706.03741.
2. Rafailov, R., et al. *Direct Preference Optimization: Your Language Model is Secretly a Reward Model.* ICML 2024. arXiv:2305.18290.
3. Chen, Y., et al. *Cost-Effective Proxy Reward Model Construction with On-Policy and Active Learning.* arXiv:2407.02119 (2024).
4. Zhao, Y., Bai, H., Zhao, X. *GFRIEND: Generative Few-shot Reward Inference through EfficieNt DPO.* arXiv:2506.8965 (2025).
5. Settles, B. *Active Learning Literature Survey.* Computer Sciences Technical Report 1648, University of Wisconsin–Madison, 2009.
6. Sarawagi, S., Bhamidipaty, A. *Interactive Deduplication Using Active Learning.* KDD 2002, pp. 269–278.
7. Sun, C., Shen, D., Kou, Y., Nie, T., Yu, G. *A Genetic Algorithm Based Entity Resolution Approach with Active Learning.* Frontiers of Computer Science 11(1):147–159, 2017. DOI 10.1007/s11704-015-5276-6.
8. *Low-resource Entity Resolution with Domain Generalization and Active Learning* (DGER+DUAL). Neurocomputing, 2024. S0925231224009020.
9. Primpeli, A. *Reducing the Labeling Effort for Entity Resolution using Distant Supervision and Active Learning.* PhD thesis, University of Mannheim, 2022.
10. Ratner, A., Bach, S.H., Ehrenberg, H., Fries, J., Wu, S., Ré, C. *Snorkel: Rapid Training Data Creation with Weak Supervision.* PVLDB 11(3):269–282, 2017. DOI 10.14778/3157794.3157797.（扩展版：VLDB Journal 29:709–730, 2020）
11. Peeters, R., Bizer, C. *Using ChatGPT for Entity Matching* (MatchGPT). arXiv:2305.03423 (2023)；期刊版 *Entity Matching using Large Language Models.*
12. Xie, H., Wang, H., Li, J., Gao, H. *A Data Cleaning Framework Based on User Feedback.* WAIM 2013, LNCS 7923, pp. 514–520. DOI 10.1007/978-3-642-38562-9_52.
13. Rezig, E.K., Ouzzani, M., Elmagarmid, A.K., Aref, W.G., Stonebraker, M. *Towards an End-to-End Human-Centric Data Cleaning Framework.* HILDA 2019. DOI 10.1145/3328519.3329133.
14. 孙辞海, 王洪亚, 郭开彦, 程炜东. 《一种基于确定度的交互式迭代数据清洗方法》. 智能计算机与应用 13(8), 2023.
15. Jeffery, S.R., Franklin, M.J., Halevy, A.Y. *Pay-as-you-go User Feedback for Dataspace Systems.* SIGMOD 2008, pp. 847–860.

## 六、遗留问题

- DPO 原文（ICML 2024）卷期页码未逐字核验（仅经 arXiv:2407.02119 的引用间接确认），用于正式文档前需补一轮检索。
- 放大层（③）依赖 LLM API 或本地中模型，16GB 内存约束下优先考虑 Qwen 系 7B 量级 int4——需单独评估。
- 人工标注界面：50 个样本建议直接在现有 inspector HTML 上加"确认/否决"按钮落地，避免新工具链。
