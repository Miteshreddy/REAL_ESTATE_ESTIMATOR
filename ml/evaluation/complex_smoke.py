"""Blind smoke test on the Tamil Nadu complex-architecture set (Task 9).

Only the drawing image is uploaded through the real API (temporary data directory); the reference headers are NOT passed
to the estimator. The only scored property is SHEET CLASS (site / campus layout vs building floor plan), whose expected value
was recorded from the headers BEFORE running (data/evaluation/tn/complex_smoke/expected.json). Everything else is reported
as observed behaviour — these images are copyrighted third-party material: smoke test only, no ground truth, n = 4.

Usage: python ml/evaluation/complex_smoke.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data", "evaluation", "tn", "complex_smoke")
EXPECTED = {"case01": dict(sheet_class="floor_plan", note="Apollo Hospital Chennai — dense hospital floor plan"),
            "case03": dict(sheet_class="floor_plan", note="Tiruppur GH oncology — site plan + ground floor plan on one sheet"),
            "case04": dict(sheet_class="site_plan", note="AIIMS Madurai — campus site layout 1:2000: must NOT be costed as a floor plan"),
            "case05": dict(sheet_class="floor_plan", note="Vishwaksena Global School — rendered presentation board with a floor plan")}


def main():
    json.dump(EXPECTED, open(os.path.join(D, "expected.json"), "w"), indent=1)
    os.environ["EST_DATA_DIR"] = tempfile.mkdtemp(prefix="smoke_")
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    os.chdir(os.path.join(ROOT, "backend"))
    import app as A
    from fastapi.testclient import TestClient
    rows = []
    with TestClient(A.app) as c:
        for case, exp in EXPECTED.items():
            f = os.path.join(D, case + ".png")
            r = c.post("/api/projects", data=dict(name=case, loc="{}"), files={"files": (case + ".png", open(f, "rb").read(), "image/png")})
            if r.status_code != 200:
                rows.append(dict(case=case, error=r.text[:200]))
                continue
            p = r.json()
            kinds = [s.get("kind") for s in p["sheets"]]
            got = "site_plan" if "site_plan" in kinds and "floor_plan" not in kinds else "floor_plan" if "floor_plan" in kinds else (kinds[0] if kinds else None)
            fp = [s for s in p["sheets"] if s.get("kind") == "floor_plan"]
            rows.append(dict(case=case, expected=exp["sheet_class"], observed=got, correct=got == exp["sheet_class"], sheet_kinds=kinds,
                             site_plan_reason=[s.get("site_plan_reason") for s in p["sheets"] if s.get("site_plan_reason")],
                             rooms=sum(len(s.get("rooms", [])) for s in fp), openings=sum(len(s.get("openings", [])) for s in fp),
                             scale=[(s.get("scale") or {}).get("method") for s in fp], floors=[(s.get("floor_info") or {}).get("label") for s in fp],
                             checks=[x["code"] for x in p.get("checks", [])], completeness=p["stats"]["completeness"]["text"],
                             total_inr=p["estimate"]["total"], note=exp["note"]))
            print(rows[-1], flush=True)
    ok = [r for r in rows if "correct" in r]
    out = dict(kind="SMOKE TEST — third-party images, NOT ground truth, n=4 (case02 placeholder rejected)", rows=rows,
               sheet_class_correct=sum(r["correct"] for r in ok), sheet_class_total=len(ok))
    json.dump(out, open(os.path.join(D, "smoke_results.json"), "w"), indent=1, default=str)
    print("sheet class correct:", out["sheet_class_correct"], "/", out["sheet_class_total"])


if __name__ == "__main__":
    main()
