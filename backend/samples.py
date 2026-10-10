"""Synthetic floor-plan generator.

Produces ground-truth plans (metres) and renders them to DXF / vector PDF / raster PNG.
Used for (a) the "Try a sample" demo drawings and (b) generating training data for the ML models.
"""
from __future__ import annotations

import math
import random
from typing import Any

import numpy as np

T_EXT, T_INT = 0.23, 0.115
ROOM_SEQ = ["LIVING ROOM", "KITCHEN", "MASTER BEDROOM", "BEDROOM 2", "TOILET", "DINING", "BEDROOM 3",
            "TOILET 2", "STUDY", "STORE", "POOJA", "UTILITY"]


def _split(rect, rng, depth, out, splits):
    x, y, w, h = rect
    can_v, can_h = w > 5.4, h > 5.4
    if depth <= 0 or not (can_v or can_h) or (depth < 3 and rng.random() < 0.18):
        out.append(rect)
        return
    vertical = can_v and (not can_h or (w > h if rng.random() < 0.8 else rng.random() < 0.5))
    if vertical:
        cut = round(rng.uniform(2.7, w - 2.7) * 10) / 10
        splits.append(("v", x + cut, y, y + h))
        _split((x, y, cut, h), rng, depth - 1, out, splits)
        _split((x + cut, y, w - cut, h), rng, depth - 1, out, splits)
    else:
        cut = round(rng.uniform(2.7, h - 2.7) * 10) / 10
        splits.append(("h", y + cut, x, x + w))
        _split((x, y, w, cut), rng, depth - 1, out, splits)
        _split((x, y + cut, w, h - cut), rng, depth - 1, out, splits)


def _merge_intervals(iv):
    iv = sorted(iv)
    out = []
    for a, b in iv:
        if out and a <= out[-1][1] + 1e-6:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def generate_plan(seed: int | None = None, W: float | None = None, H: float | None = None) -> dict[str, Any]:
    rng = random.Random(seed)
    W = W or round(rng.uniform(9.0, 15.0), 1)
    H = H or round(rng.uniform(8.0, 13.0), 1)
    rects, splits = [], []
    _split((0.0, 0.0, W, H), rng, 4, rects, splits)
    # names: biggest = living, smallest = toilets
    order = sorted(range(len(rects)), key=lambda i: -rects[i][2] * rects[i][3])
    names = [""] * len(rects)
    small = sorted(range(len(rects)), key=lambda i: rects[i][2] * rects[i][3])
    toilet_ids = small[: max(1, len(rects) // 4)]
    seq = [n for n in ROOM_SEQ if not n.startswith("TOILET")]
    k = 0
    for i in order:
        if i in toilet_ids:
            continue
        names[i] = seq[k % len(seq)] if k < len(seq) else f"ROOM {k}"
        k += 1
    for j, i in enumerate(toilet_ids):
        names[i] = "TOILET" if j == 0 else f"TOILET {j + 1}"

    # walls: merge collinear edges
    hs, vs = {}, {}
    for (x, y, w, h) in rects:
        hs.setdefault(round(y, 3), []).append((x, x + w))
        hs.setdefault(round(y + h, 3), []).append((x, x + w))
        vs.setdefault(round(x, 3), []).append((y, y + h))
        vs.setdefault(round(x + w, 3), []).append((y, y + h))
    walls = []
    for yy, iv in hs.items():
        ext = abs(yy) < 1e-6 or abs(yy - H) < 1e-6
        for a, b in _merge_intervals(iv):
            walls.append(dict(x1=a, y1=yy, x2=b, y2=yy, t=T_EXT if ext else T_INT, ext=ext))
    for xx, iv in vs.items():
        ext = abs(xx) < 1e-6 or abs(xx - W) < 1e-6
        for a, b in _merge_intervals(iv):
            walls.append(dict(x1=xx, y1=a, x2=xx, y2=b, t=T_EXT if ext else T_INT, ext=ext))
    for i, w in enumerate(walls):
        w["id"] = f"W{i + 1}"

    openings = []
    # one door per BSP split, kept clear of perpendicular wall junctions
    def clear_of_junctions(orient, line, p0, p1):
        for w in walls:
            if orient == "v" and w["y1"] == w["y2"] and min(w["x1"], w["x2"]) - 0.05 <= line <= max(w["x1"], w["x2"]) + 0.05:
                if p0 - 0.35 <= w["y1"] <= p1 + 0.35:
                    return False
            if orient == "h" and w["x1"] == w["x2"] and min(w["y1"], w["y2"]) - 0.05 <= line <= max(w["y1"], w["y2"]) + 0.05:
                if p0 - 0.35 <= w["x1"] <= p1 + 0.35:
                    return False
        return True

    for s in splits:
        _, line, a, b = s
        if b - a < 1.4:
            continue
        for _ in range(40):
            p = rng.uniform(a + 0.4, b - 1.3)
            if clear_of_junctions(s[0], line, p, p + 0.9):
                break
        else:
            continue
        if s[0] == "v":
            openings.append(dict(kind="door", x=line, y=p + 0.45, w=0.9, h=2.1, horiz=False, ext=False))
        else:
            openings.append(dict(kind="door", x=p + 0.45, y=line, w=0.9, h=2.1, horiz=True, ext=False))
    # main door on living room exterior edge
    rooms = []
    for i, (x, y, w, h) in enumerate(rects):
        poly = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        ins = lambda a, lim: (T_EXT if abs(a) < 1e-6 or abs(a - lim) < 1e-6 else T_INT) / 2
        clear = (round(w - ins(x, W) - ins(x + w, W), 2), round(h - ins(y, H) - ins(y + h, H), 2))
        rooms.append(dict(id=f"R{i + 1}", name=names[i], poly=poly, area=round(w * h, 3),
                          perimeter=round(2 * (w + h), 3), dims=(w, h), clear=clear))
        edges = [("h", y, x, x + w), ("h", y + h, x, x + w), ("v", x, y, y + h), ("v", x + w, y, y + h)]
        is_toilet = names[i].startswith("TOILET")
        for e in edges:
            on_ext = (e[0] == "h" and (abs(e[1]) < 1e-6 or abs(e[1] - H) < 1e-6)) or \
                     (e[0] == "v" and (abs(e[1]) < 1e-6 or abs(e[1] - W) < 1e-6))
            if not on_ext:
                continue
            L = e[3] - e[2]
            if L < 1.8:
                continue
            ww = 0.6 if is_toilet else (1.8 if L > 3.6 else 1.2)
            hh = 0.6 if is_toilet else 1.5
            c = (e[2] + e[3]) / 2
            if e[0] == "h":
                openings.append(dict(kind="window", x=c, y=e[1], w=ww, h=hh, horiz=True, ext=True))
            else:
                openings.append(dict(kind="window", x=e[1], y=c, w=ww, h=hh, horiz=False, ext=True))
    living = next(r for r in rooms if r["name"] == "LIVING ROOM")
    lx, ly = living["poly"][0]
    lw, lh = living["dims"]
    if abs(ly) < 1e-6:
        openings.append(dict(kind="door", x=lx + lw * 0.3, y=0.0, w=1.0, h=2.1, horiz=True, ext=True))
    elif abs(lx) < 1e-6:
        openings.append(dict(kind="door", x=0.0, y=ly + lh * 0.3, w=1.0, h=2.1, horiz=False, ext=True))
    elif abs(ly + lh - H) < 1e-6:
        openings.append(dict(kind="door", x=lx + lw * 0.3, y=H, w=1.0, h=2.1, horiz=True, ext=True))
    else:
        openings.append(dict(kind="door", x=W, y=ly + lh * 0.3, w=1.0, h=2.1, horiz=False, ext=True))
    # drop windows that collide with main door
    md = openings[-1]
    openings = [o for o in openings if o["kind"] == "door" or o["horiz"] != md["horiz"]
                or math.hypot(o["x"] - md["x"], o["y"] - md["y"]) > (o["w"] + md["w"]) / 2 + 0.3]
    for i, o in enumerate(openings):
        o["id"] = ("D" if o["kind"] == "door" else "WN") + str(i + 1)
    pts = set()
    for w in walls:
        if w["ext"]:
            pts.add((w["x1"], w["y1"]))
            pts.add((w["x2"], w["y2"]))
    for (x, y, w, h) in rects:
        for p in [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]:
            pts.add(p)
    columns = [dict(id=f"C{i + 1}", x=p[0], y=p[1], w=0.23, d=0.38) for i, p in enumerate(sorted(pts))]
    return dict(W=W, H=H, walls=walls, rooms=rooms, openings=openings, columns=columns)


def _ft(m):
    total_in = m / 0.0254
    f = int(total_in // 12)
    i = int(round(total_in - f * 12))
    if i == 12:
        f, i = f + 1, 0
    return f"{f}'{i}\""


# ----------------------------------------------------------------------------- renderers

def render_dxf(plan: dict, path: str):
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # mm
    msp = doc.modelspace()
    for name, col in [("A-WALL", 7), ("A-DOOR", 3), ("A-GLAZ-WINDOW", 5), ("A-AREA-ROOM", 8),
                      ("A-ANNO-TEXT", 2), ("S-COLS", 1), ("A-ANNO-DIMS", 4)]:
        doc.layers.add(name, color=col)
    S = 1000.0
    for w in plan["walls"]:
        t = w["t"] / 2
        if w["y1"] == w["y2"]:
            x1, x2, y = min(w["x1"], w["x2"]) - (t if w["ext"] else 0), max(w["x1"], w["x2"]) + (t if w["ext"] else 0), w["y1"]
            msp.add_line((x1 * S, (y - t) * S), (x2 * S, (y - t) * S), dxfattribs={"layer": "A-WALL"})
            msp.add_line((x1 * S, (y + t) * S), (x2 * S, (y + t) * S), dxfattribs={"layer": "A-WALL"})
        else:
            y1, y2, x = min(w["y1"], w["y2"]) - (t if w["ext"] else 0), max(w["y1"], w["y2"]) + (t if w["ext"] else 0), w["x1"]
            msp.add_line(((x - t) * S, y1 * S), ((x - t) * S, y2 * S), dxfattribs={"layer": "A-WALL"})
            msp.add_line(((x + t) * S, y1 * S), ((x + t) * S, y2 * S), dxfattribs={"layer": "A-WALL"})
    for o in plan["openings"]:
        hw = o["w"] / 2
        if o["kind"] == "door":
            if o["horiz"]:
                hx, hy = o["x"] - hw, o["y"]
                msp.add_arc((hx * S, hy * S), o["w"] * S, 0, 90, dxfattribs={"layer": "A-DOOR"})
                msp.add_line((hx * S, hy * S), (hx * S, (hy + o["w"]) * S), dxfattribs={"layer": "A-DOOR"})
            else:
                hx, hy = o["x"], o["y"] - hw
                msp.add_arc((hx * S, hy * S), o["w"] * S, 0, 90, dxfattribs={"layer": "A-DOOR"})
                msp.add_line((hx * S, hy * S), ((hx + o["w"]) * S, hy * S), dxfattribs={"layer": "A-DOOR"})
        else:
            if o["horiz"]:
                pts = [(o["x"] - hw, o["y"] - 0.115), (o["x"] + hw, o["y"] - 0.115), (o["x"] + hw, o["y"] + 0.115), (o["x"] - hw, o["y"] + 0.115)]
            else:
                pts = [(o["x"] - 0.115, o["y"] - hw), (o["x"] + 0.115, o["y"] - hw), (o["x"] + 0.115, o["y"] + hw), (o["x"] - 0.115, o["y"] + hw)]
            msp.add_lwpolyline([(a * S, b * S) for a, b in pts], close=True, dxfattribs={"layer": "A-GLAZ-WINDOW"})
    for r in plan["rooms"]:
        msp.add_lwpolyline([(a * S, b * S) for a, b in r["poly"]], close=True, dxfattribs={"layer": "A-AREA-ROOM"})
        cx = sum(p[0] for p in r["poly"]) / 4
        cy = sum(p[1] for p in r["poly"]) / 4
        msp.add_text(r["name"], dxfattribs={"layer": "A-ANNO-TEXT", "height": 180}).set_placement((cx * S, cy * S + 120), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        w, h = r["clear"]
        msp.add_text(f"{w:.2f} X {h:.2f}", dxfattribs={"layer": "A-ANNO-TEXT", "height": 130}).set_placement((cx * S, cy * S - 160), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    for c in plan["columns"]:
        x, y = c["x"], c["y"]
        msp.add_lwpolyline([((x - .115) * S, (y - .115) * S), ((x + .115) * S, (y - .115) * S), ((x + .115) * S, (y + .115) * S), ((x - .115) * S, (y + .115) * S)], close=True, dxfattribs={"layer": "S-COLS"})
    msp.add_text("GROUND FLOOR PLAN  -  G+1  FLOOR HEIGHT 3.0 M", dxfattribs={"layer": "A-ANNO-TEXT", "height": 250}).set_placement((0, -1200))
    doc.saveas(path)


def render_pdf(plan: dict, path: str | None, style: dict | None = None, ann: list | None = None, doc=None):
    import pymupdf as fitz
    style = style or {}
    scale_den = style.get("scale_den", 100)
    A = (lambda lbl, r: ann.append((lbl, fitz.Rect(r)))) if ann is not None else (lambda lbl, r: None)
    pt_per_m = 1000 / 25.4 * 72 / scale_den  # 28.35 pt per metre at 1:100
    W, H = plan["W"], plan["H"]
    margin = 70
    extra = 300 if style.get("schedule") else 0
    pw, ph = max(842, W * pt_per_m + 2 * margin + 40 + extra), max(595, H * pt_per_m + 2 * margin + 120)
    doc = doc if doc is not None else fitz.open()
    page = doc.new_page(width=pw, height=ph)
    ox, oy = margin + 20, margin + 20

    def P(x, y):
        return fitz.Point(ox + x * pt_per_m, oy + (H - y) * pt_per_m)

    wall_fill = style.get("wall_fill", (0.22, 0.22, 0.24))
    # border / title block
    page.draw_rect(fitz.Rect(15, 15, pw - 15, ph - 15), color=(0, 0, 0), width=1.2)
    A("other", fitz.Rect(15, 15, pw - 15, ph - 15))
    page.draw_rect(fitz.Rect(pw - 260, ph - 75, pw - 15, ph - 15), color=(0, 0, 0), width=0.8)
    A("other", fitz.Rect(pw - 260, ph - 75, pw - 15, ph - 15))
    page.insert_text(fitz.Point(pw - 250, ph - 52), style.get("title", "GROUND FLOOR PLAN"), fontsize=11)
    page.insert_text(fitz.Point(pw - 250, ph - 34), f"SCALE 1:{scale_den}   " + style.get("note", "G+1   FLOOR HT 3.0 M"), fontsize=8)
    page.insert_text(fitz.Point(pw - 250, ph - 22), "ALL DIMENSIONS IN METRES", fontsize=7)
    for w in plan["walls"]:
        t = w["t"] / 2
        ext = t if w["ext"] else 0
        if w["y1"] == w["y2"]:
            a, b = P(min(w["x1"], w["x2"]) - ext, w["y1"] + t), P(max(w["x1"], w["x2"]) + ext, w["y1"] - t)
        else:
            a, b = P(w["x1"] - t, max(w["y1"], w["y2"]) + ext), P(w["x1"] + t, min(w["y1"], w["y2"]) - ext)
        page.draw_rect(fitz.Rect(a, b), color=(0, 0, 0), fill=wall_fill, width=style.get("wall_lw", 0.4))
        A("wall", fitz.Rect(a, b))
    for o in plan["openings"]:
        hw = o["w"] / 2
        if o["kind"] == "door":
            # clear wall at opening, then draw leaf + swing arc
            if o["horiz"]:
                r = fitz.Rect(P(o["x"] - hw, o["y"] + 0.13), P(o["x"] + hw, o["y"] - 0.13))
                page.draw_rect(r, color=None, fill=(1, 1, 1), width=0)
                hinge = P(o["x"] - hw, o["y"])
                leaf = P(o["x"] - hw, o["y"] + o["w"])
                end = P(o["x"] + hw, o["y"])
            else:
                r = fitz.Rect(P(o["x"] - 0.13, o["y"] + hw), P(o["x"] + 0.13, o["y"] - hw))
                page.draw_rect(r, color=None, fill=(1, 1, 1), width=0)
                hinge = P(o["x"], o["y"] - hw)
                leaf = P(o["x"] + o["w"], o["y"] - hw)
                end = P(o["x"], o["y"] + hw)
            sh = page.new_shape()
            sh.draw_line(hinge, leaf)
            sh.draw_sector(hinge, end, -90 if o["horiz"] else 90, fullSector=False)
            sh.finish(color=(0.1, 0.35, 0.2), width=style.get("door_lw", 0.6))
            sh.commit()
            A("door", fitz.Rect(hinge.x - o["w"] * pt_per_m, hinge.y - o["w"] * pt_per_m, hinge.x + o["w"] * pt_per_m, hinge.y + o["w"] * pt_per_m))
        else:
            if o["horiz"]:
                r = fitz.Rect(P(o["x"] - hw, o["y"] + 0.115), P(o["x"] + hw, o["y"] - 0.115))
            else:
                r = fitz.Rect(P(o["x"] - 0.115, o["y"] + hw), P(o["x"] + 0.115, o["y"] - hw))
            page.draw_rect(r, color=(0.1, 0.2, 0.6), fill=(1, 1, 1), width=0.5)
            A("window", r)
            sh = page.new_shape()
            if o["horiz"]:
                sh.draw_line(P(o["x"] - hw, o["y"]), P(o["x"] + hw, o["y"]))
            else:
                sh.draw_line(P(o["x"], o["y"] - hw), P(o["x"], o["y"] + hw))
            sh.finish(color=(0.1, 0.2, 0.6), width=0.3)
            sh.commit()
            A("window", r)
    for c in plan["columns"]:
        cr = fitz.Rect(P(c["x"] - .115, c["y"] + .115), P(c["x"] + .115, c["y"] - .115))
        page.draw_rect(cr, color=(0, 0, 0), fill=(0, 0, 0), width=0.2)
        A("column", cr)
    for r in plan["rooms"]:
        cx = sum(p[0] for p in r["poly"]) / 4
        cy = sum(p[1] for p in r["poly"]) / 4
        c = P(cx, cy)
        fs = 7.5
        tw = fitz.get_text_length(r["name"], fontsize=fs)
        page.insert_text(fitz.Point(c.x - tw / 2, c.y - 2), r["name"], fontsize=fs)
        w, h = r["clear"]
        d = f"{w:.2f} X {h:.2f}"
        tw = fitz.get_text_length(d, fontsize=6)
        page.insert_text(fitz.Point(c.x - tw / 2, c.y + 8), d, fontsize=6)
    if style.get("tags"):
        for o in plan["openings"]:
            mk = opening_mark(o)
            if o["kind"] == "door":
                dx, dy = (0.0, 0.42) if o["horiz"] else (0.42, 0.0)
            elif o["horiz"]:
                dx, dy = 0.0, (0.45 if o["y"] < 0.1 else -0.45)
            else:
                dx, dy = (0.45 if o["x"] < 0.1 else -0.45), 0.0
            q = P(o["x"] + dx, o["y"] + dy)
            page.insert_text(fitz.Point(q.x - 6, q.y + 3), mk, fontsize=6.5, color=(0.1, 0.2, 0.6))
    if style.get("schedule"):
        x0, y0 = pw - 300, 60
        page.insert_text(fitz.Point(x0, y0), "DOOR & WINDOW SCHEDULE", fontsize=9)
        for i, row in enumerate(style["schedule"]):
            page.insert_text(fitz.Point(x0, y0 + 18 + i * 13), row, fontsize=7.5)
    # overall dimension line
    sh = page.new_shape()
    sh.draw_line(P(0, -0.9), P(W, -0.9))
    sh.draw_line(P(0, -0.7), P(0, -1.1))
    sh.draw_line(P(W, -0.7), P(W, -1.1))
    sh.finish(color=(0.3, 0.3, 0.3), width=0.4)
    sh.commit()
    A("dimension", fitz.Rect(P(0, -0.7), P(W, -1.1)))
    d = f"{W:.2f}"
    if style.get("furniture"):
        rng = random.Random(style.get("seed", 0))
        for r in plan["rooms"]:
            (x, y), (w, h) = r["poly"][0], r["dims"]
            for _ in range(rng.randint(0, 3)):
                fw, fh = rng.uniform(0.4, min(2.0, w - 0.6)), rng.uniform(0.4, min(2.0, h - 0.6))
                fx, fy = x + rng.uniform(0.3, w - fw - 0.3), y + rng.uniform(0.3, h - fh - 0.3)
                fr = fitz.Rect(P(fx, fy + fh), P(fx + fw, fy))
                if rng.random() < 0.5:
                    page.draw_rect(fr, color=(0.45, 0.45, 0.45), width=rng.choice([0.2, 0.3, 0.5]))
                else:
                    page.draw_oval(fr, color=(0.45, 0.45, 0.45), width=0.3)
                A("furniture", fr)
        # grid / hatch lines
        for gx in range(int(W) + 1):
            if rng.random() < 0.25:
                page.draw_line(P(gx, -0.5), P(gx, -0.2), color=(0.5, 0.5, 0.5), width=0.2, dashes="[2] 0")
                A("dimension", fitz.Rect(P(gx, -0.2), P(gx, -0.5)))
    page.insert_text(fitz.Point(P(W / 2, -0.9).x - 10, P(W / 2, -0.9).y - 3), d, fontsize=7)
    if path:
        doc.save(path)
    return doc


def render_png(plan: dict, path: str, ppm: float = 60.0):
    import cv2
    W, H = plan["W"], plan["H"]
    m = 1.5
    img = np.full((int((H + 2 * m) * ppm), int((W + 2 * m) * ppm), 3), 255, np.uint8)

    def P(x, y):
        return int(round((x + m) * ppm)), int(round((H - y + m) * ppm))

    for w in plan["walls"]:
        t = w["t"] / 2
        ext = t if w["ext"] else 0
        if w["y1"] == w["y2"]:
            a, b = P(min(w["x1"], w["x2"]) - ext, w["y1"] + t), P(max(w["x1"], w["x2"]) + ext, w["y1"] - t)
        else:
            a, b = P(w["x1"] - t, max(w["y1"], w["y2"]) + ext), P(w["x1"] + t, min(w["y1"], w["y2"]) - ext)
        cv2.rectangle(img, a, b, (40, 40, 40), -1)
    for o in plan["openings"]:
        hw = o["w"] / 2
        if o["kind"] == "door":
            if o["horiz"]:
                cv2.rectangle(img, P(o["x"] - hw, o["y"] + .13), P(o["x"] + hw, o["y"] - .13), (255, 255, 255), -1)
                hx, hy = P(o["x"] - hw, o["y"])
                cv2.ellipse(img, (hx, hy), (int(o["w"] * ppm), int(o["w"] * ppm)), 0, -90, 0, (60, 120, 60), 1, cv2.LINE_AA)
                cv2.line(img, (hx, hy), (hx, hy - int(o["w"] * ppm)), (60, 120, 60), 1, cv2.LINE_AA)
            else:
                cv2.rectangle(img, P(o["x"] - .13, o["y"] + hw), P(o["x"] + .13, o["y"] - hw), (255, 255, 255), -1)
                hx, hy = P(o["x"], o["y"] - hw)
                cv2.ellipse(img, (hx, hy), (int(o["w"] * ppm), int(o["w"] * ppm)), 0, -90, 0, (60, 120, 60), 1, cv2.LINE_AA)
                cv2.line(img, (hx, hy), (hx + int(o["w"] * ppm), hy), (60, 120, 60), 1, cv2.LINE_AA)
        else:
            if o["horiz"]:
                a, b = P(o["x"] - hw, o["y"] + .115), P(o["x"] + hw, o["y"] - .115)
            else:
                a, b = P(o["x"] - .115, o["y"] + hw), P(o["x"] + .115, o["y"] - hw)
            cv2.rectangle(img, a, b, (255, 255, 255), -1)
            cv2.rectangle(img, a, b, (160, 80, 30), 1)
    for r in plan["rooms"]:
        cx = sum(p[0] for p in r["poly"]) / 4
        cy = sum(p[1] for p in r["poly"]) / 4
        x, y = P(cx, cy)
        (tw, _), _ = cv2.getTextSize(r["name"], cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.putText(img, r["name"], (x - tw // 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (30, 30, 30), 1, cv2.LINE_AA)
        if "clear" in r:
            dm = f"{r['clear'][0]:.2f} X {r['clear'][1]:.2f}"
            (tw2, _), _ = cv2.getTextSize(dm, cv2.FONT_HERSHEY_SIMPLEX, 0.33, 1)
            cv2.putText(img, dm, (x - tw2 // 2, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (30, 30, 30), 1, cv2.LINE_AA)
    cv2.imwrite(path, img)


def ensure_samples(folder: str, force: bool = False):
    import os
    os.makedirs(folder, exist_ok=True)
    specs = [("villa_g1", 11, 13.2, 10.8), ("bungalow", 23, 14.6, 11.4), ("compact_home", 5, 10.2, 8.6)]
    out = []
    for name, seed, W, H in specs:
        plan = generate_plan(seed, W, H)
        files = {"dxf": f"{name}.dxf", "pdf": f"{name}.pdf", "png": f"{name}.png"}
        for k, fn in files.items():
            p = os.path.join(folder, fn)
            if force or not os.path.exists(p):
                {"dxf": render_dxf, "pdf": render_pdf, "png": render_png}[k](plan, p)
        out.append(dict(name=name, W=W, H=H, rooms=len(plan["rooms"]), files=files))
    return out


# ----------------------------------------------------------------------------- complete drawing set
MARKS = {("door", 1.0): ("D1", 2.1), ("door", 0.9): ("D2", 2.1), ("window", 1.8): ("W1", 1.2), ("window", 1.2): ("W2", 1.2), ("window", 0.6): ("V1", 0.6)}


def opening_mark(o):
    return MARKS.get((o["kind"], round(o["w"], 1)), ("D2" if o["kind"] == "door" else "W2", 1.2))[0]


def opening_schedule_rows(plans):
    cnt = {}
    for p in plans:
        for o in p["openings"]:
            cnt[opening_mark(o)] = cnt.get(opening_mark(o), 0) + 1
    rows = []
    for (kind, w), (mk, h) in MARKS.items():
        if mk in cnt:
            desc = "FLUSH DOOR" if kind == "door" else ("VENTILATOR" if mk == "V1" else "ALUMINIUM SLIDING WINDOW")
            rows.append(f"{mk}   {int(round(w * 1000))} X {int(round(h * 1000))}   {desc}   {cnt[mk]} NOS")
    return rows


def wall_len(plan, ext=None):
    return sum(abs(w["x2"] - w["x1"]) + abs(w["y2"] - w["y1"]) for w in plan["walls"] if ext is None or w["ext"] == ext)


def footing_type(c, W, H):
    on_x = abs(c["x"]) < 1e-6 or abs(c["x"] - W) < 1e-6
    on_y = abs(c["y"]) < 1e-6 or abs(c["y"] - H) < 1e-6
    return "F1" if on_x and on_y else ("F2" if on_x or on_y else "F3")


FOOTINGS = {"F1": (1200, 1200, 400, 10, 150), "F2": (1500, 1500, 450, 12, 150), "F3": (1800, 1800, 500, 12, 125)}
LEVELS = dict(plinth=0.45, h=3.15, slab=0.125, parapet=0.9, sill=0.9, lintel=2.1, found=1.5)


def drawing_set(seed=11, W=13.2, H=10.8):
    g = generate_plan(seed, W, H)
    f = generate_plan(seed + 100, W, H)
    ftypes = {}
    for c in g["columns"]:
        ftypes.setdefault(footing_type(c, W, H), []).append(c)
    truth = dict(footings={k: len(v) for k, v in ftypes.items()}, columns=len(g["columns"]),
                 pb_len=round(wall_len(g), 2), b1_len=round(wall_len(g), 2), rb_len=round(wall_len(f), 2), ground=g, first=f)
    return g, f, ftypes, truth


def render_set_pdf(path, seed=11, W=13.2, H=10.8):
    import pymupdf as fitz
    g, f, ftypes, truth = drawing_set(seed, W, H)
    L = LEVELS
    doc = fitz.open()
    rows = opening_schedule_rows([g, f])
    render_pdf(g, None, dict(title="GROUND FLOOR PLAN", note="ALL LEVELS AS PER SECTION A-A", tags=True, schedule=rows), doc=doc)
    render_pdf(f, None, dict(title="FIRST FLOOR PLAN", note="ALL LEVELS AS PER SECTION A-A", tags=True), doc=doc)

    def frame(page, title, note=""):
        pw, ph = page.rect.width, page.rect.height
        page.draw_rect(fitz.Rect(15, 15, pw - 15, ph - 15), color=(0, 0, 0), width=1.2)
        page.draw_rect(fitz.Rect(pw - 260, ph - 75, pw - 15, ph - 15), color=(0, 0, 0), width=0.8)
        page.insert_text(fitz.Point(pw - 250, ph - 52), title, fontsize=11)
        page.insert_text(fitz.Point(pw - 250, ph - 34), note, fontsize=8)

    # ---- section A-A with levels
    pg = doc.new_page(width=842, height=595)
    frame(pg, "SECTION A-A", "SCALE 1:100   LEVELS IN METRES")
    k = 28.35
    gx, gy = 120, 470
    Y = lambda lv: gy - lv * k
    Wd = min(W, 14) * k
    pg.draw_line(fitz.Point(60, gy), fitz.Point(gx + Wd + 60, gy), color=(0.4, 0.3, 0.2), width=1.2)
    top = L["plinth"] + 2 * L["h"]
    for lv in (L["plinth"] + L["h"], top):
        pg.draw_rect(fitz.Rect(gx, Y(lv), gx + Wd, Y(lv - L["slab"])), color=(0, 0, 0), fill=(0.6, 0.6, 0.6))
    for x in (gx, gx + Wd - 0.23 * k):
        pg.draw_rect(fitz.Rect(x, Y(top + L["parapet"]), x + 0.23 * k, Y(0)), color=(0, 0, 0), fill=(0.85, 0.85, 0.85))
        pg.draw_rect(fitz.Rect(x - 0.6 * k, Y(-L["found"] + 0.45), x + 0.83 * k, Y(-L["found"])), color=(0, 0, 0), fill=(0.6, 0.6, 0.6))
    tx = gx + Wd + 20
    marks = [("GL  +0.000", 0), (f"PLINTH LVL  +{L['plinth']:.3f}", L["plinth"]), (f"FFL  +{L['plinth'] + L['h']:.3f}", L["plinth"] + L["h"]),
             (f"TOP OF SLAB  +{top:.3f}", top), (f"PARAPET TOP  +{top + L['parapet']:.3f}", top + L["parapet"]),
             (f"BOTTOM OF FOOTING  -{L['found']:.3f}", -L["found"])]
    for t, lv in marks:
        pg.draw_line(fitz.Point(tx - 10, Y(lv)), fitz.Point(tx, Y(lv)), color=(0, 0, 0), width=0.5)
        pg.insert_text(fitz.Point(tx + 4, Y(lv) + 3), t, fontsize=7.5)
    pg.insert_text(fitz.Point(60, 60), f"SILL LVL  +{L['plinth'] + L['sill']:.3f}", fontsize=7.5)
    pg.insert_text(fitz.Point(60, 73), f"LINTEL LVL  +{L['plinth'] + L['lintel']:.3f}", fontsize=7.5)
    pg.insert_text(fitz.Point(60, 86), f"ROOF SLAB {int(L['slab'] * 1000)} THK", fontsize=7.5)

    # ---- foundation plan with footing marks + schedule
    pg = doc.new_page(width=max(842, W * k + 480), height=max(595, H * k + 200))
    frame(pg, "FOUNDATION PLAN", "SCALE 1:100   STRUCTURAL")
    ox, oy = 80, 80
    P = lambda x, y: fitz.Point(ox + x * k, oy + (H - y) * k)
    pg.draw_rect(fitz.Rect(P(0, H), P(W, 0)), color=(0.5, 0.5, 0.5), width=0.4, dashes="[3] 0")
    for ft, cols in ftypes.items():
        Lf = FOOTINGS[ft][0] / 1000
        for c in cols:
            pg.draw_rect(fitz.Rect(P(c["x"] - Lf / 2, c["y"] + Lf / 2), P(c["x"] + Lf / 2, c["y"] - Lf / 2)), color=(0, 0, 0), width=0.4)
            pg.draw_rect(fitz.Rect(P(c["x"] - .115, c["y"] + .225), P(c["x"] + .115, c["y"] - .225)), color=(0, 0, 0), fill=(0, 0, 0))
            q = P(c["x"] + 0.12, c["y"] - 0.4)
            pg.insert_text(fitz.Point(q.x, q.y), ft, fontsize=6.5)
    sx = ox + W * k + 50
    pg.insert_text(fitz.Point(sx, 70), "FOOTING SCHEDULE", fontsize=9)
    for i, ft in enumerate(sorted(ftypes)):
        Lf, Bf, Df, d, s = FOOTINGS[ft]
        pg.insert_text(fitz.Point(sx, 88 + i * 13), f"{ft}   {Lf} X {Bf} X {Df}   Y{d} @ {s} BOTH WAYS   {len(ftypes[ft])} NOS", fontsize=7.5)
    pg.insert_text(fitz.Point(sx, 150), "PCC 1:4:8 100 THK BELOW ALL FOOTINGS", fontsize=7.5)
    pg.insert_text(fitz.Point(sx, 163), f"BOTTOM OF FOOTING  -{L['found']:.3f}", fontsize=7.5)

    # ---- column / beam / slab schedule
    pg = doc.new_page(width=842, height=595)
    frame(pg, "COLUMN & BEAM SCHEDULE", "STRUCTURAL   CONCRETE M25   STEEL FE500D")
    lines = ["COLUMN SCHEDULE",
             f"C1   230 X 450   4-Y16 + 2-Y12   TIES Y8 @ 150   {truth['columns']} NOS", "",
             "BEAM SCHEDULE",
             f"PB1   230 X 300   TOP 2-Y12   BOT 2-Y12   STR Y8 @ 150   L= {truth['pb_len']:.2f} M   PLINTH BEAMS",
             f"B1   230 X 450   TOP 2-Y12   BOT 3-Y16   STR Y8 @ 150   L= {truth['b1_len']:.2f} M   FIRST FLOOR BEAMS",
             f"RB1   230 X 450   TOP 2-Y12   BOT 3-Y12   STR Y8 @ 150   L= {truth['rb_len']:.2f} M   ROOF BEAMS", "",
             "SLAB SCHEDULE",
             f"S1   SLAB {int(L['slab'] * 1000)} THK   MAIN Y10 @ 150   DIST Y8 @ 200"]
    for i, t in enumerate(lines):
        pg.insert_text(fitz.Point(60, 70 + i * 16), t, fontsize=9 if t.endswith("SCHEDULE") else 8)
    doc.save(path)
    return truth
