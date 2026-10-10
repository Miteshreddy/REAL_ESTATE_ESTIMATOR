"""Train / evaluate the door-window detector from a config (configs/tn_opening_detector.yaml).

    <trainenv python> ml/training/train_detector.py configs/tn_opening_detector.yaml stage1   # generic pretraining
    <trainenv python> ml/training/train_detector.py configs/tn_opening_detector.yaml stage2   # TN fine-tune (needs verified TN labels)
    <trainenv python> ml/training/train_detector.py configs/tn_opening_detector.yaml eval <weights>

Writes train / val / test metrics to <run>/metrics.json and exports ONNX for the app (data/models/opening_det.onnx).
"""
import json
import os
import shutil
import sys

import yaml
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def metrics(model, data, split):
    r = model.val(data=data, split=split, imgsz=CFG["imgsz"], batch=CFG["batch"], verbose=False, plots=False)
    out = dict(map50=float(r.box.map50), map50_95=float(r.box.map))
    for i, name in enumerate(CFG["classes"]):
        p, rc = float(r.box.p[i]), float(r.box.r[i])
        out[name] = dict(precision=round(p, 4), recall=round(rc, 4), f1=round(2 * p * rc / max(1e-9, p + rc), 4), ap50=round(float(r.box.ap50[i]), 4))
    return out


if __name__ == "__main__":
    CFG = yaml.safe_load(open(sys.argv[1]))
    stage = sys.argv[2]
    if stage in ("stage1", "stage2"):
        data = CFG["stage1_data"] if stage == "stage1" else os.path.join(ROOT, CFG["stage2_data"])
        if not os.path.exists(data):
            sys.exit(f"{data} not found — for stage2 build the TN dataset with verified annotations first (ml/dataset/build_splits.py)")
        base = CFG["model"] if stage == "stage1" else os.path.join(ROOT, "data", "models", "opening_det.pt")
        m = YOLO(base)
        m.train(data=data, imgsz=CFG["imgsz"], epochs=CFG["epochs"], batch=CFG["batch"], seed=CFG["seed"], deterministic=CFG["deterministic"],
                project=CFG["project"], name=CFG["name"] + ("_tn" if stage == "stage2" else ""), exist_ok=True, workers=4, plots=False,
                patience=CFG.get("patience", 100), cos_lr=CFG.get("cos_lr", False))
        best = os.path.join(CFG["project"], CFG["name"] + ("_tn" if stage == "stage2" else ""), "weights", "best.pt")
    else:
        best, data = sys.argv[3], CFG["stage1_data"]
    m = YOLO(best)
    res = {s: metrics(m, data, s) for s in ("train", "val", "test")}
    res["dataset"] = data
    json.dump(res, open(os.path.join(os.path.dirname(os.path.dirname(best)), "metrics.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))
    prod = os.path.join(ROOT, "data", "models", "opening_det.metrics.json")
    f1 = lambda r: (r["test"]["door"]["f1"] + r["test"]["window"]["f1"]) / 2
    if os.path.exists(prod) and f1(json.load(open(prod))) >= f1(res):  # never replace a better production model
        print(f"NOT PROMOTED: test mean F1 {f1(res):.4f} <= production {f1(json.load(open(prod))):.4f}")
        sys.exit(0)
    onnx = m.export(format="onnx", imgsz=CFG["imgsz"], dynamic=False, simplify=False)
    os.makedirs(os.path.join(ROOT, "data", "models"), exist_ok=True)
    shutil.copy(onnx, os.path.join(ROOT, "data", "models", "opening_det.onnx"))
    shutil.copy(best, os.path.join(ROOT, "data", "models", "opening_det.pt"))
    json.dump(res, open(os.path.join(ROOT, "data", "models", "opening_det.metrics.json"), "w"), indent=1)
