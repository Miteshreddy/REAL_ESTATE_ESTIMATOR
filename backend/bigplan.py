"""Large vector-PDF floor plans (commercial / institutional buildings).

Architect-issued PDFs of hospitals, colleges, offices and hostels differ from small residential plans:
  * walls are drawn as two outlines with hatching (or a grey fill) between them, not as filled shapes;
  * dimensions are written in cm or mm along dimension lines, often with no plinth-area note;
  * one A0/A1 sheet carries 50-150 rooms, grids, dimension chains, schedules and a title block.

This reader works directly on the vector geometry:
  1. units      - "ALL DIMENSIONS ARE IN CENTIMETERS / MM" notes, else inferred;
  2. scale      - every numeric dimension text is matched with the dimension line it sits on
                  (value x unit / line length); the mode of those ratios is the drawing scale, cross-checked
                  with the "SCALE 1:100" text;
  3. walls      - solid / grey fills + regions densely covered by short diagonal hatch strokes, bounded by
                  the wall outlines, rasterised at 25 mm per pixel (no down-sampling of big sheets);
  4. rooms      - the shared room/door/area engine (analyze_masks) with the PDF's own text as labels.
"""
from __future__ import annotations

import math
import re

import cv2
import numpy as np

import nlp

RES = 0.025
LAST = {}  # debug: last wall mask
JOIN_LABELS = False
PT_M = 25.4 / 72 / 1000  # paper metres per PDF point
NUM = re.compile(r"^\d{1,2},\d{3}(?:\.\d{1,2})?$|^\d{2,5}(?:\.\d{1,2})?$")
UNIT_NOTE = [(re.compile(r"(?:DIMENSIONS?|DIMS?\.?)[^.|]{0,40}\b(?:IN\s+)?(?:CENTIMET|CMS?\b)", re.I), 0.01),
             (re.compile(r"(?:DIMENSIONS?|DIMS?\.?)[^.|]{0,40}\b(?:IN\s+)?(?:MILLIMET|MM\b)", re.I), 0.001),
             (re.compile(r"(?:DIMENSIONS?|DIMS?\.?)[^.|]{0,40}\b(?:IN\s+)?(?:METRES?|METERS?|MTRS?)\b", re.I), 1.0)]
# drawing notes and tags that sit inside rooms but are not room names
NOTE = re.compile(r"\b(ABOVE|BELOW|AS PER|LOCATION|CEILING|DETAIL|HIGH|PARTITION|PARAPET|LEVEL|REFER|EXPANSION|JOINT|"
                  r"COVER|SPECS?|THK|THICK|BRICK|R\.?C\.?C|JALI|SHAFT FOR|DN\b|UP\b|SLOPE|OPEN TO SKY|CUT[- ]OUT|LINE OF|"
                  r"DRG|DRAWING|NOTE|SECTION|ELEVATION|GRID|TYP\.?|NOS?\.)", re.I)
TAG = re.compile(r"^(?:[A-Z]{1,3}\d{1,3}[A-Z]?|\d{1,3}|[A-Z]|[+-]?\d+\.\d+|\(?[A-Z]\)?)$")
STD_DEN = [20, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500]


def _lines(page):
    out = []
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            txt = " ".join(s["text"] for s in ln["spans"]).strip()
            if txt:
                x0, y0, x1, y1 = ln["bbox"]
                d = ln.get("dir", (1, 0))
                out.append((txt, x0, y0, x1, y1, abs(d[1]) > abs(d[0])))
    return out


def _segments(drawings):
    """All straight segments (x0, y0, x1, y1, width) of the page, and filled paths."""
    segs, fills, widths = [], [], []
    for d in drawings:
        n0 = len(segs)
        fill = d.get("fill")
        if fill is not None and d.get("rect") is not None:
            lum = 0.299 * fill[0] + 0.587 * fill[1] + 0.114 * fill[2]
            fills.append((d, lum))
        for it in d.get("items", []):
            if it[0] == "l":
                p, q = it[1], it[2]
                segs.append((p.x, p.y, q.x, q.y))
            elif it[0] == "re":
                r = it[1]
                segs += [(r.x0, r.y0, r.x1, r.y0), (r.x1, r.y0, r.x1, r.y1), (r.x1, r.y1, r.x0, r.y1), (r.x0, r.y1, r.x0, r.y0)]
            elif it[0] == "qu":
                qd = it[1]
                pts = [qd.ul, qd.ur, qd.lr, qd.ll, qd.ul]
                segs += [(a.x, a.y, b.x, b.y) for a, b in zip(pts, pts[1:])]
        widths += [round(d.get("width") or 0, 2)] * (len(segs) - n0)
    _segments.widths = np.array(widths, float)
    return np.array(segs, float).reshape(-1, 4), fills


def detect_unit(texts):
    blob = " | ".join(texts)
    for rx, u in UNIT_NOTE:
        if rx.search(blob):
            return u, "stated on the drawing"
    return None, None


def detect_scale(page, lines, segs, unit):
    """metres per PDF point, from dimension texts vs the dimension lines they label."""
    nums = [(float(t.replace(',', '')), x0, y0, x1, y1, vert) for t, x0, y0, x1, y1, vert in lines if NUM.match(t.strip())]
    if not len(segs) or not nums:
        return None, None, 0
    dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
    L = np.hypot(dx, dy)
    hor = (np.abs(dy) < 0.02 * np.maximum(L, 1e-6)) & (L > 8)
    ver = (np.abs(dx) < 0.02 * np.maximum(L, 1e-6)) & (L > 8)
    H = segs[hor]
    V = segs[ver]
    Hx0, Hx1 = np.minimum(H[:, 0], H[:, 2]), np.maximum(H[:, 0], H[:, 2])
    Vy0, Vy1 = np.minimum(V[:, 1], V[:, 3]), np.maximum(V[:, 1], V[:, 3])
    ratios = []
    for v, x0, y0, x1, y1, vert in nums:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        th = (x1 - x0) if vert else (y1 - y0)  # text height
        if not vert:
            # a horizontal line just below/above the text whose span is centred on the text
            m = (Hx0 < cx) & (Hx1 > cx) & (np.abs(H[:, 1] - cy) < 1.6 * th) & (np.abs((Hx0 + Hx1) / 2 - cx) < 0.15 * (Hx1 - Hx0) + 2)
            cand = (Hx1 - Hx0)[m]
        else:
            m = (Vy0 < cy) & (Vy1 > cy) & (np.abs(V[:, 0] - cx) < 1.6 * th) & (np.abs((Vy0 + Vy1) / 2 - cy) < 0.15 * (Vy1 - Vy0) + 2)
            cand = (Vy1 - Vy0)[m]
        if len(cand):
            ratios.append(v / float(np.min(cand)))  # shortest = the dimension segment itself
            LAST.setdefault("dims", []).append((v, vert, float(np.min(cand))))
    if len(ratios) < 4:
        return None, None, len(ratios)
    r = np.log(np.array(ratios))
    hist, edges = np.histogram(r, bins=np.arange(r.min() - 0.02, r.max() + 0.04, 0.02))
    i = int(hist.argmax())
    sel = r[(r >= edges[max(0, i - 1)]) & (r <= edges[min(len(edges) - 1, i + 2)])]
    val_per_pt = float(np.exp(np.median(sel)))
    support = int(len(sel))
    # combine with the unit: m per pt = val_per_pt * unit; pick the unit giving a standard scale when unknown
    best = None
    for u in ([unit] if unit else [0.001, 0.01, 1.0]):
        den = val_per_pt * u / PT_M
        near = min(STD_DEN, key=lambda s: abs(math.log(den / s)))
        err = abs(math.log(den / near))
        if best is None or err < best[2]:
            best = (u, den, err, near)
    u, den, err, near = best
    if err < 0.03:
        den = near  # snap to the standard scale when the measurement agrees with it
    return den * PT_M, u, support


def wall_mask(drawings, segs, fills, f, shape):
    """Walls from solid / grey fills and from hatching (dense short diagonal strokes)."""
    H, W = shape
    solid = np.zeros((H, W), np.uint8)
    for d, lum in fills:
        if lum < 0.85:
            r = d["rect"]
            if r.width * f < 3 and r.height * f < 3:
                continue
            if r.width * f * r.height * f > 0.02 * H * W:  # page background / title-block panels
                continue
            for it in d["items"]:
                if it[0] == "re":
                    q = it[1]
                    cv2.rectangle(solid, (int(q.x0 * f), int(q.y0 * f)), (int(q.x1 * f), int(q.y1 * f)), 1, -1)
                elif it[0] in ("l", "qu", "c"):
                    pass
            pts = []
            for it in d["items"]:
                if it[0] == "l":
                    pts += [it[1], it[2]]
                elif it[0] == "c":
                    pts += [it[1], it[4]]
                elif it[0] == "qu":
                    pts += [it[1].ul, it[1].ur, it[1].lr, it[1].ll]
            if len(pts) >= 3:
                cv2.fillPoly(solid, [np.array([[p.x * f, p.y * f] for p in pts], np.int32)], 1)
    hatch = np.zeros((H, W), np.uint8)
    if len(segs):
        dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
        L = np.hypot(dx, dy) * f * RES  # metres
        ang = np.degrees(np.arctan2(np.abs(dy), np.abs(dx)))
        diag = (ang > 20) & (ang < 70) & (L > 0.03) & (L < 0.9)
        for x0, y0, x1, y1 in segs[diag]:
            cv2.line(hatch, (int(x0 * f), int(y0 * f)), (int(x1 * f), int(y1 * f)), 1, 1)
        # hatch strokes are spaced a few cm apart: close the gaps, then drop isolated strokes
        # (dimension ticks, door leaves, section arrows) that do not form a dense patch
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dens = cv2.blur(hatch.astype(np.float32), (9, 9))
        hatch = cv2.morphologyEx(((dens > 0.12) | (hatch > 0)).astype(np.uint8), cv2.MORPH_CLOSE, k)
        n, lab, st, _ = cv2.connectedComponentsWithStats(hatch, connectivity=8)
        keep = np.zeros(n, bool)
        for i in range(1, n):
            w_, h_, a_ = st[i, 2], st[i, 3], st[i, 4]
            # wall patches are long and thin; reject big blobs (hatched floors/landscape) and specks
            if a_ >= 12 and max(w_, h_) >= 8 and a_ <= 0.6 * w_ * h_ + 40:
                keep[i] = True
            elif 12 <= a_ <= 900:  # short wall stubs and piers
                keep[i] = True
        hatch = keep[lab].astype(np.uint8)
        # trim the patch back to the drawn wall outline: all strokes split the sheet into cells; a wall is
        # made of the small cells (between hatch strokes and the two outlines) lying inside the patch
        ink = np.zeros((H, W), np.uint8)
        for x0, y0, x1, y1 in segs:
            cv2.line(ink, (int(x0 * f), int(y0 * f)), (int(x1 * f), int(y1 * f)), 1, 1)
        n, cell = cv2.connectedComponents(1 - ink, connectivity=4)
        area = np.bincount(cell.ravel(), minlength=n)
        inside = np.bincount(cell.ravel(), weights=hatch.ravel().astype(np.float64), minlength=n)
        ok = (inside >= 0.85 * area) & (area <= 0.4 / (RES * RES))
        ok[0] = False
        trimmed = (ok[cell] | ((ink > 0) & (hatch > 0))).astype(np.uint8)
        trimmed[cell == 0] = 0
        trimmed |= (ink & hatch)
        hatch = cv2.morphologyEx(trimmed, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return solid, hatch


def outline_walls(segs, f, shape, t_lo=0.05, t_hi=0.45):
    """Walls drawn as two parallel outlines (no fill / hatch): fill between paired parallel lines."""
    H, W = shape
    m = np.zeros((H, W), np.uint8)
    if not len(segs):
        return m
    dx, dy = segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]
    L = np.hypot(dx, dy) * f * RES
    for axis in (0, 1):
        sel = (np.abs(dy if axis == 0 else dx) < 1e-3 * np.maximum(1, np.abs(dx if axis == 0 else dy))) & (L > 0.4)
        S = segs[sel]
        if not len(S):
            continue
        pos = (S[:, 1] if axis == 0 else S[:, 0]) * f * RES
        a0 = np.minimum(S[:, 0], S[:, 2]) if axis == 0 else np.minimum(S[:, 1], S[:, 3])
        a1 = np.maximum(S[:, 0], S[:, 2]) if axis == 0 else np.maximum(S[:, 1], S[:, 3])
        order = np.argsort(pos)
        pos, a0, a1 = pos[order], a0[order] * f, a1[order] * f
        j0 = 0
        for i in range(len(pos)):
            while pos[i] - pos[j0] > t_hi:
                j0 += 1
            for j in range(j0, i):
                d = pos[i] - pos[j]
                if d < t_lo:
                    continue
                lo, hi = max(a0[i], a0[j]), min(a1[i], a1[j])
                if hi - lo < 0.4 / RES:
                    continue
                p, q = int(pos[j] / RES), int(pos[i] / RES)
                if axis == 0:
                    m[p:q + 1, int(lo):int(hi) + 1] = 1
                else:
                    m[int(lo):int(hi) + 1, p:q + 1] = 1
    return m


def door_closers(drawings, f, m_per_pt):
    """Door swings are drawn as arcs about the hinge (one quarter curve or several pieces). The circle
    centre is where the normals at both ends of a curve piece meet; the doorway is closed along the radii
    so spaces do not leak through door openings. Returns pixel line segments and the door list."""
    lines, doors = [], []
    for d in drawings:
        for it in d.get("items", []):
            if it[0] != "c":
                continue
            p1, c1, c2, p2 = it[1], it[2], it[3], it[4]
            t1 = np.array([c1.x - p1.x, c1.y - p1.y])
            t2 = np.array([p2.x - c2.x, p2.y - c2.y])
            if np.linalg.norm(t1) < 1e-6 or np.linalg.norm(t2) < 1e-6:
                continue
            n1, n2 = np.array([-t1[1], t1[0]]), np.array([-t2[1], t2[0]])
            A = np.array([n1, -n2]).T
            if abs(np.linalg.det(A)) < 1e-9:
                continue
            s_ = np.linalg.solve(A, np.array([p2.x - p1.x, p2.y - p1.y]))
            cx, cy = p1.x + s_[0] * n1[0], p1.y + s_[0] * n1[1]
            r1, r2 = math.hypot(p1.x - cx, p1.y - cy), math.hypot(p2.x - cx, p2.y - cy)
            r_m = (r1 + r2) / 2 * m_per_pt
            if not (0.45 <= r_m <= 1.6) or abs(r1 - r2) > 0.08 * max(r1, r2):
                continue
            for q in (p1, p2):
                lines.append(((int(cx * f), int(cy * f)), (int(q.x * f), int(q.y * f))))
            doors.append(dict(x=cx * f, y=cy * f, w=round(r_m, 2)))
    return lines, doors


def cm_labels(text, unit):
    """'240x394.5' in a cm drawing -> '2.40x3.945' so the shared label parser reads metres."""
    if unit in (None, 1.0):
        return text

    def conv(m):
        a, b = float(m.group(1)), float(m.group(2))
        return f"{a * unit:.3f}x{b * unit:.3f}"
    return re.sub(r"(\d{2,5}(?:\.\d+)?)\s*[xX×\*]\s*(\d{2,5}(?:\.\d+)?)", conv, text)


def read_page(page, models, analyze_masks, finish_sheet, text_kind, docparse, scale_hint_den=None):
    """Returns (result dict or None, diagnostics)."""
    LAST.clear()
    lines = _lines(page)
    texts = [t[0] for t in lines]
    drawings = page.get_drawings()
    segs, fills = _segments(drawings)
    unit, unit_src = detect_unit(texts)
    m_per_pt, unit2, support = detect_scale(page, lines, segs, unit)
    diag = dict(unit=unit, unit_source=unit_src, dim_matches=support)
    note = nlp.parse_project_notes(texts)
    if m_per_pt is None:
        den = scale_hint_den or note.get("scale_den")
        if not den:
            return None, dict(diag, reason="no scale")
        m_per_pt, method = den * PT_M, f"title text SCALE 1:{den}"
    else:
        unit = unit or unit2
        method = f"{support} dimension strings matched to their dimension lines (1:{m_per_pt / PT_M:.0f}, unit {'cm' if unit == 0.01 else 'mm' if unit == 0.001 else 'm'})"
    f = m_per_pt / RES  # px per pt
    Wp, Hp = int(page.rect.width * f) + 1, int(page.rect.height * f) + 1
    if Wp * Hp > 60e6:
        return None, dict(diag, reason="sheet too large")
    solid, hatch = wall_mask(drawings, segs, fills, f, (Hp, Wp))
    # wall outlines are drawn with their own pen weight: learn it from the outlines of the hatched walls,
    # so grid / dimension / furniture lines (other weights) are not paired into false walls
    widths = _segments.widths
    osegs = segs
    if hatch.sum() and len(segs):
        edge = cv2.dilate(hatch, np.ones((3, 3), np.uint8)) - cv2.erode(hatch, np.ones((3, 3), np.uint8))
        mx = np.clip(((segs[:, 0] + segs[:, 2]) / 2 * f).astype(int), 0, Wp - 1)
        my = np.clip(((segs[:, 1] + segs[:, 3]) / 2 * f).astype(int), 0, Hp - 1)
        Lm = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1]) * f * RES
        on = (edge[my, mx] > 0) & (Lm > 0.3)
        if on.sum() >= 20:
            ws, cnt = np.unique(widths[on], return_counts=True)
            order = np.argsort(-cnt)
            keep, acc = [], 0
            for i in order:
                keep.append(ws[i])
                acc += cnt[i]
                if acc >= 0.8 * cnt.sum():
                    break
            osegs = segs[np.isin(widths, keep)]
            LAST["wall_widths"] = keep
    outl = outline_walls(osegs, f, (Hp, Wp))
    core = (solid | hatch).astype(np.uint8)
    # paired outlines (thin partitions, window bands, outline-only walls) count as wall where they connect
    # to the hatched / filled structure, or everywhere when the drawing has no hatching at all
    if core.sum() * RES * RES < 3.0:
        wall, wall_src = (core | outl).astype(np.uint8), "parallel outlines"
    else:
        n_, lab_, _, _ = cv2.connectedComponentsWithStats((core | outl).astype(np.uint8), connectivity=8)
        touch = np.zeros(n_, bool)
        touch[np.unique(lab_[core > 0])] = True
        touch[0] = False
        wall, wall_src = touch[lab_].astype(np.uint8), "hatch/fill + connected outlines"
    # single partition lines (shower screens, glazed partitions): straight lines in the wall pen weight
    # running from one wall to another
    if False and osegs is not segs and len(osegs):  # tried: wall-to-wall single lines as partitions - cut real rooms, net worse
        base = wall.copy()
        for x0, y0, x1, y1 in osegs:
            L = math.hypot(x1 - x0, y1 - y0) * m_per_pt
            if not (0.5 <= L <= 3.2) or (abs(x1 - x0) > 1e-3 and abs(y1 - y0) > 1e-3):
                continue
            ends = []
            for px, py in ((x0, y0), (x1, y1)):
                cx, cy = int(px * f), int(py * f)
                win = base[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
                ends.append(win.any())
            mid = base[min(Hp - 1, int((y0 + y1) / 2 * f)), min(Wp - 1, int((x0 + x1) / 2 * f))]
            if all(ends) and not mid:
                cv2.line(wall, (int(x0 * f), int(y0 * f)), (int(x1 * f), int(y1 * f)), 1, 2)
    dlines, dlist = door_closers(drawings, f, m_per_pt)
    for a_, b_ in dlines:
        cv2.line(wall, a_, b_, 1, 2)
    # a room name and its size are usually two text lines ("TOILET" / "138.5X180"): join them
    lines = list(lines)
    used = set()
    joined = []
    for i, (t, x0, y0, x1, y1, v) in enumerate(lines):
        if JOIN_LABELS is False or i in used or nlp.parse_pair(cm_labels(t, unit)) or not nlp.looks_like_room_label(t):
            continue
        cx, cy, th = (x0 + x1) / 2, (y0 + y1) / 2, max(y1 - y0, x1 - x0) if v else (y1 - y0)
        best = None
        for j, (u, a0, b0, a1_, b1_, v2) in enumerate(lines):
            if j == i or j in used or not nlp.parse_pair(cm_labels(u, unit)):
                continue
            dx_, dy_ = (a0 + a1_) / 2 - cx, (b0 + b1_) / 2 - cy
            near = (abs(dx_) < 0.8 * th and 0 < dy_ < 3.2 * th) if not v else (abs(dy_) < 0.8 * th and 0 < dx_ < 3.2 * th)
            if near and (best is None or abs(dx_) + abs(dy_) < best[0]):
                best = (abs(dx_) + abs(dy_), j)
        if best:
            used.add(best[1])
            used.add(i)
            joined.append((t + " " + lines[best[1]][0], x0, y0, x1, y1, v))
    lines = [ln for k, ln in enumerate(lines) if k not in used] + joined
    labels = []
    for t, x0, y0, x1, y1, _ in lines:
        t = cm_labels(t, unit)
        if nlp.parse_pair(t) and not nlp.looks_like_room_label(t):
            labels.append((t, (x0 + x1) / 2 * f, (y0 + y1) / 2 * f))
            continue
        t = re.sub(r"\(.*?\)", "", t).strip()
        if not t or TAG.match(t) or NOTE.search(t) or NUM.match(t):
            continue
        labels.append((t, (x0 + x1) / 2 * f, (y0 + y1) / 2 * f))
    rows = docparse.group_rows([(w[4], w[0], w[1], w[2], w[3]) for w in page.get_text("words")])
    # keep only the building: drop wall specks far from the main structure (title-block logos etc.)
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(wall, np.ones((41, 41), np.uint8)), connectivity=8)
    if n > 1:
        big = 1 + int(np.argmax(st[1:, 4]))
        tot = st[1:, 4].sum()
        keep = np.zeros(n, bool)
        for i in range(1, n):
            if st[i, 4] >= 0.08 * tot or i == big:
                keep[i] = True
        wall = (wall & keep[lab]).astype(np.uint8)
    LAST.update(wall=wall, f=f)
    res = analyze_masks(wall, wall.copy(), RES, labels, None, None, None, models.room_label, models.room_geom,
                        detect_openings=True, close_m=1.25, precise=True)
    # overall building size written on the drawing: the longest dimension string in each direction
    # whose value agrees with its line length at the detected scale
    od = {}
    for v, vert, Lpt in LAST.get("dims", []):
        if abs(v * (unit or 1) / (Lpt * m_per_pt) - 1) < 0.03:
            od[vert] = max(od.get(vert, 0), v * (unit or 1))
    diag.update(overall_written=(round(od.get(False, 0), 2), round(od.get(True, 0), 2)))
    diag.update(wall_source=wall_src, wall_m2=round(float(wall.sum() * RES * RES), 1), scale=method)
    res["_labels"] = labels
    res["scale"] = dict(method=method, scale_den=round(m_per_pt / PT_M), confidence=0.95 if support >= 8 else 0.8)
    return res, diag
