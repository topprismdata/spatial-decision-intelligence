# -*- coding: utf-8 -*-
"""
Step 7: 路网密度修复版生成器
- 核心修复：路线 buffer 2m → union → boundary → polygonize（32块→374块）
- 叠加建筑足迹外轮廓作为补充边界线
- 重跑 A3/B3/C3 评估 IoU
"""
import json, math, sys
import pandas as pd, numpy as np
from shapely.geometry import LineString, Polygon, Point, MultiPolygon
from shapely.ops import unary_union, polygonize, transform as shp_transform
from shapely import wkt as swkt
from shapely.validation import make_valid
from src.coordinate.transforms import gcj02_to_wgs84, wgs84_to_gcj02, transform_geometry_wkt

M2_SCALE = 111320 * 111320 * 0.767  # cos(39.9°) 面积换算
BUF_M = 2
BUF_DEG = BUF_M / 111320.0

def area_m2(geom):
    return geom.area * M2_SCALE

def load_road_lines(path):
    """加载 OSM 路网 JSON → LineString 列表"""
    data = json.load(open(path))
    lines = []
    for e in data["elements"]:
        if e["type"] != "way" or "geometry" not in e:
            continue
        coords = [(n["lon"], n["lat"]) for n in e["geometry"]]
        if len(coords) < 2:
            continue
        lines.append(LineString(coords))
    return lines

def load_building_outlines(path):
    """加载建筑足迹 JSON → 外轮廓 LineString 列表"""
    data = json.load(open(path))
    outlines = []
    for e in data["elements"]:
        if e["type"] != "way" or "geometry" not in e:
            continue
        coords = [(n["lon"], n["lat"]) for n in e["geometry"]]
        if len(coords) < 3:
            continue
        outlines.append(LineString(coords + [coords[0]]))  # 闭合
    return outlines

def build_blocks(road_lines, building_outlines=None):
    """路线 buffer → union → boundary → polygonize → 街区面列表"""
    # buffer 路线
    bufed = [l.buffer(BUF_DEG) for l in road_lines]
    merged = unary_union(bufed)
    boundary = merged.boundary
    bound_lines = list(boundary.geoms) if boundary.geom_type == "MultiLineString" else [boundary]

    # 可选：加入建筑外轮廓作为额外边界
    if building_outlines:
        all_lines = bound_lines + building_outlines
    else:
        all_lines = bound_lines

    blocks = list(polygonize(all_lines))
    # 过滤无效/过大块
    valid = []
    for b in blocks:
        b = make_valid(b) if not b.is_valid else b
        if b.is_empty or b.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        a = area_m2(b)
        if a < 10:  # 过滤噪声碎块
            continue
        if a > 1_000_000:  # 过滤超大块
            continue
        valid.append(b)
    return valid

def find_seed_block(seed_pt, blocks):
    """找种子点所在的街区块"""
    for i, b in enumerate(blocks):
        if b.contains(seed_pt):
            return i, b
    # fallback: 最近块
    dists = [(b.distance(seed_pt), i) for i, b in enumerate(blocks)]
    dists.sort()
    if dists:
        return dists[0][1], blocks[dists[0][1]]
    return -1, None

def greedy_merge(idx, blocks, target_area):
    """贪心并入邻块，直到 ≥ 0.5×目标面积"""
    cur = blocks[idx]
    used = {idx}
    for guard in range(6):
        if area_m2(cur) >= 0.5 * target_area:
            break
        # 找相邻块
        nbrs = []
        for j, b in enumerate(blocks):
            if j in used:
                continue
            if cur.distance(b) <= BUF_DEG * 2:
                nbrs.append((area_m2(b), j, b))
        if not nbrs:
            break
        # 选面积最接近的小块并
        nbrs.sort(key=lambda x: abs(x[0] - target_area * 0.3))
        _, j, b = nbrs[0]
        cur = unary_union([cur, b])
        used.add(j)
    cur = make_valid(cur) if not cur.is_valid else cur
    return cur

def area_clip(geom, target_area):
    """过大则裁剪到 1.2×目标面积"""
    a = area_m2(geom)
    if a > 1.2 * target_area:
        # 用质心圆裁剪
        c = geom.representative_point()
        r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
        circle = c.buffer(r_deg * 1.1)
        result = geom.intersection(circle)
        result = make_valid(result) if not result.is_valid else result
        return result
    return geom

def generate_A3(seed_lon, seed_lat, target_area, blocks):
    """A3: 种子街区 + 贪心并块 + 面积裁剪"""
    seed_pt = Point(seed_lon, seed_lat)
    idx, blk = find_seed_block(seed_pt, blocks)
    if blk is None:
        return None
    merged = greedy_merge(idx, blocks, target_area)
    clipped = area_clip(merged, target_area)
    return clipped

def generate_C3(seed_lon, seed_lat, target_area):
    """C3: 先验面积圆"""
    c = Point(seed_lon, seed_lat)
    r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
    return c.buffer(r_deg)

def eval_iou(pred, truth):
    if pred is None or truth is None:
        return 0.0
    pred = make_valid(pred) if not pred.is_valid else pred
    truth = make_valid(truth) if not truth.is_valid else truth
    inter = pred.intersection(truth).area
    union = pred.union(truth).area
    return inter / union if union > 0 else 0.0

# ---- 主流程 ----
WINDOWS = {
    "W1_oldcity": {
        "roads": "data/roads_windows/W1_oldcity_all.json",
        "buildings": "data/buildings/W1_oldcity_buildings.json",
    },
    "W2_chaoyang": {
        "roads": "data/roads_windows/W2_chaoyang_all.json",
        "buildings": "data/buildings/W2_chaoyang_buildings.json",
    },
}

# 加载评估数据
ev = pd.read_csv("outputs/selfdraw_eval.csv")
geoms = json.load(open("outputs/selfdraw_geoms.json"))

results = []
geoms_out = {}

for win, paths in WINDOWS.items():
    print(f"\n=== {win} ===")
    road_lines = load_road_lines(paths["roads"])
    print(f"  路线: {len(road_lines)}")

    # 尝试加载建筑足迹
    try:
        bldg_outlines = load_building_outlines(paths["buildings"])
        print(f"  建筑外轮廓: {len(bldg_outlines)}")
    except Exception as ex:
        print(f"  建筑足迹加载失败: {ex}")
        bldg_outlines = None

    # 构建 + 对比：不buffer / buffer / buffer+建筑
    blocks_nobuf = list(polygonize(road_lines))
    blocks_nobuf = [b for b in blocks_nobuf if area_m2(b) > 10 and area_m2(b) < 1_000_000]
    print(f"  无buffer polygonize: {len(blocks_nobuf)} 块")

    blocks_buf = build_blocks(road_lines, building_outlines=None)
    print(f"  buffer {BUF_M}m polygonize: {len(blocks_buf)} 块")

    if bldg_outlines:
        blocks_bldg = build_blocks(road_lines, building_outlines=bldg_outlines)
        print(f"  buffer+建筑 polygonize: {len(blocks_bldg)} 块")
    else:
        blocks_bldg = blocks_buf

    # 选最优块集
    blocks = blocks_buf if len(blocks_buf) > len(blocks_nobuf) else blocks_nobuf
    if len(blocks_bldg) > len(blocks):
        blocks = blocks_bldg
    print(f"  使用块集: {len(blocks)} 块")

    win_ev = ev[ev.window == win]
    for _, r in win_ev.iterrows():
        rid = r["source_record_id"]
        target_area = int(r["fence_area"])
        name = r["name"]

        # 真值围栏（WGS-84）
        item = geoms.get(rid, {})
        truth_wkt = item.get("fence")
        if not truth_wkt:
            continue
        truth = swkt.loads(truth_wkt)

        # 种子点（WGS-84）
        seed = item.get("seed")
        if not seed:
            continue
        s_lon, s_lat = seed[0], seed[1]

        # 生成
        a3 = generate_A3(s_lon, s_lat, target_area, blocks)
        c3 = generate_C3(s_lon, s_lat, target_area)

        # 评估
        iou_a3 = eval_iou(a3, truth)
        iou_c3 = eval_iou(c3, truth)

        results.append({
            "window": win,
            "source_record_id": rid,
            "name": name,
            "fence_area": target_area,
            "iou_A3_v2": round(iou_a3, 3),
            "iou_C3_v2": round(iou_c3, 3),
            "iou_A3_old": r.get("iou_A3_block", None),
        })

        # 存几何（WGS-84）
        geoms_out[rid] = {
            "fence": truth_wkt,
            "seed": [s_lon, s_lat],
        }
        if a3:
            geoms_out[rid]["A3_v2"] = swkt.dumps(a3)
        if c3:
            geoms_out[rid]["C3_v2"] = swkt.dumps(c3)

# 保存结果
df_out = pd.DataFrame(results)
df_out.to_csv("outputs/selfdraw_eval_v2.csv", index=False)

# 对比统计
print("\n=== 对比结果 ===")
for label, col_old, col_new in [("A3 街区法", "iou_A3_old", "iou_A3_v2"), ("C3 先验圆", None, "iou_C3_v2")]:
    if col_old:
        old = df_out[col_old].dropna()
        print(f"{label} 旧版: n={len(old)} med={old.median():.3f} >0.5={(old>0.5).mean():.1%} >0.7={(old>0.7).mean():.1%}")
    new = df_out[col_new].dropna()
    print(f"{label} 新版: n={len(new)} med={new.median():.3f} >0.5={(new>0.5).mean():.1%} >0.7={(new>0.7).mean():.1%}")

# 择优
best = df_out[["iou_A3_v2", "iou_C3_v2"]].max(axis=1)
print(f"择优(A3_v2,C3_v2): med={best.median():.3f} >0.5={(best>0.5).mean():.1%} >0.7={(best>0.7).mean():.1%}")

json.dump(geoms_out, open("outputs/selfdraw_geoms_v2.json", "w"))
print(f"\n保存: outputs/selfdraw_eval_v2.csv + outputs/selfdraw_geoms_v2.json")
