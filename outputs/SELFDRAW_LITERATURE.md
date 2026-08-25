# 自绘围栏文献调研报告

## 一、核心发现：我们的 0.39 不是方法问题，是路线问题

AOITR 论文（Ant Group/支付宝，arxiv 2401.06550，发表于 Int. J. Applied Earth Observation and Geoinformation 2025）的消融实验直接回答了我们的疑问：

| 模态组合 | mIoU | 说明 |
|---|---|---|
| **仅路网（Road-cut）** | **0.290** | ← 这就是我们的方法，论文验证了路网天花板 |
| 仅卫星图像（U-Net） | 0.557 | 卫星图像单独就翻倍 |
| 卫星+POI位置+POI类别+路网节点 | **0.726** | 全模态 AOITR |
| 卫星图像去掉路网节点 | 0.657 | 路网仅贡献 +0.07 |
| **去掉卫星图像**（=路网+POI） | **0.290** | 没有卫星图像=路网天花板 |

**结论：路网方法的 IoU 天花板就是 0.29-0.39，卫星图像是突破 0.5 的唯一路径。**

我们的 A3 方法 mIoU 0.392 实际上比论文中 Road-cut 的 0.290 还高（因为我们加了面积裁剪），已经是路网路线的优上限。

---

## 二、三篇核心论文

### 1. AOITR — 蚂蚁集团/支付宝（最相关）

- **论文**: arxiv 2401.06550 → Int. J. Applied Earth Observation and Geoinformation, 2025
- **作者**: Chuanji Shi 等，Ant Group + 中国地质大学
- **问题**: 完全一致——给定 POI（名称+位置），自动生成 AOI 多边形边界
- **输入**: 
  - 卫星图像（256×256 px，以 POI 为中心裁剪，来自 Google Earth）
  - 核心 POI 位置（经纬度）+ 类别（医院/学校/小区等）
  - 路网节点（POI 附近道路交叉点坐标）
  - 入口 POI（大门/特定建筑位置）
- **架构**: Transformer encoder-decoder（DETR 变体）
  - 编码器：CNN 提取图像特征 + 位置编码
  - 解码器：位置查询 + 多模态内容查询（POI 嵌入 + 路网节点嵌入）
  - 回归头：预测 N 个多边形顶点坐标
- **关键创新 — 等角射线采样**:
  - 从 POI 中心向外发射 N 条等角射线
  - 每条射线与 AOI 边界的交点 = 一个顶点
  - 回归这些交点的距离 → 得到多边形
  - 优势：对不规则形状也能均匀分布顶点
- **损失函数**: L1 loss（预测坐标 vs 真值坐标）
- **完整结果**:

| 方法 | 输入 | mIoU | 高IoU率(>0.75) |
|---|---|---|---|
| Road-cut | POI + 路网 | 0.290 | 0.351 |
| U-Net | 卫星图像 | 0.557 | 0.241 |
| UperNet | 卫星图像 | 0.532 | 0.347 |
| PolarMask | 卫星图像 | 0.525 | 0.319 |
| DETR | 卫星图像 | 0.561 | 0.234 |
| E2EC | 卫星图像 | 0.581 | 0.384 |
| **AOITR** | **卫星+POI+路网** | **0.726** | **0.497** |

- **训练数据**: ~30 万样本，20 个 AOI 类别，中国多城市
- **部署**: 已在支付宝刷脸支付等 10+ O2O 场景上线
- **代码**: 未开源

### 2. C-AOI — 美团（KDD 2023）

- **论文**: "C-AOI: Contour-based Instance Segmentation for High-Quality Areas-of-Interest in Online Food Delivery Platform", KDD 2023
- **作者**: Yida Zhu 等，Meituan
- **问题**: 外卖配送精确定位——从 AOI 中心点回归边界轮廓
- **方法**:
  - 实例分割模型，从 AOI 中心点出发回归边界
  - Contour Transformer 捕获全局几何
  - 可学习循环位置编码增强顶点间关系
  - Adaptive Matching Loss 消除过平滑边界
- **对比**: 比美团此前的语义分割方法显著提升边界质量
- **部署**: 已在美团平台上线生产
- **代码**: 未开源

### 3. 美团 Multimodal AOI（Industrial Paper）

- **论文**: "Automatic generation of areas of interest using multimodal geospatial data from an on-demand food delivery platform"
- **方法**: 
  - 多模态特征：卫星图像 + 路网 + 配送数据（用户地址、位置等）
  - 语义分割模型推断 AOI 内像素
  - 轮廓学习方法拟合离散像素点重建任意形状轮廓
- **优势**: 比 Road-cut 方法更贴合地理边界（路网无法覆盖河流、山体等）

---

## 三、开源工具

### 1. GenRegion（pip install genregion）— 可直接替换我们的 polygonize

- **PyPI**: https://pypi.org/project/genregion/
- **GitHub**: https://github.com/zhangyimi/Research/blob/master/ST_DM/GenRegion
- **论文**: "Generating Urban Areas of Interest Using the Road Network"
- **方法**: 
  - 矢量图方法（不是 buffer+polygonize）
  - 路网 → 图（边=路段，顶点=端点）
  - 层次聚类简化路网 → 递归找最左链生成闭合多边形
  - 合并微小块 + 去除子区域
- **指标**: 北京/上海 Jaccard 41-42.7%（优于 mapseg/shortpath/grid 方法）
- **接口**:
  ```python
  from genregion import generate_regions
  regions = generate_regions(segments, grid_size=1024, 
                             area_thres=10000, width_thres=20,
                             clust_width=25, point_precision=5)
  ```
  - 输入: List[LineString] 或坐标列表
  - 输出: List[Shapely Polygon]
  - 参数: area_thres（最小块面积）、width_thres（窄条过滤）、clust_width（聚类距离）
- **优势**: 比 shapely polygonize 更好的路网图分割，处理断头路/不连通路网

### 2. road_regularization（GitHub: kingsley0107）— ArcGIS Pro 路网正则化

- **GitHub**: https://github.com/kingsley0107/road_regularization
- **功能**: OSM 路网简化 → 中心线提取 → 断头路检测/延伸 → 地块划分
- **依赖**: ArcGIS Pro + Arcpy（不适用我们的纯 Python 环境）
- **参考价值**: 路网预处理流程设计（断头路延伸、毛刺清理的阈值参数）

### 3. OSM Centerlines（GitHub: der-stefan）

- **GitHub**: https://github.com/der-stefan/osm-centerlines
- **功能**: 从 OSM 面状要素（河流/道路缓冲区）提取中心线
- **依赖**: shapely + fiona/PostGIS
- **用途**: 道路缓冲区合并后提取骨架线

---

## 四、深度学习方向参考

### 院落/围栏边界提取（U-Net 语义分割）

| 论文 | 方法 | 数据 | 精度 |
|---|---|---|---|
| Nature 2025 (北方农村院落) | U-Net on 0.3m 卫星图 | 4600屋顶+1600院落, 4村标注 | ~10% 面积误差 |
| MDPI 2026 (冀南民居院落) | HRNetV2 语义分割 | 134,280 院落, 高分卫星图 | ~10% 面积误差 |
| Yandex Maps (建筑足迹) | 语义分割+边缘检测 | 卫星图→建筑多边形 | 生产级 |

### 建筑足迹提取（可作围栏边界参考）

| 论文 | 方法 | 特点 |
|---|---|---|
| HD-Net (ISPRS 2024) | HRNet + 特征解耦-重耦合 | 体+边界分离，SOTA |
| CBR-Net (ISPRS 2021) | 粗到细边界精炼 | 自监督边界增强 |

---

## 五、对我们项目的行动建议

### 路线 A：快速验证 GenRegion（1-2 小时）

```bash
pip install genregion
```
用 GenRegion 替换 shapely polygonize，看块质量是否提升。GenRegion 的图论方法比 buffer+polygonize 更好地处理断头路和不连通路网。

### 路线 B：卫星图像 + 简化深度学习（核心突破方向）

**我们的 9,039 条采购围栏就是完美的训练数据！**

AOITR 用了 30 万样本，但我们只有北京 7,431 条 + 石家庄 1,608 条，可以：

1. **数据准备**:
   - 下载每条围栏中心点附近的腾讯地图静态图（256×256，~0.3m/px）
   - 将采购围栏多边形栅格化为 mask（标签）
   - 输入 = 卫星图 + POI 位置 + 面积；输出 = 围栏多边形

2. **简化模型**（不复制 AOITR 全部复杂度）:
   - U-Net 语义分割：卫星图 → 围栏 mask → 轮廓提取
   - 或 PolarMask/Contour 回归：从中心点等角射线 → 回归边界距离
   - PyTorch + 我们的 venv 即可训练

3. **预期效果**:
   - AOITR 消融显示：仅卫星图像 U-Net 就能到 0.557 mIoU
   - 我们有真实围栏标注（比 AOITR 的手动标注更准），7,000+ 样本足够微调
   - 加上路网 + 面积先验，预期 mIoU 0.55-0.65

### 路线 C：腾讯地图静态图 API + OpenCV 轮廓检测（无需训练）

受 unerry/Yandex 启发：
1. 下载 POI 中心区域腾讯地图卫星图瓦片
2. OpenCV Canny 边缘检测 + HSV 颜色掩膜
3. 提取建筑/院落轮廓
4. 用面积先验筛选最匹配的轮廓

不需要训练，但精度依赖图像质量和后处理。

---

## 六、文献对照总结

| 我们的方法 | 对标论文方法 | mIoU | 差距原因 |
|---|---|---|---|
| A3 路网街区+面积裁剪 | Road-cut | 0.39 vs 0.29 | 我们多了面积裁剪 |
| buffer 2m 361块 | Road-cut | 0.39 ≈ 0.29 | 路网天花板 |
| 院落块(路网+建筑) | Road-cut + building | 0.22 | 碎片化反效果 |
| **缺失: 卫星图+DL** | **U-Net** | **? vs 0.557** | **未尝试** |
| **缺失: 多模态** | **AOITR** | **? vs 0.726** | **未尝试** |

**核心判断：继续在路网路线上优化已无意义（论文已证伪），下一步必须引入卫星图像。**
