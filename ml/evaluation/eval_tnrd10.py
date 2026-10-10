"""TNRD 10 official layouts: run each case through the real app and compare with the area printed on the drawing and the
official TNRD unit-cost row supplied with the case (price_reference.json; checked against the official 2023-24 table).

    python ml/evaluation/eval_tnrd10.py <pack_dir> <out.json> [pdf|png|both]

Throw-away data directory, no user input, nothing tuned to these numbers. The unit cost is a published type cost (not a
BOQ) from an older price year, so cost is reported as a diagnostic only.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import tempfile
import time

PACK, OUT = sys.argv[1], sys.argv[2]
MODE = sys.argv[3] if len(sys.argv) > 3 else "both"
os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="tnrd10_")
os.environ["EST_NO_DOTENV"] = "1"
os.environ["LLM_BACKEND"] = "none"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

SQFT = 10.7639
BTYPE = {"01": "School", "02": "Commercial building", "03": "Community / public building", "04": "Community / public building",
         "05": "Government office", "06": "Commercial building", "07": "Community / public building",
         "08": "Community / public building", "09": "Community / public building", "10": "Community / public building"}


def run(c, case, ref, files):
    p = c.post("/api/projects", data={"name": f"tnrd10 {case}", "building_type": BTYPE.get(case, ""),
                                      "loc": '{"district":"Chennai"}'}).json()
    t0 = time.time()
    q = c.post(f"/api/projects/{p['id']}/files", files=[("files", (os.path.basename(f), open(f, "rb").read())) for f in files]).json()
    secs = round(time.time() - t0, 1)
    sheets = q.get("sheets", [])
    plans = [s for s in sheets if s.get("kind") == "floor_plan" and s.get("enabled", True)]
    S, E = q.get("summary") or {}, q.get("estimate") or {}
    ss = (q.get("stats") or {}).get("status_summary") or {}
    src = lambda s, k: sum(1 for o in s.get("openings") or [] if o.get("kind") == k and o.get("source") != "detector")
    det = lambda s, k: sum(1 for o in s.get("openings") or [] if o.get("kind") == k and o.get("source") == "detector")
    built = round((S.get("built_up_area") or 0) * SQFT, 1)
    drawn = ref["drawing_evidence"].get("drawn_area_sqft")
    pc = ref["published_cost_reference"]
    total_lakh = round((E.get("total") or 0) / 1e5, 2)
    return dict(
        files=[os.path.basename(f) for f in files], sha256=[hashlib.sha256(open(f, "rb").read()).hexdigest()[:16] for f in files],
        seconds=secs, sheet_kinds=[s.get("kind") for s in sheets], floor_plans=len(plans),
        floors_param=q["params"].get("floors"), floors_src=(q["params"].get("_src") or {}).get("floors"),
        floor_labels=[(s.get("floor") or {}).get("label") for s in plans],
        scale=[((s.get("areas") or {}).get("calibration") or {}).get("status") for s in plans],
        scale_method=[str((s.get("scale") or {}).get("method"))[:70] for s in plans],
        rooms=sum(len(s.get("rooms") or []) for s in plans),
        room_names=[r.get("name") for s in plans for r in (s.get("rooms") or [])][:20],
        doors_geom_unet=sum(src(s, "door") for s in plans), doors_detector=sum(det(s, "door") for s in plans),
        windows_geom_unet=sum(src(s, "window") for s in plans), windows_detector=sum(det(s, "window") for s in plans),
        detector_models=sorted({str(s.get("detector_model")) for s in plans}),
        app_built_up_sqft=built, drawn_area_sqft=drawn,
        area_err_pct=round(100 * (built - drawn) / drawn, 1) if built and drawn else None,
        budget_area_sqft=round((S.get("budget_area_m2") or 0) * SQFT, 1) or None,
        total_lakh=total_lakh, per_sqft=S.get("cost_per_sqft"), cost_range=S.get("cost_range"),
        ref_year=pc["table_year"], ref_area_sqft=pc["area_sqft_in_cost_table"], ref_lakh=pc["published_unit_cost_inr_lakh"],
        ref_rate_sqft=pc["published_rate_inr_per_sqft"], ref_match=pc.get("area_match_flag"),
        cost_ratio=round(total_lakh / pc["published_unit_cost_inr_lakh"], 2) if total_lakh else None,
        lines=len(E.get("items") or []), counted=ss.get("lines_counted"), status=ss.get("status"),
        reasons=(ss.get("reasons") or [])[:5], qty={k: v["lines"] for k, v in (ss.get("quantity") or {}).items() if v.get("lines")},
        rate={k: v["lines"] for k, v in (ss.get("rate") or {}).items() if v.get("lines")},
        top_lines=[(i["key"], round(i.get("amount") or 0)) for i in sorted(E.get("items") or [], key=lambda i: -(i.get("amount") or 0))[:6]],
        checks=sorted({f"{k['level']}: {k['code']}" for k in q.get("checks", [])}), project=p["id"])


def main():
    rows = []
    with TestClient(app.app) as c:
        for d in sorted(glob.glob(os.path.join(PACK, "01_CASES", "CASE_*"))):
            ref = json.load(open(os.path.join(d, "price_reference.json"), encoding="utf-8"))
            case = ref["case_id"]
            inputs = []
            if MODE in ("pdf", "both"):
                inputs.append(("pdf", [os.path.join(d, "original_layout.pdf")]))
            if MODE in ("png", "both"):
                inputs.append(("png", sorted(glob.glob(os.path.join(d, "layout*_300dpi.png")))))
            for fmt, files in inputs:
                r = dict(case=case, title=ref["layout_title"], fmt=fmt)
                try:
                    r.update(run(c, case, ref, files))
                except Exception as e:  # report, never hide
                    r["error"] = repr(e)[:300]
                rows.append(r)
                print(json.dumps({k: r.get(k) for k in ("case", "fmt", "app_built_up_sqft", "drawn_area_sqft", "area_err_pct",
                                                        "total_lakh", "ref_lakh", "status", "error")}), flush=True)
    json.dump(rows, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
