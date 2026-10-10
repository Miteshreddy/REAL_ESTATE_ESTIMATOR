"""Smoke-test the production door/window detector on the 20-image synthetic pack (labels audited first).

    python ml/evaluation/eval_synthetic_pack.py [pack_dir] [onnx_model]

SYNTHETIC schematic drawings — results are a pipeline smoke test, NOT real / Tamil Nadu accuracy.
Writes reports_v2/door_window_synthetic_pack/{label_validation.json, results.json, predictions/*.png}.
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
PACK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "synthetic_tn20", "TN_Door_Window_20_Synthetic_Samples")
OUT = os.path.join(ROOT, "reports_v2", "door_window_synthetic_pack")
NAMES = {0: "door", 1: "window"}
DOOR_M = 0.9  # assumed door-leaf width used to set ONE fixed scale for the whole pack


def read_labels(path, W, H):
    boxes, problems = [], []
    for n, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 5:
            problems.append(f"{os.path.basename(path)}:{n} expected 5 fields, got {len(parts)}")
            continue
        try:
            c, x, y, w, h = int(parts[0]), *map(float, parts[1:])
        except ValueError:
            problems.append(f"{os.path.basename(path)}:{n} non-numeric")
            continue
        if c not in NAMES:
            problems.append(f"{os.path.basename(path)}:{n} class {c} not in {list(NAMES)}")
        if not all(math.isfinite(v) for v in (x, y, w, h)) or not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
            problems.append(f"{os.path.basename(path)}:{n} box outside [0,1] or non-positive size")
        if x - w / 2 < -1e-6 or x + w / 2 > 1 + 1e-6 or y - h / 2 < -1e-6 or y + h / 2 > 1 + 1e-6:
            problems.append(f"{os.path.basename(path)}:{n} box extends beyond the image")
        boxes.append(dict(kind=NAMES.get(c, "?"), x0=(x - w / 2) * W, y0=(y - h / 2) * H, x1=(x + w / 2) * W, y1=(y + h / 2) * H))
    return boxes, problems


def iou(a, b):
    ix = max(0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    iy = max(0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
    inter = ix * iy
    u = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]) + (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]) - inter
    return inter / u if u > 0 else 0.0


def contains(g, p, pad=8):
    """Convention-neutral match: predicted box centre lies inside the labelled box (± pad px)."""
    cx, cy = (p["x0"] + p["x1"]) / 2, (p["y0"] + p["y1"]) / 2
    return g["x0"] - pad <= cx <= g["x1"] + pad and g["y0"] - pad <= cy <= g["y1"] + pad


def match(gt, pred, thr):
    tp, used = 0, set()
    for p in sorted(pred, key=lambda d: -d["score"]):
        best, bj = 0.0, None
        for j, g in enumerate(gt):
            if j not in used and g["kind"] == p["kind"]:
                v = (1.0 if contains(g, p) else 0.0) if thr == "centre" else iou(p, g)
                if v > best:
                    best, bj = v, j
        if bj is not None and best >= (0.5 if thr == "centre" else thr):
            used.add(bj)
            tp += 1
    return tp


def prf(tp, pred, gt):
    npred, ngt = pred, gt
    p = tp / npred if npred else 0.0
    r = tp / ngt if ngt else 0.0
    return dict(tp=tp, pred=npred, gt=ngt, precision=round(p, 4), recall=round(r, 4), f1=round(2 * p * r / (p + r), 4) if p + r else 0.0)


def main():
    import detector
    if len(sys.argv) > 2:
        detector.MODEL = sys.argv[2]
        detector._sess = None
    os.makedirs(os.path.join(OUT, "predictions"), exist_ok=True)
    imgs = sorted(glob.glob(os.path.join(PACK, "images", "*", "*.png")))
    data, problems = [], []
    for ip in imgs:
        split = os.path.basename(os.path.dirname(ip))
        lp = os.path.join(PACK, "labels", split, os.path.splitext(os.path.basename(ip))[0] + ".txt")
        img = cv2.imread(ip)
        H, W = img.shape[:2]
        gt, pr = read_labels(lp, W, H) if os.path.exists(lp) else ([], [f"missing label for {ip}"])
        problems += pr
        data.append(dict(path=ip, split=split, img=img, gt=gt))
    door_px = statistics.median(max(g["x1"] - g["x0"], g["y1"] - g["y0"]) for d in data for g in d["gt"] if g["kind"] == "door")
    ppm = door_px / DOOR_M
    json.dump(dict(images=len(imgs), problems=problems, ok=not problems, class_map_pack=NAMES,
                   class_map_production=dict(enumerate(detector.NAMES)),
                   class_map_compatible=list(NAMES.values()) == list(detector.NAMES)),
              open(os.path.join(OUT, "label_validation.json"), "w"), indent=1)
    res = {}
    for thr in (0.5, 0.3, "centre"):
        tot = {k: dict(tp=0, pred=0, gt=0) for k in ("door", "window")}
        per = []
        for d in data:
            dets = detector.detect(d["img"], ppm, conf=0.35)
            pred = [dict(kind=x["kind"], score=x["score"], x0=x["x_px"] - x["w_px"] / 2, x1=x["x_px"] + x["w_px"] / 2,
                         y0=x["y_px"] - x["h_px"] / 2, y1=x["y_px"] + x["h_px"] / 2) for x in dets]
            row = dict(image=os.path.basename(d["path"]), split=d["split"])
            for k in ("door", "window"):
                g = [b for b in d["gt"] if b["kind"] == k]
                p = [b for b in pred if b["kind"] == k]
                tp = match(g, p, thr)
                tot[k]["tp"] += tp
                tot[k]["pred"] += len(p)
                tot[k]["gt"] += len(g)
                row[k] = dict(gt=len(g), pred=len(p), tp=tp)
            per.append(row)
            if thr == "centre":
                vis = d["img"].copy()
                for b in d["gt"]:
                    cv2.rectangle(vis, (int(b["x0"]), int(b["y0"])), (int(b["x1"]), int(b["y1"])), (160, 160, 160), 1)
                for b in pred:
                    col = (0, 150, 0) if b["kind"] == "door" else (200, 90, 0)
                    cv2.rectangle(vis, (int(b["x0"]), int(b["y0"])), (int(b["x1"]), int(b["y1"])), col, 2)
                cv2.imwrite(os.path.join(OUT, "predictions", os.path.basename(d["path"])), vis)
        res[f"iou_{thr}"] = dict(door=prf(**tot["door"]), window=prf(**tot["window"]), per_image=per)
    out = dict(model=detector.MODEL, assumed_scale=dict(px_per_m=round(ppm, 2), basis=f"median door box {door_px:.1f} px / {DOOR_M} m"),
               conf=0.35, warning="SYNTHETIC schematic pack (20 images, one generator). Smoke test only — not real or Tamil Nadu accuracy.",
               **res)
    json.dump(out, open(os.path.join(OUT, "results.json"), "w"), indent=1)
    for k, v in res.items():
        print(k, "door", v["door"], "window", v["window"])


if __name__ == "__main__":
    main()
