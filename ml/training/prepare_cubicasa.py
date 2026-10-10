"""Convert CubiCasa5K (image + SVG polygons) into training pairs: grayscale image + class mask.

Classes: 0 background, 1 wall (incl. columns), 2 room interior, 3 door, 4 window.
Images are resized so the longest side is MAX_SIDE. Official train/val/test splits are kept.
"""
import os
import sys
from multiprocessing import Pool

import cv2
import numpy as np
from lxml import etree

ROOT = r"G:\velo\real-estate\datasets\cubicasa5k"
OUT = r"G:\velo\real-estate\prepared"
MAX_SIDE = 1024
NS = "{http://www.w3.org/2000/svg}"


def polys(group):
    """Direct child polygons of an SVG group (nested label/dimension groups are ignored)."""
    out = []
    for ch in group:
        if ch.tag == NS + "polygon" and ch.get("points"):
            pts = [p.split(",") for p in ch.get("points").strip().split()]
            try:
                arr = np.array([[float(x), float(y)] for x, y in pts], np.float32)
            except ValueError:
                continue
            if len(arr) >= 3:
                out.append(arr)
    return out


def build_mask(svg_path, h, w):
    tree = etree.parse(svg_path)
    spaces, walls, doors, windows = [], [], [], []
    for g in tree.iter(NS + "g"):
        cls = (g.get("class") or "").split()
        if not cls:
            continue
        head = cls[0]
        if head == "Space":
            spaces += polys(g)
        elif head in ("Wall", "Column"):
            walls += polys(g)[:1] if head == "Wall" else polys(g)
        elif head == "Door":
            doors += polys(g)[:1]
        elif head == "Window":
            windows += polys(g)[:1]
    m = np.zeros((h, w), np.uint8)
    for val, ps in ((2, spaces), (1, walls), (4, windows), (3, doors)):
        for p in ps:
            cv2.fillPoly(m, [np.round(p).astype(np.int32)], val)
    return m, dict(spaces=len(spaces), walls=len(walls), doors=len(doors), windows=len(windows))


def work(args):
    split, rel = args
    src = os.path.join(ROOT, rel.strip("/").replace("/", os.sep))
    name = rel.strip("/").replace("/", "_")
    dst_i = os.path.join(OUT, split, "img", name + ".png")
    dst_m = os.path.join(OUT, split, "mask", name + ".png")
    if os.path.exists(dst_m):
        return name, "skip"
    img = cv2.imread(os.path.join(src, "F1_scaled.png"), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return name, "noimg"
    h, w = img.shape
    try:
        m, info = build_mask(os.path.join(src, "model.svg"), h, w)
    except Exception as e:
        return name, f"svgerr {e}"
    if info["walls"] == 0:
        return name, "nowalls"
    k = MAX_SIDE / max(h, w)
    if k < 1:
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        m = cv2.resize(m, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(dst_i, img)
    cv2.imwrite(dst_m, m)
    return name, "ok"


if __name__ == "__main__":
    jobs = []
    for split in ("train", "val", "test"):
        os.makedirs(os.path.join(OUT, split, "img"), exist_ok=True)
        os.makedirs(os.path.join(OUT, split, "mask"), exist_ok=True)
        with open(os.path.join(ROOT, f"{split}.txt")) as f:
            jobs += [(split, l.strip()) for l in f if l.strip()]
    if len(sys.argv) > 1:
        jobs = jobs[: int(sys.argv[1])]
    with Pool(12) as p:
        res = p.map(work, jobs, chunksize=8)
    from collections import Counter
    print(Counter(r for _, r in res).most_common())
    bad = [n for n, r in res if r not in ("ok", "skip")]
    print("problems:", bad[:10])
