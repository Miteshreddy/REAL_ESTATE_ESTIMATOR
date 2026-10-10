"""Door / window object detector (YOLO, ONNX) — the third opening source next to U-Net segmentation and wall-gap geometry.

Trained on plans drawn at ~25-40 px per door (CubiCasa plans resized to 1024 px). A drawing is therefore resampled so
that 1 m ≈ TARGET_PPM px before detection, tiled at 1024 px with overlap, and boxes are mapped back to metres.
Model metadata (version, train / val / test metrics) is read from data/models/opening_det.metrics.json.
"""
from __future__ import annotations

import json
import os

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "data", "models")
CONFIG = os.path.join(MODELS_DIR, "detector.json")  # {"active": "<file in data/models>"} — explicit, cwd-independent
DEFAULT_MODEL = "opening_det.onnx"  # YOLOv8s (CubiCasa5K) — production; rollback = set "active" back to this file


def active_model_file() -> str:
    """Detector selection: env EST_DETECTOR_MODEL (a file name inside data/models) > data/models/detector.json > default.
    Only file names inside data/models are accepted (no paths)."""
    name = os.environ.get("EST_DETECTOR_MODEL")
    if not name and os.path.exists(CONFIG):
        try:
            name = json.load(open(CONFIG, encoding="utf-8")).get("active")
        except (ValueError, OSError):
            name = None
    name = os.path.basename(name or DEFAULT_MODEL)
    path = os.path.join(MODELS_DIR, name)
    # a Git LFS pointer that was not fetched (a few hundred bytes) is not a model: fall back to the default weights
    if name != DEFAULT_MODEL and (not os.path.exists(path) or os.path.getsize(path) < 1_000_000):
        return os.path.join(MODELS_DIR, DEFAULT_MODEL)
    return path


MODEL = active_model_file()
TARGET_PPM = 38.0   # px per metre at which doors look like the training data
TILE, OVER = 1024, 160
NAMES = ("door", "window")
_sess = None


def available() -> bool:
    return os.path.exists(active_model_file()) and os.environ.get("EST_DETECTOR", "1") == "1"


def info():
    p = active_model_file().replace(".onnx", ".metrics.json")
    return json.load(open(p)) if os.path.exists(p) else None


_sess_model = None


def model_name() -> str:
    return os.path.basename(active_model_file())


def _session():
    global _sess, _sess_model, MODEL
    MODEL = active_model_file()
    if _sess is not None and _sess_model != MODEL:  # selection changed (config / env): reload
        _sess = None
    if _sess is None:
        _sess_model = MODEL
        import onnxruntime as ort
        _sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    return _sess


def _run(tile: np.ndarray, conf: float):
    s = _session()
    x = cv2.cvtColor(tile, cv2.COLOR_GRAY2RGB) if tile.ndim == 2 else cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)
    x = np.ascontiguousarray(x.transpose(2, 0, 1)[None].astype(np.float32) / 255.0)
    out = s.run(None, {s.get_inputs()[0].name: x})[0][0]  # (4 + nc, N)
    boxes, scores, cls = out[:4].T, out[4:].max(0), out[4:].argmax(0)
    keep = scores >= conf
    return boxes[keep], scores[keep], cls[keep]


def detect(img: np.ndarray, px_per_m: float, conf: float = 0.35) -> list[dict]:
    """[{kind, x_px, y_px, w_px, h_px, score}] in the INPUT image pixels."""
    if not available() or not px_per_m:
        return []
    k = TARGET_PPM / px_per_m
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(g, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    H, W = small.shape
    B, S, C = [], [], []
    step = TILE - OVER
    for y0 in range(0, max(1, H - OVER), step):
        for x0 in range(0, max(1, W - OVER), step):
            tile = np.full((TILE, TILE), 255, np.uint8)
            crop = small[y0:y0 + TILE, x0:x0 + TILE]
            tile[:crop.shape[0], :crop.shape[1]] = crop
            b, s, c = _run(tile, conf)
            for (cx, cy, w, h), sc, cl in zip(b, s, c):
                if cx > crop.shape[1] or cy > crop.shape[0]:
                    continue
                B.append([x0 + cx - w / 2, y0 + cy - h / 2, w, h])
                S.append(float(sc))
                C.append(int(cl))
    out = []
    for cl in (0, 1):
        idx = [i for i, c in enumerate(C) if c == cl]
        if not idx:
            continue
        keep = cv2.dnn.NMSBoxes([B[i] for i in idx], [S[i] for i in idx], conf, 0.45)
        for j in np.array(keep).flatten():
            x, y, w, h = B[idx[j]]
            out.append(dict(kind=NAMES[cl], x_px=(x + w / 2) / k, y_px=(y + h / 2) / k, w_px=w / k, h_px=h / k, score=S[idx[j]]))
    return out


def to_openings(dets: list[dict], px_per_m: float, frame: dict, ds: float = 1.0) -> list[dict]:
    """Detections (image px of the analysed image) → plan openings in metres (same frame as the parser)."""
    out = []
    for d in dets:
        L = max(d["w_px"], d["h_px"]) / px_per_m
        if not 0.4 <= L <= 3.5:
            continue
        out.append(dict(kind=d["kind"], x=round(d["x_px"] / px_per_m - frame["ox"], 2), y=round(d["y_px"] / px_per_m - frame["oy"], 2),
                        w=round(L, 2), score=round(d["score"], 3), horiz=bool(d["w_px"] > d["h_px"])))
    return out
