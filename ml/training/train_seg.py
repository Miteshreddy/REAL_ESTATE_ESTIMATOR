"""Train the floor-plan segmentation model (wall / room / door / window) on CubiCasa5K.

U-Net with an ImageNet-pretrained ResNet-34 encoder, mixed precision, CE + Dice loss.
Heavy augmentation simulates B/W prints, scans and photocopies so the model generalises to
Indian PWD drawings, not only CubiCasa's style.
"""
import argparse
import glob
import json
import math
import os
import random
import time

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

import segmentation_models_pytorch as smp

DATA = r"G:\velo\real-estate\prepared"
OUT = r"G:\velo\real-estate\runs"
NC = 5
CLASSES = ["background", "wall", "room", "door", "window"]


# ----------------------------------------------------------------------------- augmentation
def degrade(img):
    """Make a clean plan look like a print / scan / photocopy."""
    r = random.random
    if r() < 0.5:
        a, b = random.uniform(0.7, 1.3), random.uniform(-40, 40)
        img = np.clip(img.astype(np.float32) * a + b, 0, 255).astype(np.uint8)
    if r() < 0.35:
        t = random.randint(150, 230)
        img = np.where(img < t, 0, 255).astype(np.uint8)
    if r() < 0.3:
        k = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (k, k), 0)
    if r() < 0.3:
        img = np.clip(img.astype(np.float32) + np.random.normal(0, random.uniform(3, 15), img.shape), 0, 255).astype(np.uint8)
    if r() < 0.3:
        q = random.randint(25, 80)
        img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_GRAYSCALE)
    if r() < 0.15:  # thin all ink lines (light scans)
        img = cv2.dilate(img, np.ones((2, 2), np.uint8))
    if r() < 0.15:  # thicken lines (heavy prints)
        img = cv2.erode(img, np.ones((2, 2), np.uint8))
    return img


WORDS = ["PLAN", "SCHEDULE OF JOINERY", "TYPE", "WIDTH", "HEIGHT", "SILL", "REMARKS", "STEEL DOOR", "R.C.C", "NOTES",
         "ALL DIMENSIONS ARE IN MM", "PLINTH AREA", "SQ.M", "DRAWING NO", "SCALE 1:100", "APPROVED", "CHECKED", "D1", "W2",
         "V1", "900", "2100", "1200", "1500", "BRICK WORK IN CM 1:6", "PCC 1:4:8", "EXECUTIVE ENGINEER", "SECTION A-A", "ELEVATION"]


def _rand_text(rng=random):
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 4)))


def distractors(img, m, n=None):
    """Paint sheet furniture that real drawings carry - schedule tables, notes, title blocks, dimension
    lines, hatching, frames - onto background areas, labelled as background (0)."""
    H, W = img.shape
    out = img.copy()
    want = n if n is not None else random.randint(1, 4)
    placed = 0
    for _ in range(want * 8):
        if placed >= want:
            break
        kind = random.choice(["table", "notes", "title", "dims", "hatch", "frame", "table", "notes"])
        w, h = random.randint(W // 8, max(W // 8 + 1, W // 3)), random.randint(H // 10, max(H // 10 + 1, H // 3))
        x, y = random.randint(0, max(0, W - w)), random.randint(0, max(0, H - h))
        if (m[y:y + h, x:x + w] > 0).mean() > 0.05:
            continue  # only on empty background
        patch = np.full((h, w), 255, np.uint8)
        th = random.choice([1, 1, 2])
        fs = random.uniform(0.3, 0.7)
        if kind in ("table", "title"):
            rows, cols = random.randint(3, 12), random.randint(2, 7)
            ys = np.linspace(0, h - 1, rows + 1).astype(int)
            xs = np.sort(np.random.choice(np.arange(1, w - 1), cols - 1, replace=False)) if w > cols + 2 else []
            for yy in ys:
                cv2.line(patch, (0, yy), (w - 1, yy), 0, th)
            for xx in [0, w - 1] + list(xs):
                cv2.line(patch, (int(xx), 0), (int(xx), h - 1), 0, th)
            for yy in ys[:-1]:
                for xx in [0] + list(xs):
                    if random.random() < 0.7:
                        cv2.putText(patch, _rand_text()[:12], (int(xx) + 3, int(yy) + max(10, int((ys[1] - ys[0]) * 0.7))), cv2.FONT_HERSHEY_SIMPLEX, fs, 0, 1)
        elif kind == "notes":
            for i in range(random.randint(3, 15)):
                cv2.putText(patch, f"{i + 1}. " + _rand_text() + " " + _rand_text(), (4, 14 + i * int(18 * fs + 8)), cv2.FONT_HERSHEY_SIMPLEX, fs, 0, 1)
        elif kind == "dims":
            for i in range(random.randint(1, 4)):
                yy = random.randint(5, h - 5)
                cv2.line(patch, (0, yy), (w - 1, yy), 0, 1)
                for xx in np.sort(np.random.randint(0, w, random.randint(2, 5))):
                    cv2.line(patch, (int(xx), yy - 6), (int(xx), yy + 6), 0, 1)
                    cv2.putText(patch, str(random.choice([230, 900, 1200, 2570, 3050, 11610])), (int(xx) + 4, yy - 4), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.8, 0, 1)
        elif kind == "hatch":
            for d in range(-h, w, random.randint(5, 12)):
                cv2.line(patch, (d, h), (d + h, 0), 0, 1)
        else:  # frame
            cv2.rectangle(patch, (2, 2), (w - 3, h - 3), 0, random.choice([1, 2, 3]))
        if random.random() < 0.4:
            patch = np.ascontiguousarray(np.rot90(patch, random.choice([1, 3])))
            ph_, pw_ = patch.shape
            if y + ph_ > H or x + pw_ > W or (m[y:y + ph_, x:x + pw_] > 0).mean() > 0.05:
                continue
            h, w = ph_, pw_
        out[y:y + h, x:x + w] = np.minimum(out[y:y + h, x:x + w], patch)
        placed += 1
    return out


def compose_sheet(img, m):
    """Shrink the plan onto a larger page surrounded by sheet furniture (teaches plan localisation)."""
    H, W = img.shape
    k = random.uniform(0.45, 0.8)
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    sm = cv2.resize(m, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
    page = np.full((H, W), 255, np.uint8)
    pm = np.zeros((H, W), np.uint8)
    y, x = random.randint(0, H - small.shape[0]), random.randint(0, W - small.shape[1])
    page[y:y + small.shape[0], x:x + small.shape[1]] = small
    pm[y:y + small.shape[0], x:x + small.shape[1]] = sm
    return distractors(page, pm, random.randint(2, 6)), pm


class PlanSet(Dataset):
    def __init__(self, split, crop=512, train=True, repeat=1):
        self.files = sorted(glob.glob(os.path.join(DATA, split, "img", "*.png"))) * repeat
        self.crop, self.train = crop, train

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        f = self.files[i]
        img = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        m = cv2.imread(f.replace(os.sep + "img" + os.sep, os.sep + "mask" + os.sep), cv2.IMREAD_GRAYSCALE)
        if self.train:
            if random.random() < 0.25:
                img, m = compose_sheet(img, m)
            elif random.random() < 0.5:
                img = distractors(img, m)
            s = random.uniform(0.45, 1.25)
            img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
            m = cv2.resize(m, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
            if random.random() < 0.15:  # small rotation (skewed scans)
                ang = random.uniform(-4, 4)
                M = cv2.getRotationMatrix2D((img.shape[1] / 2, img.shape[0] / 2), ang, 1)
                img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderValue=255)
                m = cv2.warpAffine(m, M, (m.shape[1], m.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)
            c = self.crop
            ph, pw = max(0, c - img.shape[0]), max(0, c - img.shape[1])
            if ph or pw:
                img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=255)
                m = cv2.copyMakeBorder(m, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=0)
            # prefer crops containing walls
            for _ in range(6):
                y, x = random.randint(0, img.shape[0] - c), random.randint(0, img.shape[1] - c)
                mc = m[y:y + c, x:x + c]
                if (mc == 1).mean() > 0.01:
                    break
            img, m = img[y:y + c, x:x + c], m[y:y + c, x:x + c]
            k = random.randint(0, 3)
            img, m = np.rot90(img, k), np.rot90(m, k)
            if random.random() < 0.5:
                img, m = img[:, ::-1], m[:, ::-1]
            img = degrade(np.ascontiguousarray(img))
            m = np.ascontiguousarray(m)
        else:
            H, W = img.shape
            ph, pw = (32 - H % 32) % 32, (32 - W % 32) % 32
            img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=255)
            m = cv2.copyMakeBorder(m, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=255)  # 255 = ignore
        x = torch.from_numpy(img).float().div(255).unsqueeze(0)
        return x, torch.from_numpy(m.astype(np.int64))


# ----------------------------------------------------------------------------- model / loss
def make_model():
    return smp.Unet("resnet34", encoder_weights="imagenet", in_channels=1, classes=NC)


def dice_loss(logits, y, eps=1.0):
    valid = (y != 255).unsqueeze(1)
    yy = y.clone()
    yy[yy == 255] = 0
    p = logits.softmax(1) * valid
    oh = F.one_hot(yy, NC).permute(0, 3, 1, 2).float() * valid
    inter = (p * oh).sum((0, 2, 3))
    den = p.sum((0, 2, 3)) + oh.sum((0, 2, 3))
    return 1 - ((2 * inter + eps) / (den + eps))[1:].mean()


# ----------------------------------------------------------------------------- evaluation
@torch.no_grad()
def confusion(model, loader, dev, limit=None):
    model.eval()
    cm = torch.zeros(NC, NC, dtype=torch.long, device=dev)
    for i, (x, y) in enumerate(loader):
        if limit and i >= limit:
            break
        x, y = x.to(dev), y.to(dev)
        with torch.autocast("cuda", dtype=torch.float16):
            p = model(x).argmax(1)
        v = y != 255
        cm += torch.bincount(y[v] * NC + p[v], minlength=NC * NC).view(NC, NC)
    return cm.cpu().numpy()


def scores(cm):
    tp = np.diag(cm).astype(float)
    iou = tp / np.maximum(1, cm.sum(0) + cm.sum(1) - tp)
    prec = tp / np.maximum(1, cm.sum(0))
    rec = tp / np.maximum(1, cm.sum(1))
    f1 = 2 * prec * rec / np.maximum(1e-9, prec + rec)
    return dict(pixel_acc=float(tp.sum() / cm.sum()), miou=float(iou.mean()), miou_fg=float(iou[1:].mean()),
                iou={c: float(v) for c, v in zip(CLASSES, iou)}, precision={c: float(v) for c, v in zip(CLASSES, prec)},
                recall={c: float(v) for c, v in zip(CLASSES, rec)}, f1={c: float(v) for c, v in zip(CLASSES, f1)})


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=4e-4)
    ap.add_argument("--crop", type=int, default=512)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--name", default="unet_r34")
    ap.add_argument("--init", default="")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--val_limit", type=int, default=0)
    a = ap.parse_args()
    torch.backends.cudnn.benchmark = True
    dev = "cuda"
    run = os.path.join(OUT, a.name)
    os.makedirs(run, exist_ok=True)
    tr = DataLoader(PlanSet("train", a.crop, True, repeat=a.repeat), batch_size=a.bs, shuffle=True, num_workers=a.workers,
                    pin_memory=True, drop_last=True, persistent_workers=True)
    va = DataLoader(PlanSet("val", train=False), batch_size=1, num_workers=4)
    model = make_model().to(dev).to(memory_format=torch.channels_last)
    if a.init and os.path.exists(a.init):
        model.load_state_dict(torch.load(a.init, map_location=dev))
        print("initialised from", a.init, flush=True)
    # class weights against the heavy room/background imbalance
    w = torch.tensor([0.5, 2.0, 0.6, 4.0, 3.5], device=dev)
    ce = nn.CrossEntropyLoss(weight=w, ignore_index=255)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    steps = a.epochs * len(tr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.05)
    scaler = torch.amp.GradScaler()
    best, hist = -1, []
    for ep in range(a.epochs):
        model.train()
        t0, tot = time.time(), 0.0
        for x, y in tr:
            x, y = x.to(dev, non_blocking=True).to(memory_format=torch.channels_last), y.to(dev, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.float16):
                out = model(x)
                loss = ce(out, y) + dice_loss(out.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item()
            step_i = getattr(main, "_s", 0) + 1
            main._s = step_i
            if step_i % 100 == 0:
                print(json.dumps(dict(step=step_i, epoch=ep + 1, loss=round(loss.item(), 4), it_per_s=round(100 / (time.time() - getattr(main, "_t", t0)), 2),
                                      mem_gb=round(torch.cuda.max_memory_allocated() / 2**30, 2))), flush=True)
                main._t = time.time()
        s = scores(confusion(model, va, dev, limit=a.val_limit or None))
        hist.append(dict(epoch=ep + 1, loss=tot / len(tr), val_miou_fg=s["miou_fg"], val_iou=s["iou"], sec=round(time.time() - t0)))
        print(json.dumps(hist[-1]), flush=True)
        if s["miou_fg"] > best:
            best = s["miou_fg"]
            torch.save(model.state_dict(), os.path.join(run, "best.pt"))
        torch.save(model.state_dict(), os.path.join(run, "last.pt"))
        json.dump(hist, open(os.path.join(run, "history.json"), "w"), indent=1)
    print("BEST val mIoU (fg)", best, flush=True)


if __name__ == "__main__":
    main()
