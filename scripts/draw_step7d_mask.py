# -*- coding: utf-8 -*-
"""
Step 7d: 路网掩膜切割法
- 核心思路：目标面积圆 ∩ 非路网区域 = 贴路网的围栏近似
- 比 block union 更平滑（连续切割 vs 碎块拼接）
- 取包含种子点的连通分量
"""
import json, math, time
import pandas as pd, numpy as np
from shapely.geometry import LineString, Polygon, Point, MultiPolygon, box
from shapely.ops import unary_union, polygonize
from shapely import wkt as swkt
from shapely.validation import make_valid

M2_SCALE = 111320 * 111320 * 0.767
ROAD_BUF_M = 3  # 路网掩膜宽度（半宽）

def area_m2(g):
    return g.area * M2_SCALE

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

def build_road_mask(road_lines, bbox):
    """路线 buffer → union = 路网掩膜（道路占用区域）"""
    buf_deg = ROAD_BUF_M / 111320.0
    bufed = [l.buffer(buf_deg) for l in road_lines]
    mask = unary_union(bufed)
    # 裁到 bbox
    mask = mask.intersection(bbox)
    return mask

def generate_masked(seed_lon, seed_lat, target_area, road_mask, road_mask_inv):
    """
    目标面积圆 - 路网掩膜 = 非路网区域
    取包含种子点的连通分量
    """
    r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
    seed = Point(seed_lon, seed_lat)

    # 逐步扩大，确保有结果
    for scale in [1.0, 1.2, 1.5, 2.0]:
        circle = seed.buffer(r_deg * scale)
        # 非路网区域 = 圆 - 路网
        free = circle.difference(road_mask)
        if free.is_empty:
            continue
        free = make_valid(free) if not free.is_valid else free

        # 取包含种子点的连通分量
        geoms = list(free.geoms) if free.geom_type == "MultiPolygon" else [free]
        for g in geoms:
            if g.contains(seed) or g.intersects(seed):
                # 裁剪到目标面积上界
                a = area_m2(g)
                if a > 1.3 * target_area:
                    # 用更小的圆裁
                    g = g.intersection(seed.buffer(r_deg * 1.05))
                    if not g.is_valid:
                        g = make_valid(g)
                return g
        # 如果种子点恰好在路上，取最近的分量
        if geoms:
            best = min(geoms, key=lambda g: g.distance(seed))
            a = area_m2(best)
            if a > 1.3 * target_area:
                best = best.intersection(seed.buffer(r_deg * 1.05))
            return best
    return None

def generate_C3(slon, slat, tarea):
    r = math.sqrt(tarea / (math.pi * M2_SCALE))
    return Point(slon, slat).buffer(r)

def eval_iou(pred, truth):
    if pred is None or truth is None:
        return 0.0
    pred = make_valid(pred) if not pred.is_valid else pred
    truth = make_valid(truth) if not truth.is_valid else truth
    try:
        i = pred.intersection(truth).area
        u = pred.union(truth).area
        return i / u if u > 0 else 0.0
    except:
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
    t0 = time.time()
    road_lines = load_road_lines(road_path)

    # bbox
    all_coords = []
    for l in road_lines:
        all_coords.extend(list(l.coords))
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    margin = 0.003
    bbox = box(min(lons)-margin, min(lats)-margin, max(lons)+margin, max(lats)+margin)

    road_mask = build_road_mask(road_lines, bbox)
    print(f"  路线: {len(road_lines)}, 掩膜构建: {time.time()-t0:.1f}s")

    # 测试不同掩膜宽度
    for buf_m in [3, 5, 8]:
        buf_deg = buf_m / 111320.0
        bufed = [l.buffer(buf_deg) for l in road_lines]
        mask = unary_union(bufed).intersection(bbox)
        # 测几个样本
        test_ev = ev[ev.window == win].head(10)
        ious = []
        for _, r in test_ev.iterrows():
            item = geoms.get(r["source_record_id"], {})
            if not item.get("fence") or not item.get("seed"):
                continue
            truth = swkt.loads(item["fence"])
            slon, slat = item["seed"]
            pred = generate_masked(slon, slat, int(r["fence_area"]), mask, None)
            ious.append(eval_iou(pred, truth))
        if ious:
            print(f"  buf={buf_m}m: 10样本 IoU med={np.median(ious):.3f}")

    # 用最佳宽度跑全量
    BEST_BUF = 5
    buf_deg = BEST_BUF / 111320.0
    road_mask = unary_union([l.buffer(buf_deg) for l in road_lines]).intersection(bbox)

    win_ev = ev[ev.window == win]
    for _, r in win_ev.iterrows():
        rid = r["source_record_id"]
        tarea = int(r["fence_area"])
        item = geoms.get(rid, {})
        truth_wkt = item.get("fence")
        if not truth_wkt:
            continue
        truth = swkt.loads(truth_wkt)
        seed = item.get("seed")
        if not seed:
            continue
        slon, slat = seed[0], seed[1]

        pred = generate_masked(slon, slat, tarea, road_mask, None)
        c3 = generate_C3(slon, slat, tarea)
        iou_p = eval_iou(pred, truth)
        iou_c = eval_iou(c3, truth)

        results.append({
            "window": win, "source_record_id": rid, "name": r["name"],
            "fence_area": tarea,
            "iou_masked": round(iou_p, 3),
            "iou_C3": round(iou_c, 3),
            "iou_A3_old": r.get("iou_A3_block", None),
        })
        geoms_out[rid] = {"fence": truth_wkt, "seed": [slon, slat]}
        if pred: geoms_out[rid]["masked"] = swkt.dumps(pred)
        if c3: geoms_out[rid]["C3"] = swkt.dumps(c3)

    print(f"  全量完成: {time.time()-t0:.1f}s")

df = pd.DataFrame(results)
df.to_csv("outputs/selfdraw_eval_v4.csv", index=False)

print("\n=== 最终对比 ===")
old = df["iou_A3_old"].dropna()
masked = df["iou_masked"].dropna()
c3 = df["iou_C3"].dropna()
print(f"A3 旧版(街区+裁剪):    med={old.median():.3f} >0.5={(old>0.5).mean():.1%} >0.7={(old>0.7).mean():.1%}")
print(f"掩膜切割法(圆-路网):   med={masked.median():.3f} >0.5={(masked>0.5).mean():.1%} >0.7={(masked>0.7).mean():.1%}")
print(f"C3 先验圆:             med={c3.median():.3f} >0.5={(c3>0.5).mean():.1%} >0.7={(c3>0.7).mean():.1%}")
best = df[["iou_masked","iou_C3"]].max(axis=1)
print(f"择优(掩膜,C3):         med={best.median():.3f} >0.5={(best>0.5).mean():.1%} >0.7={(best>0.7).mean():.1%}")
for w in WINDOWS:
    ww = df[df.window==w]
    bb = ww[["iou_masked","iou_C3"]].max(axis=1)
    print(f"  {w}: masked med={ww.iou_masked.median():.3f}, 择优 med={bb.median():.3f}")

json.dump(geoms_out, open("outputs/selfdraw_geoms_v4.json", "w"))
