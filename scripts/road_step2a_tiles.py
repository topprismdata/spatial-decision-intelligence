"""Step 2a: 计算北京围栏覆盖 bbox 并分片下载路网（可断点续传）."""
import sys, os, json, time, math
sys.path.insert(0, "/Users/user/WorkBuddy/2026-08-18-17-47-15")
import urllib.request, urllib.parse

import pandas as pd
from shapely import wkt

EXCEL = "data/client_a_sites.xlsx"
QA = "/Users/user/WorkBuddy/2026-08-18-17-47-15/outputs/qa_issues_report.csv"
ROAD_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/roads"
OVERPASS = "https://overpass-api.de/api/interpreter"
HIGHWAY_FILTER = "^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street)(_link)?$"

os.makedirs(ROAD_DIR, exist_ok=True)

df = pd.read_excel(EXCEL, sheet_name="sheet1")
df["source_record_id"] = [f"SRC_{i+1:06d}" for i in range(len(df))]
qa = pd.read_csv(QA)
m = qa.merge(df[["source_record_id", "城市", "坐标面[内置]"]], on="source_record_id", how="left")
m = m[m["坐标面[内置]"].notna() & (m["坐标面[内置]"].astype(str).str.len() > 10)]
bj = m[m["城市"].astype(str).str.contains("北京")]
print("北京有几何围栏:", len(bj))

# bbox（多边形原始 GCJ-02 坐标即可确定范围，纠偏量级 <1km）
xs, ys = [], []
for w in bj["坐标面[内置]"].astype(str):
    try:
        g = wkt.loads(w)
        b = g.bounds
        xs += [b[0], b[2]]; ys += [b[1], b[3]]
    except Exception:
        pass
xs = sorted(xs); ys = sorted(ys)
# 0.5% 截尾去离群
n = len(xs)
W, S = xs[int(n*0.005)], ys[int(n*0.005)]
E, N = xs[int(n*0.995)], ys[int(n*0.995)]
print("北京围栏 bbox (W,S,E,N): %.4f %.4f %.4f %.4f" % (W, S, E, N))

PAD = 0.004  # ~400m
W, S, E, N = W - PAD, S - PAD, E + PAD, N + PAD
NX, NY = 6, 5  # 30 片
tiles = []
dw, dh = (E - W) / NX, (N - S) / NY
for i in range(NX):
    for j in range(NY):
        tiles.append((round(W + i*dw, 6), round(S + j*dh, 6), round(W + (i+1)*dw, 6), round(S + (j+1)*dh, 6)))
print("tiles:", len(tiles), "| 每片 %.3f°x%.3f°" % (dw, dh))

def fetch(tile, retries=4):
    w, s, e, n = tile
    q = (f'[out:json][timeout:90];'
         f'(way["highway"~"{HIGHWAY_FILTER}"]({s:.6f},{w:.6f},{n:.6f},{e:.6f}););'
         f'out geom;')
    for i in range(retries):
        try:
            req = urllib.request.Request(OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "fence-road-diagnosis/1.0 (contact: research)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as ex:
            print(f"    retry {i+1}: {ex}")
            time.sleep(8 * (i + 1))
    return None

done, todo = 0, 0
for k, t in enumerate(tiles):
    fp = os.path.join(ROAD_DIR, f"tile_{k:02d}.json")
    if os.path.exists(fp) and os.path.getsize(fp) > 100:
        done += 1
        continue
    todo += 1
    print(f"[{k+1}/{len(tiles)}] {t} ...", flush=True)
    data = fetch(t)
    if data is None:
        print("    FAIL, skip (rerun script to resume)")
        continue
    open(fp, "wb").write(data)
    done += 1
    print(f"    ok {len(data)/1e6:.1f} MB", flush=True)
    time.sleep(2.5)

print(f"\n完成 {done}/{len(tiles)} 片 | 目录 {ROAD_DIR}")
