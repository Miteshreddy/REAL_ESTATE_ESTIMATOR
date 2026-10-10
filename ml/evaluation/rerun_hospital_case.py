"""Re-run the hospital demo case (synthetic image 'Additional 4th, 5th & 6th Floors') through the real app and export PDFs.

    python ml/evaluation/rerun_hospital_case.py <image.png> <output_dir>

Runs in a throw-away data directory (never the user's database). Variants:
  a  defaults — no user input (as the original run)
  b  reviewed — scope 'floors 4,5,6', door/window counts confirmed from the drawing's markers (27 / 12), floors confirmed,
     provisional assumptions allowed
  c  as b, strict policy — assumed structural quantities left unresolved
SYNTHETIC drawing: results test the workflow, not real construction cost.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

IMG, OUT = sys.argv[1], sys.argv[2]
os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="hosp_rerun_")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402


def summ(q, tag):
    e = q["estimate"]
    s = [x for x in q["sheets"] if x["kind"] == "floor_plan"][0]
    ss = q["stats"]["status_summary"]
    it = {i["key"]: i for i in e["items"]}
    kinds = lambda k, src=None: sum(1 for o in s["openings"] if o["kind"] == k and (src is None or (o.get("source") != "detector") == (src == "geo")))
    return dict(tag=tag, floors=(s.get("floor") or {}).get("occurrences"), floors_param=q["params"]["floors"], scope=q["scope_text"],
                plinth=q["summary"]["plinth_area"], built_up=q["summary"]["built_up_area"], rooms=len(s["rooms"]),
                discarded_rooms=len(s.get("discarded_rooms") or []), doors_geometry=kinds("door", "geo"),
                doors_detector=(s.get("detector_counts") or {}).get("door"), doors_combined=kinds("door"),
                windows_geometry=kinds("window", "geo"), windows_detector=(s.get("detector_counts") or {}).get("window"),
                windows_combined=kinds("window"), confirmed=s.get("opening_confirmed"), detector_model=s.get("detector_model"),
                scale=(s.get("areas") or {}).get("calibration", {}).get("status"),
                rcc_qty={k: (round(it[k]["qty"], 2), it[k]["qty_status"]) for k in ("rcc_column", "rcc_beam", "rcc_slab", "rcc_footing") if k in it},
                steel_kg_in_total=round(sum(it[k]["qty"] for k in ("steel_footing", "steel_column", "steel_beam", "steel_slab") if k in it and it[k]["in_scope"]), 1),
                total=e["total"], subtotal=e["subtotal"], lines=len(e["items"]), counted=ss["lines_counted"], status=ss["status"],
                reasons=ss["reasons"], qty={k: v["lines"] for k, v in ss["quantity"].items() if v["lines"]},
                rate={k: v["lines"] for k, v in ss["rate"].items() if v["lines"]},
                out_of_scope=[x["description"][:60] for x in e["out_of_scope"]], unresolved=[x["description"][:60] for x in e.get("unresolved", [])],
                checks=sorted({f"{c['level']}: {c['code']}" for c in q["checks"]}), cats={c["name"]: c["amount"] for c in e["categories"]},
                cost_per_sqft=q["summary"]["cost_per_sqft"])


def main():
    os.makedirs(OUT, exist_ok=True)
    data = open(IMG, "rb").read()
    fn = "demo_05_additional_4th__5th___6th_floors.png"
    with TestClient(app.app) as c:
        p = c.post("/api/projects", data={"name": "hospital (rerun, defaults)", "loc": '{"district":"Chennai"}'}).json()
        a = c.post(f"/api/projects/{p['id']}/files", files={"files": (fn, data)}).json()
        open(os.path.join(OUT, "hospital_rerun_a_defaults.pdf"), "wb").write(c.get(f"/api/projects/{p['id']}/report.pdf").content)
        A = summ(a, "a_defaults (no user input)")
        sc = {"type": "floors", "label": "Additional 4th, 5th & 6th floors", "config": {"floors_list": "4,5,6", "assumption_policy": "provisional"}}
        p2 = c.post("/api/projects", data={"name": "hospital (rerun, reviewed)", "loc": '{"district":"Chennai"}', "scope": json.dumps(sc)}).json()
        b = c.post(f"/api/projects/{p2['id']}/files", files={"files": (fn, data)}).json()
        i = next(k for k, s in enumerate(b["sheets"]) if s["kind"] == "floor_plan")
        c.patch(f"/api/projects/{p2['id']}/sheets/{i}", json={"opening_confirmed": {"door": 27, "window": 12}})
        b = c.patch(f"/api/projects/{p2['id']}/sheets/{i}", json={"floor": {"label": "Typical floor — floors 4, 5, 6", "level": 4, "repeat": 3,
                                                                           "occurrences": [4, 5, 6]}}).json()
        open(os.path.join(OUT, "hospital_rerun_b_reviewed_provisional.pdf"), "wb").write(c.get(f"/api/projects/{p2['id']}/report.pdf").content)
        B = summ(b, "b_reviewed (scope floors 4,5,6; counts confirmed 27/12; floors confirmed; provisional assumptions)")
        sc["config"]["assumption_policy"] = "strict"
        b2 = c.patch(f"/api/projects/{p2['id']}", json={"scope": sc}).json()
        open(os.path.join(OUT, "hospital_rerun_c_reviewed_strict.pdf"), "wb").write(c.get(f"/api/projects/{p2['id']}/report.pdf").content)
        C = summ(b2, "c_reviewed_strict (as b, assumed structure left unresolved)")
    json.dump([A, B, C], open(os.path.join(OUT, "hospital_rerun_summary.json"), "w"), indent=1, default=str)
    for d in (A, B, C):
        print(d["tag"][:40], d["total"], d["status"])


if __name__ == "__main__":
    main()
