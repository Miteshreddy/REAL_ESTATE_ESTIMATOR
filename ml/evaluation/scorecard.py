"""Final TN scorecard (Task 17): 15 pre-defined gates + labelled evidence rows. Machine-generated; nothing estimated.

Gate status:
  PASS / FAIL          measured on ≥ min_projects FINAL-HOLDOUT Tamil Nadu projects with ≥ min_samples verified examples
  INSUFFICIENT DATA    some holdout evidence, below the minimum sample / project count
  NOT MEASURED         no verified TN ground truth exists for the gate
  NOT VALIDATED        cost / mapping gates without approved BOQs / engineer reviews
Development-benchmark (exposed), smoke, synthetic, generic (CubiCasa) and non-TN reference results are EVIDENCE ROWS only and
can never satisfy a gate. Overall PASS requires every critical gate to PASS.
"""
import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gates import GATES  # noqa: E402


def load(p):
    p = os.path.join(D, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def provenance():
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "backend", "ml"], cwd=ROOT, capture_output=True, text=True).stdout.strip())
    except OSError:
        commit, dirty = None, None
    man = load(os.path.join("tn_dataset", "metadata", "split_manifest.json")) or {}
    reg = load(os.path.join("models", "registry.json")) or {}
    return dict(code_commit=commit, uncommitted_changes=dirty, dataset_manifest_sha256=man.get("sha256"), split_seed=man.get("seed"),
                models={m["model_name"]: m.get("version") for m in reg.get("models", [])}, evaluated_at=datetime.datetime.now().isoformat(timespec="seconds"))


def evidence():
    rows = []
    E = lambda **k: rows.append(k)
    tn = load("tn_eval_results.json")
    if tn:
        s = tn["summary"]
        E(name="Plinth area within ±10 %", value=s["plinth_within_10pct"], n=s["plinth_checked"], label="DEVELOPMENT (exposed)",
          dataset="TN Rural Development type-design sheets", gt="written plinth-area notes", note=f"median APE {s['plinth_median_err_pct']} %")
        E(name="Sheet view classification", value=s["view_correct_pct"], n=s["sheets"], label="DEVELOPMENT (exposed)",
          dataset="TN Rural Development type-design sheets", gt="hand-labelled plan boxes")
    ap = load(os.path.join("evaluation", "tn", "aparna_regression.json"))
    if ap:
        a = ap["after"]
        E(name="Floor occurrences (refuge floor)", value=100.0 if ap["agreement"]["floor_occurrences_match"] else 0.0, n=1, label="REFERENCE (non-TN: Hyderabad)",
          dataset="Aparna Block-A refuge floor", gt="floor list printed on the sheet")
        E(name="Apartments found", value=round(100 * min(1, ap["agreement"]["units_found"] / ap["printed_reference"]["flats_3bhk"]), 1), n=1,
          label="REFERENCE (non-TN: Hyderabad)", dataset="Aparna Block-A refuge floor", gt="area statement table")
        E(name="Openings detected (no reference)", value=None, n=1, label="REFERENCE (non-TN: Hyderabad)", dataset="Aparna",
          gt="none", note=f"{a.get('doors')} doors / {a.get('windows')} windows — not scored")
    sm = load(os.path.join("evaluation", "tn", "complex_smoke", "smoke_results.json"))
    if sm:
        E(name="Site-plan vs floor-plan classification", value=round(100 * sm["sheet_class_correct"] / max(1, sm["sheet_class_total"]), 1),
          n=sm["sheet_class_total"], label="SMOKE (third-party images, exposed after one fix)", dataset="TN complex-architecture set (4 usable images)",
          gt="expected class recorded from headers before the run")
    ac = load("accuracy_eval_results.json")
    if ac and "real_commercial_openings" in ac:
        rc = ac["real_commercial_openings"]
        E(name="Door count within ±10 % of tags", value=rc["door_count"].get("within10_pct"), n=rc["sheets"], label="REFERENCE (non-TN: Bihar)",
          dataset="Nalanda commercial", gt="opening tags")
        E(name="Window count within ±10 % of tags", value=rc["window_count"].get("within10_pct"), n=rc["sheets"], label="REFERENCE (non-TN: Bihar)",
          dataset="Nalanda commercial", gt="opening tags")
    re_ = load("real_eval_results.json")
    if re_:
        s = re_["summary"]
        E(name="Room area within ±10 %", value=s["within_10pct"], n=s["labelled_rooms"], label="REFERENCE (non-TN: Uttarakhand)",
          dataset="Uttarakhand Govt CAD", gt="room dimension labels", note=f"median {s['median_abs_err_pct']} %")
    det = load(os.path.join("models", "opening_det.metrics.json"))
    if det:
        for sp in ("train", "val", "test"):
            for k in ("door", "window"):
                E(name=f"Detector {k} F1 ({sp})", value=round(det[sp][k]["f1"] * 100, 1), n={"train": 4200, "val": 400, "test": 400}[sp],
                  label="GENERIC (CubiCasa5K — not TN)", dataset="CubiCasa5K", gt="CubiCasa SVG annotations")
    if ac and "synthetic_basic" in ac:
        for f in ("dxf", "pdf", "png"):
            t = ac["synthetic_basic"][f]["total_cost"]
            E(name=f"Total vs exact geometry ({f})", value=t["within5_pct"], n=t["n"], label="SYNTHETIC", dataset="generator", gt="generated geometry")
    pc = load(os.path.join("evaluation", "tn", "pricing_coverage.json"))
    if pc:
        E(name="Take-off lines priced from TN data", value=pc["priced_pct"], n=pc["total"], label="COVERAGE (sample drawings)",
          dataset=pc.get("samples", "villa_g1"), gt="n/a (coverage, not accuracy)")
    return rows


def gates(evid):
    ds = load(os.path.join("tn_dataset", "metadata", "projects.json")) or {}
    holdout = [p for p in ds.values() if p.get("split") == "final_holdout"]
    con = sqlite3.connect(os.path.join(D, "estimate.db"))
    tbl = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    approved_boqs = con.execute("SELECT COUNT(DISTINCT project_id) FROM boq_uploads WHERE approval_status='approved'").fetchone()[0] if "boq_uploads" in tbl else 0
    reviews = con.execute("SELECT COUNT(*) FROM mapping_reviews WHERE decision='approve'").fetchone()[0] if "mapping_reviews" in tbl else 0
    pc = load(os.path.join("evaluation", "tn", "pricing_coverage.json"))
    out = []
    for g in GATES:
        r = dict(g, value=None, evidence_projects=len(holdout))
        if g["id"] in ("G11", "G12", "G13", "G14"):
            r["status"] = "NOT VALIDATED" if approved_boqs < g["min_projects"] else "INSUFFICIENT DATA"
            r["reason"] = f"{approved_boqs} approved Tamil Nadu BOQ project(s); {g['min_projects']} required"
        elif g["id"] == "G09":
            r["status"] = "NOT VALIDATED" if reviews == 0 else "INSUFFICIENT DATA" if reviews < g["min_samples"] else "PENDING"
            r["reason"] = f"{reviews} engineer-approved mapping(s); {g['min_samples']} required"
        elif g["id"] == "G10":
            r["value"] = pc["priced_pct"] if pc else None
            r["status"] = ("PASS" if r["value"] >= g["threshold"] else "FAIL") if pc else "NOT MEASURED"
            r["reason"] = "coverage of applicable take-off lines on the sample drawings (needs no ground truth)"
        elif g["id"] == "G15":
            r["status"] = "NOT MEASURED"
            r["reason"] = "NOT CALIBRATED — no labelled TN validation predictions"
        else:
            r["status"] = "NOT MEASURED" if not holdout else "INSUFFICIENT DATA"
            r["reason"] = (f"{len(holdout)} final-holdout TN project(s) with verified ground truth; {g['min_projects']} required. "
                           "Development-benchmark / reference results are shown as evidence only.")
        out.append(r)
    crit = [r for r in out if r["critical"]]
    final = "PASS" if all(r["status"] == "PASS" for r in crit) else "FAIL"
    return out, final, dict(final_holdout_projects=len(holdout), approved_boq_projects=approved_boqs, engineer_reviews=reviews)


def build():
    ev = evidence()
    gs, final, counts = gates(ev)
    sc = dict(generated=datetime.date.today().isoformat(), target_pct=90.0, final=final, provenance=provenance(), counts=counts, gates=gs, evidence=ev,
              rule="A system cannot PASS while any critical gate is not PASS. Evidence rows never satisfy a gate.")
    json.dump(sc, open(os.path.join(D, "evaluation", "tn", "scorecard.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return sc


def pricing_coverage(samples=("villa_g1.dxf", "compact_home.dxf", "bungalow.dxf")):
    B = os.path.join(ROOT, "backend")
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
    m = Models(os.path.join(D, "models"))
    tot = pri = 0
    gaps = {}
    for f in samples:
        items = takeoff.compute_quantities(parsers.parse_any(os.path.join(D, "samples", f), m), dict(takeoff.DEFAULT_PARAMS))
        tn_pricing.price_items(con, items, by, dict(financial_year="2025-26"))
        tot += len(items)
        pri += sum(1 for i in items if i.get("derived") or i.get("sor_code"))
        for i in items:
            if not (i.get("derived") or i.get("sor_code")):
                gaps[i["key"]] = i.get("rate_gap")
    r = dict(samples=", ".join(samples), priced=pri, total=tot, priced_pct=round(100 * pri / tot, 1), unpriced=gaps,
             schedule=sid, measured=datetime.datetime.now().isoformat(timespec="seconds"))
    json.dump(r, open(os.path.join(D, "evaluation", "tn", "pricing_coverage.json"), "w"), indent=1)
    return r
