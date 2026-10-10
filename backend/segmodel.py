"""Deep-learning floor-plan segmentation (U-Net / ResNet-34, trained on CubiCasa5K) via ONNX Runtime.

Classes: 0 background, 1 wall, 2 room, 3 door, 4 window.
The model expects plans where walls are a few pixels thick (as in its training data), so the input is
resized from the estimated wall thickness, processed in overlapping tiles and mapped back.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models", "floorplan_unet.onnx")
TARGET_WALL_PX = 12.0  # typical external wall thickness the model saw in training (px), after scale augmentation
TILE, OVERLAP = 768, 128
_SESS = None
_MTIME = None


def available() -> bool:
    return os.path.exists(MODEL)


def _session():
    """ONNX Runtime session on the CPU. Reloaded automatically when the model file is replaced
    (e.g. after retraining), so a running server picks up a new model without a restart."""
    global _SESS, _MTIME
    mt = os.path.getmtime(MODEL)
    if _SESS is None or mt != _MTIME:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) // 2)
        _SESS = ort.InferenceSession(MODEL, sess_options=opts, providers=["CPUExecutionProvider"])
        _MTIME = mt
        print("[seg] model loaded:", os.path.basename(MODEL), flush=True)
    return _SESS


def info() -> dict:
    meta = os.path.join(os.path.dirname(MODEL), "floorplan_unet.json")
    if os.path.exists(meta):
        import json
        return json.load(open(meta, encoding="utf-8"))
    return {"available": available()}


def _run(tile: np.ndarray) -> np.ndarray:
    x = (tile.astype(np.float32) / 255.0)[None, None]
    return _session().run(None, {"image": x})[0][0]  # (5, h, w) logits


def segment(gray: np.ndarray, wall_px: float | None = None, long_side: int = 1024) -> tuple[np.ndarray, float]:
    """Class map at the input resolution, and the resize factor used.

    A single floor plan is normalised to ~1024 px on its longest side (the training distribution);
    if the wall thickness is known the image is scaled so walls are ~TARGET_WALL_PX thick instead."""
    k = TARGET_WALL_PX / wall_px if wall_px else long_side / max(gray.shape)
    k = float(np.clip(k, 0.1, 3.0))
    img = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
    H, W = img.shape
    ph, pw = (-H) % 32, (-W) % 32
    img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=255)
    Hp, Wp = img.shape
    acc = np.zeros((5, Hp, Wp), np.float32)
    cnt = np.zeros((Hp, Wp), np.float32)
    if max(Hp, Wp) <= TILE + OVERLAP:
        acc += _run(img)
        cnt += 1
    else:
        step = TILE - OVERLAP
        ys = list(range(0, max(1, Hp - TILE), step)) + [max(0, Hp - TILE)]
        xs = list(range(0, max(1, Wp - TILE), step)) + [max(0, Wp - TILE)]
        for y in sorted(set(ys)):
            for x in sorted(set(xs)):
                t = img[y:y + TILE, x:x + TILE]
                th, tw = t.shape
                t = cv2.copyMakeBorder(t, 0, (-th) % 32, 0, (-tw) % 32, cv2.BORDER_CONSTANT, value=255)
                out = _run(t)[:, :th, :tw]
                acc[:, y:y + th, x:x + tw] += out
                cnt[y:y + th, x:x + tw] += 1
    cls = (acc / np.maximum(cnt, 1)).argmax(0)[:H, :W].astype(np.uint8)
    cls = cv2.resize(cls, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    return cls, k
