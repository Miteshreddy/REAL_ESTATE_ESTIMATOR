"""Door / window detector evaluation with one-to-one, class-aware matching (run with the training env python).

    <trainenv python> ml/evaluation/eval_door_window.py <out.json> <model.pt> <dataset: cubicasa_val | synthetic_corrected> [name]

Matching rule (per image, per class): predictions sorted by confidence; each prediction is matched to the unmatched
ground-truth box of the SAME class with the highest IoU, if that IoU ≥ threshold (greedy, COCO-style). Every GT and
every prediction is used at most once. Predictions whose best overlap is with an IGNORE region (ambiguous labels;
IoA ≥ 0.5) are discarded — neither TP nor FP; ignore regions are never counted as FN.

* Operating point: confidence ≥ 0.35 (the app's threshold), IoU ≥ 0.5 → TP / FP / FN, precision, recall, F1.
* AP: all predictions (conf ≥ 0.001), 101-point interpolated AP at IoU 0.50 (mAP50) and averaged over IoU 0.50:0.05:0.95
  (mAP50-95); mAP = mean over the two classes.
* Diagnostic (NOT F1): centre-hit rate = share of GT boxes containing the centre of some same-class prediction.

Preprocessing is identical for every model: cubicasa_val images are used as-is at imgsz 1024 (training scale);
synthetic images are resampled to the app's 38 px/m using ONE fixed pack scale and tiled 1024 px with 160 px overlap,
exactly like backend/detector.py. NMS IoU 0.45 per class (as the app).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import statistics
import sys
from datetime import datetime, timezone

import cv2
import numpy as np
import torch
import torchvision
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CUBI = "G:/velo/real-estate/prepared_det"
SYN = os.path.join(ROOT, "data", "synthetic_tn20_corrected")
CLASSES = ("door", "window")
CONF_OP, CONF_AP, IOU_OP, NMS_IOU = 0.35, 0.001, 0.5, 0.45
TARGET_PPM, TILE, OVER, DOOR_M = 38.0, 1024, 160, 0.9


def load_boxes(path, W, H):
    out = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.strip():
                c, x, y, w, h = map(float, line.split())
                out.append((int(c), (x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H))
    return out


def iou_mat(a, b):
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    a, b = np.asarray(a, float), np.asarray(b, float)
    ix = np.clip(np.minimum(a[:, None, 2], b[None, :, 2]) - np.maximum(a[:, None, 0], b[None, :, 0]), 0, None)
    iy = np.clip(np.minimum(a[:, None, 3], b[None, :, 3]) - np.maximum(a[:, None, 1], b[None, :, 1]), 0, None)
    inter = ix * iy
    area = lambda x: (x[:, 2] - x[:, 0]) * (x[:, 3] - x[:, 1])
    return inter / (area(a)[:, None] + area(b)[None, :] - inter + 1e-9)


def ioa(pred, ign):
    """intersection / prediction area."""
    if not len(pred) or not len(ign):
        return np.zeros((len(pred), len(ign)))
    p, g = np.asarray(pred, float), np.asarray(ign, float)
    ix = np.clip(np.minimum(p[:, None, 2], g[None, :, 2]) - np.maximum(p[:, None, 0], g[None, :, 0]), 0, None)
    iy = np.clip(np.minimum(p[:, None, 3], g[None, :, 3]) - np.maximum(p[:, None, 1], g[None, :, 1]), 0, None)
    return ix * iy / ((p[:, 2] - p[:, 0]) * (p[:, 3] - p[:, 1]) + 1e-9)[:, None]


def predict(model, img, scale=None):
    """[(cls, x0, y0, x1, y1, score)] in input pixels. scale=None → whole image at imgsz 1024; else resample + tile."""
    if scale is None:
        r = model.predict(img, imgsz=1024, conf=CONF_AP, iou=0.7, verbose=False, max_det=1000)[0]
        b = r.boxes
        return [(int(c), *map(float, xy), float(s)) for c, xy, s in zip(b.cls.tolist(), b.xyxy.tolist(), b.conf.tolist())]
    k = scale
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    H, W = small.shape[:2]
    out, step = [], TILE - OVER
    for y0 in range(0, max(1, H - OVER), step):
        for x0 in range(0, max(1, W - OVER), step):
            tile = np.full((TILE, TILE, 3), 255, np.uint8)
            crop = small[y0:y0 + TILE, x0:x0 + TILE]
            tile[:crop.shape[0], :crop.shape[1]] = crop
            r = model.predict(tile, imgsz=TILE, conf=CONF_AP, iou=0.7, verbose=False, max_det=1000)[0]
            for c, (a, b, cc, d), s in zip(r.boxes.cls.tolist(), r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
                if (a + cc) / 2 > crop.shape[1] or (b + d) / 2 > crop.shape[0]:
                    continue
                out.append((int(c), (x0 + a) / k, (y0 + b) / k, (x0 + cc) / k, (y0 + d) / k, s))
    keep = []
    for c in (0, 1):  # per-class NMS across tiles, as the app
        P = [p for p in out if p[0] == c]
        if P:
            idx = torchvision.ops.nms(torch.tensor([p[1:5] for p in P]), torch.tensor([p[5] for p in P]), NMS_IOU)
            keep += [P[i] for i in idx.tolist()]
    return keep


def match(gt, pred, ign, thr):
    """One-to-one greedy matching for ONE class. Returns (tp flags per kept prediction, scores, n_gt)."""
    pred = sorted(pred, key=lambda p: -p[4])
    P = [p[:4] for p in pred]
    if ign:
        a = ioa(P, ign)
        keep = [i for i in range(len(P)) if not (a.shape[1] and a[i].max() >= 0.5 and (not gt or iou_mat([P[i]], gt).max() < thr))]
        pred, P = [pred[i] for i in keep], [P[i] for i in keep]
    M = iou_mat(P, gt)
    used, flags = set(), []
    for i in range(len(P)):
        j = int(np.argmax(np.where([k not in used for k in range(len(gt))], M[i], -1))) if len(gt) else -1
        if j >= 0 and M[i, j] >= thr and j not in used:
            used.add(j)
            flags.append(1)
        else:
            flags.append(0)
    return flags, [p[4] for p in pred], len(gt)


def ap101(flags, scores, n_gt):
    if n_gt == 0:
        return float("nan")
    o = np.argsort(-np.asarray(scores))
    f = np.asarray(flags)[o] if len(flags) else np.zeros(0)
    tp, fp = np.cumsum(f), np.cumsum(1 - f)
    rec = tp / n_gt
    prec = tp / np.maximum(tp + fp, 1e-9)
    prec = np.maximum.accumulate(prec[::-1])[::-1] if len(prec) else prec
    return float(np.mean([prec[rec >= t].max() if np.any(rec >= t) else 0.0 for t in np.linspace(0, 1, 101)]))


def dataset(name):
    items = []
    if name == "cubicasa_val":
        for ip in sorted(glob.glob(os.path.join(CUBI, "images", "val", "*"))):
            im = cv2.imread(ip)
            H, W = im.shape[:2]
            lp = os.path.join(CUBI, "labels", "val", os.path.splitext(os.path.basename(ip))[0] + ".txt")
            items.append(dict(path=ip, img=im, gt=load_boxes(lp, W, H), ign=[], scale=None))
        return items, dict(source=CUBI + "/images/val", split="val (model-selection split; test split NOT used)")
    for ip in sorted(glob.glob(os.path.join(SYN, "images", "*", "*.png"))):
        sp, n = os.path.basename(os.path.dirname(ip)), os.path.splitext(os.path.basename(ip))[0]
        im = cv2.imread(ip)
        H, W = im.shape[:2]
        items.append(dict(path=ip, img=im, gt=load_boxes(os.path.join(SYN, "labels", sp, n + ".txt"), W, H),
                          ign=load_boxes(os.path.join(SYN, "ignore", sp, n + ".txt"), W, H), split=sp))
    spans = [max(g[3] - g[1], g[4] - g[2]) for it in items for g in it["gt"] if g[0] == 0]
    ppm = statistics.median(spans) / DOOR_M
    for it in items:
        it["scale"] = TARGET_PPM / ppm
    return items, dict(source=SYN, pack_scale_px_per_m=round(ppm, 2), scale_basis=f"median corrected door span / {DOOR_M} m",
                       note="SYNTHETIC — smoke / supplementary only; not real or Tamil Nadu accuracy")


def main():
    out_path, model_path, ds_name = sys.argv[1:4]
    name = sys.argv[4] if len(sys.argv) > 4 else os.path.basename(model_path)
    model = YOLO(model_path)
    items, ds_info = dataset(ds_name)
    preds = [predict(model, it["img"], it["scale"]) for it in items]
    res = dict(model=name, checkpoint=model_path, checkpoint_sha256=hashlib.sha256(open(model_path, "rb").read()).hexdigest(),
               dataset=ds_name, dataset_info=ds_info, images=len(items), evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
               config=dict(conf_operating=CONF_OP, conf_for_ap=CONF_AP, iou_match=IOU_OP, nms_iou_tiles=NMS_IOU, imgsz=1024,
                           matching="one-to-one greedy by confidence, same class, IoU>=0.5; ignore regions excluded"),
               classes={})
    for c, cname in enumerate(CLASSES):
        agg = {t: ([], [], 0) for t in np.round(np.arange(0.5, 0.96, 0.05), 2)}
        op = dict(tp=0, fp=0, fn=0)
        centre_hit, n_gt_all = 0, 0
        for it, pr in zip(items, preds):
            g = [b[1:] for b in it["gt"] if b[0] == c]
            ig = [b[1:] for b in it["ign"] if b[0] == c]
            P = [(p[1], p[2], p[3], p[4], p[5]) for p in pr if p[0] == c]
            for t in agg:
                f, s, n = match(g, P, ig, t)
                agg[t][0].extend(f)
                agg[t][1].extend(s)
                agg[t] = (agg[t][0], agg[t][1], agg[t][2] + n)
            f, s, n = match(g, [p for p in P if p[4] >= CONF_OP], ig, IOU_OP)
            op["tp"] += sum(f)
            op["fp"] += len(f) - sum(f)
            op["fn"] += n - sum(f)
            n_gt_all += len(g)
            for gb in g:
                if any(gb[0] <= (p[0] + p[2]) / 2 <= gb[2] and gb[1] <= (p[1] + p[3]) / 2 <= gb[3] for p in P if p[4] >= CONF_OP):
                    centre_hit += 1
        aps = {float(t): ap101(*v) for t, v in agg.items()}
        p = op["tp"] / max(1, op["tp"] + op["fp"])
        r = op["tp"] / max(1, op["tp"] + op["fn"])
        res["classes"][cname] = dict(**op, precision=round(p, 4), recall=round(r, 4), f1=round(2 * p * r / max(1e-9, p + r), 4),
                                     ap50=round(aps[0.5], 4), ap50_95=round(float(np.mean(list(aps.values()))), 4), gt=n_gt_all,
                                     diagnostic_centre_hit_rate=round(centre_hit / max(1, n_gt_all), 4))
    res["mAP50"] = round(np.mean([v["ap50"] for v in res["classes"].values()]), 4)
    res["mAP50_95"] = round(np.mean([v["ap50_95"] for v in res["classes"].values()]), 4)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(res, open(out_path, "w"), indent=1)
    if ds_name == "synthetic_corrected":  # prediction visualisations at the operating point
        vd = os.path.join(os.path.dirname(out_path), "predictions_" + name)
        os.makedirs(vd, exist_ok=True)
        for it, pr in zip(items, preds):
            v = it["img"].copy()
            for b in it["gt"]:
                cv2.rectangle(v, (int(b[1]), int(b[2])), (int(b[3]), int(b[4])), (150, 150, 150), 1)
            for b in it["ign"]:
                cv2.rectangle(v, (int(b[1]), int(b[2])), (int(b[3]), int(b[4])), (0, 0, 230), 1)
            for p in pr:
                if p[5] >= CONF_OP:
                    cv2.rectangle(v, (int(p[1]), int(p[2])), (int(p[3]), int(p[4])), (0, 150, 0) if p[0] == 0 else (220, 90, 0), 2)
            cv2.imwrite(os.path.join(vd, os.path.basename(it["path"])[:-4] + ".jpg"), v, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(json.dumps({k: res[k] for k in ("model", "dataset", "mAP50", "mAP50_95")}), json.dumps(res["classes"]))


if __name__ == "__main__":
    main()
