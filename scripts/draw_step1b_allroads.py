"""补下两窗口的全类型路网 (含 footway/service/path) — 胡同级街区切分必需."""
import json, os, time, urllib.request, urllib.parse

OUT_DIR = "/Users/user/WorkBuddy/2026-08-18-17-47-15/data/roads_windows"
OVERPASS = "https://overpass-api.de/api/interpreter"
os.makedirs(OUT_DIR, exist_ok=True)

WINDOWS = {"W1_oldcity": (116.37, 39.93), "W2_chaoyang": (116.43, 39.93)}
HALF_LNG, HALF_LAT = 0.0117 + 0.002, 0.009 + 0.002   # 加边距

for name, (lon, lat) in WINDOWS.items():
    fp = os.path.join(OUT_DIR, f"{name}_all.json")
    if os.path.exists(fp) and os.path.getsize(fp) > 100:
        print(name, "已存在"); continue
    w, s, e, n = lon-HALF_LNG, lat-HALF_LAT, lon+HALF_LNG, lat+HALF_LAT
    q = (f'[out:json][timeout:180];'
         f'(way["highway"]({s:.6f},{w:.6f},{n:.6f},{e:.6f}););'
         f'out geom;')
    for i in range(5):
        try:
            req = urllib.request.Request(OVERPASS,
                data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": "fence-road-diagnosis/1.0 (contact: research)"})
            with urllib.request.urlopen(req, timeout=240) as r:
                data = r.read()
            open(fp, "wb").write(data)
            els = json.loads(data).get("elements", [])
            print(f"{name}: ok {len(data)/1e6:.1f} MB, {len(els)} ways (全类型)")
            break
        except Exception as ex:
            print(f"{name} retry {i+1}: {ex}"); time.sleep(10*(i+1))
    time.sleep(3)
