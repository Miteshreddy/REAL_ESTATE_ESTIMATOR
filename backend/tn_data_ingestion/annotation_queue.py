"""Annotation workflow:  pretrained models → pseudo labels → human correction → VERIFIED annotation → training.

Pseudo labels (data/tn_dataset/pseudo_labels) are never ground truth. Only annotations/verified/<page_id>.json with
verification_status in ('verified', 'expert-verified') are exported for training (export_yolo) or used for evaluation.

Annotation JSON:
  {page_id, project_id, annotator, annotation_version, verification_status,
   objects: [{class, bbox:[x0,y0,x1,y1] (page-image px), polygon?: [[x,y]…]}]}
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import numpy as np

from .dataset_builder import DS, _load, _save

CLASSES = ["door", "window", "ventilator", "wall", "room", "column", "beam", "footing", "stair", "lift", "shaft", "dimension", "text",
           "floor_label", "unit_boundary", "title", "scale"]
PRIORITY = {"door": 1, "window": 2, "wall": 3, "room": 4}


def build_queue() -> list[dict]:
    pages = _load("pages.json", {})
    projects = _load("projects.json", {})
    q = []
    for pid, p in pages.items():
        sp = projects.get(p.get("project_id"), {}).get("split")
        if sp not in ("tn_train", "tn_validation"):
            continue  # evaluation pages are annotated separately, by a different reviewer, and never trained on
        if os.path.exists(os.path.join(DS, "annotations", "verified", pid + ".json")):
            continue
        hard = os.path.exists(os.path.join(DS, "hard_cases", pid + ".json"))
        q.append(dict(page_id=pid, project_id=p.get("project_id"), split=sp, drawing_type=p["drawing_type"],
                      priority=0 if hard else (1 if p["drawing_type"] == "ARCHITECTURAL PLAN" else 3), hard_case=hard,
                      pseudo_available=os.path.exists(os.path.join(DS, "pseudo_labels", pid + ".json"))))
    q.sort(key=lambda x: (x["priority"], x["page_id"]))
    _save("queue.json", q)
    return q


def pseudo_label(page_ids: list[str] | None = None, limit=200) -> int:
    """U-Net segmentation → door / window / room boxes as PSEUDO labels (to speed up human annotation)."""
    import cv2
    import segmodel
    pages = _load("pages.json", {})
    n = 0
    for pid in (page_ids or list(pages))[:limit]:
        out = os.path.join(DS, "pseudo_labels", pid + ".json")
        if os.path.exists(out) or not segmodel.available():
            continue
        img = cv2.imread(os.path.join(DS, "processed", pid + ".png"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        cls, _ = segmodel.segment(img)
        objs = []
        for val, name in ((3, "door"), (4, "window"), (2, "room")):
            k, lab, st, _ = cv2.connectedComponentsWithStats((cls == val).astype(np.uint8), connectivity=8)
            for i in range(1, k):
                x, y, w, h, a = st[i]
                if a >= (20 if name != "room" else 400):
                    objs.append({"class": name, "bbox": [int(x), int(y), int(x + w), int(y + h)]})
        json.dump(dict(page_id=pid, model="floorplan_unet v1.0", created=datetime.now().isoformat(timespec="seconds"),
                       verification_status="pseudo", objects=objs), open(out, "w"))
        n += 1
    return n


def verified(pid: str) -> dict | None:
    """VERIFIED record on a training-eligible page (backend/annotations.py — two independent reviewer approvals)."""
    import annotations as A
    r = A.load(pid)
    pg = _load("pages.json", {}).get(pid, {})
    return r if r and r["status"] == "VERIFIED" and not A.validate(r) and pg.get("training_eligible") else None


def export_yolo(classes=("door", "window")) -> dict:
    """Verified annotations → YOLO dataset (data/tn_dataset/yolo) using the PROJECT split. Pseudo labels are excluded."""
    import shutil
    projects = _load("projects.json", {})
    pages = _load("pages.json", {})
    out = os.path.join(DS, "yolo")
    counts = {}
    for sp, yname in (("tn_train", "train"), ("tn_validation", "val"), ("final_holdout", "test")):
        os.makedirs(os.path.join(out, "images", yname), exist_ok=True)
        os.makedirs(os.path.join(out, "labels", yname), exist_ok=True)
        n = 0
        for pid, p in pages.items():
            if projects.get(p.get("project_id"), {}).get("split") != sp:
                continue
            a = verified(pid)
            if not a:
                continue
            W, H = p["width"], p["height"]
            shutil.copy(os.path.join(DS, "processed", pid + ".png"), os.path.join(out, "images", yname, pid + ".png"))
            with open(os.path.join(out, "labels", yname, pid + ".txt"), "w") as fh:
                for o in a["objects"]:
                    if o["class"] in classes:
                        x0, y0, x1, y1 = o["bbox"]
                        fh.write(f"{classes.index(o['class'])} {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}\n")
            n += 1
        counts[yname] = n
    with open(os.path.join(out, "data.yaml"), "w") as fh:
        fh.write(f"path: {out}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(classes)))
    return counts
