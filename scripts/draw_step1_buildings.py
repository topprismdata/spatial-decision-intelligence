"""自绘围栏 Step 1: 为两个演示窗口下载 OSM 建筑足迹 (way[building])."""
import json, os, time, urllib.request, urllib.parse

OUT_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/buildings"
OVERPASS = "https://overpass-api.de/api/interpreter"
os.makedirs(OUT_DIR, exist_ok=True)

# 2km x 2km 窗口 (中心 ± 1km)
WINDOWS = {
    "W1_oldcity": (116.37, 39.93),   # 东城老城 (胡同区, 小社区密集)
    "W2_chaoyang": (116.43, 39.93),  # 朝阳 (现代居住区)
}
HALF_LNG = 0.0117   # ~1km at lat 39.93
HALF_LAT = 0.009

def fetch(name, lon, lat, retries=5):
    fp = os.path.join(OUT_DIR, f"{name}.json")
    if os.path.exists(fp) and os.path.getsize(fp) > 100:
        print(f"{name}: 已存在, skip")
        return
    w, s, e, n = lon-HALF_LNG, lat-HALF_LAT, lon+HALF_LNG, lat+HALF_LAT
    q = (f'[out:json][timeout:180];'
         f'(way["building"]({s:.6f},{w:.6f},{n:.6f},{e:.6f}););'
         f'out geom;')
    for i in range(retries):
        try:
            req = urllib.request.Request(OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "fence-road-diagnosis/1.0 (contact: research)"})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = r.read()
            open(fp, "wb").write(data)
            els = json.loads(data).get("elements", [])
            print(f"{name}: ok {len(data)/1e6:.1f} MB, {len(els)} buildings")
            return
        except Exception as ex:
            print(f"{name} retry {i+1}: {ex}")
            time.sleep(10 * (i + 1))
    print(f"{name}: FAIL")

for name, (lon, lat) in WINDOWS.items():
    fetch(name, lon, lat)
    time.sleep(3)
