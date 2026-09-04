"""Stage-by-stage completeness/correctness checker for onboarding a new city.

Designed to be run by a newcomer at EVERY step of docs/new-city-guide.md; each
stage prints PASS / WARN / FAIL lines with a one-sentence fix, exit code 0 only
when nothing FAILED.

Stages
  input   : Geofabrik shapefiles present, readable, right CRS, Chinese names
            intact (encoding trap), layer fclass inventories.
  output  : city_gb50137.py results: counts reconcile geojson<->shp<->map html,
            class distribution sane, no NaN geometry, U-rate not exploding,
            stale-directory shapefile trap detected.
  all     : input + output (default).

Examples
  python3 scripts/check_city_data.py --stage input  --data-dir data/xian_shp
  python3 scripts/check_city_data.py --stage output --city xian \
      --bbox 34.10,108.50,34.55,109.30
"""

import argparse
import json
import math
import os
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd

_REPO = Path(os.environ.get("SDI_ROOT") or Path(__file__).resolve().parents[1])

REQUIRED_LAYERS = ["landuse_a", "pois_a", "transport_a"]
EXPECTED_COLUMNS = {"osm_id", "code", "fclass", "name", "geometry"}
CLASS_ORDER = ["R", "B1", "B2", "M", "S", "A3", "A4", "A5", "G", "MIL", "AGR", "U"]

n_pass = n_warn = n_fail = 0


def ok(msg):
    global n_pass
    n_pass += 1
    print(f"  PASS {msg}")


def warn(msg, fix=""):
    global n_warn
    n_warn += 1
    print(f"  WARN {msg}" + (f"\n       fix: {fix}" if fix else ""))


def fail(msg, fix=""):
    global n_fail
    n_fail += 1
    print(f"  FAIL {msg}" + (f"\n       fix: {fix}" if fix else ""))


def resolve(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else _REPO / q


# ── stage: input ──────────────────────────────────────────────────────────────

def check_input(data_dir: Path, bbox=None):
    print(f"\n[1/4] 目录与必需图层 — {data_dir}")
    if not data_dir.is_dir():
        fail(f"数据目录不存在: {data_dir}",
             "python3 scripts/fetch_city_data.py --region <geofabrik-slug> --dest "
             f"{data_dir.relative_to(_REPO)}")
        return
    for layer in REQUIRED_LAYERS:
        shp = data_dir / f"gis_osm_{layer}_free_1.shp"
        if not shp.exists():
            fail(f"缺图层 {shp.name}",
                 "重新跑 fetch_city_data.py；若 zip 内确无此图层，说明该地抽取粒度不同，"
                 "检查目录里实际有哪些 gis_osm_*.shp")
    leftovers = sorted(p.name for p in data_dir.glob("*-free.zip")) + \
                sorted(p.name for p in data_dir.glob("part_*"))
    if leftovers:
        warn(f"目录残留压缩包/分片: {leftovers}",
             "fetch_city_data.py 会自动解包并删除；手动下载的话 unzip -o 后删除 zip")

    print("\n[2/4] 图层可读性与 schema")
    frames = {}
    for layer in REQUIRED_LAYERS:
        shp = data_dir / f"gis_osm_{layer}_free_1.shp"
        if not shp.exists():
            continue
        try:
            gdf = gpd.read_file(shp)
        except Exception as e:
            fail(f"{shp.name} 读取失败: {str(e)[:90]}",
                 "确认 .shp/.dbf/.shx/.prj 四件套齐全（缺 .dbf 则属性全丢）")
            continue
        frames[layer] = gdf
        cols = set(gdf.columns)
        miss = EXPECTED_COLUMNS - cols
        if miss:
            fail(f"{layer} 缺列 {sorted(miss)}", "该 zip 不是 *-free.shp 聚合包？核对下载 URL")
        else:
            ok(f"{layer}: {len(gdf):>7,} 面, 列齐全")
        epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
        if epsg not in (None, 4326):
            fail(f"{layer} CRS=EPSG:{epsg}，非 WGS84", "先 to_crs(4326) 再入库")
        empty = gdf[gdf.is_empty]
        if len(empty):
            warn(f"{layer} 有 {len(empty)} 个空几何", "分类脚本会跳过，但建议记录 osm_id 上报数据源问题")

    print("\n[3/4] 中文名编码抽查（.cpg/.dbf 陷阱）")
    for layer, gdf in frames.items():
        names = gdf["name"].dropna()
        if names.empty:
            warn(f"{layer} 无任何 name —— 可能 .cpg 丢失导致 DBF 编码错乱",
                 "删除 .dbf 重新解压，或 read_file(encoding='utf-8')")
            continue
        sample = str(names.iloc[0])
        cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
        mojibake = bool(re.search(r"[\ufffd]|[À-ÿ]{4,}", sample))
        if mojibake:
            fail(f"{layer} 首条 name 疑似乱码: {sample[:40]!r}", "同上，检查 .cpg/.dbf")
        elif cjk:
            ok(f"{layer} 中文正常（例: {sample[:24]}）")
        else:
            warn(f"{layer} 首条 name 无中日韩字符: {sample[:40]!r}（若该层本就多为英文/空可忽略）")

    print("\n[4/4] 抽取范围判断（省包 vs 市包）")
    lu = frames.get("landuse_a")
    if lu is None:
        return
    total_res = int((lu.fclass == "residential").sum())
    if bbox:
        min_lat, min_lng, max_lat, max_lng = bbox
        c = lu.geometry.representative_point()
        inside = ((c.y >= min_lat) & (c.y <= max_lat) & (c.x >= min_lng) & (c.x <= max_lng))
        n_in = int(((lu.fclass == "residential") & inside).sum())
        ratio = n_in / max(total_res, 1)
        print(f"  提示: landuse=residential 全量 {total_res:,} -> bbox 内 {n_in:,} "
              f"({ratio:.0%})")
        if ratio > 0.9:
            warn("bbox 覆盖 >90%：要么整省都选了，要么这就是市包",
                 "对照 Geofabrik 页面确认；整省数据请调小 bbox（见指南 §1.3）")
        elif ratio < 0.01:
            fail("bbox 内 residential <1%：bbox 大概率写反或写错坐标",
                 "顺序必须是 min_lat,min_lng,max_lat,max_lng（西安=34.10,108.50,34.55,109.30）")
        else:
            ok(f"bbox 截取比例合理（{ratio:.0%}）")
    elif total_res > 20000:
        warn(f"residential 面 {total_res:,} 个：这几乎肯定是省包，city_gb50137 不带 --bbox "
             "会把整省算进来", "加 --bbox（见指南 §2）")
    else:
        ok(f"residential {total_res:,} 个，量级像市包")

    # fclass inventory against the mapping table — unknown tags land in U
    try:
        sys.path.insert(0, str(_REPO))
        from scripts.city_gb50137 import LANDUSE_GB
    except Exception:
        LANDUSE_GB = {}
    if LANDUSE_GB and lu is not None:
        unk = lu[~lu.fclass.isin(LANDUSE_GB)]
        pct = 100 * len(unk) / max(len(lu), 1)
        top = unk.fclass.value_counts().head(5)
        if pct > 5:
            warn(f"{len(unk):,} 面 ({pct:.0f}%) 的 fclass 无 GB 映射，将落入 U 类: "
                 f"{dict(top)}", "量大的类请扩充 city_gb50137.py::LANDUSE_GB 后重跑")
        else:
            ok(f"fclass 映射覆盖 {100-pct:.0f}%（未知类 {len(unk):,} 面落 U）")


# ── stage: output ─────────────────────────────────────────────────────────────

def check_output(city: str, out_root: Path, bbox=None, data_dir=None):
    d = out_root / f"{city}_full"
    geo = d / f"{city}_gb50137_all.geojson"
    shp_dir = d / f"{city}_gb50137_all"
    html = d / f"{city}_gb50137_map.html"

    print(f"\n[1/4] 三类产物存在性 — {d}")
    for p, name in [(geo, "geojson"), (shp_dir / f"{city}_gb50137_all.shp", "shapefile"),
                    (html, "map html")]:
        if p.exists():
            ok(f"{name}: {p.name} ({p.stat().st_size/1048576:.1f} MB)")
        else:
            fail(f"缺 {name} ({p})", "先跑 python3 scripts/city_gb50137.py --city "
                 f"{city} --out-root {out_root}" + (f" --bbox {bbox}" if bbox else ""))

    if not geo.exists():
        return
    print("\n[2/4] geojson 内容契约")
    try:
        gj = json.loads(geo.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"geojson 解析失败: {str(e)[:80]}", "重跑分类脚本")
        return
    feats = gj["features"]
    n = len(feats)
    ok(f"features: {n:,}")
    codes = Counter(f["properties"]["gb_code"] for f in feats)
    missing_classes = [c for c in CLASS_ORDER if codes.get(c, 0) == 0]
    if len(missing_classes) > 3:
        warn(f"{len(missing_classes)} 个 GB 类为 0: {missing_classes}",
             "小城市合理；大城市需抽查该类 OSM 标签是否变体")
    else:
        ok(f"12 类分布: { {k: codes.get(k, 0) for k in CLASS_ORDER} }")
    u_pct = 100 * codes.get("U", 0) / max(n, 1)
    if u_pct > 15:
        fail(f"未分类占 {u_pct:.1f}% > 15%", "看 input 阶段 WARN 的未知 fclass，扩映射")
    else:
        ok(f"未分类率 {u_pct:.1f}% (<15% 健康线)")

    bad_geom = 0
    for f in feats:
        g = f["geometry"]
        if not g:
            bad_geom += 1
            continue
        rings = g["coordinates"] if g["type"] == "Polygon" else \
            [r for p in g["coordinates"] for r in p]
        for ring in rings:
            if any(len(pt) < 2 or math.isnan(pt[0]) or math.isnan(pt[1]) for pt in ring):
                bad_geom += 1
                break
    if bad_geom:
        warn(f"{bad_geom} 个要素含 NaN/退化坐标环", "地图会跳过，但建议查 OSM 原始要素并上报")
    else:
        ok("无 NaN/退化坐标")

    print("\n[3/4] 三产物交叉对账")
    if shp_dir.exists() and (shp_dir / f"{city}_gb50137_all.shp").exists():
        try:
            s = gpd.read_file(shp_dir / f"{city}_gb50137_all.shp")
            if len(s) != n:
                fail(f"shp {len(s)} 面 ≠ geojson {n} 面", "重跑分类（两者必须同源）")
            else:
                sc = Counter(s.gb_code)
                if dict(sc) != {k: v for k, v in codes.items() if v}:
                    fail("shp 与 geojson 类分布不一致", "重跑分类")
                else:
                    ok(f"shp↔geojson 恒等（{n:,} 面，逐类一致）")
        except Exception as e:
            fail(f"shp 读取失败: {str(e)[:80]}", "检查五件套是否齐全")
    if html.exists():
        h = html.read_text(encoding="utf-8", errors="ignore")
        npoly = h.count("L.polygon(")
        rings_expected = sum(
            len(f["geometry"]["coordinates"])
            if f["geometry"] and f["geometry"]["type"] == "Polygon"
            else (sum(len(p) for p in f["geometry"]["coordinates"])
                  if f["geometry"] and f["geometry"]["type"] == "MultiPolygon" else 0)
            for f in feats)
        if npoly == rings_expected:
            ok(f"html 环数 {npoly:,} == geojson 环数 {rings_expected:,}")
        else:
            warn(f"html 环数 {npoly:,} ≠ geojson {rings_expected:,}",
                 "多数正常（<3 点环被跳过）；偏差 >10% 则重跑")
        if "preferCanvas:true" not in h:
            warn("html 未用 canvas 渲染", "要素上万时 SVG 会冻结浏览器，确认脚本版本")
        if "ODbL" not in h and "OpenStreetMap" not in h:
            fail("html 缺 ODbL/OSM 署名", "再发布必须带署名（合规红线）")
        m = re.search(r"全量分类 \((\d+) 地块\)", h)
        if m and int(m.group(1)) != n:
            fail(f"html 标题 {m.group(1)} ≠ features {n}", "地图是旧产物，重跑")
        else:
            ok("html 标题计数与数据一致")

    print("\n[4/4] 量级与空间范围 sanity")
    res = codes.get("R", 0)
    if n < 50:
        fail(f"仅 {n} 面：bbox 可能太小或写反", "先跑 --stage input 看 bbox 截取比例")
    else:
        ok(f"总量 {n:,} 面、居住 {res:,}")
    # (a) recompute the centroid extent of the result and compare to --bbox:
    #     an artifact produced WITHOUT --bbox (or with an older one) spills out.
    if bbox and feats:
        lngs, lats = [], []
        for f in feats:
            g = f["geometry"]
            if not g:
                continue
            rings = g["coordinates"] if g["type"] == "Polygon" else \
                [p[0] for p in g["coordinates"]]
            for r0 in rings:
                for pt in r0[:20]:
                    if len(pt) >= 2 and not any(map(math.isnan, pt[:2])):
                        lngs.append(pt[0]); lats.append(pt[1])
        if lngs:
            min_lat, min_lng, max_lat, max_lng = bbox
            pad = 0.25  # representative-point vs raw coords tolerance (deg)
            out_of = sum(1 for la, lo in zip(lats, lngs)
                         if not (min_lat - pad <= la <= max_lat + pad
                                 and min_lng - pad <= lo <= max_lng + pad))
            pct = 100 * out_of / len(lats)
            if pct > 2:
                fail(f"{pct:.0f}% 采样点落在 --bbox 之外：产物可能不是用这个 bbox 生成的",
                     "用同一 --bbox 重跑 city_gb50137.py")
            else:
                ok(f"产物空间范围与 --bbox 一致（越界采样 {pct:.1f}%）")
    # (b) landuse coverage: recompute from the raw extract how many landuse
    #     faces SHOULD fall in this bbox and compare with the artifact. Catches
    #     "artifact produced with a different/missing bbox" and "bbox too small".
    if data_dir and bbox:
        src = data_dir / "gis_osm_landuse_a_free_1.shp"
        if src.exists():
            try:
                g0 = gpd.read_file(src, usecols=["geometry"])
                c = g0.geometry.representative_point()
                min_lat, min_lng, max_lat, max_lng = bbox
                expect = int(((c.y >= min_lat) & (c.y <= max_lat) &
                              (c.x >= min_lng) & (c.x <= max_lng)).sum())
                ratio = n / max(expect, 1)
                if ratio < 0.5:
                    fail(f"bbox 内原始 landuse 面 {expect:,}，产物仅 {n:,}（{ratio:.0%}）"
                         "——多数面被 bbox 过滤外的层/旧产物混入或 bbox 不一致",
                         "确认生成与校验用同一 --bbox，重跑")
                elif ratio > 1.5:
                    warn(f"产物面数 {n:,} 远超 bbox 原始 landuse {expect:,}"
                         "（POI/transport 层补充所致，若 >50% 补充不常见请抽查）")
                else:
                    ok(f"bbox 覆盖一致：原始 landuse {expect:,} vs 产物 {n:,} "
                       f"({ratio:.0%}，含 POI/transport 补充)")
            except Exception as e:
                warn(f"无法复核原始抽取: {str(e)[:60]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", choices=["input", "output", "all"], default="all")
    ap.add_argument("--city", default="xian", help="city slug used by city_gb50137.py")
    ap.add_argument("--data-dir", default=None, help="shapefile dir (default data/<city>_shp)")
    ap.add_argument("--out-root", default="outputs")
    ap.add_argument("--bbox", default=None, help="min_lat,min_lng,max_lat,max_lng")
    args = ap.parse_args()
    bbox = tuple(float(v) for v in args.bbox.split(",")) if args.bbox else None
    data_dir = resolve(args.data_dir or f"data/{args.city}_shp")
    out_root = resolve(args.out_root)

    print(f"check_city_data · city={args.city} · stage={args.stage}")
    if args.stage in ("input", "all"):
        check_input(data_dir, bbox)
    if args.stage in ("output", "all"):
        check_output(args.city, out_root, bbox, data_dir if args.bbox else None)

    print(f"\n==== {n_pass} PASS / {n_warn} WARN / {n_fail} FAIL ====")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
