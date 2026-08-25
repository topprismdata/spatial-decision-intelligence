# -*- coding: utf-8 -*-
"""
Step 7b: 路网密度修复版 v2
- buffer 2m polygonize → 361块(W1) / 595块(W2)
- 新策略：种子点目标面积圆内所有街区块 union → 天然贴路网边界
- 对比旧版 A3 (IoU 0.392)
"""
import json, math
import pandas as pd, numpy as np
from shapely.geometry import LineString, Polygon, Point, MultiPolygon
from shapely.ops import unary_union, polygonize
from shapely import wkt as swkt
from shapely.validation import make_valid
from shapely.strtree import STRtree
from src.coordinate.transforms import gcj02_to_wgs84

M2_SCALE = 111320 * 111320 * 0.767
BUF_DEG = 2 / 111320.0

def area_m2(geom):
    return geom.area * M2_SCALE

def load_road_lines(path):
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

def build_blocks(road_lines):
    """buffer → union → boundary → polygonize → 街区面"""
    bufed = [l.buffer(BUF_DEG) for l in road_lines]
    merged = unary_union(bufed)
    boundary = merged.boundary
    bound_lines = list(boundary.geoms) if boundary.geom_type == "MultiLineString" else [boundary]
    raw = list(polygonize(bound_lines))
    # 过滤
    valid = []
    for b in raw:
        if not b.is_valid:
            b = make_valid(b)
        if b.is_empty or b.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        a = area_m2(b)
        if a < 10 or a > 1_000_000:
            continue
        valid.append(b)
    return valid

def generate_A3_circle(seed_lon, seed_lat, target_area, blocks, strtree):
    """
    新策略：目标面积圆内所有块 union → 贴路网边界
    1. 算目标面积对应的半径
    2. 种子点 buffer → 查询 STRtree 命中的块
    3. union 所有命中块 → 天然路网边界
    4. 如过大则裁剪，如过小则扩圈
    """
    r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
    seed = Point(seed_lon, seed_lat)

    # 逐步扩大搜索半径，直到覆盖目标面积
    for scale in [1.0, 1.3, 1.6, 2.0, 2.5]:
        search_circle = seed.buffer(r_deg * scale)
        hits = strtree.query(search_circle)
        if len(hits) == 0:
            continue
        hit_blocks = [blocks[int(i)] for i in hits]
        unioned = unary_union(hit_blocks)
        a = area_m2(unioned)
        if a >= 0.3 * target_area:
            break
    else:
        return None

    # 裁剪到目标面积上界
    if area_m2(unioned) > 1.3 * target_area:
        # 用目标面积圆裁剪
        clip_circle = seed.buffer(r_deg * 1.1)
        unioned = unioned.intersection(clip_circle)
        if not unioned.is_valid:
            unioned = make_valid(unioned)

    return unioned

def generate_C3(seed_lon, seed_lat, target_area):
    r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
    return Point(seed_lon, seed_lat).buffer(r_deg)

def eval_iou(pred, truth):
    if pred is None or truth is None:
        return 0.0
    pred = make_valid(pred) if not pred.is_valid else pred
    truth = make_valid(truth) if not truth.is_valid else truth
    try:
        inter = pred.intersection(truth).area
        union = pred.union(truth).area
        return inter / union if union > 0 else 0.0
    except Exception:
        return 0.0

# ---- 主流程 ----
WINDOWS = {
    "W1_oldcity": "data/roads_windows/W1_oldcity_all.json",
    "W2_chaoyang": "data/roads_windows/W2_chaoyang_all.json",
}

ev = pd.read_csv("outputs/selfdraw_eval.csv")
geoms = json.load(open("outputs/selfdraw_geoms.json"))

results = []
geoms_out = {}

for win, road_path in WINDOWS.items():
    print(f"\n=== {win} ===")
    road_lines = load_road_lines(road_path)
    blocks = build_blocks(road_lines)
    print(f"  路线: {len(road_lines)}, 街区块: {len(blocks)}")

    # STRtree 空间索引
    strtree = STRtree(blocks)

    win_ev = ev[ev.window == win]
    for _, r in win_ev.iterrows():
        rid = r["source_record_id"]
        target_area = int(r["fence_area"])
        name = r["name"]

        item = geoms.get(rid, {})
        truth_wkt = item.get("fence")
        if not truth_wkt:
            continue
        truth = swkt.loads(truth_wkt)

        seed = item.get("seed")
        if not seed:
            continue
        s_lon, s_lat = seed[0], seed[1]

        # 生成
        a3 = generate_A3_circle(s_lon, s_lat, target_area, blocks, strtree)
        c3 = generate_C3(s_lon, s_lat, target_area)

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

        geoms_out[rid] = {
            "fence": truth_wkt,
            "seed": [s_lon, s_lat],
        }
        if a3:
            geoms_out[rid]["A3_v2"] = swkt.dumps(a3)
        if c3:
            geoms_out[rid]["C3_v2"] = swkt.dumps(c3)

# 结果
df_out = pd.DataFrame(results)
df_out.to_csv("outputs/selfdraw_eval_v2.csv", index=False)

print("\n=== 对比 ===")
for label, col_old, col_new in [("A3 街区法", "iou_A3_old", "iou_A3_v2")]:
    old = df_out[col_old].dropna()
    new = df_out[col_new].dropna()
    print(f"{label} 旧: n={len(old)} med={old.median():.3f} >0.5={(old>0.5).mean():.1%} >0.7={(old>0.7).mean():.1%}")
    print(f"{label} 新: n={len(new)} med={new.median():.3f} >0.5={(new>0.5).mean():.1%} >0.7={(new>0.7).mean():.1%}")

new_c3 = df_out["iou_C3_v2"].dropna()
print(f"C3 新: n={len(new_c3)} med={new_c3.median():.3f} >0.5={(new_c3>0.5).mean():.1%} >0.7={(new_c3>0.7).mean():.1%}")

best = df_out[["iou_A3_v2", "iou_C3_v2"]].max(axis=1)
print(f"择优(A3_v2,C3_v2): med={best.median():.3f} >0.5={(best>0.5).mean():.1%} >0.7={(best>0.7).mean():.1%}")

# 按窗口分
for win in WINDOWS:
    w = df_out[df_out.window == win]
    b = w[["iou_A3_v2", "iou_C3_v2"]].max(axis=1)
    print(f"  {win}: A3_v2 med={w.iou_A3_v2.median():.3f}, 择优 med={b.median():.3f}")

json.dump(geoms_out, open("outputs/selfdraw_geoms_v2.json", "w"))
print(f"\n保存完成")
