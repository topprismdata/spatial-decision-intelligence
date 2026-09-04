"""Step 1a: 选预校验样本 + 计算路网下载包围盒."""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
import sys, re, json, random
sys.path.insert(0, str(_REPO))

import pandas as pd
from shapely import wkt

EXCEL = str(_REPO / 'data/client_a_sites.xlsx')
QA = str(_REPO / 'outputs/qa_issues_report.csv')

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]

qa = pd.read_csv(QA)
print("qa rows:", len(qa), "| narrow_strip:", qa["qa_issues"].str.contains("NARROW_STRIP").sum())

m = qa.merge(df[["source_record_id", "小区名称", "城市", "坐标面[内置]"]], on="source_record_id", how="left")
m = m[m["坐标面[内置]"].notna() & (m["坐标面[内置]"].astype(str).str.len() > 10)]

# 城市：北京 vs 石家庄
print(m["城市"].value_counts().to_string())

street_pat = re.compile(r"街|路|胡同|巷|大道|大街")
bj = m[m["城市"].astype(str).str.contains("北京")]
street_ns = bj[bj["qa_issues"].str.contains("NARROW_STRIP") & bj["小区名称"].astype(str).str.contains(street_pat)]
print("北京 NARROW_STRIP 且名字含街/路/胡同/巷:", len(street_ns))

random.seed(42)
street_sample = street_ns.sample(min(20, len(street_ns)), random_state=42)
# 随机对照：全量有几何围栏中随机 20（排除已选街道样本）
rest = m[~m["source_record_id"].isin(street_sample["source_record_id"])]
rand_sample = rest.sample(20, random_state=42)
sample = pd.concat([street_sample.assign(group="street"), rand_sample.assign(group="random")])
print("样本:", len(sample), "| street:", (sample["group"]=="street").sum(), "| random:", (sample["group"]=="random").sum())

# 计算样本 WGS84 bbox（多边形 GCJ-02 → WGS84）
from src.coordinate.transforms import transform_geometry_wkt
from src.coordinate.transforms import gcj02_to_wgs84

import numpy as np
xs, ys = [], []
ok = 0
for _, r in sample.iterrows():
    try:
        wgs = transform_geometry_wkt(str(r["坐标面[内置]"]), gcj02_to_wgs84)
        if not wgs:
            continue
        g = wkt.loads(wgs)
        xs += [g.bounds[0], g.bounds[2]]; ys += [g.bounds[1], g.bounds[3]]
        ok += 1
    except Exception:
        pass
print("解析成功:", ok, "/", len(sample))
bbox = [min(ys)-0.003, min(xs)-0.003, max(ys)+0.003, max(xs)+0.003]  # south,west,north,east
print("样本 bbox (S,W,N,E):", [round(v,4) for v in bbox])
print("bbox 跨度: lat %.3f° lng %.3f°" % (bbox[2]-bbox[0], bbox[3]-bbox[1]))

# 全量北京围栏 bbox（供对比决定下载范围）
bj_all = m[m["城市"].astype(str).str.contains("北京")]
bxs, bys = [], []
for w in bj_all["坐标面[内置]"].astype(str).head(2000):
    try:
        g = wkt.loads(w)
        bxs += [g.bounds[0], g.bounds[2]]; bys += [g.bounds[1], g.bounds[3]]
    except Exception:
        pass
print("北京全量(前2000) GCJ02 bbox: lat %.4f~%.4f lng %.4f~%.4f" % (min(bys), max(bys), min(bxs), max(bxs)))

_out = _REPO / "outputs" / "road_precheck"; _out.mkdir(parents=True, exist_ok=True)
sample.to_json(_out / "samples.json", orient="records", force_ascii=False)
json.dump({"bbox_sample": bbox}, open(_out / "bbox_sample.json", "w"))
print(f"saved {_out / 'samples.json'}")
