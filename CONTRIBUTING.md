# Contributing

## Dev environment (30 秒)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # dev extra 带 pytest；数据准备见 docs/DATA.md §0
pytest tests -q                # 应 328 passed（无客户数据也能全绿）
```

测试里的 27 条 warnings（shapely `oriented_envelope`、pandas dtype 等）是**已知无害**噪音，
不代表环境坏了；新增 warning 才需要解释。

## 先读什么（按顺序）

1. `README.md` §1–§4 —— 系统定位、4-Agent 架构、Decision-Readiness 契约
2. `docs/architecture.md` —— 分层职责（哪层可以碰几何、哪层不行）
3. `docs/DATA.md` —— 仓库**不带**数据；每个数据集怎么一条命令取回、Excel 列契约（§6）
4. 入口二选一：
   - 批处理：`run.py` → `src/pipelines/batch_pipeline.py`
   - 单小区交互：`src/cli.py`（`spatial-di generate/diagnose/inspect`）
5. 改核心前必读两份契约文件：
   - `src/domain/models.py` —— **v1** 持久化模型（`SourceRecord`、`EntityRelation`，`*_raw` 字段）
   - `src/domain/contracts.py` —— **v2** 领域契约（`Observation`、`SpatialRelation`、frozen dataclass）
   - v1→v2 只经 `contracts.py` 尾部的三个 adapter 函数转换，**不要绕过**

## src/ 子包速查

| 想改… | 去… |
|---|---|
| 实体解析/规模推断 | `agents/`（4-Agent 层）+ `entity_resolution/` |
| 围栏候选生成/排序 | `providers/` + `generation/candidate_fusion.py` + `benchmark/runner.py` |
| 验证闸门（fail-closed） | `validation/pipeline.py`、`validation/external_coverage_gate.py` |
| 坐标系/米制几何 | `coordinate/`（MetricGeometryService，UTM 50N） |
| 拓扑/边界分段 | `topology/`、`segmentation/` |
| 道路语义、建筑归属 | `road_semantics/`、`membership/analyzer_v2.py` |
| 基准实验（R0–R15） | `benchmark/`，对应测试 `tests/test_r{N}_*.py`，轮次报告在 `docs/archive_zh/` |

## 硬性约定（违反会被 CI/评审打回）

- **零硬编码绝对路径**：脚本顶部 `_REPO = SDI_ROOT or Path(__file__).parents[1]`，其余一律仓库根相对；临时产物写 `outputs/`，不写 `/tmp`
- **零静默合并红线**：任何让两个实体自动合并的代码路径都不存在也不许加——只产出 work order 给人（README §3.2）
- **数据不进 git**：`data/`、`outputs/` 已 gitignore；OSM 派生物再发布必须带 `© OpenStreetMap contributors (ODbL)` 署名；高德瓦片派生物禁止分发（DATA.md §3.3）
- **frozen dataclass 不可变**：v2 契约字段是 `frozen=True`，改状态=构造新对象
- 测试命名跟随轮次：新增 R{n} 能力 → `tests/test_r{n}_*.py`；纯契约测试进 `test_domain_contracts.py`

## 提 PR 前

```bash
pytest tests -q                      # 必须全绿，不许新增 skip 掩盖失败
python3 run.py                       # 合成样例端到端冒烟（无需任何客户数据）
python3 scripts/verify_data_readiness.py   # 若你改了数据路径/取数脚本
```
