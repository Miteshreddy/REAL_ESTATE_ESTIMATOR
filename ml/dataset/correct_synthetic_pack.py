"""Derive a corrected copy of the 20-image synthetic door/window pack whose boxes follow the production detector's
object definition (CubiCasa convention): a door or window is the OPENING STRIP — span along the wall × wall thickness.

    python ml/dataset/correct_synthetic_pack.py

The original pack is never modified. Output: data/synthetic_tn20_corrected/ (images copied, labels re-derived,
manifest + per-object correction log). Boxes are re-derived from the drawing's pixels:

* wall mask = dark pixels kept by a morphological opening (walls are ≥10 px thick; door leaves / arcs / frame lines are
  thin and disappear).
* DOOR: the original box is the swing square; exactly one of its four edges lies on a wall line — the wall continues
  beyond BOTH ends of that edge. Corrected box = that edge's span × the wall band measured just outside both ends.
* WINDOW: the original box is the frame symbol centred on the wall; the long axis is the span. Corrected box = the span ×
  the wall band measured just outside both ends of the span.
* Anything else (no wall edge, two candidate edges, wall band not found / inconsistent on the two sides) → AMBIGUOUS:
  written to ignore/<name>.txt and used as an ignore region in evaluation, never guessed.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import shutil

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "data", "synthetic_tn20", "TN_Door_Window_20_Synthetic_Samples")
DST = os.path.join(ROOT, "data", "synthetic_tn20_corrected")
NAMES = {0: "door", 1: "window"}
PROBE = 6  # px beyond the box end where the wall is sampled


def wall_mask(gray):
    dark = (gray < 90).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    return cv2.morphologyEx(dark, cv2.MORPH_OPEN, k)


def band(mask, axis_horizontal, at, lo, hi):
    """Wall band crossing position `at` (an x for a horizontal wall, a y for a vertical one), searched within [lo, hi]
    perpendicular to the wall. Returns (start, end) of the contiguous wall run nearest the search centre, or None."""
    H, W = mask.shape
    lo, hi = max(0, int(lo)), min((H if axis_horizontal else W) - 1, int(hi))
    if not (0 <= at < (W if axis_horizontal else H)) or hi <= lo:
        return None
    line = mask[lo:hi + 1, int(at)] if axis_horizontal else mask[int(at), lo:hi + 1]
    idx = np.flatnonzero(line)
    if not len(idx):
        return None
    runs, s = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b != a + 1:
            runs.append((s, a))
            s = b
    runs.append((s, idx[-1]))
    mid = (hi - lo) / 2
    s, e = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - mid))
    return lo + s, lo + e + 1


def wall_band_both_sides(mask, horizontal, a0, a1, c_lo, c_hi):
    """Wall band just outside both ends of span [a0, a1]; must exist and agree on both sides."""
    b1 = band(mask, horizontal, a0 - PROBE, c_lo, c_hi)
    b2 = band(mask, horizontal, a1 + PROBE, c_lo, c_hi)
    if not b1 or not b2:
        return None, "wall not found beyond both ends"
    if abs(b1[0] - b2[0]) > 3 or abs(b1[1] - b2[1]) > 3:
        return None, f"wall band differs on the two sides {b1} vs {b2}"
    return (min(b1[0], b2[0]), max(b1[1], b2[1])), None


def correct_door(mask, x0, y0, x1, y1):
    cands = []
    for edge, horizontal, pos, a0, a1 in (("top", True, y0, x0, x1), ("bottom", True, y1, x0, x1),
                                         ("left", False, x0, y0, y1), ("right", False, x1, y0, y1)):
        wb, why = wall_band_both_sides(mask, horizontal, a0, a1, pos - 14, pos + 14)
        if wb:
            cands.append((edge, horizontal, a0, a1, wb))
    if not cands:  # wall runs THROUGH the swing box: opening = longest gap of that wall inside the box
        return door_through_wall(mask, x0, y0, x1, y1)
    if len(cands) != 1:
        return None, f"{len(cands)} edges lie on a wall (need exactly 1)"
    edge, horizontal, a0, a1, (b0, b1) = cands[0]
    box = (a0, b0, a1, b1) if horizontal else (b0, a0, b1, a1)
    return box, f"swing square → opening on {edge} edge"


def door_through_wall(mask, x0, y0, x1, y1):
    """A wall crossing the swing box: the same wall band must be found just beyond BOTH opposite edges (inside the
    edge's span, away from the corners); the opening is the longest wall-free run inside the box along that band."""
    found = []
    for vertical in (True, False):  # vertical wall enters at top and leaves at bottom
        if vertical:
            b1, b2 = band(mask, False, y0 - PROBE, x0 + 4, x1 - 4), band(mask, False, y1 + PROBE, x0 + 4, x1 - 4)
        else:
            b1, b2 = band(mask, True, x0 - PROBE, y0 + 4, y1 - 4), band(mask, True, x1 + PROBE, y0 + 4, y1 - 4)
        if b1 and b2 and abs(b1[0] - b2[0]) <= 3 and abs(b1[1] - b2[1]) <= 3:
            found.append((vertical, (min(b1[0], b2[0]), max(b1[1], b2[1]))))
    if len(found) != 1:
        return None, f"wall-through-box: {len(found)} candidate walls (need exactly 1)"
    vertical, (b0, b1) = found[0]
    a0, a1 = (int(y0), int(y1)) if vertical else (int(x0), int(x1))
    strip = mask[a0:a1, b0:b1] if vertical else mask[b0:b1, a0:a1].T
    free = strip.mean(axis=1) < 0.2  # rows (along the wall) with no wall pixels = the opening
    best, cur, start = (0, 0), 0, 0
    for i, f in enumerate(free):
        cur = cur + 1 if f else 0
        if cur == 1:
            start = i
        if cur > best[1] - best[0]:
            best = (start, i + 1)
    if best[1] - best[0] < 0.3 * (a1 - a0):
        return None, "wall-through-box: no clear opening gap"
    g0, g1 = a0 + best[0], a0 + best[1]
    return ((b0, g0, b1, g1) if vertical else (g0, b0, g1, b1)), "swing drawn across the wall → gap in wall inside box"


def correct_window(mask, x0, y0, x1, y1):
    horizontal = (x1 - x0) >= (y1 - y0)
    if horizontal:
        wb, why = wall_band_both_sides(mask, True, x0, x1, y0, y1)
        return ((x0, wb[0], x1, wb[1]), "frame symbol → wall band") if wb else (None, why)
    wb, why = wall_band_both_sides(mask, False, y0, y1, x0, x1)
    return ((wb[0], y0, wb[1], y1), "frame symbol → wall band") if wb else (None, why)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    log, manifest = [], []
    for ip in sorted(glob.glob(os.path.join(SRC, "images", "*", "*.png"))):
        split = os.path.basename(os.path.dirname(ip))
        name = os.path.splitext(os.path.basename(ip))[0]
        lp = os.path.join(SRC, "labels", split, name + ".txt")
        gray = cv2.imread(ip, cv2.IMREAD_GRAYSCALE)
        H, W = gray.shape
        mask = wall_mask(gray)
        out, ign = [], []
        for n, line in enumerate(open(lp, encoding="utf-8").read().split("\n")):
            if not line.strip():
                continue
            c, x, y, w, h = line.split()
            c = int(c)
            x0, y0, x1, y1 = (float(x) - float(w) / 2) * W, (float(y) - float(h) / 2) * H, (float(x) + float(w) / 2) * W, (float(y) + float(h) / 2) * H
            box, how = (correct_door if c == 0 else correct_window)(mask, x0, y0, x1, y1)
            if box is not None:  # verification: an opening must be a GAP in the wall, not a strip over solid wall
                bx0, by0, bx1, by1 = (int(round(v)) for v in box)
                fill = float(mask[by0:by1, bx0:bx1].mean()) if by1 > by0 and bx1 > bx0 else 1.0
                if fill > 0.3:
                    box, how = None, f"derived strip is {fill:.0%} solid wall — the drawing shows no opening here"
            rec = dict(image=name, split=split, obj=n, cls=NAMES[c], original_xyxy=[round(v, 1) for v in (x0, y0, x1, y1)])
            if box is None:
                ign.append((c, x0, y0, x1, y1))
                rec.update(status="AMBIGUOUS", reason=how, corrected_xyxy=None)
            else:
                bx0, by0, bx1, by1 = box
                out.append((c, bx0, by0, bx1, by1))
                rec.update(status="CORRECTED", method=how, corrected_xyxy=[round(float(v), 1) for v in box],
                           corrected_wh=[round(float(bx1 - bx0), 1), round(float(by1 - by0), 1)])
            log.append(rec)
        for sub in ("images", "labels", "ignore"):
            os.makedirs(os.path.join(DST, sub, split), exist_ok=True)
        shutil.copy2(ip, os.path.join(DST, "images", split, name + ".png"))
        yolo = lambda b: f"{b[0]} {(b[1] + b[3]) / 2 / W:.6f} {(b[2] + b[4]) / 2 / H:.6f} {(b[3] - b[1]) / W:.6f} {(b[4] - b[2]) / H:.6f}"
        open(os.path.join(DST, "labels", split, name + ".txt"), "w").write("\n".join(yolo(b) for b in out) + ("\n" if out else ""))
        open(os.path.join(DST, "ignore", split, name + ".txt"), "w").write("\n".join(yolo(b) for b in ign) + ("\n" if ign else ""))
        manifest.append(dict(image=name, split=split, image_sha256=sha(ip), original_label_sha256=sha(lp),
                             corrected_label_sha256=sha(os.path.join(DST, "labels", split, name + ".txt")),
                             doors=sum(1 for b in out if b[0] == 0), windows=sum(1 for b in out if b[0] == 1),
                             ambiguous=len(ign)))
    open(os.path.join(DST, "data.yaml"), "w").write("# CORRECTED synthetic pack (opening-strip convention). SYNTHETIC — not real / TN data.\n"
                                                     "path: .\ntrain: images/train\nval: images/val\nnames:\n  0: door\n  1: window\n")
    with open(os.path.join(DST, "manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, list(manifest[0]))
        w.writeheader()
        w.writerows(manifest)
    json.dump(dict(source=os.path.relpath(SRC, ROOT), convention="opening strip: span along wall x wall thickness (CubiCasa / production)",
                   synthetic=True, real_tamil_nadu_source=False, approved_for_real_training=False, objects=log),
              open(os.path.join(DST, "correction_log.json"), "w"), indent=1)
    st = {}
    for r in log:
        st.setdefault((r["cls"], r["status"]), 0)
        st[(r["cls"], r["status"])] += 1
    print({f"{a}:{b}": v for (a, b), v in sorted(st.items())})
    for r in log:
        if r["status"] == "AMBIGUOUS":
            print("AMBIGUOUS", r["image"], r["cls"], r["original_xyxy"], r["reason"])


if __name__ == "__main__":
    main()
