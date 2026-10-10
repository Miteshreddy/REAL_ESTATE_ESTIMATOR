"""Tamil Nadu evaluation + scorecard. Runs / collects every evaluation and writes data/evaluation/tn/scorecard.json.

    python ml/evaluation/run_tn_eval.py basic        # TN government sheets (plinth area, view classification)
    python ml/evaluation/run_tn_eval.py large        # Aparna (floors, units, unit areas, openings)
    python ml/evaluation/run_tn_eval.py commercial   # TN commercial set (none yet) + non-TN reference (Nalanda)
    python ml/evaluation/run_tn_eval.py unseen       # all of the above + detector + synthetic + pricing → scorecard
    python ml/evaluation/run_tn_eval.py scorecard    # rebuild the scorecard from the stored results only

Every metric states dataset, projects, metric, ground-truth source, split, model version and evaluation date.
A metric without TN ground truth is NOT MEASURED; cost without an approved BOQ is NOT VALIDATED. Nothing is estimated.
"""
import datetime
import json
import os
import sqlite3
import statistics as st
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
B = os.path.join(ROOT, "backend")
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "evaluation", "tn", "scorecard.json")
TARGET = 90.0
TODAY = datetime.date.today().isoformat()


def run(script, *args):
    subprocess.run([sys.executable, script, *args], cwd=B, check=False, env=dict(os.environ, PYTHONIOENCODING="utf-8"))


def load(p):
    p = os.path.join(D, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def model_versions():
    reg = load(os.path.join("models", "registry.json")) or {}
    det = load(os.path.join("models", "opening_det.metrics.json"))
    return dict(unet="floorplan_unet 1.0", detector=("opening_det " + (det or {}).get("version", "v1")) if det else "not trained",
                rules="hybrid geometry/OCR rules (backend @ HEAD)", registry=[m["model_name"] for m in reg.get("models", [])])


def M(name, value, dataset, projects, metric, gt, split, cls, status=None, note=None):
    s = status or ("NOT MEASURED" if value is None else "PASS" if value >= TARGET else "FAIL")
    return dict(name=name, value=None if value is None else round(value, 1), status=s, dataset=dataset, projects=projects, metric=metric,
                ground_truth=gt, split=split, class_=cls, model_version=model_versions(), evaluation_date=TODAY, note=note)


def scorecard():
    rows = []
    tn = load("tn_eval_results.json")
    if tn:
        s = tn["summary"]
        rows.append(M("AREA (basic, plinth)", s["plinth_within_10pct"], "TN Govt type-design sheets", s["plinth_checked"],
                      "% of plans with plinth area within ±10%", "written plinth-area notes (hand-labelled)", "unseen_test", "BASIC",
                      note=f"median APE {s['plinth_median_err_pct']}%"))
        rows.append(M("SHEET VIEW (basic)", s["view_correct_pct"], "TN Govt type-design sheets", s["sheets"], "% sheets with correct plan view",
                      "hand-labelled plan boxes", "unseen_test", "BASIC"))
    ap = load(os.path.join("evaluation", "tn", "aparna_regression.json"))
    if ap:
        a = ap["after"]
        PR = ap["printed_reference"]
        rows.append(M("FLOOR (large)", 100.0 if ap["agreement"]["floor_occurrences_match"] else 0.0, "Aparna refuge floor", 1,
                      "floor occurrences exactly correct", "floor list printed on the sheet", "unseen_test", "LARGE", note="n = 1 drawing"))
        rows.append(M("UNIT (large)", 100.0 * min(1, ap["agreement"]["units_found"] / PR["flats_3bhk"]), "Aparna refuge floor", 1,
                      "apartments found / printed", "area statement table", "unseen_test", "LARGE", note="n = 1 drawing"))
        errs = []
        sft = {v: PR["carpet_sft"][k] for k, v in PR["saleable_sft"].items()}
        for u in a.get("units") or []:
            ref = sft.get(int(u.get("stated_area_sft") or 0))
            if ref:
                errs.append(abs(u["measured_area_m2"] * 10.764 / ref - 1))
        if errs:
            rows.append(M("ROOM / UNIT AREA (large)", 100.0 * sum(e <= 0.10 for e in errs) / len(errs), "Aparna refuge floor", 1,
                          "% units with carpet area within ±10%", "printed carpet area per flat", "unseen_test", "LARGE",
                          note=f"median APE {st.median(errs) * 100:.1f}% over {len(errs)} units"))
        rows.append(M("DOOR (large)", None, "Aparna refuge floor", 1, "door F1", "no door ground truth printed", "unseen_test", "LARGE",
                      note=f"system count {a.get('doors')} (no reference) — needs annotation"))
        rows.append(M("WINDOW (large)", None, "Aparna refuge floor", 1, "window F1", "no window ground truth printed", "unseen_test", "LARGE",
                      note=f"system count {a.get('windows')} (no reference) — needs annotation"))
    rows.append(M("COMMERCIAL / INSTITUTIONAL (TN)", None, "none", 0, "any", "no TN commercial drawing set with ground truth", "unseen_test", "COMMERCIAL"))
    ac = load("accuracy_eval_results.json")
    if ac and "real_commercial_openings" in ac:
        rc = ac["real_commercial_openings"]
        rows.append(M("DOOR count (non-TN reference)", rc["door_count"].get("within10_pct"), "Nalanda (Bihar) — NOT TN", rc["sheets"],
                      "% sheets door count within ±10% of tags", "opening tags printed on the plan", "reference", "COMMERCIAL",
                      status="REFERENCE ONLY", note="non-TN; shown so the commercial weakness is not hidden"))
        rows.append(M("WINDOW count (non-TN reference)", rc["window_count"].get("within10_pct"), "Nalanda (Bihar) — NOT TN", rc["sheets"],
                      "% sheets window count within ±10% of tags", "opening tags", "reference", "COMMERCIAL", status="REFERENCE ONLY"))
    re_ = load("real_eval_results.json")
    if re_:
        s = re_["summary"]
        rows.append(M("ROOM AREA (non-TN reference)", s["within_10pct"], "Uttarakhand Govt CAD — NOT TN", s["files"],
                      "% rooms within ±10% of written dimensions", "room dimension labels", "reference", "BASIC", status="REFERENCE ONLY",
                      note=f"{s['labelled_rooms']} rooms, median APE {s['median_abs_err_pct']}%"))
    det = load(os.path.join("models", "opening_det.metrics.json"))
    if det:
        for sp, lab in (("train", "TRAIN"), ("val", "VALIDATION"), ("test", "TEST")):
            for k in ("door", "window"):
                rows.append(M(f"DETECTOR {k.upper()} F1 ({lab})", det[sp][k]["f1"] * 100, "CubiCasa5K — NOT TN (generic pretraining)",
                              {"train": 4200, "val": 400, "test": 400}[sp], f"{k} F1 @0.5 IoU", "CubiCasa SVG annotations", sp, "PRETRAINING",
                              status="REFERENCE ONLY"))
    if ac and "synthetic_basic" in ac:
        for f in ("dxf", "pdf", "png"):
            t = ac["synthetic_basic"][f]["total_cost"]
            rows.append(M(f"SYNTHETIC total vs exact geometry ({f})", t["within5_pct"], "generator (SYNTHETIC)", t["n"], "% within ±5%",
                          "exact generated geometry", "synthetic", "BASIC", status="SYNTHETIC — NOT REAL"))
    con = sqlite3.connect(os.path.join(D, "estimate.db"))
    runs = [json.loads(r[0]) for r in con.execute("SELECT metrics FROM evaluation_runs WHERE kind='reference_boq'")] \
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='evaluation_runs'").fetchone() else []
    real_runs = [r for r in runs if r.get("reference_lines", 0) > 3]
    rows.append(M("TOTAL COST vs approved BOQ", None, "approved TN BOQs", len(real_runs), "total cost within ±10%", "approved BOQ",
                  "unseen_test", "COST", status="NOT VALIDATED" if not real_runs else None))
    pc = load(os.path.join("evaluation", "tn", "pricing_coverage.json"))
    if pc:
        rows.append(M("PWD RATE COMPLETENESS", pc["priced_pct"], "villa_g1 sample take-off", 1, "% take-off lines priced from TN data",
                      "TN SOR / Standard Data", "n/a", "PRICING", status="COVERAGE (not accuracy)"))
    measured = [r for r in rows if r["status"] in ("PASS", "FAIL")]
    final = "PASS" if measured and all(r["status"] == "PASS" for r in measured) and not any(r["status"] in ("NOT MEASURED", "NOT VALIDATED") for r in rows) else "FAIL"
    sc = dict(generated=TODAY, target_pct=TARGET, final=final, rows=rows,
              summary=dict(measured=len(measured), passed=sum(r["status"] == "PASS" for r in measured),
                           not_measured=sum(r["status"] == "NOT MEASURED" for r in rows), not_validated=sum(r["status"] == "NOT VALIDATED" for r in rows)))
    json.dump(sc, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return sc


def pricing_coverage():
    sys.path.insert(0, B)
    os.chdir(B)
    import parsers
    import takeoff
    import tn_pricing
    from ml import Models
    con = sqlite3.connect(os.path.join(D, "estimate.db"))
    con.row_factory = sqlite3.Row
    sid = con.execute("SELECT id FROM rate_schedules WHERE region='Tamil Nadu' AND status='active'").fetchone()[0]
    by = {r["code"]: dict(r) for r in con.execute("SELECT code, description, unit, rate FROM rate_items WHERE schedule_id=?", (sid,))}
    sh = parsers.parse_any(os.path.join(D, "samples", "villa_g1.dxf"), Models(os.path.join(D, "models")))
    items = takeoff.compute_quantities(sh, dict(takeoff.DEFAULT_PARAMS))
    tn_pricing.price_items(con, items, by, dict(financial_year="2025-26"))
    priced = [i for i in items if i.get("derived") or i.get("sor_code")]
    r = dict(priced=len(priced), total=len(items), priced_pct=round(100 * len(priced) / len(items), 1),
             unpriced={i["key"]: i.get("rate_gap") for i in items if not (i.get("derived") or i.get("sor_code"))})
    json.dump(r, open(os.path.join(D, "evaluation", "tn", "pricing_coverage.json"), "w"), indent=1)
    return r


if __name__ == "__main__":
    import scorecard as SC
    what = sys.argv[1] if len(sys.argv) > 1 else "scorecard"
    if what in ("basic", "unseen"):
        run("tn_eval.py")
    if what in ("large", "unseen"):
        run("aparna_regression.py")
    if what in ("commercial", "unseen"):
        run("commercial_eval.py")
        subprocess.run([sys.executable, os.path.join(ROOT, "ml", "evaluation", "complex_smoke.py")], check=False,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    if what == "unseen":
        run("real_eval.py", os.path.join(ROOT, "ml", "test_drawings", "uttarakhand", "dxf", "ARCH_*.dxf"))
        SC.pricing_coverage()
    sc = SC.build()
    print("GATES")
    for g in sc["gates"]:
        print(f"  {g['id']} {g['name']:38} {'' if g['value'] is None else str(g['value']) + '%':>7}  {g['status']:18} {g.get('reason', '')[:90]}")
    print("EVIDENCE (cannot satisfy a gate)")
    for r in sc["evidence"]:
        print(f"  {r['name']:44} {'' if r['value'] is None else str(r['value']) + '%':>7}  n={r['n']:<5} {r['label']}")
    print("FINAL:", sc["final"])
