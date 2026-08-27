# R16 设计修正 v2：从"圆形兜底"升级为 POI-KDE + OSM 路网切块法

状态：**设计修订**（2026-08-27，用户质询"方法太傻"后按文献重构）
前版缺陷：路径 D 用固定半径画圆 — 34 个 4A/5A 景区是粗糙圆，视觉不可接受。

---

## 一、文献结论（本次搜索核实）

城市功能区边界刻画的标准范式（ISPRS/MDPI 2024-2026 多篇）：

1. **POI KDE 活动强度面** — 把离散 POI 转成连续活动强度面（核密度估计）；
2. **OSM 路网作"骨架"切块** — 用道路网络把空间剖分成地块单元（block polygonize），单元内 POI 构成分类投票；
3. **Jaccard/STEP 相似度验证** — 与遥感土地覆盖对比验证。

> 这正是我们住宅管线 RoadBlock 的同源思想 — 直接迁移。

## 二、新版 CONSTRUCTED 路径（替换固定圆）

```text
对 NOT_FOUND/无面的景区 (name, amap_point):
1. 取景区点周围 R=1.5km 缓冲窗
2. 收集窗内 OSM POI 点 (含 bench/toilet/camera 等园区设施特征!)
   实测香山公园: 175 个设施 POI, 其中 bench 67/shelter 22 —
   这些是"园区内部设施", 天然只在景区围墙内出现 → 强信号!
3. KDE/凸包收缩: 对 POI 点做 concave hull(α 自适应), 得到活动范围面
4. 路网裁剪: 用 road block 分割线裁掉跨路外溢部分
5. 面积守门: 对比同行景区面积先验(名称类型),
   山岳类 ~2-10km² / 园林类 <0.5km² / 场馆类 <0.1km²
   超限 → 回退 shrink 包络
```

### 关键洞察（为什么这比圆聪明）
园区内部设施 POI（长椅、垃圾桶、监控、避难亭、售票处、观景台）**只存在于围墙内**——
它们的分布就是园区的真实形状。这是从数据里读边界，而不是拍脑袋画圆。

## 三、实施

| 步骤 | 内容 | 验证 |
|:-:|:---|:---|
| 1 | `scenic_poi_hull.py`: 收集景区周边 800m POI 设施点 | 香山 175 点 |
| 2 | 过滤设施白名单(bench/shelter/toilet/waste/picnic/gate/viewpoint/ticket) | 剔除路过型POI |
| 3 | concave hull (R14-P1 复用) + road-clip | 边界贴合围墙 |
| 4 | 视觉质检环：browser 截图 + GLM-5.2 图像判定 | 每个都过目 |
| 5 | 替换 34 个 CONSTRUCTED 圆, 更新地图 | 视觉抽检 ≥90% |

## 四、验收更新

- ~~CONSTRUCTED 圆形~~ → **POI-HULL 面**
- 4A/5A 全部有 POI-HULL 或更好来源
- 视觉质检通过率 ≥90%（截图留档 docs/screenshots/scenic/）

## 参考文献要点

- ISPRS XLVIII-4-W16-2025:45 — 城市功能区 POI+影像融合
- MDPI RS 14(16):3996 — nDSM+NIR+POI 语义, 88% 准确率
- M2LHI (RS 15:4920) — 多尺度景观异质性合并算法, 景观/乡村场景
