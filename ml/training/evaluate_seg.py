"""Evaluate a trained segmentation model on a held-out split (default: the 399 official TEST plans).

Reports pixel metrics (IoU / precision / recall / F1 per class) and object-level metrics that matter
for estimation: room instances (IoU >= 0.5), door and window detection (overlap match), wall IoU.
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np
import torch

from train_seg import CLASSES, NC, PlanSet, make_model, scores


def components(mask):
    n, lab, st, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=4)
    return [(lab == i) for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 30]


def match(gt, pr, thr):
    """Greedy one-to-one matching of instances by IoU."""
    used, tp = set(), 0
    for g in gt:
        best, bj = 0, -1
        ys, xs = np.nonzero(g)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        for j, p in enumerate(pr):
            if j in used or not p[y0:y1, x0:x1].any():
                continue
            inter = (g & p).sum()
            iou = inter / (g | p).sum()
            if iou > best:
                best, bj = iou, j
        if best >= thr:
            used.add(bj)
            tp += 1
    return tp, len(gt), len(pr)


def prf(tp, ng, npred):
    p, r = tp / max(1, npred), tp / max(1, ng)
    return dict(precision=round(p, 4), recall=round(r, 4), f1=round(2 * p * r / max(1e-9, p + r), 4), gt=ng, pred=npred)


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=r"G:\velo\real-estate\runs\unet_r34\best.pt")
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    dev = "cuda"
    model = make_model().to(dev)
    model.load_state_dict(torch.load(a.weights, map_location=dev))
    model.eval()
    ds = PlanSet(a.split, train=False)
    cm = np.zeros((NC, NC), np.int64)
    agg = {k: [0, 0, 0] for k in ("room", "door", "window")}
    for i in range(len(ds)):
        x, y = ds[i]
        with torch.autocast("cuda", dtype=torch.float16):
            p = model(x[None].to(dev)).argmax(1)[0].cpu().numpy()
        y = y.numpy()
        v = y != 255
        cm += np.bincount(y[v] * NC + p[v], minlength=NC * NC).reshape(NC, NC)
        for cls, name, thr in ((2, "room", 0.5), (3, "door", 0.3), (4, "window", 0.3)):
            t = match(components((y == cls) & v), components((p == cls) & v), thr)
            for k in range(3):
                agg[name][k] += t[k]
    res = scores(cm)
    res["objects"] = {k: prf(*v) for k, v in agg.items()}
    res["split"], res["images"] = a.split, len(ds)
    print(json.dumps(res, indent=1))
    out = os.path.join(os.path.dirname(a.weights), f"metrics_{a.split}.json")
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
