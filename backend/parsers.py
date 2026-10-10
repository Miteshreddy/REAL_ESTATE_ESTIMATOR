"""Drawing analysis: DXF (CAD), vector PDF and raster images -> unified metric plan model.

Every source is converted into two binary masks in a metric raster frame (RES metres / pixel):
  * wall mask  - thick construction (walls, columns)
  * seg mask   - everything that bounds a space (walls + windows + closed door gaps)
The shared `analyze_masks` routine then segments rooms, finds the building envelope, classifies
external / internal walls, measures thicknesses and centre-line lengths and vectorises the result.
"""
from __future__ import annotations

import math
import os
import re
from typing import Any

import cv2
import numpy as np

import docparse
import nlp
import segmodel

RES = 0.025  # metres per pixel of the analysis raster
DEBUG = None  # set to a dict to capture intermediate masks
STD_T = [0.115, 0.15, 0.23, 0.3, 0.35]


def _snap_t(t):
    return min(STD_T, key=lambda s: abs(s - t))


def _ridge_thickness(wall: np.ndarray, sel: np.ndarray | None = None) -> float | None:
    """Median wall thickness in px from distance-transform ridge."""
    if wall.sum() == 0:
        return None
    dt = cv2.distanceTransform(wall.astype(np.uint8), cv2.DIST_L2, 3)
    mx = cv2.dilate(dt, np.ones((3, 3), np.uint8))
    ridge = (dt >= mx - 1e-3) & (dt > 1.0)
    if sel is not None:
        ridge &= sel
    vals = dt[ridge]
    if len(vals) < 10:
        return None
    return float(np.median(vals) * 2.0 - 1.0)


def _crop_pad(img, x0, y0, x1, y1, fill=255):
    """Crop img to [x0:x1, y0:y1], padding with `fill` where the window leaves the image."""
    h, w = img.shape[:2]
    out = np.full((max(1, y1 - y0), max(1, x1 - x0)) + img.shape[2:], fill, img.dtype)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = img[sy0:sy1, sx0:sx1]
    return out


def _poly_to_m(cnt, ox, oy, res):
    return [[round(float(p[0][0]) * res - ox, 3), round(float(p[0][1]) * res - oy, 3)] for p in cnt]


def split_by_labels(room_lab, labels, res):
    """A detected space holding several room-name labels is several rooms merged through open doorways.
    Split it: erode until the label seeds fall into separate parts (doorways break first), then grow the
    parts back inside the space."""
    named = [(t, int(x), int(y)) for t, x, y in labels if nlp.looks_like_room_label(t)
             and (not nlp.parse_pair(t) or nlp.ROOM_WORDS.search(t))
             and 0 <= int(y) < room_lab.shape[0] and 0 <= int(x) < room_lab.shape[1]]
    sized = {(x, y): nlp.parse_pair(t) for t, x, y in named}
    nxt = int(room_lab.max()) + 1
    for j in range(1, int(room_lab.max()) + 1):
        seeds = [(x, y) for t, x, y in named if room_lab[y, x] == j]
        # labels written on two lines of one name (e.g. "DRAWING" / "ROOM") are one seed
        uniq = []
        for p in seeds:
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) * res > 1.0 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            continue
        m = (room_lab == j).astype(np.uint8)
        parts = None
        for e in range(2, int(1.2 / res), 2):
            er = cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * e + 1,) * 2))
            n, lab = cv2.connectedComponents(er, connectivity=4)
            ids = [lab[y, x] for x, y in uniq]
            if 0 in ids:
                break
            if len(set(ids)) == len(ids):
                parts = np.zeros_like(lab)
                for k, i in enumerate(ids, start=1):
                    parts[lab == i] = k
                break
        if parts is None and len(uniq) == 2 and all(sized.get(p) for p in uniq):
            # two rooms with written sizes sharing one space (e.g. toilet + shower behind a screen):
            # cut across the axis separating the labels where the parts get their written share of area
            (ax_, ay_), (bx_, by_) = uniq
            a1 = sized[uniq[0]][0] * sized[uniq[0]][1]
            a2 = sized[uniq[1]][0] * sized[uniq[1]][1]
            horiz = abs(bx_ - ax_) >= abs(by_ - ay_)
            prof = m.sum(0) if horiz else m.sum(1)
            cum = np.cumsum(prof) / max(1, prof.sum())
            first_is_a = (ax_ < bx_) if horiz else (ay_ < by_)
            share = a1 / (a1 + a2) if first_is_a else a2 / (a1 + a2)
            cut = int(np.searchsorted(cum, share))
            parts = np.zeros(room_lab.shape, np.int32)
            ys, xs = np.nonzero(m)
            pos = xs if horiz else ys
            lo_k, hi_k = (1, 2) if first_is_a else (2, 1)
            parts[ys, xs] = np.where(pos < cut, lo_k, hi_k)
        if parts is None:
            # no doorway constriction (wide opening / open plan): split by nearest label (Voronoi)
            ys, xs = np.nonzero(m)
            d2 = np.stack([(xs - sx) ** 2 + (ys - sy) ** 2 for sx, sy in uniq])
            parts = np.zeros(room_lab.shape, np.int32)
            parts[ys, xs] = d2.argmin(0) + 1
        # grow the seeds back inside the space (geodesic dilation)
        for _ in range(int(2.5 / res)):
            grown = cv2.dilate(parts.astype(np.uint8), np.ones((3, 3), np.uint8))
            upd = (parts == 0) & (m > 0) & (grown > 0)
            if not upd.any():
                break
            parts[upd] = grown[upd]
        for k in range(2, len(uniq) + 1):
            room_lab[(parts == k) & (m > 0)] = nxt
            nxt += 1
    return room_lab


def analyze_masks(wall: np.ndarray, seg: np.ndarray, res: float, labels=None, doors=None, windows=None,
                  columns=None, room_model=None, geom_model=None, detect_openings=False, ink=None, line_walls=False, close_m=1.25, envelope_from_walls=False, precise=False,
                  gap_merge=False) -> dict[str, Any]:
    labels = labels or []
    H, W = wall.shape
    wall = (wall > 0).astype(np.uint8)
    seg = ((seg > 0) | (wall > 0)).astype(np.uint8)

    def dclose(m, metres):
        k = max(3, int(round(metres / res)))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))

    # door gaps are closed for space segmentation; a wider closing defines the envelope
    # bridge doorway gaps: directional closing, but only thin bridging strips (doorways, wall-thick) are
    # accepted - large filled areas would be narrow rooms (toilets, passages) swallowed by the closing
    raw = dclose(seg, close_m)
    br = ((raw > 0) & (seg == 0)).astype(np.uint8)
    nb_br, lab_br, st_br, _ = cv2.connectedComponentsWithStats(br, connectivity=4)
    dt_br = cv2.distanceTransform(br, cv2.DIST_L2, 3)
    mx_br = np.zeros(nb_br, np.float32)
    np.maximum.at(mx_br, lab_br.ravel(), dt_br.ravel())
    keep = (mx_br * res <= 0.24)
    keep[0] = False
    closed = (seg | keep[lab_br]).astype(np.uint8) if not precise else seg.copy()
    closed_big = dclose(seg, 2.4)
    free_big = (closed_big == 0).astype(np.uint8)
    nb_, lab_b, _, _ = cv2.connectedComponentsWithStats(free_big, connectivity=4)
    border_b = np.unique(np.concatenate([lab_b[0, :], lab_b[-1, :], lab_b[:, 0], lab_b[:, -1]]))
    outside = np.isin(lab_b, border_b) & (free_big > 0)
    envelope = (~outside).astype(np.uint8)
    ne, elab, est, _ = cv2.connectedComponentsWithStats(envelope, connectivity=8)
    if ne > 1:  # keep the main building only: the enclosed blob holding the most wall (not tables / legends)
        wall_in = np.bincount(elab.ravel(), weights=wall.ravel().astype(np.float64), minlength=ne)
        big = 1 + int(np.argmax(wall_in[1:]))
        envelope = (elab == big).astype(np.uint8)
        outside = envelope == 0
    if envelope_from_walls:
        # footprint = the connected wall structure with the most wall, holes filled (tables, notes and
        # title blocks carry no walls and drop out)
        wc = dclose(seg, 1.25)
        nw, wl, _, _ = cv2.connectedComponentsWithStats(wc, connectivity=8)
        if nw > 1:
            wsum = np.bincount(wl.ravel(), weights=wall.ravel().astype(np.float64), minlength=nw)
            main_c = (wl == 1 + int(np.argmax(wsum[1:]))).astype(np.uint8)
            ff = main_c.copy()
            h_, w_ = ff.shape
            mask_ff = np.zeros((h_ + 2, w_ + 2), np.uint8)
            inv = (1 - ff).astype(np.uint8)
            cv2.floodFill(inv, mask_ff, (0, 0), 0)
            envelope = (ff | inv).astype(np.uint8)
            outside = envelope == 0
    # rooms may not extend into the external wall band (window gaps would otherwise leak into it)
    t0_px = _ridge_thickness(wall, cv2.dilate(outside.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(0.84 / res) | 1,) * 2)) > 0) or (0.23 / res)
    rr = max(1, min(int(round(t0_px - 1)), int(0.3 / res)))  # never more than a 300 mm wall
    # precise vector walls: openings are closed exactly (door arcs, window frames) - no safety band needed
    ext_band0 = (cv2.dilate(outside.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rr + 1,) * 2)) > 0) if not precise else (outside > 0)
    free = ((closed == 0) & (envelope > 0) & ~ext_band0).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    if DEBUG is not None:
        DEBUG.update(closed=closed.copy(), free=free.copy(), lab=lab.copy(), wall=wall.copy(), seg=seg.copy())
    border = {0}

    # ---- rooms
    dt_free = cv2.distanceTransform(free, cv2.DIST_L2, 3)
    rooms_raw, pockets = [], []
    min_area = 1.2 / (res * res)
    for i in range(1, n):
        if i in border:
            continue
        m = lab == i
        if not envelope[m].any():
            continue
        area = stats[i, cv2.CC_STAT_AREA]
        inscribed = dt_free[m].max() * res
        if area < min_area or inscribed < 0.38:
            pockets.append((i, area, inscribed))
        else:
            rooms_raw.append(i)
    room_lab = np.zeros_like(lab)
    for j, i in enumerate(rooms_raw, start=1):
        room_lab[lab == i] = j
    # merge pockets (door swings, wall cavities) into neighbours; detect door swings
    for i, area, ins in pockets:
        m = (lab == i).astype(np.uint8)
        if ins < 0.14:  # wall cavity (double-line CAD walls)
            wall[m > 0] = 1
            continue
        ring = cv2.dilate(m, np.ones((5, 5), np.uint8)) & (m == 0)
        nb = room_lab[ring > 0]
        nb = nb[nb > 0]
        if len(nb):
            room_lab[m > 0] = np.bincount(nb).argmax()

    if labels:
        room_lab = split_by_labels(room_lab, labels, res)
        rooms_raw = list(range(1, int(room_lab.max()) + 1))

    # ---- external / internal wall split
    t_px_all = _ridge_thickness(wall) or (0.2 / res)
    def _band(r_px):
        r_px = int(round(r_px))
        return cv2.dilate(outside.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r_px + 1,) * 2)) > 0
    band0 = _band(0.42 / res)
    t_ext_px = _ridge_thickness(wall, band0) or t_px_all
    band = _band(t_ext_px * 1.12 + 2)
    ext_wall = (wall > 0) & band
    int_wall = (wall > 0) & ~band & (envelope > 0)
    t_int_px = _ridge_thickness(wall, ~band) or t_ext_px * 0.5
    t_ext, t_int = _snap_t(t_ext_px * res), _snap_t(t_int_px * res)

    cnts, _ = cv2.findContours(envelope, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    env_cnt = max(cnts, key=cv2.contourArea) if cnts else None
    plinth_area = float(envelope.sum() * res * res)
    env_perim = float(cv2.arcLength(env_cnt, True) * res) if env_cnt is not None else 0.0
    x0, y0, bw, bh = cv2.boundingRect(env_cnt) if env_cnt is not None else (0, 0, W, H)
    ox, oy = x0 * res - 0.6, y0 * res - 0.6

    # ---- openings = wall gaps bridged by the closings (used when the drawing has no explicit symbols)
    det_open = []
    if (detect_openings or gap_merge) and env_cnt is not None:
        gaps = ((closed_big > 0) & (seg == 0) & (envelope > 0)).astype(np.uint8)
        gaps = cv2.morphologyEx(gaps, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        gn, glab, gst, gcent = cv2.connectedComponentsWithStats(gaps, connectivity=8)
        for i in range(1, gn):
            gw, gh = gst[i, cv2.CC_STAT_WIDTH], gst[i, cv2.CC_STAT_HEIGHT]
            L, Tn = max(gw, gh) * res, min(gw, gh) * res
            if not (0.5 <= L <= 2.6 and Tn <= 0.42):
                continue
            gm = glab == i
            is_ext = bool(band[gm].mean() > 0.5)
            dens = float(ink[gm].mean()) if ink is not None else 0.0
            kind = "window" if (is_ext and (dens > 0.04 or L > 1.35 or L < 0.75)) else "door"
            cx, cy = gcent[i]
            det_open.append(dict(kind=kind, x=float(cx), y=float(cy), w=round(L, 2), ext=is_ext, horiz=bool(gw > gh)))

    # ---- assemble rooms
    rooms = []
    lab_pts = [(t, x, y) for (t, x, y) in labels]
    for j in range(1, len(rooms_raw) + 1):
        m = (room_lab == j).astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cs:
            continue
        c = max(cs, key=cv2.contourArea)
        filled = np.zeros_like(m)
        cv2.drawContours(filled, [c], -1, 1, -1)
        area = float(filled.sum() * res * res)
        perim = float(cv2.arcLength(c, True) * res)
        if line_walls:  # walls drawn as 1-px CAD lines: the room boundary pixel ring belongs to the room
            area += perim * res
            perim += 8 * res
        approx = cv2.approxPolyDP(c, 0.06 / res, True)
        rx, ry, rw, rh = cv2.boundingRect(c)
        touches_ext = bool((cv2.dilate(m, np.ones((int(t_ext_px) + 6,) * 2, np.uint8)) & outside.astype(np.uint8)).any())
        names = [t for (t, x, y) in lab_pts if 0 <= int(y) < H and 0 <= int(x) < W and filled[int(y), int(x)]]
        name_txt = [nlp.PAIR.sub("", t).strip() for t in names if nlp.looks_like_room_label(t)]
        name_txt = [t for t in name_txt if t and nlp.ROOM_WORDS.search(t)]
        dims = [nlp.parse_pair(t) for t in names if nlp.parse_pair(t)]
        name = " ".join(name_txt[:2]).strip()
        rtype, conf, src = "unknown", 0.0, "none"
        if name and room_model:
            rtype, conf = room_model.predict(name)
            src = "label-nlp"
        feats = dict(area=area, aspect=max(rw, rh) / max(1, min(rw, rh)), min_side=min(rw, rh) * res,
                     touches_ext=touches_ext)
        if (not name or conf < 0.35) and geom_model is not None:
            g_t, g_c = geom_model.predict(feats, plinth_area)
            if g_c > conf:
                rtype, conf, src = g_t, g_c * 0.85, "geometry-ml"
        rooms.append(dict(
            id=f"R{len(rooms) + 1}", name=name or f"SPACE {len(rooms) + 1}", type=rtype, type_conf=round(conf, 2),
            type_source=src, poly=_poly_to_m(approx, ox, oy, res), area=round(area, 2), perimeter=round(perim, 2),
            touches_ext=touches_ext, label_dims=dims[0] if dims else None,
            bbox_m=[round(rx * res - ox, 2), round(ry * res - oy, 2), round(rw * res, 2), round(rh * res, 2)],
            cx=round((rx + rw / 2) * res - ox, 2), cy=round((ry + rh / 2) * res - oy, 2)))

    # ---- wall polygons (vectorised) & lengths
    def polys(mask):
        cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in cs:
            if cv2.contourArea(c) * res * res < 0.02:
                continue
            ap = cv2.approxPolyDP(c, 0.03 / res, True)
            out.append(_poly_to_m(ap, ox, oy, res))
        return out

    walls = [dict(id=f"WE{i + 1}", ext=True, t=t_ext, poly=p) for i, p in enumerate(polys(ext_wall))] + \
            [dict(id=f"WI{i + 1}", ext=False, t=t_int, poly=p) for i, p in enumerate(polys(int_wall))]

    def to_m(o):
        return dict(o, x=round(o["x"] * res - ox, 2), y=round(o["y"] * res - oy, 2))

    openings = []
    src_doors = [dict(to_m(d), _src=d.get("_src", "symbol / segmentation")) for d in (doors or [])]
    src_wins = [dict(to_m(w), _src=w.get("_src", "symbol / segmentation")) for w in (windows or [])]
    if detect_openings and not doors and not windows:
        for o in det_open:
            (src_doors if o["kind"] == "door" else src_wins).append(dict(to_m(o), _src="wall interruption"))
    elif gap_merge:
        # hybrid: wall interruptions that no detected symbol explains are openings too (doors drawn without a swing,
        # windows drawn as thin lines in a wall gap). Kept only when > 0.7 m from every detected opening.
        have = src_doors + src_wins
        for o in det_open:
            om = to_m(o)
            if all(math.hypot(om["x"] - h["x"], om["y"] - h["y"]) > 0.7 for h in have):
                (src_doors if o["kind"] == "door" else src_wins).append(dict(om, _src="wall interruption"))
                have.append(om)
    for d in src_doors:
        openings.append(dict(kind="door", x=d["x"], y=d["y"], w=d.get("w", 0.9), h=2.1, ext=bool(d.get("ext", False)), source=d["_src"],
                             confidence=0.8 if d["_src"] != "wall interruption" else 0.55, horiz=d.get("horiz")))
    for w in src_wins:
        openings.append(dict(kind="window", x=w["x"], y=w["y"], w=w.get("w", 1.2), h=w.get("h", 1.5 if w.get("w", 1.2) > 0.7 else 0.6), ext=True,
                             source=w["_src"], confidence=0.8 if w["_src"] != "wall interruption" else 0.55, horiz=w.get("horiz")))
    # exterior door classification: door near envelope outside
    for o in openings:
        if o["kind"] == "door":
            px, py = int((o["x"] + ox) / res), int((o["y"] + oy) / res)
            r = int(0.45 / res)
            win = outside[max(0, py - r):py + r, max(0, px - r):px + r]
            o["ext"] = bool(o.get("ext") or (win.size and win.any()))
    for i, o in enumerate(openings):
        o["id"] = ("D" if o["kind"] == "door" else "WN") + str(i + 1)
    cols = [dict(id=f"C{i + 1}", x=round(c[0] * res - ox, 2), y=round(c[1] * res - oy, 2)) for i, c in enumerate(columns or [])]

    # door widths are added back to internal wall length only where the drawing shows a real gap
    door_int_w = 0.0
    for o in openings:
        if o["kind"] == "door" and not o["ext"]:
            px, py = int((o["x"] + ox) / res), int((o["y"] + oy) / res)
            r = max(2, int(0.08 / res))
            if not wall[max(0, py - r):py + r, max(0, px - r):px + r].any():
                door_int_w += o["w"]
    L_ext = max(0.0, env_perim - 4 * t_ext)
    # centre-line length of internal walls ~ half the outline perimeter of each wall blob
    ics, _ = cv2.findContours(int_wall.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    L_int = float(sum(cv2.arcLength(c, True) for c in ics if cv2.contourArea(c) * res * res > 0.005) * res / 2)

    L_int += door_int_w
    carpet = sum(r["area"] for r in rooms)

    return dict(
        bbox=[0, 0, round(bw * res + 1.2, 2), round(bh * res + 1.2, 2)],
        walls=walls, rooms=rooms, openings=openings, columns=cols,
        envelope=_poly_to_m(cv2.approxPolyDP(env_cnt, 0.05 / res, True), ox, oy, res) if env_cnt is not None else [],
        metrics=dict(plinth_area=round(plinth_area, 2), envelope_perimeter=round(env_perim, 2),
                     L_ext=round(L_ext, 2), L_int=round(L_int, 2), t_ext=t_ext, t_int=t_int,
                     carpet_area=round(carpet, 2), n_rooms=len(rooms),
                     n_doors=sum(o["kind"] == "door" for o in openings),
                     n_windows=sum(o["kind"] == "window" for o in openings)),
        frame=dict(ox=ox, oy=oy, res=res),
    )


# =============================================================================== text, tags, OCR
NON_PLAN = ("structural", "section", "elevation", "schedule")


def text_kind(texts):
    blob = " ".join(texts).upper()
    if re.search(r"FLOOR\s+PLAN", blob):
        return "floor_plan"
    k = docparse.classify_sheet(texts, 0)
    return k if k in NON_PLAN else None


def attach_tags(res, tags_px):
    """Link door/window marks written on the plan (D1, W2 …) to the nearest detected opening."""
    fr = res.get("frame")
    if not fr or not tags_px:
        return
    tags = [(mk, x * fr["res"] - fr["ox"], y * fr["res"] - fr["oy"]) for mk, x, y in tags_px]
    pairs = []
    for o in res["openings"]:
        want = "door" if o["kind"] == "door" else "window"
        for i, (mk, x, y) in enumerate(tags):
            kind = "door" if mk[0] in "DMSF" else "window"
            if kind == want:
                d = math.hypot(o["x"] - x, o["y"] - y)
                if d <= 1.3:
                    pairs.append((d, o["id"], i))
    used_o, used_t = set(), set()
    by_id = {o["id"]: o for o in res["openings"]}
    for d, oid, i in sorted(pairs):
        if oid in used_o or i in used_t:
            continue
        used_o.add(oid)
        used_t.add(i)
        by_id[oid]["tag"] = tags[i][0]


def finish_sheet(res, rows, labels_px, kind=None):
    """Attach everything read from the sheet's text: type, floor, levels, schedules, structural data."""
    info = docparse.read_sheet_text(rows, labels_px, len(res.get("rooms", [])))
    res["kind"] = kind or info["kind"]
    rms = res.get("rooms", [])
    # a single-room drawing is a valid plan when the room is labelled or has a door / window (room-only estimates);
    # no room, or one unlabelled blob without openings, is not a floor plan
    if res["kind"] == "floor_plan" and (not rms or (len(rms) == 1 and str(rms[0].get("name", "")).startswith("SPACE")
                                                    and not res.get("openings"))):
        res["kind"] = "other"
    res["floor"] = info["floor"]
    res["levels"] = info["levels"]
    res["schedule"] = info["schedule"]
    res["structural"] = info["structural"]
    res["notes"] = {**(res.get("notes") or {}), **info["notes"]}
    res["texts"] = [r[0] for r in rows][:300]
    fr = res.get("frame")
    if fr and labels_px:  # text with its position on the plan (metres): unit tags, room labels, dimensions
        res["text_items"] = [dict(t=str(t)[:80], x=round(x * fr["res"] - fr["ox"], 2), y=round(y * fr["res"] - fr["oy"], 2))
                             for t, x, y in labels_px[:1500]]
    attach_tags(res, docparse.opening_tags(labels_px))
    return res


def text_sheet(kind, rows, labels, preview, size_m, method):
    res = dict(kind=kind, rooms=[], walls=[], openings=[], columns=[], metrics={}, envelope=[], bbox=[0, 0, size_m[0], size_m[1]],
               confidence=0.9, method=method, scale=dict(method="not needed (text & schedules)", confidence=1.0), _preview=preview)
    return finish_sheet(res, rows, labels, kind)


_OCR = None


def ocr(img):
    """Text boxes from a raster drawing: [(text, x0, y0, x1, y1)] in image pixels."""
    global _OCR
    try:
        if _OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _OCR = RapidOCR()
        h, w = img.shape[:2]
        k = min(1.0, 3000 / max(h, w))
        im = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
        out, _ = _OCR(im)
    except Exception as e:  # OCR is an enhancement; never block the analysis
        print("[ocr] unavailable:", e, flush=True)
        return []
    words = []
    for box, text, score in out or []:
        if float(score) < 0.5 or not str(text).strip():
            continue
        xs, ys = [p[0] / k for p in box], [p[1] / k for p in box]
        words.append((str(text).strip(), min(xs), min(ys), max(xs), max(ys)))
    return words


# =============================================================================== DXF
def parse_dxf(path: str, models) -> list[dict]:
    """CAD drawings. Real CAD files often hold several views (plans, elevations, sections) in one model
    space, so the geometry is split into views and every floor-plan view becomes its own sheet."""
    import ezdxf
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    units = doc.header.get("$INSUNITS", 4)
    to_m = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}.get(units, 0.001)
    segs = {}
    arcs, texts, closed_polys = [], [], {"window": [], "column": [], "room": [], "opening": []}
    layer_map = {}

    def L(layer):
        if layer not in layer_map:
            layer_map[layer] = nlp.classify_layer(layer)
        return layer_map[layer]

    def walk(entities, parent_layer=None, depth=0):
        for e in entities:
            t = e.dxftype()
            layer = e.dxf.layer
            if parent_layer and layer in ("0", "BYBLOCK", "Defpoints"):
                layer = parent_layer  # block contents on layer 0 take the layer of the block insert
            cls = L(layer)
            try:
                if t == "LINE":
                    a, b = e.dxf.start, e.dxf.end
                    segs.setdefault(cls, []).append(((a.x, a.y), (b.x, b.y)))
                elif t in ("LWPOLYLINE", "POLYLINE"):
                    pts = [(p[0], p[1]) for p in (e.get_points("xy") if t == "LWPOLYLINE" else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices])]
                    closed = e.closed if t == "LWPOLYLINE" else e.is_closed
                    if closed and cls in closed_polys:
                        closed_polys[cls].append(pts)
                    seq = pts + ([pts[0]] if closed else [])
                    for a, b in zip(seq, seq[1:]):
                        segs.setdefault(cls, []).append((a, b))
                elif t == "ARC":
                    c = e.dxf.center
                    arcs.append((c.x, c.y, e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle, cls))
                elif t in ("TEXT", "MTEXT", "ATTRIB"):
                    txt = e.dxf.text if t != "MTEXT" else e.plain_text()
                    p = e.dxf.insert
                    if t == "TEXT" and (e.dxf.halign or e.dxf.valign):
                        p = e.dxf.align_point or p
                    h = float(getattr(e.dxf, "char_height", 0) or getattr(e.dxf, "height", 0) or 0) or 150
                    # multi-line labels ("BED ROOM" / "3850 X 3500") -> one label per line, dimensions kept together
                    parts = [x.strip() for x in str(txt).split("\n") if x.strip()]
                    joined = " ".join(parts)
                    if len(parts) > 1 and nlp.parse_pair(joined) and not any(nlp.parse_pair(x) for x in parts):
                        names = [x for x in parts if not re.search(r"\d", x)]
                        dims = re.sub(r"^[^\d]*", "", " ".join(x for x in parts if re.search(r"\d|^[xX×]$", x)))
                        parts = names + [dims]
                    for i, part in enumerate(parts):
                        texts.append((part, p.x, p.y - i * h * 1.3))
                elif t == "INSERT" and depth < 4:
                    walk(e.virtual_entities(), layer, depth + 1)
            except Exception:
                continue

    walk(msp)
    has_walls = bool(segs.get("wall"))
    if not has_walls:
        # structural / services drawings have no masonry layer: split views using all geometry instead
        segs["wall"] = [sg for k_, v_ in segs.items() if k_ not in ("text", "dim") for sg in v_]
        if not segs["wall"]:
            raise ValueError("No geometry found in the DXF")
    # ---- split the model space into views using the wall geometry
    wpts = np.array([p for s_ in segs["wall"] for p in s_], float)
    # declared units are often wrong in practice: the typical wall segment must be a plausible length
    med = float(np.median(np.hypot(*(np.array([b_ for _, b_ in segs["wall"]]) - np.array([a_ for a_, _ in segs["wall"]])).T)))
    span_units = float(np.max(np.percentile(wpts, 99, axis=0) - np.percentile(wpts, 1, axis=0)))
    for cand in (to_m, 0.001, 0.01, 1.0, 0.0254):
        if 0.05 <= med * cand <= 8 and span_units * cand <= 1500:
            if cand != to_m:
                units = f"{units} (declared) -> treated as {cand} m/unit from wall lengths"
            to_m = cand
            break
    # robust extents: ignore stray entities far away from the drawing body
    lo, hi = np.percentile(wpts, 1, axis=0), np.percentile(wpts, 99, axis=0)
    span_ = np.maximum(hi - lo, 1e-9)
    keep_ = np.all((wpts >= lo - 0.5 * span_) & (wpts <= hi + 0.5 * span_), axis=1)
    wpts = wpts[keep_]
    segs["wall"] = [sg for sg in segs["wall"] if np.all((np.array(sg) >= lo - 0.5 * span_) & (np.array(sg) <= hi + 0.5 * span_))]
    gx0, gy0 = wpts.min(0)
    gx1, gy1 = wpts.max(0)
    cres = 0.2 / to_m  # coarse grid: 20 cm
    gw, gh = int((gx1 - gx0) / cres) + 3, int((gy1 - gy0) / cres) + 3
    if gw * gh > 40_000_000:
        raise ValueError("Drawing extents too large - check units / stray entities")
    grid = np.zeros((gh, gw), np.uint8)
    for (ax, ay), (bx, by) in segs["wall"]:
        cv2.line(grid, (int((ax - gx0) / cres) + 1, int((gy1 - ay) / cres) + 1), (int((bx - gx0) / cres) + 1, int((gy1 - by) / cres) + 1), 1, 1)
    grid = cv2.dilate(grid, np.ones((9, 9), np.uint8))  # join walls of one building (1.8 m)
    n, lab, st, _ = cv2.connectedComponentsWithStats(grid, connectivity=8)
    views = []
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if w * cres * to_m < 3 or h * cres * to_m < 3:
            continue
        bx0, bx1 = gx0 + (x - 1) * cres, gx0 + (x + w - 1) * cres
        by1, by0 = gy1 - (y - 1) * cres, gy1 - (y + h - 1) * cres
        views.append((bx0, by0, bx1, by1))
    sheets = []
    struct_marks = []
    all_texts = [t for t, _, _ in texts]
    for vi, (vx0, vy0, vx1, vy1) in enumerate(sorted(views, key=lambda v: (-v[3], v[0]))):
        span = max(vx1 - vx0, vy1 - vy0)
        vtexts = [(t, x, y) for t, x, y in texts if vx0 - 0.02 * span <= x <= vx1 + 0.02 * span and vy0 - 0.02 * span <= y <= vy1 + 0.02 * span]
        # view title: nearest title-like text just below the view
        below = [(t, x, y) for t, x, y in texts if vx0 - 0.05 * span <= x <= vx1 + 0.05 * span and vy0 - 0.3 * span <= y < vy0 + 0.02 * span]
        title = next((t for t, _, _ in sorted(below, key=lambda z: -z[2]) if re.search(r"PLAN|ELEVATION|SECTION", t, re.I)), "")
        if re.search(r"ELEVATION|SECTION", title, re.I) and not re.search(r"PLAN", title, re.I):
            continue
        if re.search(r"EXCAVATION|FOUNDATION|FOOTING|COLUMN|BEAM|SLAB|STRUCT|REINF|CENTRE\s*LINE|LAYOUT", title, re.I):
            # structural layout: count column / footing marks instead of reading rooms
            marks = {}
            for t, _, _ in vtexts:
                u = t.strip().upper()
                if re.fullmatch(r"[CF]\d{1,2}[A-Z]?", u):
                    marks[u] = marks.get(u, 0) + 1
            if marks:
                struct_marks.append(dict(title=title, marks=marks))
            continue
        if not has_walls:
            continue
        r = _dxf_view(segs, arcs, closed_polys, vtexts, (vx0, vy0, vx1, vy1), to_m, models)
        if r is None or not r["rooms"]:
            continue
        named = sum(1 for rm in r["rooms"] if not rm["name"].startswith("SPACE"))
        # a single labelled room with an opening is a valid plan (room-only estimates); unlabelled geometry without a
        # PLAN title, or with no opening, is treated as a detail / elevation, as before
        if not re.search(r"PLAN", title, re.I) and (named < (1 if len(r["rooms"]) == 1 else 2) or not r["openings"]):
            continue  # details, elevations or sections without a title are not floor plans
        P = r.pop("_P")
        finish_sheet(r, vtexts + [(title, 0, 0)], [(t, *P(x, y)) for t, x, y in vtexts], "floor_plan")
        fl = docparse.parse_floor([title]) if title else None
        if fl:
            r["floor"] = fl
        used = sorted({k for k, v in layer_map.items() if v in ("wall", "door", "window", "opening", "column")})
        r.update(source="dxf", sheet=title.title() if title else f"View {vi + 1}",
                 method="CAD layers (" + ", ".join(used)[:120] + ") + view splitting",
                 scale=dict(method=f"DXF $INSUNITS={units} -> {to_m} m/unit", confidence=0.97), layers=dict(layer_map))
        r["confidence"] = 0.93
        sheets.append(r)
    # sections / elevations / notes in the same file: one text sheet for levels and schedules
    tk = text_kind(all_texts)
    # CAD tables put every cell in its own text entity: group them into rows before reading schedules
    rows_ = docparse.group_rows([(t, x - 1, -y - 1, x + 1, -y + 1) for t, x, y in texts], tol=150.0 / (to_m * 1000))
    info = docparse.read_sheet_text(rows_ + texts, [], 0)
    if struct_marks:
        st = info["structural"] or dict(footings=[], columns=[], beams=[], slabs=[])
        for sm in struct_marks:
            for mk, n in sm["marks"].items():
                grp = "columns" if mk.startswith("C") else "footings"
                ex = next((e for e in st[grp] if e.get("mark") == mk), None)
                if ex is None:
                    st[grp].append(dict(mark=mk, count=n, count_src=f"counted on {sm['title']}", b=None, d=None, main=[], ties=None,
                                        L=None, B=None, D=None, bar=None, text=f"{mk} × {n} on layout"))
                elif not ex.get("count") or ex.get("count_src") != "schedule":
                    ex["count"], ex["count_src"] = n, f"counted on {sm['title']}"
        info["structural"] = st
    if info["levels"] or info["schedule"] or info["structural"]:
        ts = text_sheet("structural" if info["structural"] and not info["levels"] else ("section" if info["levels"] else (tk or "other")), rows_ + texts, [], np.full((10, 10, 3), 255, np.uint8), (1, 1),
                        "CAD text: levels, schedules and notes")
        ts.update(source="dxf", sheet="Notes, sections & schedules")
        for k_ in ("levels", "schedule", "structural"):
            if info.get(k_):
                ts[k_] = info[k_]
        sheets.append(ts)
    if not sheets:
        raise ValueError("No floor plan, schedule or structural information found in the DXF")
    return sheets


def _dxf_view(segs, arcs, closed_polys, vtexts, box, to_m, models):
    vx0, vy0, vx1, vy1 = box
    pad = 1.5 / to_m
    minx, miny, maxx, maxy = vx0 - pad, vy0 - pad, vx1 + pad, vy1 + pad
    Wp, Hp = int((maxx - minx) * to_m / RES) + 1, int((maxy - miny) * to_m / RES) + 1
    if Wp * Hp > 30_000_000:
        return None

    def P(x, y):
        return int(round((x - minx) * to_m / RES)), int(round((maxy - y) * to_m / RES))

    def inside(p):
        return minx <= p[0] <= maxx and miny <= p[1] <= maxy

    wall = np.zeros((Hp, Wp), np.uint8)
    seg = np.zeros_like(wall)
    for cls in ("wall", "column"):
        for a, b in segs.get(cls, []):
            if inside(a) or inside(b):
                cv2.line(wall, P(*a), P(*b), 1, 1)
    for pts in closed_polys["column"]:
        if inside(pts[0]):
            cv2.fillPoly(wall, [np.array([P(*p) for p in pts], np.int32)], 1)
    kk = max(3, int(0.36 / RES))
    wall = cv2.morphologyEx(wall, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (kk, 1)))
    wall = cv2.morphologyEx(wall, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kk)))
    doors = []
    for cx, cy, r, sa, ea, cls in arcs:
        rm = r * to_m
        if not inside((cx, cy)) or not (0.55 <= rm <= 1.4) or cls in ("wall", "dim", "text", "furniture"):
            continue
        px, py = P(cx, cy)
        # the doorway runs from the hinge to whichever arc end lies on the wall line
        ends = [P(cx + r * math.cos(math.radians(a_)), cy + r * math.sin(math.radians(a_))) for a_ in (sa, ea)]

        def on_wall(pt):
            x_, y_ = pt
            return int(wall[max(0, y_ - 3):y_ + 4, max(0, x_ - 3):x_ + 4].sum())
        ex, ey = max(ends, key=on_wall)
        doors.append(dict(x=(px + ex) / 2, y=(py + ey) / 2, w=round(rm, 2), chord=((px, py), (ex, ey))))
    # close each doorway exactly along its wall (instead of aggressive morphological closing)
    for d in doors:
        cv2.line(seg, d["chord"][0], d["chord"][1], 1, max(2, int(0.2 / RES)))
    for d in doors:
        d.pop("chord", None)
    windows = []
    for pts in closed_polys["window"]:
        if inside(pts[0]):
            arr = np.array([P(*p) for p in pts], np.int32)
            cv2.fillPoly(seg, [arr], 1)
            x, y, w, h = cv2.boundingRect(arr)
            windows.append(dict(x=x + w / 2, y=y + h / 2, w=round(max(w, h) * RES, 2), ext=True))
    om = np.zeros_like(wall)
    for cls in ("window", "opening"):
        for a, b in segs.get(cls, []):
            if inside(a) or inside(b):
                cv2.line(om, P(*a), P(*b), 1, 2)
    # door leaves / frames on the joinery layer must not split rooms: erase them around each door swing
    om_doorless = om.copy()
    for d in doors:
        rr = int(d["w"] * 1.05 / RES)
        cv2.circle(om_doorless, (int(d["x"]), int(d["y"])), rr, 0, -1)
    seg |= om_doorless
    if not windows:
        n, lab, st, cen = cv2.connectedComponentsWithStats(cv2.dilate(om, np.ones((5, 5), np.uint8)), connectivity=8)
        for i in range(1, n):
            L = max(st[i, 2], st[i, 3]) * RES
            sh = min(st[i, 2], st[i, 3]) * RES
            if 0.45 <= L <= 3.2 and sh <= 0.45 and not any(math.hypot(cen[i][0] - d["x"], cen[i][1] - d["y"]) < 0.8 / RES for d in doors):
                windows.append(dict(x=float(cen[i][0]), y=float(cen[i][1]), w=round(L, 2), ext=True))
    labels = [(t, *P(x, y)) for t, x, y in vtexts]
    cols = [np.array([P(*p) for p in pts]).mean(axis=0) for pts in closed_polys["column"] if inside(pts[0])]
    r = analyze_masks(wall, seg, RES, labels, doors, windows, cols, models.room_label, models.room_geom, line_walls=True,
                      close_m=1.25)
    r["_preview"] = _blueprint(wall, seg, r["frame"], r["bbox"])
    r["_P"] = P
    return r


def _blueprint(wall, seg, frame, bbox):
    res = frame["res"]
    x0, y0 = int(round(frame["ox"] / res)), int(round(frame["oy"] / res))
    w, h = int(bbox[2] / res), int(bbox[3] / res)
    crop_w = _crop_pad(wall, x0, y0, x0 + w, y0 + h, 0)
    crop_s = _crop_pad(seg, x0, y0, x0 + w, y0 + h, 0)
    img = np.full(crop_w.shape + (3,), 255, np.uint8)
    img[crop_s > 0] = (190, 140, 70)
    img[crop_w > 0] = (60, 50, 40)
    return img


# =============================================================================== PDF
def pdf_primitive_features(d: dict, page_med_short: float) -> list[float]:
    r = d["rect"]
    w, h = max(r.width, 0.01), max(r.height, 0.01)
    items = d.get("items", [])
    n_l = sum(1 for it in items if it[0] == "l")
    n_c = sum(1 for it in items if it[0] == "c")
    n_re = sum(1 for it in items if it[0] in ("re", "qu"))
    fill = d.get("fill")
    col = d.get("color")
    fg = float(np.mean(fill)) if fill else 1.5
    cg = float(np.mean(col)) if col else 1.5
    short, long_ = min(w, h), max(w, h)
    return [short, long_, long_ / short, w * h, n_l, n_c, n_re, len(items), 1.0 if fill else 0.0, fg, cg,
            float(d.get("width") or 0), 1.0 if d.get("dashes") not in (None, "[] 0", "") else 0.0,
            short / max(page_med_short, 0.1), 1.0 if d.get("closePath") else 0.0]


def _page_med_short(drawings):
    vals = [min(d["rect"].width, d["rect"].height) for d in drawings if d.get("fill") and min(d["rect"].width, d["rect"].height) > 1]
    return float(np.median(vals)) if vals else 6.0


def parse_pdf(path: str, models, user_scale_den: int | None = None) -> list[dict]:
    import pymupdf as fitz
    doc = fitz.open(path)
    sheets = []
    for pno, page in enumerate(doc):
        drawings = page.get_drawings()
        words = page.get_text("dict")
        lines = []
        for b in words.get("blocks", []):
            for ln in b.get("lines", []):
                txt = " ".join(s["text"] for s in ln["spans"]).strip()
                if txt:
                    x0, y0, x1, y1 = ln["bbox"]
                    lines.append((txt, (x0 + x1) / 2, (y0 + y1) / 2))
        notes = nlp.parse_project_notes([t for t, _, _ in lines])
        wl = page.get_text("words")
        rows = docparse.group_rows([(w[4], w[0], w[1], w[2], w[3]) for w in wl])
        tk = text_kind([r[0] for r in rows])
        if tk in NON_PLAN and rows:
            pix = page.get_pixmap(dpi=110)
            prev = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy(), cv2.COLOR_RGB2BGR)
            k_m = 25.4 / 72 / 1000 * 100
            r = text_sheet(tk, rows, lines, prev, (page.rect.width * k_m, page.rect.height * k_m), "Text, levels & schedule reading")
            r.update(source="pdf", sheet=f"Page {pno + 1}", preview_scale=None)
            sheets.append(r)
            continue
        if not rows and len(drawings) > 400:
            # vector drawing whose text is drawn as outlines (very common in plotted government drawings); 300 dpi so the
            # outlined small print (e.g. "PLINTH AREA : 20.62 SQM / 221.87 SFT") is readable
            dpi = int(min(300, 6000 / (max(page.rect.width, page.rect.height) / 72)))
            pix = page.get_pixmap(dpi=max(150, dpi))
            img = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy(), cv2.COLOR_RGB2BGR)
            r = analyze_full_sheet(img, models, f"Page {pno + 1}", "pdf")
            r["method"] = "Plotted PDF (outlined text) — " + r.get("method", "")
            sheets.append(r)
            continue
        if len(drawings) < 8:
            # scanned / raster PDF page -> raster pipeline. 300 dpi (capped at ~6000 px on the long side): at 200 dpi the
            # small print of type-design sheets (room names, "PLINTH AREA … sq.m") is unreadable and plans were misread as
            # sections (TNRD passenger shelter); large sheets keep a bounded image size
            dpi = int(min(300, 6000 / (max(page.rect.width, page.rect.height) / 72)))
            pix = page.get_pixmap(dpi=max(150, dpi))
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
            r = analyze_full_sheet(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), models, f"Page {pno + 1}", "pdf")
            r.update(notes={**r.get("notes", {}), **notes})
            sheets.append(r)
            continue
        if len(drawings) > 3000 and not user_scale_den:
            # large architect-issued sheets (commercial / institutional): hatched walls, cm/mm dimensions
            try:
                import bigplan
                rb, diag = bigplan.read_page(page, models, analyze_masks, finish_sheet, text_kind, docparse)
            except Exception as e:
                rb, diag = None, {"reason": str(e)[:100]}
            if rb is not None and len(rb.get("rooms", [])) >= 4 and diag.get("dim_matches", 0) >= 10:
                finish_sheet(rb, rows, [(t, x, y) for t, x, y in rb.get("_labels", [])], tk)
                rb.update(source="pdf", sheet=f"Page {pno + 1}", notes={**notes, **rb.get("notes", {})},
                          method=f"Large vector plan reader: walls from {diag.get('wall_source')}, door arcs, PDF text labels",
                          confidence=0.85, read_diag={k: v for k, v in diag.items() if k != "scale"})
                rb.pop("_labels", None)
                fr, bb = rb["frame"], rb["bbox"]
                k_pt = RES / (rb["scale"]["scale_den"] * bigplan.PT_M)
                clip = fitz.Rect(fr["ox"] / RES * k_pt, fr["oy"] / RES * k_pt, (fr["ox"] + bb[2]) / RES * k_pt, (fr["oy"] + bb[3]) / RES * k_pt)
                pix = page.get_pixmap(clip=clip, dpi=110)
                rb["_preview"] = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy(), cv2.COLOR_RGB2BGR)
                sheets.append(rb)
                continue
        med = _page_med_short(drawings)
        X = np.array([pdf_primitive_features(d, med) for d in drawings])
        pred, proba = models.primitive.predict(X)
        scale_den = user_scale_den or notes.get("scale_den")
        scale_method = "title-block NLP ('SCALE 1:%s')" % scale_den if scale_den and not user_scale_den else ("user supplied" if user_scale_den else None)
        if not scale_den:
            scale_den = 100
            scale_method = "assumed 1:100 (refined by room-label dimensions if found)"
        m_per_pt = 25.4 / 72 / 1000 * scale_den

        def build(m_per_pt):
            f = m_per_pt / RES  # px per pt
            Wp, Hp = int(page.rect.width * f) + 1, int(page.rect.height * f) + 1
            wall = np.zeros((Hp, Wp), np.uint8)
            seg = np.zeros_like(wall)
            doors, wins, cols = [], [], []
            for d, c in zip(drawings, pred):
                r = d["rect"]
                a, b = (int(r.x0 * f), int(r.y0 * f)), (int(r.x1 * f), int(r.y1 * f))
                if c == "wall":
                    cv2.rectangle(wall, a, b, 1, -1)
                elif c == "column":
                    cv2.rectangle(wall, a, b, 1, -1)
                    cols.append(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
                elif c == "window":
                    cv2.rectangle(seg, a, b, 1, -1)
                    wins.append(dict(x=(a[0] + b[0]) / 2, y=(a[1] + b[1]) / 2, w=round(max(r.width, r.height) * m_per_pt, 2), ext=True))
                elif c == "door":
                    sd, ld = sorted((r.width, r.height))
                    w_m = (sd if ld / max(sd, 0.1) > 1.5 else ld) * m_per_pt
                    if 0.5 <= w_m <= 1.6:
                        doors.append(dict(x=(a[0] + b[0]) / 2, y=(a[1] + b[1]) / 2, w=round(w_m, 2), _r=(a, b)))
            # door centre -> move to the wall line: nearest wall pixel inside its bbox edge
            for dd in doors:
                (ax, ay), (bx, by) = dd.pop("_r")
                s = 3
                edges = {
                    (ax, (ay + by) / 2): wall[ay:by + 1, max(0, ax - s):ax + s].sum(),
                    (bx, (ay + by) / 2): wall[ay:by + 1, max(0, bx - s):bx + s].sum(),
                    ((ax + bx) / 2, ay): wall[max(0, ay - s):ay + s, ax:bx + 1].sum(),
                    ((ax + bx) / 2, by): wall[max(0, by - s):by + s, ax:bx + 1].sum(),
                }
                dd["x"], dd["y"] = max(edges, key=edges.get)
            labels = [(t, x * f, y * f) for t, x, y in lines]
            return wall, seg, doors, wins, cols, labels

        wall, seg, doors, wins, cols, labels = build(m_per_pt)
        res = analyze_masks(wall, seg, RES, labels, doors, wins, cols, models.room_label, models.room_geom)
        # auto-scale refinement from room-label dimensions (e.g. "3.60 X 4.20")
        ratios = []
        for r in res["rooms"]:
            if r.get("label_dims"):
                a, b = sorted(r["label_dims"])
                bw, bh = sorted(r["bbox_m"][2:4])
                if bw > 0 and bh > 0:
                    ratios += [a / bw, b / bh]
        if not user_scale_den and len(ratios) >= 4:
            k = float(np.median(ratios))
            if abs(k - 1) > 0.04:
                m_per_pt *= k
                scale_method = f"auto-calibrated from {len(ratios) // 2} room dimension labels (x{k:.3f})"
                wall, seg, doors, wins, cols, labels = build(m_per_pt)
                res = analyze_masks(wall, seg, RES, labels, doors, wins, cols, models.room_label, models.room_geom)
            elif scale_method.startswith("assumed"):
                scale_method = f"1:100 verified by {len(ratios) // 2} room dimension labels"
        cls_counts = {c: int((pred == c).sum()) for c in set(pred)}
        finish_sheet(res, rows, labels, tk)
        res.update(source="pdf", sheet=f"Page {pno + 1}", method="Vector path extraction + ML primitive classifier (RandomForest)",
                   notes={**notes, **res["notes"]}, primitive_counts=cls_counts,
                   scale=dict(method=scale_method, scale_den=round(m_per_pt / (25.4 / 72 / 1000)), confidence=0.95 if "label" in scale_method or "NLP" in scale_method else 0.7),
                   ml_confidence=round(float(np.mean(proba)), 3))
        res["confidence"] = round(0.55 + 0.4 * float(np.mean(proba)), 2) if res["rooms"] else 0.3
        # preview crop of the actual drawing
        fr, bb = res["frame"], res["bbox"]
        k_pt = RES / m_per_pt
        clip = fitz.Rect(fr["ox"] / RES * k_pt, fr["oy"] / RES * k_pt, (fr["ox"] + bb[2]) / RES * k_pt, (fr["oy"] + bb[3]) / RES * k_pt)
        pix = page.get_pixmap(clip=clip, dpi=150)
        res["_preview"] = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy(), cv2.COLOR_RGB2BGR)
        if len(res.get("rooms", [])) < 2:
            # vector page whose geometry did not close into rooms (combined sheet, several views):
            # fall back to the whole-sheet reader on a render
            try:
                pix = page.get_pixmap(dpi=200)
                img = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy(), cv2.COLOR_RGB2BGR)
                r2 = analyze_full_sheet(img, models, f"Page {pno + 1}", "pdf")
                if len(r2.get("rooms", [])) >= 2:
                    r2["method"] = "Vector PDF read as sheet — " + r2.get("method", "")
                    res = r2
            except Exception:
                pass
        sheets.append(res)
    return sheets


# =============================================================================== Raster images
def analyze_image_array(img: np.ndarray, models, px_per_m: float | None = None, _words=None, _note=None, _ds=1.0) -> dict:
    """px_per_m (in) and scale.px_per_m (out) are in the CALLER's image pixels. Large images are analysed downscaled:
    the factor is applied to the given calibration and OCR boxes, and undone on the reported scale (_ds carries it
    through the re-calibration pass, which receives the already-downscaled image)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if max(gray.shape) > 5000:
        f = 5000 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        _ds = _ds * f
        if px_per_m:
            px_per_m = px_per_m * f
        if _words is not None:
            _words = [(t, x0 * f, y0 * f, x1 * f, y1 * f) for t, x0, y0, x1, y1 in _words]
    _, ink = cv2.threshold(gray, 0, 1, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    dark = (gray < 110).astype(np.uint8)
    # thick strokes = walls: opening removes thin lines, text, hatching
    wall0 = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # deep-learning segmentation (handles double-line, hatched and thin-line walls); rules are the fallback
    dl, dl_note = None, "rule-based"
    # drawings with solid (filled) walls are measured precisely by the rules; line-drawn / hatched / noisy
    # walls go to the deep-learning model
    solid = wall0.sum() / max(1, dark.sum())
    use_rules = solid > 0.45 and wall0.sum() > 0.01 * wall0.size
    if use_rules and segmodel.available():
        # brochure / coloured plans: only the thick piers are dark enough for the rules while thinner grey walls
        # are missed - if the rules see much less wall than the model, the model is used
        try:
            cls_chk, _ = segmodel.segment(gray)
            dlw = cls_chk == 1
            if dlw.sum() > 0.01 * dlw.size and (wall0.astype(bool) & dlw).sum() < 0.5 * dlw.sum():
                use_rules = False
        except Exception as e:
            print("[seg] model unavailable:", e, flush=True)
    if use_rules:
        dl_note = f"rule-based (solid walls, {solid:.0%} of ink)"
    elif segmodel.available():
        try:
            cls, _ = segmodel.segment(gray)
            if (cls == 1).mean() > 0.002:
                dl, dl_note = cls, "U-Net segmentation"
                wall0 = (cls == 1).astype(np.uint8)
        except Exception as e:
            print("[seg] model unavailable:", e, flush=True)
    t_px = _ridge_thickness(wall0)
    method = "user calibration"
    if not px_per_m:
        if t_px:
            # the thickest common walls are assumed to be 230 mm external masonry
            dt = cv2.distanceTransform(wall0, cv2.DIST_L2, 3)
            mx = cv2.dilate(dt, np.ones((3, 3), np.uint8))
            ridge = dt[(dt >= mx - 1e-3) & (dt > 1)] * 2 - 1
            t_ext_px = t_px
            if len(ridge):
                hist, edges = np.histogram(ridge, bins=np.arange(0, ridge.max() + 2, 1.0))
                peaks = [i for i in range(len(hist)) if hist[i] >= 0.15 * hist.max()
                         and hist[i] >= hist[max(0, i - 1)] and hist[i] >= hist[min(len(hist) - 1, i + 1)]]
                if peaks:
                    i = max(peaks)
                    lo, hi = edges[max(0, i - 1)], edges[min(len(edges) - 1, i + 2)]
                    t_ext_px = float(np.median(ridge[(ridge >= lo) & (ridge < hi)]))
            px_per_m = t_ext_px / 0.23
            method = f"auto: external wall thickness {t_ext_px:.1f}px = 230 mm"
            # cross-check with the door openings found by the model (door leaves are ~0.75-1.0 m): a thickness
            # estimate taken from columns / piers instead of walls disagrees strongly and is replaced
            if dl is not None:
                n_, lab_, st_, _ = cv2.connectedComponentsWithStats((dl == 3).astype(np.uint8), connectivity=8)
                L = np.array([max(st_[i, 2], st_[i, 3]) for i in range(1, n_) if st_[i, 4] >= 6], float)
                if len(L) >= 3:
                    door_ppm = float(np.median(L)) / 0.85
                    if max(door_ppm / px_per_m, px_per_m / door_ppm) > 1.35:
                        px_per_m = door_ppm
                        method = (f"auto (low confidence): {len(L)} door openings, median {np.median(L):.0f}px = 0.85 m "
                                  f"(wall-thickness estimate disagreed) - please calibrate")
        else:
            px_per_m = 50.0
            method = "fallback 50 px/m (please calibrate)"
    f = 1.0 / (px_per_m * RES)
    rs = lambda m: (cv2.resize(m.astype(np.float32), None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR) > (0.5 if m is dark_open else 0.12)).astype(np.uint8)
    dark_open = wall0
    wall = rs(wall0)
    ink_r = rs(ink.astype(np.uint8))
    words = _words if _words is not None else ocr(img)
    rows = docparse.group_rows(words, tol=max(4.0, px_per_m * 0.06))
    labels = [(t, (x0 + x1) / 2 * f, (y0 + y1) / 2 * f) for t, x0, y0, x1, y1 in words]
    tk = text_kind([r[0] for r in rows])
    if tk in NON_PLAN:
        return text_sheet(tk, rows, labels, img, (img.shape[1] / px_per_m, img.shape[0] / px_per_m), "OCR text, levels & schedule reading")
    seg_m, dl_doors, dl_wins = wall, None, None
    if dl is not None:
        door_r, win_r = rs((dl == 3).astype(np.uint8)), rs((dl == 4).astype(np.uint8))
        seg_m = (wall | door_r | win_r).astype(np.uint8)
        dl_doors, dl_wins = [], []
        for msk, lst in ((door_r, dl_doors), (win_r, dl_wins)):
            n_, lab_, st_, cen_ = cv2.connectedComponentsWithStats(msk, connectivity=8)
            for i in range(1, n_):
                L = max(st_[i, 2], st_[i, 3]) * RES
                if 0.4 <= L <= 3.5:
                    lst.append(dict(x=float(cen_[i][0]), y=float(cen_[i][1]), w=round(L, 2), ext=lst is dl_wins, horiz=bool(st_[i, 2] > st_[i, 3])))
    res = analyze_masks(wall, seg_m, RES, labels, dl_doors or None, dl_wins or None, None, models.room_label, models.room_geom,
                        detect_openings=dl is None or not (dl_doors or dl_wins), ink=ink_r, envelope_from_walls=dl is not None,
                        gap_merge=os.environ.get("EST_GAP_MERGE", "1") == "1")
    # scale calibration from room dimension text read by OCR (e.g. "3.60 X 4.20")
    if _note in (None, "layout") and method.startswith("auto"):
        ratios = []
        for r in res["rooms"]:
            if r.get("label_dims"):
                a_, b_ = sorted(r["label_dims"])
                bw, bh = sorted(r["bbox_m"][2:4])
                if bw > 0.5 and bh > 0.5 and 0.7 < a_ / bw < 1.4 and 0.7 < b_ / bh < 1.4:
                    ratios += [a_ / bw, b_ / bh]
        if len(ratios) >= 4:
            k = float(np.median(ratios))
            return analyze_image_array(img, models, px_per_m / k, _words=words,
                                       _note=f"calibrated from {len(ratios) // 2} room dimension labels read by OCR", _ds=_ds)
    # third opening source: the door / window detector (fused: added only where no opening is within 0.7 m)
    try:
        import detector
        if detector.available() and res.get("frame"):
            dets = detector.to_openings(detector.detect(img, px_per_m), px_per_m, res["frame"])
            bw, bh = res["bbox"][2], res["bbox"][3]
            dets = [d for d in dets if -0.3 <= d["x"] <= bw + 0.3 and -0.3 <= d["y"] <= bh + 0.3]
            # an opening sits IN a wall: a detection with no wall pixel within half its width + 0.2 m is furniture / a symbol (wardrobe, bed …)
            fr = res["frame"]
            near_wall, rejected = [], []
            for d in dets:
                r_ = max(2, int((d["w"] / 2 + 0.2) / RES))  # an opening is a GAP in a wall: wall ends lie ~half its width away
                gx, gy = int((d["x"] + fr["ox"]) / RES), int((d["y"] + fr["oy"]) / RES)
                win = wall[max(0, gy - r_):gy + r_ + 1, max(0, gx - r_):gx + r_ + 1]
                (near_wall if win.size and win.any() else rejected).append(d)
            res["detector_rejected"] = [dict(d, reason="no wall within half its width + 0.2 m (furniture / symbol)") for d in rejected]
            dets = near_wall if os.environ.get("EST_DETECTOR_WALLGATE", "1") == "1" else dets
            res["detector_counts"] = dict(door=sum(1 for d in dets if d["kind"] == "door"), window=sum(1 for d in dets if d["kind"] == "window"))
            res["detector_model"] = detector.model_name()  # which weights produced these detections (traceability)
            if os.environ.get("EST_DETECTOR_FUSE", "1") == "1":
                n0 = len(res["openings"])
                for d in dets:
                    # the same opening seen by two sources: centres closer than half the summed widths (overlapping
                    # along the wall) or 0.7 m — counted once (was a fixed 0.7 m, which double-counted wide gaps)
                    if all(math.hypot(d["x"] - o["x"], d["y"] - o["y"]) > max(0.7, 0.5 * (d["w"] + o.get("w", 0))) for o in res["openings"]):
                        res["openings"].append(dict(kind=d["kind"], x=d["x"], y=d["y"], w=d["w"], h=2.1 if d["kind"] == "door" else (1.5 if d["w"] > 0.7 else 0.6),
                                                    ext=d["kind"] == "window", source="detector", confidence=d["score"], horiz=d["horiz"],
                                                    id=("D" if d["kind"] == "door" else "WN") + f"X{len(res['openings']) - n0 + 1}"))
                m_ = res.get("metrics") or {}
                m_["n_doors"] = sum(1 for o in res["openings"] if o["kind"] == "door")
                m_["n_windows"] = sum(1 for o in res["openings"] if o["kind"] == "window")
    except Exception as e:  # the detector is an enhancement; analysis never fails because of it
        print("[detector]", e, flush=True)
    finish_sheet(res, rows, labels, tk)
    if _note and _note != "layout":
        method = _note
    res.update(source="image", method=f"{dl_note} wall/door/window detection + OCR of labels" + (f" ({len(words)} text items read)" if words else " (no text read)"),
               scale=dict(method=method, px_per_m=round(px_per_m / _ds, 2), analysis_downscale=round(_ds, 4),
                          confidence=0.5 if "low confidence" in method or "fallback" in method else 0.6 if method.startswith("auto")
                          else 0.85 if "room dimension labels" in method else 0.95))
    small = max(gray.shape) < 1400
    if small and not any(nlp.parse_pair(w[0]) for w in (words or [])):
        res.setdefault("warnings", []).append(
            f"Low-resolution image ({gray.shape[1]}x{gray.shape[0]} px): the text on it is too small to read, so room names and "
            "written dimensions could not be used and the scale is estimated. Upload the original drawing (PDF / DWG / "
            "high-resolution scan) or use 'Calibrate scale' with one known dimension.")
        # text that small is OCR noise: keep it for reference but do not present it as a room name
        for i, r in enumerate(res.get("rooms", []), 1):
            if not r["name"].startswith("SPACE ") and not (r.get("type_source") == "label-nlp" and r.get("type_conf", 0) >= 0.5):
                r["ocr_text"] = r["name"]
                r["name"] = f"SPACE {i}"
    res["confidence"] = 0.72 if res["rooms"] else 0.25
    fr, bb = res["frame"], res["bbox"]
    x0, y0 = int(fr["ox"] * px_per_m), int(fr["oy"] * px_per_m)
    x1, y1 = int((fr["ox"] + bb[2]) * px_per_m), int((fr["oy"] + bb[3]) * px_per_m)
    res["_preview"] = _crop_pad(img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), x0, y0, x1, y1)
    return res


def analyze_full_sheet(img: np.ndarray, models, sheet_name: str, source: str) -> dict:
    """Real drawing sheets (several views, rotated / outlined text): pick the plan view, scale from
    written dimensions, and read schedules, levels and notes from the whole sheet."""
    import sheetreader
    res, info = sheetreader.read_sheet(img, models, source, sheet_name)
    rows = info["rows"]
    H_, W_ = img.shape[:2]
    if res is not None and res.get("view_box"):
        x_, y_, w_, h_ = res["view_box"]
        res["view_box_pct"] = [round(100 * x_ / W_, 1), round(100 * y_ / H_, 1), round(100 * (x_ + w_) / W_, 1), round(100 * (y_ + h_) / H_, 1)]
    full_kind = text_kind(info["texts"])
    if res is None or (full_kind in NON_PLAN and not res.get("rooms")):
        H, W = img.shape[:2]
        r = text_sheet(full_kind or "other", rows, [(w[0], (w[1] + w[3]) / 2, (w[2] + w[4]) / 2) for w in info["words"]], img, (W / 50, H / 50),
                       "OCR of the whole sheet (no floor plan found)")
        r.update(source=source, sheet=sheet_name)
        return r
    sheet_info = docparse.read_sheet_text(rows, [], len(res["rooms"]))
    for k in ("levels", "schedule", "structural"):
        if sheet_info.get(k):
            if isinstance(sheet_info[k], dict) and isinstance(res.get(k), dict):
                res[k] = {**sheet_info[k], **res[k]}
            else:
                res[k] = res.get(k) or sheet_info[k]
    res["notes"] = {**sheet_info["notes"], **(res.get("notes") or {})}
    res["floor"] = res.get("floor") or sheet_info["floor"]
    res["kind"] = "floor_plan" if len(res["rooms"]) >= 2 else res.get("kind", "other")
    res.update(source=source, sheet=sheet_name)
    res["method"] = "Sheet layout analysis (plan view located) + " + res["method"]
    res.pop("_sheet_preview", None)
    return res


def parse_image(path: str, models, px_per_m: float | None = None) -> list[dict]:
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Unreadable image")
    if px_per_m is None and max(img.shape[:2]) > 2200:
        return [analyze_full_sheet(img, models, "Image", "image")]
    r = analyze_image_array(img, models, px_per_m)
    r["sheet"] = "Image"
    return [r]


DWG2DXF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "libredwg", "dwg2dxf.exe")


def dwg_to_dxf(path: str) -> str:
    """AutoCAD DWG -> DXF with the bundled open-source LibreDWG converter (GNU project)."""
    import subprocess
    out = os.path.splitext(path)[0] + ".converted.dxf"
    if not os.path.exists(DWG2DXF):
        raise ValueError("DWG converter not found - save the drawing as DXF or PDF and upload that")
    subprocess.run([DWG2DXF, "-y", "-o", out, path], capture_output=True, timeout=600)
    if not os.path.exists(out) or os.path.getsize(out) < 1000:
        raise ValueError("Could not convert this DWG file - please export it as DXF or PDF")
    return out


def parse_any(path: str, models, opts: dict | None = None) -> list[dict]:
    opts = opts or {}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".dwg":
        path = dwg_to_dxf(path)
        ext = ".dxf"
    if ext == ".dxf":
        return parse_dxf(path, models)
    if ext == ".pdf":
        return parse_pdf(path, models, opts.get("scale_den"))
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
        return parse_image(path, models, opts.get("px_per_m"))
    raise ValueError(f"Unsupported file type {ext}. Use DWG, DXF, PDF, PNG or JPG.")
