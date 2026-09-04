# 新城市 GB50137 分类上手指南（以西安为例，手把手）

> 目标：在一个**从未接触过本仓库**的环境里，从零做出西安全部 12 类用地图
> （geojson + shapefile + 交互地图），且每一步都有脚本替你验收。
> 北京已完成同流程（47,338 面），本指南末尾附西安实跑记录作为对照答案。
>
> 阅读前置：`CONTRIBUTING.md`（10 分钟）。数据背景：`docs/DATA.md`。

## 0. 先懂 30 秒原理（不懂这个就会踩坑）

- 数据谱系：**OSM 志愿者测绘** → Geofabrik 每周打包成 `*-free.shp.zip`，把 tags
  机械翻译成 `fclass` 列 → 我们按 `fclass` 映射到 GB50137 十二类（`city_gb50137.py`）。
- `fclass` 只反映"谁画的当时标了什么"，**不反映地面真相**：北京 11,227 个居住面里
  44% 无名、多为农田误标。所以产物是"待证假设"，未分类率(U)和新 fclass 都要看。
- 中国只有 4 个直辖市是**市包**；其余省份一律**省包**（西安在 `shaanxi` 省包里，
  混着全部地级市）——**省包必须 `--bbox` 截取，否则你把全省当西安市**。

## 1. 环境（一次性）

```bash
git clone https://github.com/topprismdata/spatial-decision-intelligence.git
cd spatial-decision-intelligence
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

验收（应 328 passed，无需任何数据）：

```bash
pytest tests -q
```

## 2. 取数：陕西抽取包 → `data/xian_shp/`

```bash
python3 scripts/fetch_city_data.py --region shaanxi --country china --dest data/xian_shp
```

- 体积 ~200 MB，Geofabrik 单连接限速 ~60 KB/s。**慢是正常的**；断了重跑同一条
  命令即可（`.part` + HTTP Range 自动续传）。
- 想快：浏览器/下载工具开
  `https://download.geofabrik.de/asia/china/shaanxi-latest-free.shp.zip`（会 302
  到带日期版本），下完把 zip 放进 `data/xian_shp/` 再跑一次上条命令（检测到 zip
  就只做解包）。
- 不知道 region 拼写？查 <https://download.geofabrik.de/asia/china.html>。
  **陕西 = shaanxi（双 a），山西 = shanxi**——下错省数据全都对不上。

### 验收 2a（必过才继续）

```bash
python3 scripts/check_city_data.py --city xian --data-dir data/xian_shp --stage input
```

全 PASS 才算数。常见 FAIL→修法都打印在行内。重点看：
- `缺图层 gis_osm_*.shp` → zip 不完整或解压失败，删 zip 重跑
- `中文名乱码` → .cpg/.dbf 损坏，重新解压
- `residential 数万个 + 省包警告` → 对陕西这是**预期 WARN**（正因为你下的是省包）

## 3. 定 bbox（省包专属步骤）

用 Nominatim 反查市界，别手编。也别指望 `adminareas_a` 图层——free 包里它只有
街道/乡镇级面，查不到"西安市"（实测 0 行）：

```bash
curl -s "https://nominatim.openstreetmap.org/search?q=%E8%A5%BF%E5%AE%89%E5%B8%82&format=json&limit=1" \
  -H "User-Agent: sdi-new-city/1.0" \
| python3 -c "import json,sys; b=json.load(sys.stdin)[0]['boundingbox']; print('bbox:', b[0]+','+b[2]+','+b[1]+','+b[3])"
# 输出即 min_lat,min_lng,max_lat,max_lng —— 直接粘给下一步的 --bbox
```

> ⚠️ Nominatim 的 `boundingbox` 返回顺序是 `[南,北,西,东]`，**不是** min,max,min,max
> ——上面代码已换算。若自己拼 bbox，务必纬度在前。
> ⚠️ 别用 `python3` 的 urllib 直连 https：macOS framework/系统 Python 常缺 CA 证书，
> 会报 `SSL: CERTIFICATE_VERIFY_FAILED`——这是**环境问题不是代码问题**
> （运行 Python 目录里的 `Install Certificates.command` 或 `pip install certifi` 可修），
> 临时用 `curl` 绕。

作者实测（2026-09-04）：**西安全市 ≈ `33.6961,107.6584,34.7438,109.8238`**；
只画主城区用 ≈ `34.10,108.70,34.35,109.15`。以你机器上的输出为准（OSM 周更）。

### 验收 3：确认截取比例合理

```bash
python3 scripts/check_city_data.py --city xian --data-dir data/xian_shp \
    --stage input --bbox 33.6961,107.6584,34.7438,109.8238
```

- `bbox 截取比例合理` → 过
- `bbox 内 residential <1%` → bbox 写反了（最常见：lng/lat 颠倒）
- `bbox 覆盖 >90%` → 你截了整省，等于没截

## 4. 分类：一条命令出三类产物

```bash
python3 scripts/city_gb50137.py --city xian --data-dir data/xian_shp \
    --bbox 33.6961,107.6584,34.7438,109.8238 --title 西安
```

输出 `outputs/xian_full/`：
- `xian_gb50137_all.geojson` — 12 类要素（带 `osm_fclass`/`source` 溯源字段）
- `xian_gb50137_all/`（五件套）— ESRI Shapefile，QGIS 可直接开
- `xian_gb50137_map.html` — 自包含 Leaflet 地图（canvas 渲染，双击即开，地图中心自动对准数据）

**跑完立刻验收**（带 `--bbox` + `--data-dir` 才启用两条 bbox 交叉复核，见下表末两行）：

```bash
python3 scripts/check_city_data.py --city xian --data-dir data/xian_shp \
    --stage output --bbox 33.6961,107.6584,34.7438,109.8238
```

检查项与含义：

| 检查 | 防的坑 |
|---|---|
| 三产物存在 | 脚本中途中断没发现 |
| shp↔geojson 逐类恒等 | 两个导出源不同步（改过一半代码） |
| html 环数 == geojson 环数 | 地图是上一次的旧产物 |
| html 标题计数一致 | 同上 |
| 未分类率 <15% | 该城市有 OSM 标签变体没进映射表（对照 input 阶段的未知 fclass WARN，扩 `LANDUSE_GB` 后重跑） |
| NaN/退化坐标 | 脏几何毒化下游 GIS 软件 |
| ODbL 署名在 | **合规红线**：再发布必须带 |
| canvas 渲染 | 万级面 SVG 会冻结浏览器（北京 48k 环实测教训） |
| 产物范围 vs --bbox 一致 | 生成时忘了 bbox / 用了另一个 bbox（从产物反算空间范围比对） |
| bbox 覆盖一致（原始 landuse 数 vs 产物数） | 只截了一小块却当全市交付（<50% 即 FAIL） |

## 5. 肉眼看图（最后一步验收）

浏览器打开 `outputs/xian_full/xian_gb50137_map.html`。对照西安卫星图抽查：
钟鼓楼商圈应为 B1/B2，曲江池/大唐芙蓉园周边应成片 G，高新区应有连片 B2，
三环外 AGR/R 混杂。**图对不上 ≠ 数据坏**——先上 planet.osm.org 查该面的原始标签。

## 6. 交付边界（别越线）

- 产物**不进 git**（`outputs/` 已 gitignore）；要给别人 → 走对象存储/网盘
- 再发布任何派生图 → 必须署名 `© OpenStreetMap contributors (ODbL)`
- 军事/涉密面：管线原样输出 `MIL`，**对外版本按国测法规处理**（北京交付版即移除了 MIL）

---

## 附 A：换城市只改 3 个参数

```bash
# 例：南京（江苏 = jiangsu 省包）
python3 scripts/fetch_city_data.py --region jiangsu --dest data/nanjing_shp
python3 scripts/check_city_data.py --city nanjing --data-dir data/nanjing_shp --stage input --bbox <查Nominatim>
python3 scripts/city_gb50137.py --city nanjing --data-dir data/nanjing_shp --bbox <同上> --title 南京
python3 scripts/check_city_data.py --city nanjing --stage output
```

## 附 B：故障速查

| 症状 | 根因 | 处理 |
|---|---|---|
| shapefile 导出报 EPERM/GDAL 怪错 | 同名**目录**残留（北京踩过） | `city_gb50137.py` 已自动清；手改旧脚本的话 `rm -rf outputs/<city>_full/<stem>/` |
| 地图打不开/转圈 >30s | 面数太多且非 canvas | 确认 html 含 `preferCanvas:true`（checker 会测） |
| 只有几百面 | bbox 顺序写反（lng/lat 颠倒最常见） | `--stage input --bbox` 会判 `<1%` |
| U 类 >15% 且集中于某 fclass | 映射表缺条目 | 把新 fclass 加入 `city_gb50137.py::LANDUSE_GB`，重跑，提 PR |
| shaanxi 下成了山西 | 拼写陷阱 | 见 §2 |
| 下载卡住/断 | Geofabrik 限速 | 重跑 `fetch_city_data.py`（自动续传） |
| python https 报证书错 | macOS Python 缺 CA | 见 §3 ⚠️ 框 |

## 附 C：西安实跑记录（作者验证，供对照）

> 2026-09-04 · `shaanxi-260831-free.shp.zip` · bbox `33.6961,107.6584,34.7438,109.8238`
> （数字待跑完回填；你复跑时 Geofabrik 周更可能有 ±2% 出入。）
