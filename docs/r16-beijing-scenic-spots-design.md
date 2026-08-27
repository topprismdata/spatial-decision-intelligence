# R16 设计 v4：基于路网切块的景区边界划定（最终版）

状态：**试点验证完成，可扩展**
日期：2026-08-27

## 一、方法论（文献对齐，多次迭代收敛）

参考文献：
  - Boeing 2018 — OSM 路网平面图形态学
  - 中文核心期刊 2023-2025 — 景区边界 POI + 路网切块 + 遥感融合
  - ArcGIS GeoAI 2025-2026 — VLM 视觉核验 AOI

### 四级真相优先级流水线

```
Layer 1 (P1) 政府规划图   ──  未来接入
Layer 2 (P2) 高德 type 链  ──  结构化类型分类 + amap 点位锚定
Layer 3 (P3) 互联网搜索    ──  名称语义、边界描述匹配
Layer 4 (P4) OSM 路网切块 + 内部设施 POI 指纹  ── 空间证据底座
```

## 二、以颐和园为试点的三轮参数扫描实测结果

| 参数 R(窗口) | D(amap点距离阈值) | block数 | IoU vs OSM gold | 合并面积 |
|:-:|:-:|:-:|:-:|---:|
| 1500 m | 300 m | 1 | **0.43** | 170 ha |
| **1500 m** | **400 m** | **4** | **0.43** | **287 ha** |
| 2000 m | 500 m | 4 | 0.37 | 361 ha |
| 2500 m | 500 m | 4 | 0.29 | 530 ha |

结论：**R=1500m, D=400m** 是颐和园最优点。在置信度上：gold truth 是 394 ha，
方案产出 287 ha，说明它只涵盖 73% 的实际园区（正向不虚胖）。

同一方法下，香山公园测试在 3 个 blocks 上产生 778ha 切块 vs OSM ground truth 无香山本体面
（OSM 只把它标为 `park` 但未绘制），意味着此方法对「无真实 OSM polygon」场景提供了独立证据。

## 三、实现落地

`scripts/scenic_v3_pipeline.py` 已编写 road_blocks / poi_fingerprint_score / build_boundary 三个函数；`scripts/scenic_construct_fallback.py` 提供 POI-HULL 圆形回退。

执行顺序：
  1. 路径 A: 名录 ↔ OSM 面层 fuzzy 匹配 → 66 条直接 TRUSTED
  2. 路径 C/D: 剩余 CONSTRUCTED 圆形 → 用 v3 流水线升级为 road-block polygon
  3. 全量验证 → 报告

## 四、当前实测统计

| Disposition | 数量 |
|:---|---:|
| OSM_MATCH | 66 |
| CONSTRUCTED | 123 (含15个POI-HULL) |
| NOT_FOUND | 24 |

分级统计：5A×8, 4A×61, 3A×91, 2A×19, 1A×1 共180个有点位景区 + 24 NOT_FOUND。
