"""Accuracy on large commercial / institutional vector-PDF plans (backend/bigplan.py).

Ground truth is what the architect wrote on the drawing:
  * room sizes ("ROOM 300X300", cm)  -> room area error, reported separately for enclosed rooms and for
    open-plan spaces (living / lounge / verandah ... whose written size is nominal);
  * the overall building dimensions (longest dimension string each way) -> building extent error.
Run:  python commercial_eval.py [glob]   (default: ml/test_drawings/commercial/nalanda_*.pdf)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
import pymupdf

import bigplan
import docparse
import parsers
from ml import Models

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "ml", "test_drawings", "commercial", "nalanda_*.pdf")
OPEN = re.compile(r"VERANDAH|VERANDA|LIVING|DINING|FOYER|LOBBY|CORRIDOR|PASSAGE|PORCH|GARDEN|TERRACE|BALCONY|OPEN|COURT|"
                  r"SIT[- ]?OUT|WAITING|HALL\b|DECK|LANDSCAPE|PATIO|SHAFT|DUCT|LIFT|STAIR", re.I)


def stats(e):
    a = np.abs(e)
    return dict(n=int(len(a)), median_pct=round(float(np.median(a)) * 100, 2), within5=round(float((a <= .05).mean()) * 100, 1),
                within10=round(float((a <= .10).mean()) * 100, 1)) if len(a) else dict(n=0)


def main(pattern):
    models = Models(os.path.join(ROOT, "data", "models"))
    enc, opn, ext, rows = [], [], [], []
    for f in sorted(glob.glob(pattern)):
        res, d = bigplan.read_page(pymupdf.open(f)[0], models, parsers.analyze_masks, parsers.finish_sheet, parsers.text_kind, docparse)
        if res is None:
            print(os.path.basename(f), "not read:", d)
            continue
        for r in res["rooms"]:
            if r.get("label_dims"):
                a, b = r["label_dims"]
                e = r["area"] / (a * b) - 1
                (opn if OPEN.search(r["name"]) else enc).append(e)
                rows.append(dict(file=os.path.basename(f), room=r["name"], area=r["area"], label=round(a * b, 2), err=round(e, 4)))
        W, H = d.get("overall_written", (0, 0))
        ev = np.array(res["envelope"], float)
        for wv, dv in ((W, np.ptp(ev[:, 0])), (H, np.ptp(ev[:, 1]))):
            if wv:
                ext.append(dv / wv - 1)
        print(os.path.basename(f), "rooms", len(res["rooms"]), d.get("scale", ""), flush=True)
    out = dict(enclosed_rooms=stats(enc), open_plan=stats(opn), building_extent=stats(ext), rooms=rows)
    json.dump(out, open(os.path.join(ROOT, "data", "commercial_eval_results.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rooms"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
