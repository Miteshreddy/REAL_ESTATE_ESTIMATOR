"""Door / window detection dataset (YOLO format) from the prepared segmentation masks.

Classes: 0 door, 1 window. One box per connected component of the door / window mask (min 20 px²).
The source split (train / val / test) is preserved — CubiCasa's official split is by plan, so no plan crosses splits.
This is GENERIC PRETRAINING data (CubiCasa5K, not Tamil Nadu). TN fine-tuning uses data/tn_dataset once verified TN
annotations exist (ml/dataset/build_splits.py).

Usage: python build_opening_dataset.py <prepared_dir> <out_dir>
"""
import os
import sys

import cv2
import numpy as np

CLS = {3: 0, 4: 1}


def boxes(mask):
    out = []
    for val, c in CLS.items():
        n, lab, st, _ = cv2.connectedComponentsWithStats((mask == val).astype(np.uint8), connectivity=8)
        for i in range(1, n):
            x, y, w, h, a = st[i]
            if a >= 20:
                out.append((c, x, y, w, h))
    return out


def main(src, dst):
    for split in ("train", "val", "test"):
        idir, mdir = os.path.join(src, split, "img"), os.path.join(src, split, "mask")
        oi, ol = os.path.join(dst, "images", split), os.path.join(dst, "labels", split)
        os.makedirs(oi, exist_ok=True)
        os.makedirs(ol, exist_ok=True)
        n_obj = 0
        for f in sorted(os.listdir(idir)):
            m = cv2.imread(os.path.join(mdir, f), cv2.IMREAD_GRAYSCALE)
            if m is None:
                continue
            H, W = m.shape
            bx = boxes(m)
            n_obj += len(bx)
            dst_img = os.path.join(oi, f)
            if not os.path.exists(dst_img):
                os.link(os.path.join(idir, f), dst_img) if os.name == "nt" else os.symlink(os.path.join(idir, f), dst_img)
            with open(os.path.join(ol, os.path.splitext(f)[0] + ".txt"), "w") as fh:
                for c, x, y, w, h in bx:
                    fh.write(f"{c} {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}\n")
        print(split, len(os.listdir(oi)), "images", n_obj, "objects", flush=True)
    with open(os.path.join(dst, "data.yaml"), "w") as fh:
        fh.write(f"path: {dst}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: door\n  1: window\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
