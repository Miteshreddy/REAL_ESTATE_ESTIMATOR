"""Real Tamil Nadu accuracy check: app output on official TNRD type-design drawings vs the official TNRD
"Unit Cost of Various Buildings for the year 2020-21" (plinth area in sq ft, cost in Rs lakh).

    python ml/evaluation/eval_tnrd_unit_cost.py <drawings_dir> <out.json>

Runs in a throw-away data directory, entire-property scope, no user input. Nothing is tuned to these numbers.
Plinth area = quantity accuracy (like for like). Cost = indicative only: the reference uses 2020-21 rates and its own
scope (e.g. electrification, water supply); the app uses SOR 2025-26.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

DRAW, OUT = sys.argv[1], sys.argv[2]
os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="tnrd_eval_")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

SQM_PER_SQFT = 0.09290304
# (building, drawing file, official plinth sq ft, official cost Rs lakh) — TNRD unit cost 2020-21, pages 3-5
REF = [
    ("Elementary / middle school (GF)", "1.ESB-Model.pdf", 1044.37, 17.32),
    ("PDS shop", "2.PDS-Model.pdf", 802.45, 15.25),
    ("Anganwadi centre", "3.Anganwadi-Model.pdf", 528.85, 11.10),
    ("Kitchen shed type I", "4.kitchen_shed.pdf", 221.87, 4.96),
    ("School toilet (girls)", "5.STG-Model.pdf", 250.0, 4.55),
    ("School toilet (boys)", "6.STB-Model.pdf", 250.0, 4.32),
    ("Passenger shelter", "8.PSTR-Model.pdf", 152.64, 3.10),
    ("Panchayat office", "9.PO-Model.pdf", 1075.0, 23.45),
    ("Rural library", "10.LB-Model.pdf", 580.39, 11.05),
    ("Community hall type I", "11.CH-1-Model.pdf", 1963.55, 33.80),
    ("Community hall type II", "12.CH-2-Model.pdf", 2611.97, 55.90),
    ("Cement godown", "14.cement_godown.pdf", 866.07, 11.96),
    ("VAO office", "15.vao_office.pdf", 313.54, 7.75),
    ("Threshing floor", "16.TF-Model.pdf", 2593.16, 6.75),
    ("Cremation shed", "17.CS-Model.pdf", 451.92, 3.05),
    ("Milk producers co-op", "18.MC-Model.pdf", 838.20, 16.00),
    ("Integrated men's sanitary complex", "IMSC.pdf", 871.45, 8.72),
]


def pct(a, b):
    return None if not a or not b else round(100.0 * (a - b) / b, 1)


def main():
    rows = []
    with TestClient(app.app) as c:
        for name, fn, ref_sqft, ref_lakh in REF:
            path = os.path.join(DRAW, fn)
            r = dict(building=name, file=fn, ref_plinth_sqft=ref_sqft, ref_cost_lakh=ref_lakh)
            if not os.path.exists(path):
                rows.append({**r, "error": "drawing missing"}); continue
            try:
                p = c.post("/api/projects", data={"name": f"tnrd {name}", "loc": '{"district":"Chennai"}'}).json()
                q = c.post(f"/api/projects/{p['id']}/files", files={"files": (fn, open(path, "rb").read())})
                q = q.json()
                plinth_sqm = (q.get("summary") or {}).get("plinth_area") or 0
                est = (q.get("estimate") or {})
                total = est.get("total") or 0
                app_sqft = round(plinth_sqm / SQM_PER_SQFT, 1)
                r.update(app_plinth_sqft=app_sqft, plinth_err_pct=pct(app_sqft, ref_sqft),
                         app_cost_lakh=round(total / 1e5, 2), cost_err_pct=pct(total / 1e5, ref_lakh),
                         status=((q.get("stats") or {}).get("status_summary") or {}).get("status"),
                         sheets=[s.get("kind") for s in q.get("sheets", [])])
            except Exception as e:  # report, never hide
                r["error"] = repr(e)[:200]
            rows.append(r); print(json.dumps(r))
    pe = [abs(r["plinth_err_pct"]) for r in rows if r.get("plinth_err_pct") is not None]
    ce = [abs(r["cost_err_pct"]) for r in rows if r.get("cost_err_pct") is not None]
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    summary = dict(n=len(rows), plinth_measured=len(pe), plinth_within_10=sum(e <= 10 for e in pe),
                   plinth_within_25=sum(e <= 25 for e in pe), plinth_median_abs_err=med(pe),
                   cost_measured=len(ce), cost_within_25=sum(e <= 25 for e in ce), cost_median_abs_err=med(ce),
                   caveat="Development drawings (not sealed holdout). Cost reference is 2020-21 rates; indicative only.")
    json.dump(dict(summary=summary, rows=rows), open(OUT, "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
