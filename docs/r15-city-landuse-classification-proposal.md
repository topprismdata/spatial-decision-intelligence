# R15 提案：城市建设用地分类图层（对标市场在售 GIS 数据产品）

状态：**草稿**
日期：2026-08-27
依据：用户提供的两张闲鱼在售商品截图（"2025 城市建设用地类型 超详细 shp 矢量 — 2025 版"，含 FID/Shape/Class/ClassCn 属性表，按 8 大类配色渲染）；对全北京 Geofabrik 图层的实测验证。

---

## 一、竞品分析（从截图逆向）

### 商品内容
| 项 | 内容 |
|:---|:---|
| 形态 | 全国/城市级 shp 矢量 + 预渲染地图 |
| 分类体系 | 9 类：居住 / 商业服务 / 商务办公 / 工业用地 / 交通枢纽 / 体育与文化 / 公园与绿地 / 医疗卫生 / 机场设施 (+ 教育科研) |
| 属性表字段 | `FID, Shape, Class, ClassCn`（英文类名 + 中文类名） |
| 定价线索 | 闲鱼店铺"专业团队 GIS 数据"，是典型的**开放数据重包装倒卖** |

### 判定
该商品的 9 分类体系与《城市用地分类与规划建设用地标准》(GB50137) 的 R/B/M/S/A/G 大类对应。其底层数据几乎必然来自 OSM + 政府公开规划图的再加工——正是我们管线可复现的东西。

## 二、我们已有数据的覆盖验证（2026-08-27 实测）

Geofabrik 北京全量数据可直接推导出的分类：

| 商品分类 | 我们的来源 | 北京实测规模 |
|:---|:---|---:|
| **R 居住** | `landuse=residential` | 11,227 面 |
| **B 商业服务** | `landuse=retail` | 635 面 |
| **B 商务办公** | `landuse=commercial` + `building=commercial` | 1,868 面 |
| **M 工业** | `landuse=industrial` | 2,824 面 |
| **G 公园绿地** | `park/grass/meadow/forest/orchard` | ~14,800 面 |
| **A3 教育科研** | POI: school 1,929 + university 174 + college 162 + kindergarten 646 | ~2,900 点/面 |
| **A5 医疗卫生** | POI: hospital 379 + clinic 42 | ~420 点/面 |
| **A4 体育文化** | POI: stadium 218 + museum 188 + sports_centre 171 + library 90 + theatre 70 | ~740 点/面 |
| **S 交通枢纽** | `gis_osm_transport` + `gis_osm_traffic` 图层 | 待量化 |
| **机场设施** | `aeroway=*` (需补查 transport 图层) | 待量化 |

**结论：商品卖的每一类，我们的开放数据都能生产，且质量可控、来源合法。**

## 三、借力的两个真正亮点

1. **统一 ClassCn 中文属性规范 + 规划标准配色** —— 商品的价值不在数据（大家都有），而在"拿起来就能用"。我们应输出同样的四字段 schema（`FID, Shape, Class, ClassCn`）+ GB50137 标准色卡（RGB(225,150,25) 黄=R居住、RGB(200,60,60) 红=B商业、RGB(140,100,170) 紫=M工业、RGB(120,180,80) 绿=G绿地……以截图色卡采样为准）。

2. **面化(A3/A4/A5)**：教育/医疗/文体在 OSM 里大量只有点。正好复用本项目的 BuildingCluster + 围栏推断管线把点升级为面——这是纯倒卖商做不到的增值，也是与我们 R14 主线的天然衔接。

## 四、实施切片

| # | 任务 | 输入 | 输出 |
|:-:|:---|:---|:---|
| T1 | 分类器：OSM fclass/amenity → 9 大类映射表（Class/ClassCn） | landuse/pois/transport shapefile | `src/classification/gb50137.py` |
| T2 | 点转面：A3/A4/A5 POI 用 R14-P1 concave hull + 名称聚类围合成校区/院区 | pois_a + buildings_a | 面图层 |
| T3 | 属性表导出：`FID, Shape, Class, ClassCn` 四字段 shp/GeoJSON | T1+T2 结果 | `outputs/city_landuse_<city>.gpkg` |
| T4 | 渲染地图：GB50137 配色 Leaflet 页（同 huilongguan 流程） | T3 | `outputs/<city>_landuse_map.html` |
| T5 | 北京试点 → 多城市扩展（MetricCRSStrategy 已就绪） | — | 产品化交付 |

## 五、与主线关系

- R14 主线解决「单一目标实体的边界可信度」；R15 解决「全城分类覆盖的商品化输出」。两者共用 concave hull、gazetteer、Validation Gate。
- 该方向同时回应了"扩展到学校/医院/写字楼"的实体类型泛化讨论——9 大类就是 EntityProfile 配置化的第一批实例。

## 附：截图颜色采样（供 T4 配色参考）

图1 属性区主色统计：蓝 RGB(50,100,175)、橙黄 RGB(225,150,25)、绿 RGB(50,150,0)、棕橙 RGB(175,125,50) 等，符合 GB50137 标准用色印象。
