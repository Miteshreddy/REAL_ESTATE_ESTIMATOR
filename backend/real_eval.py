"""Accuracy on REAL government drawings, using the architects' own room dimension labels as ground truth.

Every room whose label carries its clear dimensions (e.g. "BED ROOM 3850 X 3500") is compared with the
area the system measured from the drawing. Run:  python real_eval.py [folder ...]
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import numpy as np

import parsers
from ml import Models

_ML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml", "test_drawings")
DEFAULT = [os.path.join(_ML, "uttarakhand", "dxf", "ARCH_*.dxf"), os.path.join(_ML, "tamilnadu", "*.pdf")]


def evaluate(patterns):
    models = Models(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "models"))
    files = sorted({f for p in patterns for f in glob.glob(p)})
    rows, per_file = [], []
    for f in files:
        t0 = time.time()
        try:
            sheets = parsers.parse_any(f, models)
        except Exception as e:
            per_file.append(dict(file=os.path.basename(f), error=str(e)[:120]))
            continue
        errs, plans = [], 0
        for s in sheets:
            if s.get("kind") != "floor_plan":
                continue
            plans += 1
            for r in s.get("rooms", []):
                if r.get("label_dims"):
                    a, b = r["label_dims"]
                    if a * b < 1.0:
                        continue
                    e = r.get("polygon_area", r["area"]) / (a * b) - 1
                    errs.append(e)
                    rows.append(dict(file=os.path.basename(f), sheet=s.get("sheet"), room=r["name"], labelled=round(a * b, 2), detected=r.get("polygon_area", r["area"]), err=round(e, 4)))
        ae = np.abs(errs) if errs else np.array([])
        per_file.append(dict(file=os.path.basename(f), plans=plans, labelled_rooms=len(errs),
                             median_abs_err_pct=round(float(np.median(ae)) * 100, 1) if len(ae) else None,
                             within_5pct=round(float((ae <= 0.05).mean()) * 100, 1) if len(ae) else None,
                             within_10pct=round(float((ae <= 0.10).mean()) * 100, 1) if len(ae) else None,
                             seconds=round(time.time() - t0, 1)))
        print(per_file[-1], flush=True)
    ae = np.abs([r["err"] for r in rows])
    summary = dict(files=len(files), labelled_rooms=len(rows),
                   median_abs_err_pct=round(float(np.median(ae)) * 100, 2) if len(ae) else None,
                   mean_abs_err_pct=round(float(np.mean(ae)) * 100, 2) if len(ae) else None,
                   within_5pct=round(float((ae <= 0.05).mean()) * 100, 1) if len(ae) else None,
                   within_10pct=round(float((ae <= 0.10).mean()) * 100, 1) if len(ae) else None)
    out = dict(summary=summary, files=per_file, rooms=rows)
    json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "real_eval_results.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))
    return out


if __name__ == "__main__":
    evaluate(sys.argv[1:] or DEFAULT)
