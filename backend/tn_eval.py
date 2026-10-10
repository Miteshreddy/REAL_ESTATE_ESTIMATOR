"""Tamil Nadu sheet accuracy against the hand-labelled ground truth (G:\velo\real-estate\tn_gt).

Metrics: plan view picked correctly (picked view centre inside a labelled plan box, and box overlap),
plinth-area error vs the written plinth area, and correct "no plan" on sheets without one."""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

import parsers
from ml import Models

GT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "ground_truth", "tn_ground_truth.json")
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "test_drawings", "tamilnadu")


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0


def main(only=None):
    gt = json.load(open(GT))["sheets"]
    models = Models(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"))
    rows = []
    for f, g in gt.items():
        if only and f not in only:
            continue
        t0 = time.time()
        try:
            sheets = parsers.parse_any(os.path.join(DIR, f), models)
        except Exception as e:
            rows.append(dict(file=f, error=str(e)[:100]))
            print(rows[-1], flush=True)
            continue
        plans = [s for s in sheets if s.get("kind") == "floor_plan"]
        r = dict(file=f, kind=g["kind"], found_plans=len(plans), sec=round(time.time() - t0))
        if g["kind"] == "none":
            r["view_ok"] = len(plans) == 0
        elif plans:
            p = plans[0]
            vb = p.get("view_box_pct")
            if vb:
                cx, cy = (vb[0] + vb[2]) / 2, (vb[1] + vb[3]) / 2
                best = max(g["plans"], key=lambda b: iou(vb, b))
                r["view_iou"] = round(iou(vb, best), 2)
                r["view_ok"] = any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in g["plans"])
                k = g["plans"].index(best)
                tgt = (g.get("plinth_m2") or [None] * len(g["plans"]))[k]
            else:
                r["view_ok"] = None  # vector sheet with a text layer: whole page analysed
                tgt = (g.get("plinth_m2") or [None])[0]
            pa = p["metrics"].get("plinth_area")
            r["plinth"] = pa
            if tgt and pa and g["kind"] == "building":
                r["plinth_gt"] = tgt
                r["plinth_err"] = round(pa / tgt - 1, 4)
            r["scale"] = p.get("scale", {}).get("method", "")[:60]
            r["rooms"] = len(p["rooms"])
        else:
            r["view_ok"] = False
        rows.append(r)
        print(r, flush=True)
    ok = [r for r in rows if r.get("view_ok") is not None and "error" not in r]
    pe = np.abs([r["plinth_err"] for r in rows if "plinth_err" in r])
    summary = dict(sheets=len(rows), errors=sum(1 for r in rows if "error" in r),
                   view_correct_pct=round(100 * np.mean([bool(r["view_ok"]) for r in ok]), 1) if ok else None,
                   plinth_checked=len(pe),
                   plinth_median_err_pct=round(float(np.median(pe)) * 100, 2) if len(pe) else None,
                   plinth_within_5pct=round(float((pe <= 0.05).mean()) * 100, 1) if len(pe) else None,
                   plinth_within_10pct=round(float((pe <= 0.10).mean()) * 100, 1) if len(pe) else None)
    json.dump(dict(summary=summary, rows=rows), open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tn_eval_results.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:] or None)
