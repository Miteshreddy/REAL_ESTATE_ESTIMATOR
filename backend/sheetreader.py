"""Reading real drawing sheets: several views per sheet, rotated text, text drawn as outlines.

1. OCR the sheet in three orientations and merge the results into one set of text boxes.
2. Split the sheet into views (connected regions of ink) and identify tables / title blocks.
3. Pick the floor-plan view (the region that forms enclosed rooms, near a "PLAN" title).
4. Find the scale from the overall dimension strings around the plan (e.g. 11610 mm), cross-checked
   with a "PLINTH AREA" note when the sheet has one.
"""
from __future__ import annotations

import math
import re

import cv2
import numpy as np

import parsers

NUM = re.compile(r"^\D{0,2}(\d{3,5})(?:\s*[\[(].*)?$")
DEBUG = False
PLINTH = re.compile(r"PLINTH\s*AREA\D{0,6}(\d+(?:\.\d+)?)\s*(SQ\.?\s*M|SQM|M2|SQ\.?\s*FT|SFT)?", re.I)


def ocr_all(img: np.ndarray):
    """OCR at 0, 90 and 270 degrees; boxes mapped back to the unrotated image; duplicates removed."""
    H, W = img.shape[:2]
    out = []
    for rot in (0, 1, 3):
        im = np.ascontiguousarray(np.rot90(img, rot))
        for t, x0, y0, x1, y1 in parsers.ocr(im):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if rot == 1:      # rot90 counter-clockwise: (x, y) in rotated = (y', W-1-x')
                cx, cy = W - 1 - cy, cx
                bw, bh = (y1 - y0), (x1 - x0)
            elif rot == 3:
                cx, cy = cy, H - 1 - cx
                bw, bh = (y1 - y0), (x1 - x0)
            else:
                bw, bh = (x1 - x0), (y1 - y0)
            out.append((t, cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, rot))
    # de-duplicate: the same text read in two orientations -> keep the longer reading
    out.sort(key=lambda w: -len(w[0]))
    kept = []
    for w in out:
        cx, cy = (w[1] + w[3]) / 2, (w[2] + w[4]) / 2
        if any(abs(cx - (k[1] + k[3]) / 2) < 12 and abs(cy - (k[2] + k[4]) / 2) < 12 for k in kept):
            continue
        kept.append(w)
    return kept


def views(gray: np.ndarray):
    """Regions of the sheet that hold separate drawings (plan, elevation, section, tables …)."""
    H, W = gray.shape
    ink = (gray < 160).astype(np.uint8)
    # erase the sheet border / title-block frame: straight lines longer than 45% of the sheet
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(W * 0.45), 1)))
    vl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.45))))
    ink = ink & ~(cv2.dilate(hl | vl, np.ones((5, 5), np.uint8)))
    k = max(15, int(min(H, W) * 0.008))
    blob = cv2.dilate(ink, np.ones((k, k), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
    regs = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if w > 0.92 * W or h > 0.92 * H:  # frame
            continue
        if w * h < 0.015 * W * H:
            continue
        sub = ink[y:y + h, x:x + w]
        # table-like: many long straight horizontal + vertical lines and lots of text
        hl = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 3), 1))).sum()
        vl = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 3)))).sum()
        regs.append(dict(box=(int(x), int(y), int(w), int(h)), ink=float(sub.mean()), tableness=float((hl + vl) / max(1, sub.sum()))))
    # if the frame swallowed everything, retry inside the frame
    if not regs:
        regs = [dict(box=(0, 0, W, H), ink=float(ink.mean()), tableness=0.0)]
    return regs


PLAN_T = re.compile(r"^\W*((GROUND|FIRST|SECOND|THIRD|TYPICAL|TOP)\s*(FLOOR)?\s*)?PLAN\W*$")
ELEV_T = re.compile(r"^\W*((FRONT|SIDE|REAR|BACK|NORTH|SOUTH|EAST|WEST)\s*)?ELEVATION\W*$")
SECT_T = re.compile(r"^\W*SECTION\b.{0,14}$")


def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / max(1, aw * ah + bw * bh - inter)


def plan_box_by_walls(gray: np.ndarray):
    """Candidate drawing views on a busy sheet: clusters of walls predicted by the segmentation model
    (tables, notes and title blocks carry no walls). Returns [((x, y, w, h), relative wall mass), ...]."""
    import segmodel
    if not segmodel.available():
        return None
    H, W = gray.shape
    g = gray.copy()
    ink = (g < 160).astype(np.uint8)
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(W * 0.45), 1)))
    vl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.45))))
    g[cv2.dilate(hl | vl, np.ones((7, 7), np.uint8)) > 0] = 255  # erase the sheet frame
    cls, _ = segmodel.segment(g, long_side=1800)
    wall = (cls == 1).astype(np.uint8)
    if wall.sum() < 50:
        return None
    out = []
    for frac in (0.02, 0.045):  # two clustering scales: tight views, and whole plans drawn in parts
        k = max(9, int(min(H, W) * frac))
        blob = cv2.dilate(wall, np.ones((k, k), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(blob, connectivity=8)
        wsum = np.bincount(lab.ravel(), weights=wall.ravel().astype(np.float64), minlength=n)
        order = [i for i in np.argsort(-wsum) if i > 0 and wsum[i] > 0.08 * wsum[1:].max()][:5]
        for i in order:
            x, y, w, h = st[i][:4]
            m = int(0.03 * max(w, h))
            x0, y0 = max(0, x - m), max(0, y - m)
            out.append(((int(x0), int(y0), int(min(W - x0, w + 2 * m)), int(min(H - y0, h + 2 * m))), float(wsum[i] / wsum[1:].max())))
    return out


def tableness(gray, box):
    """Schedule tables / title blocks: several horizontal lines spanning ~the full width AND several
    vertical lines spanning ~the full height (floor plans almost never have that). Returns 0..1."""
    x, y, w, h = box
    sub = (gray[y:y + h, x:x + w] < 160).astype(np.uint8)
    if sub.sum() == 0 or w < 20 or h < 20:
        return 0.0
    hl = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.8), 1)))
    vl = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(h * 0.8))))
    nh = int(np.sum(np.diff((hl.sum(1) > 0).astype(np.int8)) == 1))
    nv = int(np.sum(np.diff((vl.sum(0) > 0).astype(np.int8)) == 1))
    return float(min(1.0, (nh / 6.0) * (nv / 3.0))) if nh >= 4 and nv >= 2 else 0.0


def words_in(words, box, pad=0.0):
    x, y, w, h = box
    px, py = w * pad, h * pad
    return [wd for wd in words if x - px <= (wd[1] + wd[3]) / 2 <= x + w + px and y - py <= (wd[2] + wd[4]) / 2 <= y + h + py]


def dimension_scale(env_w_px, env_h_px, nums, t_ext=0.23):
    """Find metres-per-pixel so that the envelope's width and height match written overall dimensions.

    Overall dimensions may be centre-line or outer, so +/- one wall thickness is tolerated."""
    best = None
    for a in nums:
        for b in nums:
            for (dw, dh) in ((a, b),):
                sw, sh = dw / env_w_px, dh / env_h_px
                if sw <= 0 or sh <= 0:
                    continue
                err = abs(sw - sh) / ((sw + sh) / 2)
                if err < 0.03 and (best is None or err < best[1]):
                    best = ((sw + sh) / 2, err, dw, dh)
    return best


def plinth_area_m2(texts):
    """Written plinth area in m2. Tamil Nadu notes give both units ("97.06 sq.m / 1044.40 sq.ft");
    OCR digit errors are caught by requiring the pair to agree (1 m2 = 10.764 sq.ft)."""
    best = None
    for t in texts:
        u = t.upper().replace(",", "")
        if "PLINTH" not in u and "AREA" not in u:
            continue
        m2 = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:SQ\.?\s*M\b|SQ\.?\s*MT|SQM|M2|SQ\.?\s*M\.)", u)]
        ft = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?:SQ\.?\s*FT|SFT|SQ\.?\s*FEET)", u)]
        if not m2 and not ft:
            m = PLINTH.search(u)
            if m:
                v = float(m.group(1))
                m2 = [v] if not (m.group(2) and "F" in m.group(2)) else []
                ft = [v] if (m.group(2) and "F" in m.group(2)) else []
        for a in m2:
            for f in ft:
                if f > 0 and abs(a * 10.764 / f - 1) < 0.02:
                    return a, "m² and sq ft agree"
        if m2 and ft:
            # disagreement: one of the two was misread - trust the reading with more digits (sq ft has
            # 3-4 integer digits, harder to misread consistently); keep it as a fallback
            best = best or (ft[0] / 10.764, "from sq ft (m² reading inconsistent)")
        elif m2 and best is None:
            best = (m2[0], "m² only")
        elif ft and best is None:
            best = (ft[0] / 10.764, "sq ft only")
    return best


def read_sheet(img: np.ndarray, models, source="image", sheet_name="Sheet"):
    """Analyse a full sheet image. Returns a list of sheet results (the plan view + text info)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    words = ocr_all(img)
    rows = parsers.docparse.group_rows([(w[0], w[1], w[2], w[3], w[4]) for w in words], tol=8)
    texts = [r[0] for r in rows] + [w[0] for w in words]
    regs = [dict(r, by_walls=False, mass=0.0) for r in views(gray)]
    for box, mass in (plan_box_by_walls(gray) or []):
        regs.insert(0, dict(box=box, ink=0.0, tableness=tableness(gray, box), by_walls=True, mass=mass))
    # de-duplicate near-identical candidate boxes
    uniq = []
    for rg in regs:
        if all(_iou(rg["box"], u["box"]) < 0.75 for u in uniq):
            uniq.append(rg)
    regs = uniq
    Hs, Ws = gray.shape
    diag = math.hypot(Ws, Hs)
    titles = []
    for w in words:
        t = w[0].strip().upper()
        cx, cy = (w[1] + w[3]) / 2, (w[2] + w[4]) / 2
        if PLAN_T.match(t):
            titles.append(("plan", cx, cy))
        elif ELEV_T.match(t):
            titles.append(("elevation", cx, cy))
        elif SECT_T.match(t):
            titles.append(("section", cx, cy))
        elif re.search(r"SCHEDULE|IMPORTANT\s*NOTES|NOTES\s*:", t):
            titles.append(("table", cx, cy))
    best = None
    cands = []
    for rg in regs[:9]:
        if rg["tableness"] > 0.6:
            continue
        x, y, w, h = rg["box"]
        if w * h < 0.01 * Ws * Hs:
            continue
        crop = img[y:y + h, x:x + w]
        local = [(t, x0 - x, y0 - y, x1 - x, y1 - y) for t, x0, y0, x1, y1, _ in words_in(words, rg["box"], 0.02)]
        try:
            res = parsers.analyze_image_array(crop, models, _words=local, _note="layout")
        except Exception:
            continue
        rooms = res.get("rooms", [])
        named = sum(1 for r_ in rooms if r_.get("type_source") == "label-nlp" and r_.get("type_conf", 0) >= 0.6)
        m_ = res.get("metrics") or {}
        fill = (m_.get("carpet_area", 0) / m_["plinth_area"]) if m_.get("plinth_area") else 0
        # view title: a title belongs to the candidate view it is nearest to (by distance to the view
        # centre, so a neighbouring view's title is not stolen); within 15% of the sheet diagonal
        lab_ = None
        for kind, cx, cy in titles:
            def dist(bx):
                X, Y, W_, H_ = bx
                dx = max(X - cx, 0, cx - (X + W_))
                dy = max(Y - cy, 0, cy - (Y + H_))
                return math.hypot(dx, dy) + 0.25 * math.hypot(cx - (X + W_ / 2), cy - (Y + H_ / 2))
            owner = min((r_["box"] for r_ in regs if r_["tableness"] <= 0.6), key=dist, default=None)
            if owner is not None and _iou(owner, rg["box"]) > 0.5 and dist(rg["box"]) / diag < 0.15:
                if lab_ is None or kind == "plan":
                    lab_ = kind
        score = min(len(rooms), 15) * 0.5 + named * 1.5 + (1 if res.get("openings") else 0) + 3 * min(fill, 1.0)             + (2 * rg.get("mass", 0) if rg["by_walls"] else 0) - 3 * rg["tableness"]
        score += {"plan": 8, "elevation": -8, "section": -8, "table": -6}.get(lab_, 0)
        cands.append(dict(box=rg["box"], score=round(score, 2), title=lab_, rooms=len(rooms), named=named, fill=round(fill, 2)))
        if len(rooms) >= 2 and (best is None or score > best[0]):
            best = (score, rg, res, crop, local, lab_, named)
    # a sheet without a plan title and without any named room has no floor plan (elevation / section sheets)
    if best is not None and best[5] != "plan" and best[6] == 0 and any(t[0] in ("elevation", "section") for t in titles):
        best = None
    if best is None:
        return None, dict(words=words, rows=rows, texts=texts, cands=cands)
    _, rg, res, crop, local, _, _ = best
    # the picked view may hold only part of the building: grow the crop and keep it if the building
    # structure found in the larger crop still contains the picked view centre and is larger
    x, y, w, h = rg["box"]
    for grow in (0.25, 0.5):
        gx, gy = int(max(0, x - w * grow)), int(max(0, y - h * grow))
        gw, gh = int(min(Ws - gx, w * (1 + 2 * grow))), int(min(Hs - gy, h * (1 + 2 * grow)))
        crop2 = img[gy:gy + gh, gx:gx + gw]
        local2 = [(t, x0 - gx, y0 - gy, x1 - gx, y1 - gy) for t, x0, y0, x1, y1, _ in words_in(words, (gx, gy, gw, gh), 0.0)]
        try:
            r2 = parsers.analyze_image_array(crop2, models, _words=local2, _note="layout")
        except Exception:
            continue
        if "px_per_m" not in (r2.get("scale") or {}) or not r2.get("envelope") or "px_per_m" not in (res.get("scale") or {}):
            break  # the larger crop reads as a text / section sheet: keep the original view
        env = np.array(r2.get("envelope") or [[0, 0]], float)
        kk = r2["scale"]["px_per_m"]
        fr = r2.get("frame") or {}
        # envelope bbox in crop pixels
        ex0 = (env[:, 0].min() + fr.get("ox", 0)) * kk
        ex1 = (env[:, 0].max() + fr.get("ox", 0)) * kk
        ey0 = (env[:, 1].min() + fr.get("oy", 0)) * kk
        ey1 = (env[:, 1].max() + fr.get("oy", 0)) * kk
        cx, cy = x + w / 2 - gx, y + h / 2 - gy
        bigger = (r2["metrics"].get("plinth_area", 0) * kk * kk) > 1.08 * (res["metrics"].get("plinth_area", 0) * res["scale"]["px_per_m"] ** 2)
        if DEBUG:
            print("grow", grow, dict(inside=bool(ex0 <= cx <= ex1 and ey0 <= cy <= ey1), bigger=bigger, rooms=(len(r2.get("rooms", [])), len(res.get("rooms", []))),
                                     area=(r2["metrics"].get("plinth_area"), res["metrics"].get("plinth_area"))), flush=True)
        not_huge = (r2["metrics"].get("plinth_area", 0) * kk * kk) < 3.0 * (res["metrics"].get("plinth_area", 0) * res["scale"]["px_per_m"] ** 2)
        if ex0 <= cx <= ex1 and ey0 <= cy <= ey1 and bigger and not_huge and len(r2.get("rooms", [])) >= 2:
            rg = dict(rg, box=(gx, gy, gw, gh))
            res, crop, local = r2, crop2, local2
        else:
            break
    # ---- scale from dimension strings around the plan, or the plinth-area note
    x, y, w, h = rg["box"]
    near = words_in(words, rg["box"], 0.12)
    nums = sorted({int(m.group(1)) for wd in near for m in [NUM.match(wd[0].replace(",", "").replace(" ", ""))] if m and 1500 <= int(m.group(1)) <= 60000})
    env = np.array(res.get("envelope") or [[0, 0]])
    k_crop = res["scale"]["px_per_m"]          # provisional px per metre of the first pass
    env_w_px = (env[:, 0].max() - env[:, 0].min()) * k_crop
    env_h_px = (env[:, 1].max() - env[:, 1].min()) * k_crop
    scale_note, px_per_m = None, None
    ds = dimension_scale(env_w_px, env_h_px, [n / 1000 for n in nums]) if env_w_px > 10 and env_h_px > 10 else None
    if ds:
        px_per_m = 1 / ds[0]
        scale_note = f"from written overall dimensions {ds[2] * 1000:.0f} × {ds[3] * 1000:.0f} mm"
    blob_ = " ".join(texts)
    windows_ = [blob_[m_.start():m_.start() + 160] for m_ in re.finditer(r"PLINTH", blob_, re.I)]
    pa = plinth_area_m2(windows_ + texts)
    if pa:
        val = pa[0]
        area_px = res["metrics"]["plinth_area"] * k_crop * k_crop
        p_from_area = math.sqrt(area_px / val) if val > 0 else None
        if px_per_m is None and p_from_area:
            px_per_m = p_from_area
            scale_note = f"from the plinth area note ({val:.2f} m²)"
        elif p_from_area:
            dev = abs(p_from_area / px_per_m - 1)
            if dev > 0.06:  # dimension strings were paired wrongly - the written plinth area is authoritative
                px_per_m = p_from_area
                scale_note = f"from the plinth area note ({val:.2f} m²); overall dimensions did not agree"
            else:
                scale_note += f"; plinth area note {val:.2f} m² agrees within {dev * 100:.1f}%"
    if px_per_m:
        res = parsers.analyze_image_array(crop, models, px_per_m=px_per_m, _words=local, _note=scale_note)
        res["scale"]["confidence"] = 0.95 if ds else 0.85
    if pa and res.get("metrics", {}).get("plinth_area"):
        # the written plinth area is authoritative: a traced envelope far from it has picked up other views
        # (elevation / section / site boxes) — TNRD cement godown: 607 m² traced vs 80.49 m² written
        traced = res["metrics"]["plinth_area"]
        if abs(traced / pa[0] - 1) > 0.25:
            res["metrics"]["plinth_area_traced"] = traced
            res["metrics"]["plinth_area"] = round(pa[0], 2)
            res["plinth_note_override"] = (f"traced envelope {traced:.1f} m² disagrees with the written plinth area {pa[0]:.2f} m² "
                                           "by more than 25 % — written value used; room polygons need review")
    res["texts"] = texts[:400]
    res["view_box"] = list(rg["box"])
    res["_sheet_preview"] = img
    res["view_candidates"] = cands
    return res, dict(words=words, rows=rows, texts=texts, cands=cands)
