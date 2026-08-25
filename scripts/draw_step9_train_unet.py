#!/usr/bin/env python3
"""
训练 U-Net 语义分割模型
输入: data/satellite/*.npz (image 256x256x3 + mask 256x256)
输出: outputs/unet_fence.pth + 评估 IoU vs 0.392 基线
"""

import os, json, glob, random, time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

EPOCHS = int(os.environ.get('EPOCHS', '50'))
BATCH = int(os.environ.get('BATCH', '8'))
BASE = int(os.environ.get('BASE', '32'))
THREADS = int(os.environ.get('OMP_NUM_THREADS', '4'))
torch.set_num_threads(THREADS)
print(f'config: EPOCHS={EPOCHS} BATCH={BATCH} BASE={BASE} threads={THREADS}', flush=True)

device = torch.device('cuda' if torch.cuda.is_available()
                      else ('mps' if torch.backends.mps.is_available() else 'cpu'))
print(f'device: {device}', flush=True)

# ========== Dataset ==========
class FenceDataset(Dataset):
    def __init__(self, npz_files, augment=False):
        self.files = npz_files
        self.augment = augment

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        data = np.load(self.files[idx])
        img = data['image'].astype(np.float32) / 255.0  # (256,256,3)
        mask = data['mask'].astype(np.float32)  # (256,256)

        # 标准化（用 ImageNet 均值/方差）
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std

        # 数据增强
        if self.augment and random.random() < 0.5:
            # 水平翻转
            img = np.flip(img, axis=1).copy()
            mask = np.flip(mask, axis=1).copy()
        if self.augment and random.random() < 0.5:
            # 垂直翻转
            img = np.flip(img, axis=0).copy()
            mask = np.flip(mask, axis=0).copy()
        if self.augment and random.random() < 0.5:
            # 90度旋转
            k = random.choice([1, 2, 3])
            img = np.rot90(img, k).copy()
            mask = np.rot90(mask, k).copy()

        img = torch.from_numpy(img.transpose(2, 0, 1))  # (3,256,256)
        mask = torch.from_numpy(mask).unsqueeze(0)  # (1,256,256)
        return img, mask

# ========== U-Net ==========
class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    def __init__(self, in_ch=3, out_ch=1, base=32):
        super().__init__()
        self.enc1 = DoubleConv(in_ch, base)
        self.enc2 = DoubleConv(base, base*2)
        self.enc3 = DoubleConv(base*2, base*4)
        self.enc4 = DoubleConv(base*4, base*8)
        self.center = DoubleConv(base*8, base*16)
        self.up4 = nn.ConvTranspose2d(base*16, base*8, 2, stride=2)
        self.dec4 = DoubleConv(base*16, base*8)
        self.up3 = nn.ConvTranspose2d(base*8, base*4, 2, stride=2)
        self.dec3 = DoubleConv(base*8, base*4)
        self.up2 = nn.ConvTranspose2d(base*4, base*2, 2, stride=2)
        self.dec2 = DoubleConv(base*4, base*2)
        self.up1 = nn.ConvTranspose2d(base*2, base, 2, stride=2)
        self.dec1 = DoubleConv(base*2, base)
        self.out_conv = nn.Conv2d(base, out_ch, 1)
        self.pool = nn.MaxPool2d(2)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        c = self.center(self.pool(e4))
        d4 = self.up4(c)
        d4 = self.dec4(torch.cat([d4, e4], dim=1))
        d3 = self.up3(d4)
        d3 = self.dec3(torch.cat([d3, e3], dim=1))
        d2 = self.up2(d3)
        d2 = self.dec2(torch.cat([d2, e2], dim=1))
        d1 = self.up1(d2)
        d1 = self.dec1(torch.cat([d1, e1], dim=1))
        return self.out_conv(d1)

# ========== 损失函数 ==========
class DiceLoss(nn.Module):
    def __init__(self, smooth=1.0):
        super().__init__()
        self.smooth = smooth
    def forward(self, pred, target):
        pred = torch.sigmoid(pred)
        intersection = (pred * target).sum()
        return 1 - (2 * intersection + self.smooth) / (pred.sum() + target.sum() + self.smooth)

class CombinedLoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.dice = DiceLoss()
    def forward(self, pred, target):
        return 0.5 * self.bce(pred, target) + 0.5 * self.dice(pred, target)

# ========== 评估 ==========
def compute_iou(pred_mask, true_mask, threshold=0.5):
    pred = (pred_mask > threshold).float()
    inter = (pred * true_mask).sum().item()
    union = pred.sum().item() + true_mask.sum().item() - inter
    if union < 1e-6:
        return 1.0 if true_mask.sum().item() < 1e-6 else 0.0
    return inter / union

# ========== 主训练流程 ==========
def main():
    files = sorted(glob.glob('data/satellite/*.npz'))
    print(f'样本数: {len(files)}', flush=True)

    random.shuffle(files)
    n_train = int(0.7 * len(files))
    train_files = files[:n_train]
    val_files = files[n_train:]
    print(f'训练: {len(train_files)}  验证: {len(val_files)}', flush=True)

    train_ds = FenceDataset(train_files, augment=True)
    val_ds = FenceDataset(val_files, augment=False)
    train_loader = DataLoader(train_ds, batch_size=BATCH, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH, shuffle=False, num_workers=0)

    model = UNet(base=BASE).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'模型参数: {n_params/1e6:.2f}M', flush=True)

    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = CombinedLoss()

    best_iou = 0
    history = []
    t_start = time.time()
    for epoch in range(EPOCHS):
        # 训练
        model.train()
        train_loss = 0
        for img, mask in train_loader:
            img, mask = img.to(device), mask.to(device)
            pred = model(img)
            loss = criterion(pred, mask)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * img.size(0)
        train_loss /= len(train_ds)
        scheduler.step()

        # 验证
        model.eval()
        val_ious = []
        val_loss = 0
        with torch.no_grad():
            for img, mask in val_loader:
                img, mask = img.to(device), mask.to(device)
                pred = model(img)
                val_loss += criterion(pred, mask).item() * img.size(0)
                for i in range(img.size(0)):
                    val_ious.append(compute_iou(torch.sigmoid(pred[i]), mask[i]))
        val_loss /= len(val_ds)
        val_iou_med = float(np.median(val_ious))
        val_iou_mean = float(np.mean(val_ious))

        history.append({
            'epoch': epoch+1, 'train_loss': train_loss, 'val_loss': val_loss,
            'val_iou_med': val_iou_med, 'val_iou_mean': val_iou_mean,
            'val_iou>0.5': float(np.mean([i > 0.5 for i in val_ious]))
        })

        iou_50 = history[-1]["val_iou>0.5"]
        if (epoch+1) % 5 == 0 or epoch == 0:
            print(f'Epoch {epoch+1:3d} [{time.time()-t_start:6.0f}s]: train_loss={train_loss:.4f} val_loss={val_loss:.4f} '
                  f'IoU med={val_iou_med:.3f} mean={val_iou_mean:.3f} >0.5={iou_50:.1%}', flush=True)

        if val_iou_med > best_iou:
            best_iou = val_iou_med
            torch.save(model.state_dict(), 'outputs/unet_fence_best.pth')

    print(f'\n最佳验证 IoU 中位: {best_iou:.3f}', flush=True)
    print(f'基线 A3: 0.392', flush=True)
    print(f'提升: {best_iou - 0.392:+.3f}', flush=True)

    with open('outputs/unet_history.json', 'w') as f:
        json.dump(history, f, indent=2)
    print('已保存 outputs/unet_history.json', flush=True)

if __name__ == '__main__':
    main()
