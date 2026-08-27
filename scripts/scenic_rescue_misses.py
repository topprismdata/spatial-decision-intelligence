"""T2 补救: 47 条 miss 用名称变体策略重查 (去行政区词 / 简短关键词)"""
import warnings; warnings.filterwarnings("ignore")
import requests, time, re
import pandas as pd
from src.coordinate.transforms import gcj02_to_wgs84

KEY = "7cefa505e38404f1a83f8eea34565e6c"
SUFFIXES = ["旅游景区","风景名胜区","旅游度假区","旅游区","度假区","风景区","景区"]
def norm2(s):
    s=str(s or "").strip(); ch=True
    while ch:
        ch=False
        for suf in SUFFIXES:
            if s.endswith(suf): s=s[:-len(suf)].strip(); ch=True
    return s

pts = pd.read_csv("outputs/scenic_spots/amap_points.csv")
miss = pts[pts.match==0]
cache=[];hits=0
for _,row in miss.iterrows():
    primary = norm2(row["primary"])
    # 变体: 去行政区前缀(北京市/北京/XX市), 只留 2-6 字主词, 全名
    cands = set()
    s = primary
    for pref in ["北京市","北京","北京市海淀区","海淀区"]:
        if s.startswith(pref): s=s[len(pref):]; break
    cands.add(primary[:12])
    cands.add(s[:12])
    # 提取核心名词 (从右到左第一个'公园|博物馆|馆|园|山|寺|峡|湖|洞'前的部分+后缀)
    m = re.search(r"([\u4e00-\u9fa5]{2,6}(?:公园|博物馆|纪念馆|艺术馆|植物园|动物园|风景区))", s)
    if m: cands.add(m.group(1)[:12])
    best=None
    for kw in list(cands):
        if not kw: continue
        try:
            resp=requests.get("https://restapi.amap.com/v3/place/text",
                params={"key":KEY,"keywords":kw,"city":"北京","offset":5,"page":1,
                        "extensions":"all"},timeout=8).json()
        except Exception: continue
        pois=resp.get("pois") or []
        scored=[]
        d=str(row["district"]).replace("区","").strip()
        for p in pois:
            nm=p.get("name",""); nnm=norm2(nm)
            if not primary or not nnm: sc=0
            elif nnm==primary: sc=100
            elif primary in nnm or nnm in primary: sc=90
            else:
                a=set(re.findall("..",primary)); b=set(re.findall("..",nnm))
                sc=int(200*len(a&b)/max(len(a)+len(b),1))
            if d and d not in f"{p.get('pname','')}{p.get('adname','')}": sc-=50
            scored.append((sc,p))
        scored.sort(key=lambda x:-x[0])
        if scored and scored[0][0]>=70:
            best=scored[0][1]; break
    if best:
        lng,lat=map(float,best["location"].split(","))
        wl,wlt=gcj02_to_wgs84(lng,lat)
        cache.append({"primary":row["primary"],"grade":row["grade"],"district":row["district"],
                      "amap_name":best.get("name"),"address":best.get("address","") or "",
                      "wgs_lng":round(wl,6),"wgs_lat":round(wlt,6),"match":1})
        hits+=1
    time.sleep(0.08)
print(f"补救命中 {hits}/{len(miss)}")

# 合并回总表
full=pd.read_csv("outputs/scenic_spots/amap_points.csv")
newdf=pd.DataFrame(cache).drop_duplicates("primary")
full=full[~full.primary.isin(newdf.primary)]
full=pd.concat([full,newdf],ignore_index=True).sort_values("primary")
full.to_csv("outputs/scenic_spots/amap_points.csv",index=False)
final=(full.match==1).sum()
print(f"总计: {final}/{len(full)} ({final/len(full)*100:.0f}%)")
