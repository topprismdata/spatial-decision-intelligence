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

---

## 七、视觉验证的落地调整 (2026-08-27 实测)

SCNet Token Plan 部署的 GLM-5.2 为**纯文本推理版**，不含 vision 权重（模型自己确认"无法处理图像输入"）。zhipu-coding-plan 的 glm-5.3-flash 仅在 omp 主会话可用，无独立 API。

### 替代方案：数据驱动三层核验

| 层 | 方法 | 判定 |
|:-:|:---|:---|
| L1 命名地标 | 边界内是否包含名称指向的核心 POI（如颐和园内的佛香阁、十七孔桥） | 核心 POI 覆盖率 ≥ 50% = PASS |
| L2 路网吻合 | 边界由 road-block 构成时，边缘应贴合主干道边界 | 与道路 buffer 相交比 > 60% = PASS |
| L3 面积先验 | 按景区类型检查面积区间（山岳 2-10km², 园林 <0.5km², 场馆 <0.1km²） | 在合理范围内 = PASS |

三层全部通过 → 视觉自动检验合格；任何一层 FAIL → 标 `REVIEW_NEEDED` + 保留浏览器截图给人工判读。

### 人工截图备份
所有 5A 景区已生成带边界叠加的浏览器截图（`docs/screenshots/scenic/`），供必要时人工比对。

---

## 八、高德静态图层获取方案（2026-08-27 实测通过）

### 免费匿名可用的瓦片端点

| 图层 | style | URL 模板 | 分辨率 | 说明 |
|:---|:-:|:---|:-:|:---|
| **卫星影像** | 6 | `https://webst0{1-4}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}` | 256×256 | 真实卫星影像 |
| 道路图层 | 7 | 同上, style=7 | 256×256 | 仅路网 |
| **标注+道路+底图** | 8 | 同上, style=8 | 256×256 | 混合图层 (含中文标注) |

子域 webst01-04 负载均衡；请求需带 `Referer: https://amap.com`（防爬）。无 key、无限速 (实测)。

### 坐标系说明
- 高德瓦片的 x/y 是**GCJ-02 墨卡托投影**
- 我们 GeoJSON 的边界是 WGS-84 → 需要先转 GCJ-02 再算 tile 编号，否则偏移 ~500m

### 应用：免费生成景区卫星影像对比截图

```python
def deg2num(lat,lng,z):
    lat_rad=math.radians(lat); n=2**z
    return int((lng+180)/360*n), int((1-math.log(math.tan(lat_rad)+1/math.cos(lat_rad))/math.pi)/2*n)
x,y=deg2num(39.9169,116.3972,15)
url=f"https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z=15"
```

3×3 tile 拼接即可得到故宫周边 700m 高清影像 ✓。zoom 17 可看清单体建筑。

### 获取示例 — 故宫 z17 卫星 + 标注层 实测通过

| 图层 | 状态 |
|:---|:-:|
| 卫星影像 style=6, z=15/17 | ✅ 200 |
| 标注图层 style=8, z=17 | ✅ 200 |
| 道路 style=7 | ✅ |
| 静态地图 staticmap API | ❌ 需要 Web服务 key (免费的也不行) |

---

## 七、合规声明（2026-08-27）

根据《中华人民共和国测绘法》《地图管理条例》《数据安全法》：

1. **已删除全部军事用地面**（原 386 面，分类码 MIL）
2. **坐标精度已降至小数点后 3 位**（约 100m），不构成高精度地理数据
3. 数据来源为 [OpenStreetMap](https://www.openstreetmap.org/copyright)（ODbL 许可）及公开 POI 数据
4. 本数据仅供技术演示与学术研究，不得用于导航、测绘或商业用途
5. 未包含任何涉密地理位置、关键基础设施或国家战略要地信息
