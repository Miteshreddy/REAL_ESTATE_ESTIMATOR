"""Batch-2 layout pack (TNRD type designs, re-extracted PDFs + 300 dpi PNGs) vs official TNRD unit cost 2020-21.

    python ml/evaluation/eval_batch2_layouts.py <pack_dir> <out.json>

The pack's tender prices are NOT matched to these layouts and are not used. Plinth = quantity check; cost indicative
(2020-21 rates vs SOR 2025-26). Throw-away data directory; no user input; nothing tuned.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import tempfile

PACK, OUT = sys.argv[1], sys.argv[2]
os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="batch2_eval_")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

SQFT = 0.09290304
REF = {"L01": ("Elementary / middle school", 1044.37, 17.32), "L02": ("PDS shop", 802.45, 15.25),
       "L03": ("Anganwadi centre", 528.85, 11.10), "L04": ("Combined SHG & PLF building", None, None),
       "L05": ("Panchayat office", 1075.0, 23.45), "L06": ("Rural library", 580.39, 11.05),
       "L07": ("Community hall type I", 1963.55, 33.80), "L08": ("Community hall type II", 2611.97, 55.90),
       "L09": ("Community hall type III (2 sheets)", 5157.0, 85.10), "L10": ("Milk producers co-op", 838.20, 16.00)}


def pct(a, b):
    return round(100 * (a - b) / b, 1) if a and b else None


def run(c, lid, files):
    p = c.post("/api/projects", data={"name": f"b2 {lid}", "loc": '{"district":"Chennai"}'}).json()
    q = c.post(f"/api/projects/{p['id']}/files", files=[("files", (os.path.basename(f), open(f, "rb").read())) for f in files]).json()
    plan = [s for s in q.get("sheets", []) if s.get("kind") == "floor_plan"]
    sqft = round(((q.get("summary") or {}).get("built_up_area") or 0) / SQFT, 1)
    lakh = round(((q.get("estimate") or {}).get("total") or 0) / 1e5, 2)
    return dict(files=[os.path.basename(f) for f in files], sha256=[hashlib.sha256(open(f, "rb").read()).hexdigest() for f in files],
                kinds=[s.get("kind") for s in q.get("sheets", [])], floors=q["params"].get("floors"),
                scale=sorted({str(((s.get("areas") or {}).get("calibration") or {}).get("status")) for s in plan}),
                rooms=sum(len(s.get("rooms") or []) for s in plan), detector=sorted({str(s.get("detector_model")) for s in plan}),
                app_sqft=sqft, app_lakh=lakh, status=((q.get("stats") or {}).get("status_summary") or {}).get("status"),
                checks=sorted({f"{k['level']}: {k['code']}" for k in q.get("checks", [])}))


def main():
    rows = []
    with TestClient(app.app) as c:
        for lid, (name, ref_sqft, ref_lakh) in REF.items():
            for fmt, pat in (("pdf", f"01_LAYOUT_PDFS/{lid}_*.pdf"), ("png", f"02_LAYOUT_IMAGES_300DPI/{lid}_sheet_*.png")):
                files = sorted(glob.glob(os.path.join(PACK, pat)))
                r = dict(id=lid, building=name, fmt=fmt, ref_sqft=ref_sqft, ref_lakh=ref_lakh)
                try:
                    r.update(run(c, lid, files))
                    r.update(sqft_err=pct(r["app_sqft"], ref_sqft), cost_err=pct(r["app_lakh"], ref_lakh))
                except Exception as e:
                    r["error"] = repr(e)[:200]
                rows.append(r); print(json.dumps(r)[:300], flush=True)
    json.dump(rows, open(OUT, "w"), indent=2)


if __name__ == "__main__":
    main()
