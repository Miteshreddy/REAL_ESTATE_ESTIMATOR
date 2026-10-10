"""End-to-end estimation accuracy benchmark on UNSEEN drawing sets.

For each benchmark seed (never used for model training) a full drawing set is generated with known
ground-truth geometry. The pipeline estimate (drawing -> quantities -> rates -> cost) is compared with
the estimate computed from the ground truth through the same rules, isolating drawing-reading error.

Usage:  python benchmark.py [n_sets] [formats]     e.g.  python benchmark.py 40 pdf,dxf,png
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

import numpy as np

import nlp
import parsers
import samples
import sor
import takeoff
from ml import Models

SEED0 = 70000  # benchmark seeds are disjoint from every training seed (1000.., 50000..)
ROOMTYPE = {"TOILET": "toilet", "BED": "bedroom", "KITCHEN": "kitchen", "LIVING": "living", "DINING": "dining",
            "STUDY": "study", "STORE": "store", "POOJA": "pooja", "UTILITY": "utility"}


def rtype(name):
    return next((v for k, v in ROOMTYPE.items() if k in name.upper()), "bedroom")


def gt_sheet(plan, parsed, floor_label, level, columns_visible=True):
    """Ground-truth version of a parsed floor-plan sheet (exact geometry from the generator)."""
    W, H = plan["W"], plan["H"]
    te, ti = samples.T_EXT, samples.T_INT
    rooms = []
    for r in plan["rooms"]:
        cw, ch = r["clear"]
        rooms.append(dict(id=r["id"], name=r["name"], type=rtype(r["name"]), area=round(cw * ch, 3), perimeter=round(2 * (cw + ch), 3)))
    ops = []
    for o in plan["openings"]:
        h = samples.MARKS.get((o["kind"], round(o["w"], 1)), (None, o["h"]))[1]
        ops.append(dict(id=o["id"], kind=o["kind"], w=o["w"], h=h, ext=o["ext"], tag=samples.opening_mark(o)))
    metrics = dict(plinth_area=(W + te) * (H + te), envelope_perimeter=2 * (W + H) + 4 * te, L_ext=2 * (W + H),
                   L_int=samples.wall_len(plan, ext=False), t_ext=te, t_int=ti, carpet_area=sum(r["area"] for r in rooms),
                   n_rooms=len(rooms), n_doors=sum(o["kind"] == "door" for o in ops), n_windows=sum(o["kind"] == "window" for o in ops))
    s = dict(parsed)
    s.update(kind="floor_plan", rooms=rooms, openings=ops, walls=[], columns=plan["columns"] if columns_visible else [], metrics=metrics,
             floor=dict(label=floor_label, level=level, repeat=1), confidence=1.0)
    return s


def price_total(items, sor_by, matcher, P):
    takeoff.map_rates(items, matcher, sor_by)
    return takeoff.price(items, sor_by, {}, P)


def run(n=30, formats=("pdf",)):
    models = Models(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"))
    rows = [dict(code=c, description=d, unit=u, rate=r, category=k) for c, d, u, r, k in sor.SEED_SOR]
    sor_by = {r["code"]: r for r in rows}
    matcher = nlp.SORMatcher(rows)
    res = []
    tmp = tempfile.mkdtemp()
    for i in range(n):
        seed = SEED0 + i * 7
        rng = np.random.default_rng(seed)
        W, H = round(float(rng.uniform(8.5, 16)), 1), round(float(rng.uniform(7.5, 13)), 1)
        for fmt in formats:
            t0 = time.time()
            try:
                if fmt == "pdf":
                    path = os.path.join(tmp, f"set_{seed}.pdf")
                    truth = samples.render_set_pdf(path, seed=seed, W=W, H=H)
                    sheets = parsers.parse_any(path, models)
                    g, f = truth["ground"], truth["first"]
                    plans = [(g, "Ground floor", 0), (f, "First floor", 1)]
                else:
                    g = samples.generate_plan(seed, W, H)
                    path = os.path.join(tmp, f"plan_{seed}.{fmt}")
                    {"dxf": samples.render_dxf, "png": samples.render_png}[fmt](g, path)
                    sheets = parsers.parse_any(path, models)
                    plans = [(g, "Ground floor", 0)]
                for s in sheets:
                    s["file"] = os.path.basename(path)
                d, _ = takeoff.derive_params(sheets)
                P = {**takeoff.DEFAULT_PARAMS, **d}
                if fmt != "pdf":
                    P["floors"] = 1
                est = price_total(takeoff.compute_quantities(sheets, P), sor_by, matcher, P)
                parsed_plans = [s for s in sheets if s.get("kind") == "floor_plan"]
                gt_sheets = [s for s in sheets if s.get("kind") != "floor_plan"]
                for k, (pl, lbl, lv) in enumerate(plans):
                    base = parsed_plans[k] if k < len(parsed_plans) else (parsed_plans[0] if parsed_plans else {})
                    gt_sheets.append(gt_sheet(pl, base, lbl, lv, columns_visible=fmt != "png"))
                gt = price_total(takeoff.compute_quantities(gt_sheets, P), sor_by, matcher, P)
                qa = {it["key"]: it["qty"] for it in est["items"]}
                qg = {it["key"]: it["qty"] for it in gt["items"]}
                item_err = {k: abs(qa.get(k, 0) - v) / v for k, v in qg.items() if v > 0}
                rooms_found = sum(len(s["rooms"]) for s in parsed_plans)
                rooms_true = sum(len(p[0]["rooms"]) for p in plans)
                res.append(dict(seed=seed, fmt=fmt, total=est["total"], total_gt=gt["total"], cost_err=abs(est["total"] - gt["total"]) / gt["total"],
                                items_within_5=float(np.mean([e <= 0.05 for e in item_err.values()])),
                                items_within_10=float(np.mean([e <= 0.10 for e in item_err.values()])),
                                median_item_err=float(np.median(list(item_err.values()))),
                                rooms_found=rooms_found, rooms_true=rooms_true, worst=sorted(item_err.items(), key=lambda x: -x[1])[:3],
                                sec=round(time.time() - t0, 1)))
            except Exception as e:
                res.append(dict(seed=seed, fmt=fmt, error=str(e)))
            r = res[-1]
            print(f"{fmt} seed {seed}: " + (f"cost err {r['cost_err'] * 100:.2f}%  items≤5% {r['items_within_5'] * 100:.0f}%  rooms {r['rooms_found']}/{r['rooms_true']}" if "error" not in r else "ERROR " + r["error"]), flush=True)
    summary = {}
    for fmt in formats:
        ok = [r for r in res if r["fmt"] == fmt and "error" not in r]
        if not ok:
            continue
        ce = np.array([r["cost_err"] for r in ok])
        summary[fmt] = dict(sets=len(ok), failed=sum(1 for r in res if r["fmt"] == fmt and "error" in r),
                            mean_cost_err_pct=round(ce.mean() * 100, 2), p90_cost_err_pct=round(float(np.percentile(ce, 90)) * 100, 2),
                            sets_within_5pct=round(float((ce <= 0.05).mean()) * 100, 1), sets_within_3pct=round(float((ce <= 0.03).mean()) * 100, 1),
                            items_within_5pct=round(float(np.mean([r["items_within_5"] for r in ok])) * 100, 1),
                            items_within_10pct=round(float(np.mean([r["items_within_10"] for r in ok])) * 100, 1),
                            room_detection_rate=round(sum(min(r["rooms_found"], r["rooms_true"]) for r in ok) / sum(r["rooms_true"] for r in ok) * 100, 1))
    out = dict(summary=summary, runs=res)
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "benchmark_results.json")
    json.dump(out, open(path, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    return out


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    fm = tuple(sys.argv[2].split(",")) if len(sys.argv) > 2 else ("pdf",)
    run(n, fm)
