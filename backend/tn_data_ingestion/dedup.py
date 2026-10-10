"""Duplicate detection: SHA-256 (identical files), 64-bit dHash on a normalised page image (resized / re-encoded /
lightly cropped copies), OCR/vector-text Jaccard (same drawing, different file)."""
from __future__ import annotations

import re

import cv2
import numpy as np


def dhash(img: np.ndarray, size=16) -> int:
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ys, xs = np.where(g < 200)  # crop to ink so margins / small crops do not change the hash
    if len(xs) > 50:
        g = g[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (s[:, 1:] > s[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def text_sig(t: str) -> set:
    return set(re.findall(r"[a-z]{3,}|\d+(?:\.\d+)?", (t or "").lower()))


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def near_duplicate(p1: dict, p2: dict, max_ham=12, min_jac=0.85) -> str | None:
    """Same page of the same file is not a duplicate of itself; identical files / near-identical renders are."""
    if p1["sha256"] == p2["sha256"]:
        return "identical file" if p1.get("page") == p2.get("page") else None
    h = hamming(p1["dhash"], p2["dhash"])
    texts = len(p1["text_sig"]) >= 15 and len(p2["text_sig"]) >= 15
    if h <= max_ham and (not texts or jaccard(p1["text_sig"], p2["text_sig"]) >= 0.5):
        return f"perceptual hash distance {h}/256"
    if len(p1["text_sig"]) >= 15 and jaccard(p1["text_sig"], p2["text_sig"]) >= min_jac:
        return f"text similarity {jaccard(p1['text_sig'], p2['text_sig']):.2f}"
    return None
