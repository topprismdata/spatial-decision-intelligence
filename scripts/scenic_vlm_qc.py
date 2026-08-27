"""R16 视觉验证: MiniMax M3 (SCNet) 逐个核验景区边界截图"""
import warnings; warnings.filterwarnings("ignore")
import os, json, re, base64, glob
import requests
from PIL import Image
import pandas as pd

KEY = re.search(r'apiKey: (\S+)', open('/Users/user/.omp/agent/models.yml').read()).group(1)
QC_DIR = "outputs/scenic_spots/visual_qc"
OUT_CSV = "outputs/scenic_spots/visual_qc_verdicts.csv"

def vlm_judge(image_path, spot_name):
    """发送卫星图 + 边界叠加 → MiniMax M3 判断 PASS/FAIL"""
    img = Image.open(image_path).convert("RGB")
    w,h=img.size; sc=700/max(w,h)
    if sc < 1:
        img=img.resize((int(w*sc),int(h*sc)),Image.LANCZOS)
    img.save("/tmp/_qc_tmp.jpg","JPEG",quality=70)
    b64=base64.b64encode(open("/tmp/_qc_tmp.jpg","rb").read()).decode()
    
    req={"model":"MiniMax-M3","messages":[{"role":"user","content":[
      {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
      {"type":"text","text":f"图上有一个彩色高亮多边形，理论上应该完整覆盖 {spot_name} 景区。请判断边界是否贴合实际围墙轮廓。只回答一行：PASS 或 FAIL 加一句原因。"}
    ]}],"max_tokens":2000}
    
    try:
        r=requests.post("https://api.scnet.cn/api/llm/v1/chat/completions",
            headers={"Authorization":f"Bearer {KEY}"},json=req,timeout=120)
        d=r.json()
        if 'choices' in d:
            return (d['choices'][0]['message'].get('content') or '').strip()[:400]
        else: return "ERR:"+str(d)[:80]
    except Exception as e:
        return f"TIMEOUT:{e}"

# 扫描 visual_qc 目录里所有 png
files = sorted(glob.glob(f"{QC_DIR}/*.png"))
print(f"待验证截图: {len(files)}")

results=[]
for i,f in enumerate(files):
    name = os.path.basename(f).replace(".png","")
    grade = name.split("_")[0]
    spot = "_".join(name.split("_")[1:])
    verdict = vlm_judge(f, spot.replace("_"," "))
    verdict_pass = "PASS" in verdict[:40].upper()
    results.append({"file":os.path.basename(f),"grade":grade,"name":spot,
                    "verdict_raw":verdict,"pass":verdict_pass})
    tag = "✓" if verdict_pass else ("⚠" if "partial" in verdict.lower() else "✗")
    print(f"{tag} [{grade}] {spot[:22]:24s} {verdict[:100]}")
    
df=pd.DataFrame(results)
df.to_csv(OUT_CSV,index=False)
print(f"\n=== PASS 率: {(df['pass']).sum()}/{len(df)} = {(df['pass']).mean()*100:.0f}% ===")
print(f"保存 {OUT_CSV}")
