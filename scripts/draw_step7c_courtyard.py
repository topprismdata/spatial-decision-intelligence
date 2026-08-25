# -*- coding: utf-8 -*-
"""
Step 7c: 路网 + 建筑足迹 联合 polygonize
- 核心洞察：围栏 = 建筑之间的空地（院落）
- 方法：路线 buffer 2m → boundary + 建筑外轮廓 → 联合 polygonize
- 院落块 = 街区块 - 建筑内部块
"""
import json, math, time
import pandas as pd, numpy as np
from shapely.geometry import LineString, Polygon, Point, MultiPolygon, MultiLineString
from shapely.ops import unary_union, polygonize
from shapely import wkt as swkt
from shapely.validation import make_valid
from shapely.strtree import STRtree

M2_SCALE = 111320 * 111320 * 0.767
BUF_DEG = 2 / 111320.0  # 2m buffer

def area_m2(g):
    return g.area * M2_SCALE

def load_ways(path):
    """加载 OSM way → [(coords, tags)]"""
    data = json.load(open(path))
    ways = []
    for e in data["elements"]:
        if e["type"] != "way" or "geometry" not in e:
            continue
        coords = [(n["lon"], n["lat"]) for n in e["geometry"]]
        if len(coords) < 2:
            continue
        ways.append((coords, e.get("tags", {})))
    return ways

def road_to_lines(ways):
    return [LineString(c) for c, _ in ways]

def building_to_polygons(ways):
    polys = []
    for c, tags in ways:
        if len(c) < 3:
            continue
        p = Polygon(c)
        if p.is_valid and not p.is_empty:
            polys.append(p)
        else:
            p = make_valid(p)
            if p.geom_type == "Polygon" and not p.is_empty:
                polys.append(p)
    return polys

def building_to_outlines(ways):
    """建筑多边形 → 外轮廓 LineString（闭合）"""
    lines = []
    for c, _ in ways:
        if len(c) < 3:
            continue
        lines.append(LineString(c + [c[0]]))
    return lines

def build_courtyard_blocks(road_lines, building_polys, bbox_poly):
    """
    联合 polygonize：
    1. 路线 buffer 2m → union → boundary lines
    2. 建筑多边形 outlines → boundary lines
    3. 联合 polygonize → 所有块（含建筑内部 + 院落）
    4. 院落块 = 所有块 - 建筑内部块
    """
    # 路线 buffer → boundary
    t0 = time.time()
    road_bufed = [l.buffer(BUF_DEG) for l in road_lines]
    road_merged = unary_union(road_bufed)
    road_boundary = road_merged.boundary
    road_lines_final = list(road_boundary.geoms) if road_boundary.geom_type == "MultiLineString" else [road_boundary]

    # 建筑外轮廓
    bldg_outlines = []
    for p in building_polys:
        b = p.boundary
        if b.geom_type == "MultiLineString":
            bldg_outlines.extend(b.geoms)
        else:
            bldg_outlines.append(b)

    # 联合 polygonize
    all_lines = road_lines_final + bldg_outlines
    print(f"  联合 polygonize: {len(road_lines_final)} 路边界 + {len(bldg_outlines)} 建筑轮廓 = {len(all_lines)} 线")
    raw_blocks = list(polygonize(all_lines))
    print(f"  原始块: {len(raw_blocks)}, 耗时 {time.time()-t0:.1f}s")

    # 分类：建筑内部块 vs 院落块
    # 一个块是"建筑内部"如果它的中心落在某个建筑多边形内
    bldg_union = unary_union(building_polys)
    strtree_bldg = STRtree(building_polys)

    courtyard = []
    building_inner = []
    for b in raw_blocks:
        if not b.is_valid:
            b = make_valid(b)
        if b.is_empty or b.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        a = area_m2(b)
        if a < 5 or a > 500_000:
            continue
        rep = b.representative_point()
        # 查是否在建筑内
        hits = strtree_bldg.query(rep)
        is_bldg = False
        if len(hits) > 0:
            for hi in hits:
                if building_polys[int(hi)].contains(rep):
                    is_bldg = True
                    break
        if is_bldg:
            building_inner.append(b)
        else:
            courtyard.append(b)

    print(f"  院落块: {len(courtyard)}, 建筑内部块: {len(building_inner)}")
    return courtyard, building_inner

def generate_fence_v3(seed_lon, seed_lat, target_area, courtyard_blocks, strtree):
    """
    v3: 种子点所在院落块 + 邻块合并 + 面积裁剪
    """
    r_deg = math.sqrt(target_area / (math.pi * M2_SCALE))
    seed = Point(seed_lon, seed_lat)

    # 找种子点所在的院落块
    hits = strtree.query(seed)
    seed_block = None
    if len(hits) > 0:
        for hi in hits:
            b = courtyard_blocks[int(hi)]
            if b.contains(seed):
                seed_block = b
                break

    if seed_block is None:
        # fallback: 面积圆内所有院落块 union
        for scale in [1.0, 1.3, 1.6, 2.0, 2.5]:
            circle = seed.buffer(r_deg * scale)
            hits = strtree.query(circle)
            if len(hits) == 0:
                continue
            blocks = [courtyard_blocks[int(i)] for i in hits]
            unioned = unary_union(blocks)
            if area_m2(unioned) >= 0.3 * target_area:
                break
        else:
            return None
    else:
        # 从种子块开始，逐步扩圈合并
        unioned = seed_block
        for scale in [0.5, 0.8, 1.0, 1.3, 1.6, 2.0, 2.5]:
            if area_m2(unioned) >= 0.8 * target_area:
                break
            circle = seed.buffer(r_deg * scale)
            hits = strtree.query(circle)
            if len(hits) == 0:
                continue
            nearby = [courtyard_blocks[int(i)] for i in hits]
            unioned = unary_union([unioned] + nearby)

    # 裁剪
    if area_m2(unioned) > 1.3 * target_area:
        clip = seed.buffer(r_deg * 1.1)
        unioned = unioned.intersection(clip)
        if not unioned.is_valid:
            unioned = make_valid(unioned)

    return unioned

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
from shapely.geometry import box
WINDOWS = {
    "W1_oldcity": {"roads": "data/roads_windows/W1_oldcity_all.json", "bldgs": "data/buildings/W1_oldcity.json"},
    "W2_chaoyang": {"roads": "data/roads_windows/W2_chaoyang_all.json", "bldgs": "data/buildings/W2_chaoyang.json"},
}

ev = pd.read_csv("outputs/selfdraw_eval.csv")
geoms = json.load(open("outputs/selfdraw_geoms.json"))

results = []
geoms_out = {}

for win, paths in WINDOWS.items():
    print(f"\n=== {win} ===")
    road_ways = load_ways(paths["roads"])
    bldg_ways = load_ways(paths["bldgs"])
    road_lines = road_to_lines(road_ways)
    bldg_polys = building_to_polygons(bldg_ways)
    print(f"  路线: {len(road_lines)}, 建筑: {len(bldg_polys)}")

    # bbox
    all_coords = []
    for c, _ in road_ways:
        all_coords.extend(c)
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    margin = 0.002
    bbox = box(min(lons)-margin, min(lats)-margin, max(lons)+margin, max(lats)+margin)

    courtyard, bldg_inner = build_courtyard_blocks(road_lines, bldg_polys, bbox)
    strtree = STRtree(courtyard)

    # 院落块面积分布
    areas = np.array([area_m2(b) for b in courtyard])
    print(f"  院落块面积(m²): p25={np.percentile(areas,25):.0f} p50={np.percentile(areas,50):.0f} p75={np.percentile(areas,75):.0f}")

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

        a3 = generate_fence_v3(slon, slat, tarea, courtyard, strtree)
        c3 = generate_C3(slon, slat, tarea)
        iou_a3 = eval_iou(a3, truth)
        iou_c3 = eval_iou(c3, truth)

        results.append({
            "window": win, "source_record_id": rid, "name": r["name"],
            "fence_area": tarea,
            "iou_A3_v3": round(iou_a3, 3),
            "iou_C3_v3": round(iou_c3, 3),
            "iou_A3_old": r.get("iou_A3_block", None),
        })
        geoms_out[rid] = {"fence": truth_wkt, "seed": [slon, slat]}
        if a3: geoms_out[rid]["A3_v3"] = swkt.dumps(a3)
        if c3: geoms_out[rid]["C3_v3"] = swkt.dumps(c3)

df = pd.DataFrame(results)
df.to_csv("outputs/selfdraw_eval_v3.csv", index=False)

print("\n=== 最终对比 ===")
old = df["iou_A3_old"].dropna()
new = df["iou_A3_v3"].dropna()
c3n = df["iou_C3_v3"].dropna()
print(f"A3 旧版(路网街区): med={old.median():.3f} >0.5={(old>0.5).mean():.1%} >0.7={(old>0.7).mean():.1%}")
print(f"A3 v3(路网+建筑院落): med={new.median():.3f} >0.5={(new>0.5).mean():.1%} >0.7={(new>0.7).mean():.1%}")
print(f"C3 v3(先验圆): med={c3n.median():.3f} >0.5={(c3n>0.5).mean():.1%} >0.7={(c3n>0.7).mean():.1%}")
best = df[["iou_A3_v3","iou_C3_v3"]].max(axis=1)
print(f"择优(A3_v3,C3_v3): med={best.median():.3f} >0.5={(best>0.5).mean():.1%} >0.7={(best>0.7).mean():.1%}")
for w in WINDOWS:
    ww = df[df.window==w]
    bb = ww[["iou_A3_v3","iou_C3_v3"]].max(axis=1)
    print(f"  {w}: A3_v3 med={ww.iou_A3_v3.median():.3f}, 择优 med={bb.median():.3f}")

json.dump(geoms_out, open("outputs/selfdraw_geoms_v3.json", "w"))
