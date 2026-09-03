# DATA.md — 数据获取与准备指南（Handover Runbook）

> **仓库不携带任何数据。** 两个原因：① 合规——客户清单是商业机密，卫星瓦片受第三方
> 条款约束，原始地理数据不上公开托管（测绘法合规，见 `.gitignore` 尾注）；② 体积——
> 1.4 GB 派生数据。本文说明**每个数据集由谁生成、如何一条命令取回**，全部结论标注
> 代码位置（`file:line`），可逐一核对。
>
> **客户 Excel 不是接手前提。** 管线的核心能力（围栏生成、OSM 诊断、4-Agent 推理、
> 几何 QA）全部可跑在合成样例 + 公开 OSM 数据上；真实客户清单仅在复算生产批次时才需要
> （列契约见 §6）。

路径约定：脚本一律使用**仓库根相对路径**（`clone 到任意目录/任意用户名可跑`）；数据盘在
别处时设 `SDI_ROOT=<绝对路径>`，零改码。

---

## 0. 30 秒上手（全新 clone，不需要任何客户数据）

```bash
git clone https://github.com/topprismdata/spatial-decision-intelligence.git
cd spatial-decision-intelligence
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# 1) 取数据（全走公开/合成来源，联网约 1-2 分钟）
python3 scripts/prepare_sample_data.py --with-fixtures
#    -> data/sample/sample_sites.xlsx   合成 30 条（列名=真实契约，见 §6）
#    -> data/beijing_fixtures/*.json    Overpass 冻结夹具（测试用，ODbL）
#    -> data/sample/osm_window.json     小面积真实 OSM

# 2) 端到端跑主管线（本机实测：30 条记录 -> 30 canonical 实体 + 16 关系检出）
python3 run.py --input data/sample/sample_sites.xlsx

# 3) 测试（无 fixtures 时相关用例自动 skip，不会报错）
pytest tests -q

# 4) 单小区交互式诊断（本就不需要任何 Excel）
python3 -m src.cli generate "示例小区" --address "示例路1号" --lng 116.35 --lat 39.90 --area 32000

# 5) 自检：还缺哪些数据集、分别怎么取
python3 scripts/verify_data_readiness.py
```

离线应急：`--skip-osm` 只生成合成 xlsx（跑通主管线与 90% 测试）；OSM 依赖步骤待联网补拉。

---

## 1. 数据分发矩阵

| 数据 | 敏感性/条款 | 能否进公开仓库 | 协作者获取方式 |
|---|---|---|---|
| 客户场所清单 `data/client_a_sites.xlsx` | 客户商业机密 | ❌ | 项目方按 §6 契约另行发放；演示用合成样例 |
| 真实产出 `outputs/*.csv`（QA 报告、实体关系等） | 含真实小区名/坐标 | ❌ | 各自从数据重建（§2 命令） |
| 卫星瓦片派生 `data/satellite/*.npz` | 高德栅格条款 + 坐标敏感 | ❌ | 有客户 Excel 才能同 id 重建（§5）；合成样例可造小样本 |
| OSM 抽取（beijing_shp / roads / buildings / fixtures…） | **ODbL 公开**，但按仓库合规政策不入库 | ❌（本地取） | Overpass/Geofabrik 一条命令，见 §3 |
| 合成样例 `data/sample/sample_sites.xlsx` | 无真实信息 | 可自由生成 | `scripts/prepare_sample_data.py` |

---

## 2. 数据集清单（规模 / 生成者 / 重建命令）

| 路径 | 规模 | 内容与生成者（写点 `file:line`） | 重建命令 |
|---|---|---|---|
| `data/sample/sample_sites.xlsx|csv` | KB | 合成演示输入（`scripts/prepare_sample_data.py`） | `python3 scripts/prepare_sample_data.py --skip-osm` |
| `data/beijing_fixtures/` | 1.6 MB/3 | 真实 OSM 冻结夹具；消费 `src/observation/overpass_adapter.py:57`、`tests/test_r2_real_osm_smoke.py:31` | `python3 scripts/prepare_sample_data.py --with-fixtures` |
| `data/beijing_shp/` | 207 MB | OSM 官方区域抽取；消费 `scripts/satellite_wall_detection.py:16`、`scripts/scenic_road_block_hull.py` | §3.1 |
| `data/roads/` | 69 MB/30 | Overpass 道路瓦片抽取（`scripts/road_step2a_tiles.py:17`） | `python3 scripts/road_step2a_tiles.py` |
| `data/buildings/` | 1.4 MB/2 | Overpass 建筑窗口（`scripts/draw_step1_buildings.py:8`，窗口 `:11-13`） | `python3 scripts/draw_step1_buildings.py` |
| `data/roads_windows/` | 0.9 MB/2 | 全量道路窗口（`scripts/draw_step1b_allroads.py:8`） | `python3 scripts/draw_step1b_allroads.py` |
| `data/satellite/` | 1.1 GB/7683 | 卫星切片，按记录 id 命名 `SRC_xxxxxx.npz`（`scripts/draw_step8_download_sat.py:184`，瓦片源 `:45`） | §5 |
| `outputs/qa_issues_report.csv` 等管线产出 | KB-MB | `src/pipelines/batch_pipeline.py:45`（入口 `run.py`） | `python3 run.py --input <excel>` |
| `outputs/entity_relations.csv` + rerank | MB | 主管线 + 独立进程 `scripts/analysis/rerank_stage.py` | `python3 run.py …` → `python3 scripts/analysis/rerank_stage.py` |
| `outputs/selfdraw_eval.csv|selfdraw_geoms.json` | MB | `draw_step2_generate.py:25` → step3/4/5 | 依序 `draw_step2→5` |
| `outputs/road_alignment_beijing*.csv|road_placebo*.csv` | MB | `road_step2b_label.py:27`、`2c:21`、`2d:27`、`2e:24`、`2f:25` | 依序 `road_step2b→2f` |
| `outputs/beijing_full|beijing_batch` | 140 MB | `scripts/beijing_full_gb50137.py:65` | 需 beijing_shp + Excel/样例 |
| `outputs/unet_fence_best.pth` | 30 MB | 训练 `scripts/draw_step9_train_unet.py:19-22` | 需 `data/satellite`（小样本可用合成 id） |
| `outputs/scenic_spots|huilongguan_demo|schools` | MB | `scenic_final_package.py:8`、`demo_huilongguan_e2e.py:79` | 对应脚本直跑 |

---

## 3. 公开数据获取细则

### 3.1 OSM shapefile（北京，ODbL）
```bash
mkdir -p data/beijing_shp && cd data/beijing_shp
curl -LO https://download.geofabrik.de/asia/china/beijing-latest-free.shp.zip
unzip -o beijing-latest-free.shp.zip   # 代码消费 gis_osm_roads_free_1.shp / gis_osm_pois_free_1.shp 等
```

### 3.2 Overpass 端点与配额
脚本统一用 `https://overpass-api.de/api/interpreter`（`draw_step1_buildings.py:7`、
`road_step2a_tiles.py:14` 等）。公共实例有配额，大批量改自建镜像（端点是脚本常量，改一处即可）。
`prepare_sample_data.py --with-fixtures` 会写 manifest（source/query/license=ODbL）——**再发布必须署名**
`© OpenStreetMap contributors (ODbL)`。

### 3.3 高德/天地图瓦片（仅内部研究）
`draw_step8_download_sat.py:45-50` 抓高德栅格切片：**禁止二次分发**，协作者如需训练
U-Net，请换用合规图源（Sentinel-2 / .mapbox 授权 / 自采授权影像）并替换该常量。

---

## 4. 管线依赖顺序

```
[any §6-contract Excel] → run.py(batch_pipeline) → outputs/qa_issues_report.csv, entity_relations.csv
                          → rerank_stage.py（独立进程省内存）
OSM: draw_step1_buildings → step2_generate → step3 → step4 → step5 → step6(HTML)
     step7* 稠密道路 → step8_download_sat(需Excel id) → step9_train_unet → step10_eval_unet
Roads: road_step1a_sample → 1b_align → 2a_tiles → 2b_label → 2c_validate → 2d_full → 2e/2f_placebo
City:  beijing_full_gb50137 → outputs/beijing_full · demo_huilongguan_e2e · scenic_* 链
```

---

## 5. 关于 `data/satellite/`（1.1 GB）
npz 以管线内源记录 id 命名（`SRC_{idx+1:06d}`，见 `src/ingestion/parser.py`）→
同 id 重建需要**同一份输入 Excel**。演示可用 `sample_sites.xlsx` 生成 30 个小切片，
足够跑通 step8→9→10 代码路径（`EPOCHS=2 python3 scripts/draw_step9_train_unet.py`）。

---

## 6. 输入 Excel 列契约（`src/ingestion/parser.py::parse_file`，sheet=`sheet1`）
必需/可选见注释；**`prepare_sample_data.py` 生成的样例严格符合本契约**。
`小区编码` · `小区名称`* · `小区地址` · `省份名称|省[内置]` · `城市|市[内置]` ·
`区[内置]` · `街道[内置]` · `经度`* · `纬度`* · `坐标面[内置]`(WKT多边形)* · `面积[内置]`
（* 缺失将大量落入 `NO_GEOMETRY`；其余列自动归入 attrs 透传）

---

## 7. 环境变量（仓库零硬编码密钥）
| 变量 | 用途 | 位置 |
|---|---|---|
| `SDI_ROOT` | 数据/仓库根覆盖 | 各脚本 `_REPO` |
| `ZHIPU_API_KEY` 等 4 个 | 可选 VLM 复核 | `scripts/scenic_vlm_verify.py:7` |
| `EPOCHS/BATCH/BASE` | 训练超参 | `draw_step9_train_unet.py:19-22` |

---

## 8. 交接检查清单
- [ ] `python3 scripts/prepare_sample_data.py --with-fixtures && python3 run.py` 跑通（§0）
- [ ] `python3 scripts/verify_data_readiness.py` 无 MISSING（按你的角色取所需数据集）
- [ ] `pytest tests -q`：320 用例，**22 条已知历史失败**（与数据无关，见 `docs/progress-report`）
- [ ] 再发布任何 OSM 派生物时附 ODbL 署名；高德瓦片派生物不分发
- [ ] 需要复算真实批次时，向项目方索取 §6 契约的 Excel（仅此场景需要客户数据）
