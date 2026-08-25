#!/usr/bin/env python3
"""
Scalable U-Net Training on 7k Satellite Fence Dataset with In-Memory RAM Caching,
Vectorized GPU-Accelerated Validation & MPS Execution.
"""

from __future__ import annotations

import os
import sys
import json
import glob
import random
import time
from typing import Tuple, List

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)

EPOCHS = int(os.environ.get("EPOCHS", "20"))
BATCH_SIZE = int(os.environ.get("BATCH", "32"))
BASE_CHANNELS = int(os.environ.get("BASE", "32"))
LR = float(os.environ.get("LR", "1e-3"))

device = torch.device(
    "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
)
print(f"[train] Device: {device} | Epochs: {EPOCHS} | Batch: {BATCH_SIZE} | Base: {BASE_CHANNELS}", flush=True)


# ========== In-Memory Fast Dataset ==========
class FastFenceDataset(Dataset):
    def __init__(self, npz_files: List[str], augment: bool = False):
        self.augment = augment
        print(f"[dataset] Preloading {len(npz_files)} samples into RAM for zero-disk-IO GPU training...", flush=True)
        t0 = time.time()
        self.images = []
        self.masks = []
        for f in npz_files:
            try:
                with np.load(f) as d:
                    self.images.append(d["image"])  # uint8 (256, 256, 3)
                    self.masks.append(d["mask"])    # uint8 (256, 256)
            except Exception:
                pass
        self.images = np.stack(self.images, axis=0)  # (N, 256, 256, 3) uint8
        self.masks = np.stack(self.masks, axis=0)    # (N, 256, 256) uint8
        ram_mb = (self.images.nbytes + self.masks.nbytes) / (1024 * 1024)
        print(f"[dataset] Preloaded {len(self.images)} samples in {time.time()-t0:.1f}s ({ram_mb:.1f} MB RAM)", flush=True)

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        img = self.images[idx].astype(np.float32) / 255.0
        mask = self.masks[idx].astype(np.float32)

        if self.augment:
            if random.random() > 0.5:
                img = np.fliplr(img).copy()
                mask = np.fliplr(mask).copy()
            if random.random() > 0.5:
                img = np.flipud(img).copy()
                mask = np.flipud(mask).copy()
            k = random.randint(0, 3)
            if k > 0:
                img = np.rot90(img, k).copy()
                mask = np.rot90(mask, k).copy()

        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std

        img_t = torch.from_numpy(img.transpose(2, 0, 1))
        mask_t = torch.from_numpy(mask).unsqueeze(0)
        return img_t, mask_t


# ========== U-Net Architecture ==========
class DoubleConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UNet(nn.Module):
    def __init__(self, in_ch: int = 3, out_ch: int = 1, base: int = 32):
        super().__init__()
        self.inc = DoubleConv(in_ch, base)
        self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(base, base * 2))
        self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(base * 2, base * 4))
        self.down3 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(base * 4, base * 8))
        self.down4 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(base * 8, base * 8))

        self.up1 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.conv1 = DoubleConv(base * 8 + base * 4, base * 4)

        self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.conv2 = DoubleConv(base * 4 + base * 2, base * 2)

        self.up3 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.conv3 = DoubleConv(base * 2 + base, base)

        self.up4 = nn.ConvTranspose2d(base, base, 2, stride=2)
        self.conv4 = DoubleConv(base * 2, base)

        self.out_conv = nn.Conv2d(base, out_ch, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        d1 = self.up1(x5)
        d1 = torch.cat([d1, x4], dim=1)
        d1 = self.conv1(d1)

        d2 = self.up2(d1)
        d2 = torch.cat([d2, x3], dim=1)
        d2 = self.conv2(d2)

        d3 = self.up3(d2)
        d3 = torch.cat([d3, x2], dim=1)
        d3 = self.conv3(d3)

        d4 = self.up4(d3)
        d4 = torch.cat([d4, x1], dim=1)
        d4 = self.conv4(d4)
        return self.out_conv(d4)


# ========== Loss Function ==========
class SoftDiceLoss(nn.Module):
    def __init__(self, smooth: float = 1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = torch.sigmoid(logits)
        num = 2 * (probs * targets).sum(dim=(2, 3)) + self.smooth
        den = probs.sum(dim=(2, 3)) + targets.sum(dim=(2, 3)) + self.smooth
        return 1.0 - (num / den).mean()


class CombinedLoss(nn.Module):
    def __init__(self):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.dice = SoftDiceLoss()

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return 0.5 * self.bce(logits, targets) + 0.5 * self.dice(logits, targets)


def compute_batch_iou_tensor(logits: torch.Tensor, targets: torch.Tensor, threshold: float = 0.5) -> torch.Tensor:
    preds = (torch.sigmoid(logits) > threshold).float()
    inter = (preds * targets).sum(dim=(1, 2, 3))
    union = preds.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3)) - inter
    iou = torch.where(union == 0, torch.ones_like(union), inter / (union + 1e-6))
    return iou.detach().cpu()


# ========== Main Training Function ==========
def main():
    sat_dir = os.path.join(PROJECT_ROOT, "data", "satellite")
    all_files = sorted(glob.glob(os.path.join(sat_dir, "*.npz")))
    if len(all_files) < 100:
        print(f"Not enough satellite patches in {sat_dir}: {len(all_files)}", flush=True)
        return 1

    print(f"[train] Total available satellite patches: {len(all_files)}", flush=True)

    rng = random.Random(42)
    shuffled = list(all_files)
    rng.shuffle(shuffled)
    n_train = int(len(shuffled) * 0.8)
    train_files = shuffled[:n_train]
    val_files = shuffled[n_train:]
    print(f"[train] Dataset Split -> Train: {len(train_files)} | Val: {len(val_files)}", flush=True)

    train_ds = FastFenceDataset(train_files, augment=True)
    val_ds = FastFenceDataset(val_files, augment=False)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    model = UNet(in_ch=3, out_ch=1, base=BASE_CHANNELS).to(device)
    criterion = CombinedLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-5)

    best_val_iou = 0.0
    history = []
    out_pth = os.path.join(PROJECT_ROOT, "outputs", "unet_fence_7k_best.pth")
    out_hist = os.path.join(PROJECT_ROOT, "outputs", "unet_7k_history.json")

    print("\n=== Starting Fast In-Memory U-Net Training on 7k Dataset ===", flush=True)
    t_start = time.time()

    for epoch in range(1, EPOCHS + 1):
        t_ep = time.time()
        model.train()
        train_loss = 0.0
        train_batches = 0

        for imgs, masks in train_loader:
            imgs = imgs.to(device)
            masks = masks.to(device)

            optimizer.zero_grad()
            logits = model(imgs)
            loss = criterion(logits, masks)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            train_batches += 1

        scheduler.step()
        train_loss /= max(train_batches, 1)

        # Vectorized Fast GPU Validation
        model.eval()
        val_loss = 0.0
        val_batches = 0
        all_val_ious = []

        with torch.no_grad():
            for imgs, masks in val_loader:
                imgs = imgs.to(device)
                masks = masks.to(device)
                logits = model(imgs)
                loss = criterion(logits, masks)
                val_loss += loss.item()
                val_batches += 1

                ious_t = compute_batch_iou_tensor(logits, masks)
                all_val_ious.append(ious_t)

        val_loss /= max(val_batches, 1)
        val_ious_np = torch.cat(all_val_ious, dim=0).numpy()
        val_iou_mean = float(np.mean(val_ious_np))
        val_iou_med = float(np.median(val_ious_np))
        val_iou_gt50 = float(np.mean(val_ious_np > 0.50) * 100.0)
        val_iou_gt70 = float(np.mean(val_ious_np > 0.70) * 100.0)

        ep_time = time.time() - t_ep
        print(
            f"Epoch {epoch:02d}/{EPOCHS:02d} [{ep_time:.1f}s] | "
            f"TrainLoss: {train_loss:.4f} | ValLoss: {val_loss:.4f} | "
            f"ValIoU_Med: {val_iou_med:.4f} | ValIoU_Mean: {val_iou_mean:.4f} | "
            f">0.5: {val_iou_gt50:.1f}% | >0.7: {val_iou_gt70:.1f}%",
            flush=True,
        )

        record = {
            "epoch": epoch,
            "train_loss": round(train_loss, 4),
            "val_loss": round(val_loss, 4),
            "val_iou_med": round(val_iou_med, 4),
            "val_iou_mean": round(val_iou_mean, 4),
            "val_gt50_pct": round(val_iou_gt50, 2),
            "val_gt70_pct": round(val_iou_gt70, 2),
            "lr": round(scheduler.get_last_lr()[0], 6),
            "epoch_sec": round(ep_time, 2),
        }
        history.append(record)

        if val_iou_med > best_val_iou:
            best_val_iou = val_iou_med
            torch.save(model.state_dict(), out_pth)
            print(f"  --> Saved new best model to {out_pth} (ValIoU_Med={best_val_iou:.4f})", flush=True)

    total_time = time.time() - t_start
    print(f"\n[train] Training completed in {total_time/60:.1f} min! Peak ValIoU_Med: {best_val_iou:.4f}", flush=True)

    with open(out_hist, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"[train] Training history saved to: {out_hist}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
