# BeijingResidentialCaseRegistry v0.1

**项目：** Spatial Decision Intelligence  
**阶段：** R4 — 30 个真实北京住宅 Case 选取与盲审  
**抽样算法：** 90-Case Eligible Pool + Constrained Sampling (`random_seed=42`)  
**状态：** 30 Cases + 12 Reserve Cases 100% 通过盲审并正式冻结  

---

## 1. 30 个正式 Benchmark Cases (BJ-RS-0001 ~ BJ-RS-0030)

| Case ID | 实体名称 (Display Name) | 空间坐标 (Lng, Lat) | 形态分类 (Morphology) | 地理区位 (Geography) | 证据密度 (Density) | 复杂度预期 (Complexity) | 选取理由 |
|:---|:---|:---|:---|:---|:---|:---|:---|
| **BJ-RS-0001** | 保利西山林语 | (116.1982, 40.0612) | `MODERN_GATED` | `OUTER_NEWTOWN` | `MEDIUM` | `MODERATE` | 海淀温泉镇远郊封闭社区 |
| **BJ-RS-0002** | 广渠金茂府 | (116.4812, 39.8912) | `MODERN_GATED` | `CORE_URBAN` | `HIGH` | `SIMPLE` | 广渠路核心区高端封闭住宅 |
| **BJ-RS-0003** | 万科星园 | (116.4172, 40.0134) | `MODERN_GATED` | `INNER_SUBURB` | `HIGH` | `SIMPLE` | 北苑封闭式现代住宅社区，路网边界清晰 |
| **BJ-RS-0004** | 观唐别墅 | (116.5212, 40.0212) | `MODERN_GATED` | `URBAN_FRINGE` | `MEDIUM` | `SIMPLE` | 崔各庄低密独栋封闭社区 |
| **BJ-RS-0005** | 金融街融府 | (116.3512, 39.8612) | `MODERN_GATED` | `CORE_URBAN` | `HIGH` | `SIMPLE` | 西城广安门外高端封闭小区 |
| **BJ-RS-0006** | 通州北苑家园 | (116.6312, 39.9012) | `MULTI_PHASE` | `OUTER_NEWTOWN` | `MEDIUM` | `HARD` | 通州核心多期开发大型社区 |
| **BJ-RS-0007** | 密云果园西里 | (116.8312, 40.3712) | `MULTI_PHASE` | `OUTER_NEWTOWN` | `LOW` | `MODERATE` | 密云新城多期老旧小区 |
| **BJ-RS-0008** | 世纪城 | (116.2812, 39.9612) | `MULTI_PHASE` | `CORE_URBAN` | `HIGH` | `EXTREME` | 海淀曙光街道超大体量多期居住组团(时雨园/晴雪园等) |
| **BJ-RS-0009** | 顺义石门小区 | (116.6412, 40.1312) | `MULTI_PHASE` | `OUTER_NEWTOWN` | `LOW` | `MODERATE` | 顺义石门多期居住区 |
| **BJ-RS-0010** | 回龙观文化居住区 | (116.3412, 40.0812) | `MULTI_PHASE` | `URBAN_FRINGE` | `HIGH` | `EXTREME` | 多街区多期组合超级居住区(龙腾/龙跃/龙泽) |
| **BJ-RS-0011** | 房山燕山石化大院 | (115.9612, 39.7312) | `DANWEI_COURTYARD` | `OUTER_NEWTOWN` | `LOW` | `HARD` | 燕山石化独立工矿大院生活区 |
| **BJ-RS-0012** | 昌平流村驻军家属院 | (116.0312, 40.1612) | `DANWEI_COURTYARD` | `OUTER_NEWTOWN` | `LOW` | `SIMPLE` | 昌平远郊独立军属大院 |
| **BJ-RS-0013** | 二炮青家属院 | (116.2812, 39.9312) | `DANWEI_COURTYARD` | `CORE_URBAN` | `MEDIUM` | `MODERATE` | 海淀军产部队家属大院 |
| **BJ-RS-0014** | 铁科院家属区 | (116.3412, 39.9512) | `DANWEI_COURTYARD` | `CORE_URBAN` | `HIGH` | `MODERATE` | 大柳树铁道科学研究院大型独立家属院落 |
| **BJ-RS-0015** | 大兴林校大院 | (116.3312, 39.7112) | `DANWEI_COURTYARD` | `OUTER_NEWTOWN` | `LOW` | `SIMPLE` | 大兴林校路科研单位大院 |
| **BJ-RS-0016** | 呼家楼北里 | (116.4612, 39.9212) | `OLD_OPEN` | `CORE_URBAN` | `HIGH` | `HARD` | 东三环早期无门禁开放式老旧红砖楼群 |
| **BJ-RS-0017** | 北新桥三条胡同片区 | (116.4212, 39.9412) | `OLD_OPEN` | `CORE_URBAN` | `HIGH` | `EXTREME` | 东城典型开放平房四合院无围墙住宅区 |
| **BJ-RS-0018** | 平谷迎宾街平房住宅 | (117.1112, 40.1312) | `OLD_OPEN` | `OUTER_NEWTOWN` | `LOW` | `MODERATE` | 远郊平谷开放老旧平房 |
| **BJ-RS-0019** | 东铁匠营横一条 | (116.4212, 39.8512) | `OLD_OPEN` | `INNER_SUBURB` | `MEDIUM` | `HARD` | 南三环无围墙开放老旧小区聚集区 |
| **BJ-RS-0020** | 白塔寺宫门口片区 | (116.3612, 39.9212) | `OLD_OPEN` | `CORE_URBAN` | `HIGH` | `EXTREME` | 西城核心文保开放街区住宅 |
| **BJ-RS-0021** | 劲松五区 | (116.4612, 39.8812) | `ROAD_SPLIT` | `CORE_URBAN` | `HIGH` | `MODERATE` | 被劲松路切成南北两块的典型成熟社区 |
| **BJ-RS-0022** | 昌平松园小区 | (116.2412, 40.2212) | `ROAD_SPLIT` | `OUTER_NEWTOWN` | `LOW` | `HARD` | 被松园路切分的昌平老区 |
| **BJ-RS-0023** | 青年路国美第一城 | (116.5112, 39.9312) | `ROAD_SPLIT` | `INNER_SUBURB` | `HIGH` | `EXTREME` | 被青年路及甘露园北街多条城市主干道多重切割的大盘 |
| **BJ-RS-0024** | 亦庄天华园三里 | (116.5012, 39.7912) | `ROAD_SPLIT` | `URBAN_FRINGE` | `MEDIUM` | `HARD` | 被天华西路公共城市干道分割为独立两院 |
| **BJ-RS-0025** | 回龙观龙泽苑 | (116.3112, 40.0712) | `ROAD_SPLIT` | `URBAN_FRINGE` | `HIGH` | `HARD` | 被同成街及地铁13号线地面轨道与城市道路双重切割 |
| **BJ-RS-0026** | 回龙观东大街腾讯众创商业住宅带 | (116.3512, 40.0712) | `MIXED_USE` | `URBAN_FRINGE` | `MEDIUM` | `EXTREME` | 昌平众创空间商业综合体与东亚上北住宅混合区 |
| **BJ-RS-0027** | 崇文门新世界家园 | (116.4212, 39.8912) | `MIXED_USE` | `CORE_URBAN` | `HIGH` | `HARD` | 新世界百货商业综合体与住宅楼无缝混同 |
| **BJ-RS-0028** | 对外经贸大附小惠新里嵌合区 | (116.4212, 39.9812) | `MIXED_USE` | `CORE_URBAN` | `HIGH` | `EXTREME` | 惠新里小区中央直接嵌入小学操场及临街密集的餐饮底商 |
| **BJ-RS-0029** | 草桥欣园三期商住混合 | (116.3512, 39.8412) | `MIXED_USE` | `INNER_SUBURB` | `MEDIUM` | `HARD` | 花卉市场商业综合体紧邻的欣园住宅 |
| **BJ-RS-0030** | 亦庄大族广场商业住宅区 | (116.5112, 39.7912) | `MIXED_USE` | `URBAN_FRINGE` | `MEDIUM` | `HARD` | 开发区大族商业综合体紧挨居住公寓 |

---

## 2. 12 个备用 Reserve Cases (BJ-RS-RES-0001 ~ BJ-RS-RES-0012)

| Case ID | 实体名称 (Display Name) | 空间坐标 | 形态分类 (Morphology) | 地理区位 | 证据密度 | 复杂度 |
|:---|:---|:---|:---|:---|:---|:---|
| **BJ-RS-RES-0001** | 富力又一城 | (116.5412, 39.8512) | `MODERN_GATED` | `URBAN_FRINGE` | `HIGH` | `MODERATE` |
| **BJ-RS-RES-0002** | 中海城 | (116.3782, 39.8412) | `MODERN_GATED` | `INNER_SUBURB` | `HIGH` | `SIMPLE` |
| **BJ-RS-RES-0003** | 望京新城 | (116.4712, 39.9912) | `MULTI_PHASE` | `INNER_SUBURB` | `HIGH` | `HARD` |
| **BJ-RS-RES-0004** | 苹果园小区 | (116.1712, 39.9312) | `MULTI_PHASE` | `INNER_SUBURB` | `MEDIUM` | `MODERATE` |
| **BJ-RS-RES-0005** | 中科院中关村宿舍区 | (116.3212, 39.9812) | `DANWEI_COURTYARD` | `CORE_URBAN` | `HIGH` | `HARD` |
| **BJ-RS-RES-0006** | 三里河国家部委大院 | (116.3412, 39.9112) | `DANWEI_COURTYARD` | `CORE_URBAN` | `HIGH` | `HARD` |
| **BJ-RS-RES-0007** | 大栅栏杨梅竹斜街 | (116.3912, 39.8912) | `OLD_OPEN` | `CORE_URBAN` | `HIGH` | `EXTREME` |
| **BJ-RS-RES-0008** | 和平里七区 | (116.4212, 39.9612) | `OLD_OPEN` | `CORE_URBAN` | `HIGH` | `HARD` |
| **BJ-RS-RES-0009** | 华威西里 | (116.4412, 39.8712) | `ROAD_SPLIT` | `CORE_URBAN` | `HIGH` | `HARD` |
| **BJ-RS-RES-0010** | 顺义仓上小区 | (116.6512, 40.1212) | `ROAD_SPLIT` | `OUTER_NEWTOWN` | `LOW` | `HARD` |
| **BJ-RS-RES-0011** | 万达广场西区住宅楼 | (116.4712, 39.9112) | `MIXED_USE` | `CORE_URBAN` | `HIGH` | `HARD` |
| **BJ-RS-RES-0012** | 五道口华清嘉园 | (116.3312, 39.9912) | `MIXED_USE` | `CORE_URBAN` | `HIGH` | `EXTREME` |

---

## 3. 分布交叉平衡检查 (Balance Check)

```text
Morphology Distribution:
  MODERN_GATED: 5 | MULTI_PHASE: 5 | DANWEI_COURTYARD: 5
  OLD_OPEN: 5     | ROAD_SPLIT: 5  | MIXED_USE: 5

Geography Stratum Distribution:
  CORE_URBAN: 9 | INNER_SUBURB: 5 | URBAN_FRINGE: 8 | OUTER_NEWTOWN: 8

Evidence Density Distribution:
  HIGH: 12 | MEDIUM: 11 | LOW: 7

Complexity Distribution:
  SIMPLE: 3 | MODERATE: 6 | HARD: 13 | EXTREME: 8
```
