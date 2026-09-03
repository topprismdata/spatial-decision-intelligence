import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[1])
#!/usr/bin/env python3
"""
评估训练好的 U-Net vs A3 路网街区基线
- 复现训练时的 7:3 切分（seed 42, sorted glob, shuffle）
- 逐样本 IoU 对比：U-Net vs iou_A3_block
- 输出: outputs/unet_eval.csv + outputs/unet_overlay_val.png (验证集叠加图)
"""
import os, glob, random
import numpy as np
import pandas as pd
import torch

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from draw_step9_train_unet import UNet, FenceDataset

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

ROOT = str(_REPO)
device = torch.device('cpu')

# ---- 复现切分 ----
files = sorted(glob.glob(os.path.join(ROOT, 'data/satellite/*.npz')))
random.shuffle(files)
n_train = int(0.7 * len(files))
train_files = files[:n_train]
val_files = files[n_train:]
train_ids = {os.path.basename(f)[:-4] for f in train_files}
val_ids = {os.path.basename(f)[:-4] for f in val_files}

# ---- 加载模型 ----
model = UNet(base=32).to(device)
model.load_state_dict(torch.load(os.path.join(ROOT, 'outputs/unet_fence_best.pth'), map_location='cpu'))
model.eval()
print('model loaded', flush=True)

# ---- 逐样本推理 ----
mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

rows = []
val_overlays = []
with torch.no_grad():
    for f in files:
        sid = os.path.basename(f)[:-4]
        d = np.load(f)
        img = d['image'].astype(np.float32) / 255.0
        img_n = (img - mean) / std
        mask = d['mask'].astype(np.float32)
        x = torch.from_numpy(img_n.transpose(2, 0, 1)).unsqueeze(0)
        pred = torch.sigmoid(model(x))[0, 0].numpy()
        pred_bin = (pred > 0.5).astype(np.float32)
        inter = (pred_bin * mask).sum()
        union = pred_bin.sum() + mask.sum() - inter
        iou = float(inter / union) if union > 1e-6 else 0.0
        rows.append({
            'source_record_id': sid,
            'split': 'train' if sid in train_ids else 'val',
            'unet_iou': iou,
            'mask_ratio': float(mask.mean()),
            'pred_ratio': float(pred_bin.mean()),
        })
        if sid in val_ids and len(val_overlays) < 12:
            val_overlays.append((sid, d['image'], mask, pred, pred_bin, iou))

df = pd.DataFrame(rows)

# ---- join 基线 ----
base = pd.read_csv(os.path.join(ROOT, 'outputs/selfdraw_eval.csv'))
df = df.merge(base[['source_record_id', 'name', 'window', 'iou_A3_block']], on='source_record_id', how='left')
df['unet_wins'] = df['unet_iou'] > df['iou_A3_block']

# ---- 汇总 ----
print('\n===== 全量 143 =====')
print(f"U-Net IoU 中位: {df['unet_iou'].median():.3f}   A3: {df['iou_A3_block'].median():.3f}")
print(f"U-Net >0.5: {(df['unet_iou']>0.5).mean():.1%}   A3 >0.5: {(df['iou_A3_block']>0.5).mean():.1%}")

val = df[df['split'] == 'val']
print('\n===== 验证集 43（诚实评估）=====')
print(f"U-Net IoU 中位: {val['unet_iou'].median():.3f}   A3: {val['iou_A3_block'].median():.3f}")
print(f"U-Net >0.5: {(val['unet_iou']>0.5).mean():.1%}   A3 >0.5: {(val['iou_A3_block']>0.5).mean():.1%}")
print(f"U-Net >0.7: {(val['unet_iou']>0.7).mean():.1%}")
print(f"U-Net 胜率(vs A3): {val['unet_wins'].mean():.1%}")

tr = df[df['split'] == 'train']
print('\n===== 训练集 100（参考，有过拟合水分）=====')
print(f"U-Net IoU 中位: {tr['unet_iou'].median():.3f}")

df.to_csv(os.path.join(ROOT, 'outputs/unet_eval.csv'), index=False)
print('\n已保存 outputs/unet_eval.csv', flush=True)

# ---- 验证集叠加可视化 ----
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

n = len(val_overlays)
fig, axes = plt.subplots(n, 4, figsize=(12, 3 * n))
if n == 1:
    axes = axes.reshape(1, -1)
for i, (sid, img, mask, pred, pred_bin, iou) in enumerate(val_overlays):
    axes[i, 0].imshow(img)
    axes[i, 0].set_title(f'{sid[:11]} IoU={iou:.2f}', fontsize=8)
    axes[i, 1].imshow(img)
    axes[i, 1].imshow(mask, alpha=0.4, cmap='Greens')
    axes[i, 1].set_title('GT mask', fontsize=8)
    axes[i, 2].imshow(pred, cmap='jet', vmin=0, vmax=1)
    axes[i, 2].set_title('pred prob', fontsize=8)
    axes[i, 3].imshow(img)
    a3 = df.loc[df['source_record_id'] == sid, 'iou_A3_block'].values[0]
    axes[i, 3].imshow(pred_bin, alpha=0.4, cmap='Reds')
    axes[i, 3].set_title(f'pred (A3={a3:.2f})', fontsize=8)
    for ax in axes[i]:
        ax.axis('off')
plt.tight_layout()
plt.savefig(os.path.join(ROOT, 'outputs/unet_overlay_val.png'), dpi=90, bbox_inches='tight')
print('已保存 outputs/unet_overlay_val.png', flush=True)
