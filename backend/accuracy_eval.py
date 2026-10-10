"""Construction-estimate accuracy audit — per category, per layout class, REAL vs SYNTHETIC kept separate.

SYNTHETIC (exact ground truth = the generator's geometry, unseen seeds):
  * detection: room count, room areas, wall length, door / window count and widths
  * quantity & cost per category: pipeline take-off vs the take-off computed from the TRUE geometry through the same
    rules and the same CPWD DSR 2023 rates. This isolates drawing-reading error; items whose value comes from an
    ASSUMPTION (e.g. footing size, kg/m³ of steel) are identical on both sides, so their *assumption* error is NOT
    measured here (reported separately as NOT VALIDATED).
  * confidence vs accuracy: per-item extraction confidence vs quantity error
REAL COMMERCIAL (ground truth = what the architect printed on the sheet):
  * door / window count vs the D… / W… opening tags printed on the plan
  (room areas, building extent and scale: see commercial_eval.py)

Usage: python accuracy_eval.py [n_basic] [n_large]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
import time

import numpy as np
import pymupdf

import benchmark
import bigplan
import docparse
import parsers
import samples
import takeoff
from ml import Models

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = {"Earthwork": "Civil", "Waterproofing": "Civil", "Concrete Works": "Concrete", "RCC Works": "Structural (RCC)",
       "Formwork": "Structural (formwork)", "Reinforcement": "Reinforcement", "Masonry": "Masonry", "Flooring": "Flooring",
       "Plastering": "Plastering", "Painting": "Painting", "Doors & Windows": "Doors & Windows"}


def cat_of(c):
    return CAT.get(c, "Other")


def stats(err, abs_err=None):
    e = np.abs(np.array(err, float))
    if not len(e):
        return dict(n=0)
    out = dict(n=int(len(e)), mape_pct=round(float(e.mean()) * 100, 2), median_ape_pct=round(float(np.median(e)) * 100, 2),
               within5_pct=round(float((e <= .05).mean()) * 100, 1), within10_pct=round(float((e <= .10).mean()) * 100, 1))
    if abs_err is not None and len(abs_err):
        a = np.array(abs_err, float)
        out.update(mae=round(float(np.abs(a).mean()), 3), rmse=round(float(np.sqrt((a ** 2).mean())), 3))
    return out


def cpwd():
    import sqlite3
    con = sqlite3.connect(os.path.join(ROOT, "data", "estimate.db"))
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT code, description, unit, rate, category FROM rate_items WHERE schedule_id='in-cpwd-dsr-2023-civil'")]
    import nlp
    return {r["code"]: r for r in rows}, nlp.SORMatcher(rows)


def pair(a, b):
    """Pair two lists of sizes by sorted order (greedy, length = min)."""
    a, b = sorted(a), sorted(b)
    k = min(len(a), len(b))
    return list(zip(a[-k:] if len(a) > k else a, b[-k:] if len(b) > k else b))


def synthetic(n, large=False, formats=("dxf", "pdf", "png")):
    models = Models(os.path.join(ROOT, "data", "models"))
    by, matcher = cpwd()
    tmp = tempfile.mkdtemp()
    det = {f: dict(room_count=[], room_area=[], room_area_abs=[], wall_len=[], wall_abs=[], door_count=[], door_w=[], win_count=[], win_w=[],
                   rooms_true=0, rooms_found=0) for f in formats}
    qty = {f: {} for f in formats}
    cost = {f: {} for f in formats}
    tot = {f: [] for f in formats}
    conf = {f: [] for f in formats}
    size_cls = {f: {} for f in formats}
    fails = []
    for i in range(n):
        seed = (91000 if large else 81000) + i * 13
        rng = np.random.default_rng(seed)
        W, H = (round(float(rng.uniform(24, 36)), 1), round(float(rng.uniform(16, 26)), 1)) if large else \
               (round(float(rng.uniform(6.5, 16)), 1), round(float(rng.uniform(6, 13)), 1))
        g = samples.generate_plan(seed, W, H)
        nr = len(g["rooms"])
        cls = "large (24–36 m)" if large else ("small (≤4 rooms)" if nr <= 4 else "medium (5–7 rooms)" if nr <= 7 else "larger (8+ rooms)")
        for fmt in formats:
            try:
                path = os.path.join(tmp, f"p{seed}.{fmt}")
                if fmt == "pdf":
                    doc = samples.render_pdf(g, None, dict(scale_den=100), [])
                    doc.save(path)
                else:
                    {"dxf": samples.render_dxf, "png": samples.render_png}[fmt](g, path)
                sheets = parsers.parse_any(path, models)
                for s in sheets:
                    s["file"] = os.path.basename(path)
                plans = [s for s in sheets if s.get("kind") == "floor_plan"]
                if not plans:
                    fails.append(dict(seed=seed, fmt=fmt, why="no floor plan found"))
                    continue
                sp = plans[0]
                gt = benchmark.gt_sheet(g, sp, "Ground floor", 0, columns_visible=fmt != "png")
                d = det[fmt]
                d["rooms_true"] += len(gt["rooms"]); d["rooms_found"] += len(sp["rooms"])
                d["room_count"].append((len(sp["rooms"]) - len(gt["rooms"])) / len(gt["rooms"]))
                for a, b in pair([r["area"] for r in sp["rooms"]], [r["area"] for r in gt["rooms"]]):
                    d["room_area"].append((a - b) / b); d["room_area_abs"].append(a - b)
                wl, wg = sp["metrics"]["L_ext"] + sp["metrics"]["L_int"], gt["metrics"]["L_ext"] + gt["metrics"]["L_int"]
                d["wall_len"].append((wl - wg) / wg); d["wall_abs"].append(wl - wg)
                for kind, kc, kw in (("door", "door_count", "door_w"), ("window", "win_count", "win_w")):
                    po = [o["w"] for o in sp["openings"] if o["kind"] == kind]
                    go = [o["w"] for o in gt["openings"] if o["kind"] == kind]
                    if go:
                        d[kc].append((len(po) - len(go)) / len(go))
                        d[kw] += [(a - b) / b for a, b in pair(po, go)]
                P = {**takeoff.DEFAULT_PARAMS, "floors": 1}
                ia = takeoff.compute_quantities([sp], P)
                ig = takeoff.compute_quantities([gt], P)
                takeoff.map_rates(ia, matcher, by, expert=True)
                takeoff.map_rates(ig, matcher, by, expert=True)
                ea, eg = takeoff.price(ia, by, {}, P), takeoff.price(ig, by, {}, P)
                A = {x["key"]: x for x in ea["items"]}
                G = {x["key"]: x for x in eg["items"]}
                ca, cg = {}, {}
                for k, x in G.items():
                    c = cat_of(x["category"])
                    a = A.get(k)
                    if x["qty"] > 0:
                        qty[fmt].setdefault(c, []).append(((a["qty"] if a else 0) - x["qty"]) / x["qty"])
                        if a:
                            conf[fmt].append((a.get("extract_conf", 0.7), abs(a["qty"] - x["qty"]) / x["qty"]))
                    cg[c] = cg.get(c, 0) + x["amount"]
                for k, x in A.items():
                    c = cat_of(x["category"])
                    ca[c] = ca.get(c, 0) + x["amount"]
                for c, v in cg.items():
                    if v > 0:
                        cost[fmt].setdefault(c, []).append((ca.get(c, 0) - v) / v)
                tot[fmt].append((ea["total"] - eg["total"]) / eg["total"])
                size_cls[fmt].setdefault(cls, []).append((ea["total"] - eg["total"]) / eg["total"])
            except Exception as e:  # noqa: BLE001
                fails.append(dict(seed=seed, fmt=fmt, why=str(e)[:120]))
        print(f"{'large' if large else 'basic'} {i + 1}/{n} done", flush=True)
    out = {}
    for f in formats:
        d = det[f]
        cb = conf[f]
        cbins = {}
        for lo, hi, name in ((0, 0.7, "conf < 0.70"), (0.7, 0.85, "0.70–0.85"), (0.85, 1.01, "conf ≥ 0.85")):
            e = [err for c, err in cb if lo <= c < hi]
            if e:
                cbins[name] = dict(n=len(e), median_ape_pct=round(float(np.median(e)) * 100, 2), within5_pct=round(float((np.array(e) <= .05).mean()) * 100, 1))
        out[f] = dict(
            detection=dict(room_detection_rate_pct=round(min(d["rooms_found"], d["rooms_true"]) / max(1, d["rooms_true"]) * 100, 1),
                           room_count_error=stats(d["room_count"]), room_area=stats(d["room_area"], d["room_area_abs"]),
                           wall_length=stats(d["wall_len"], d["wall_abs"]), door_count=stats(d["door_count"]), door_width=stats(d["door_w"]),
                           window_count=stats(d["win_count"]), window_width=stats(d["win_w"])),
            quantity_by_category={c: stats(v) for c, v in sorted(qty[f].items())},
            cost_by_category={c: stats(v) for c, v in sorted(cost[f].items())},
            total_cost=stats(tot[f]), total_cost_by_size={c: stats(v) for c, v in size_cls[f].items()},
            confidence_vs_error=cbins)
    out["failures"] = fails
    return out


def tags_in(page, region_rect, rx):
    return sum(1 for w in page.get_text("words") if re.fullmatch(rx, w[4]) and region_rect.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)))


def real_commercial(pattern):
    """Door / window counts on real large plans vs the opening tags printed by the architect (D1, D2, DW1 … / W1 …)."""
    models = Models(os.path.join(ROOT, "data", "models"))
    rows = []
    for f in sorted(glob.glob(pattern)):
        page = pymupdf.open(f)[0]
        try:
            res, dg = bigplan.read_page(page, models, parsers.analyze_masks, parsers.finish_sheet, parsers.text_kind, docparse)
        except Exception as e:  # noqa: BLE001
            rows.append(dict(file=os.path.basename(f), error=str(e)[:100]))
            continue
        if not res:
            continue
        f_pt = 1 / (res["scale"]["scale_den"] * bigplan.PT_M)  # pt per m
        ev = np.array(res["envelope"], float)
        fr = res["frame"]
        x0, y0 = (ev[:, 0].min() + fr["ox"]) * f_pt, (ev[:, 1].min() + fr["oy"]) * f_pt
        x1, y1 = (ev[:, 0].max() + fr["ox"]) * f_pt, (ev[:, 1].max() + fr["oy"]) * f_pt
        rect = pymupdf.Rect(x0 - 2 * f_pt, y0 - 2 * f_pt, x1 + 2 * f_pt, y1 + 2 * f_pt)  # building + 2 m (tags sit on the wall line)
        gd = tags_in(page, rect, r"D\d{1,2}[A-Z]?|DW\d{1,2}|MD\d?|FD\d?")
        gw = tags_in(page, rect, r"W\d{1,2}[A-Z]?|V\d{1,2}")
        m = res.get("metrics", {})
        rows.append(dict(file=os.path.basename(f), door_tags=gd, doors_found=m.get("n_doors"), window_tags=gw, windows_found=m.get("n_windows"),
                         rooms=len(res["rooms"]), scale=res["scale"]["scale_den"], unit=dg.get("unit")))
        print(rows[-1], flush=True)
    ok = [r for r in rows if r.get("door_tags")]
    de = [(r["doors_found"] - r["door_tags"]) / r["door_tags"] for r in ok]
    wk = [r for r in rows if r.get("window_tags")]
    we = [(r["windows_found"] - r["window_tags"]) / r["window_tags"] for r in wk]
    return dict(sheets=len(rows), door_count=stats(de), window_count=stats(we), rows=rows,
                note="ground truth = opening tags printed inside the building outline; a tag can label a pair of leaves and some "
                     "openings are untagged, so this is an approximate reference")


if __name__ == "__main__":
    nb = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    nl = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    t0 = time.time()
    out = dict(
        generated=time.strftime("%Y-%m-%d %H:%M"),
        synthetic_basic=dict(kind="SYNTHETIC BENCHMARK", ground_truth="exact generator geometry (unseen seeds)", **synthetic(nb)),
        synthetic_large=dict(kind="SYNTHETIC BENCHMARK", ground_truth="exact generator geometry (unseen seeds), 24–36 m plans", **synthetic(nl, large=True, formats=("dxf", "pdf"))),
        real_commercial_openings=dict(kind="REAL DRAWINGS", **real_commercial(os.path.join(ROOT, "ml", "test_drawings", "commercial", "nalanda_*.pdf"))),
    )
    json.dump(out, open(os.path.join(ROOT, "data", "accuracy_eval_results.json"), "w"), indent=1, default=str)
    print("done in", round(time.time() - t0), "s")
