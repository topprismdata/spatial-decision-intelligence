"""R16 视觉验证 v2: 走 omp 主会话同一个 zhipu GLM-5.3-flash (多模态).
因为 SCNet 上没有这个模型, 需要走 bigmodel.cn 或通过 env 里已有的 ZHIPU key."""
import warnings; warnings.filterwarnings("ignore")
import os, json, base64, re, requests

# 检查可用 API keys
CANDIDATE_ENV = ["ZHIPU_API_KEY","GLM_API_KEY","BIGMODEL_API_KEY","ZHIPUAI_API_KEY"]
found = {k:os.environ[k][:8]+"..." for k in CANDIDATE_ENV if k in os.environ}
print("env keys:", found if found else "none")

# 尝试从 /Users/user/.zhipu/ 或 config 读取
import pathlib
for p in [pathlib.Path.home()/".zhipu", pathlib.Path.home()/".bigmodel",
          pathlib.Path.home()/".config/zhipu"]:
    if p.exists():
        print("config dir:",p)
