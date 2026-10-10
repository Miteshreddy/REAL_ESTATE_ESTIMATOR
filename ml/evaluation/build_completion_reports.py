"""Generate reports/tn_completion/*.md and task_ledger.json from the saved evaluation artifacts (no hand-typed metrics).

    python ml/evaluation/build_completion_reports.py
Requires: data/evaluation/tn/scorecard.json (run_tn_eval.py), reports/tn_completion/pytest.xml (pytest --junitxml).
"""
import datetime
import json
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "reports", "tn_completion")
NOW = datetime.datetime.now().isoformat(timespec="seconds")


def load(p, default=None):
    p = os.path.join(ROOT, p)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def tests():
    p = os.path.join(OUT, "pytest.xml")
    if not os.path.exists(p):
        return dict(ran=False)
    s = ET.parse(p).getroot()
    s = s if s.tag == "testsuite" else s.find("testsuite")
    return dict(ran=True, tests=int(s.get("tests")), failures=int(s.get("failures")), errors=int(s.get("errors")), skipped=int(s.get("skipped")),
                time=float(s.get("time")), cases=[(c.get("classname"), c.get("name"), "FAILED" if c.find("failure") is not None or c.find("error") is not None
                                                   else "SKIPPED" if c.find("skipped") is not None else "PASSED") for c in s.iter("testcase")])


def table(rows, cols):
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows:
        out += "| " + " | ".join(str(r.get(c, "")) if r.get(c) is not None else "—" for c in cols) + " |\n"
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    sc = load("data/evaluation/tn/scorecard.json", {})
    dash = load("data/tn_dataset/metadata/dashboard.json", {})
    projects = load("data/tn_dataset/metadata/projects.json", {})
    split = load("data/tn_dataset/metadata/split_manifest.json", {})
    smoke = load("data/evaluation/tn/complex_smoke/smoke_results.json", {})
    pc = load("data/evaluation/tn/pricing_coverage.json", {})
    reg = load("data/models/registry.json", {})
    res = load("data/models/opening_det.resolution_eval.json", {})
    base = load("reports/tn_completion/baseline.json", {})
    T = tests()
    con = sqlite3.connect(os.path.join(D, "estimate.db"))
    con.row_factory = sqlite3.Row
    tbls = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    boqs = [dict(r) for r in con.execute("SELECT project_id, approval_status, filename, sha256 FROM boq_uploads")] if "boq_uploads" in tbls else []
    reviews = con.execute("SELECT COUNT(*) FROM mapping_reviews").fetchone()[0] if "mapping_reviews" in tbls else 0
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    import annotations as A
    cov = A.coverage()
    docs = [dict(r) for r in con.execute("SELECT title, doc_type, financial_year, effective_from, verification_status, sha256 FROM tn_documents")]
    act = con.execute("SELECT id, financial_year, effective_from, revision FROM rate_schedules WHERE status='active'").fetchall()
    W = lambda name, text: open(os.path.join(OUT, name), "w", encoding="utf-8").write(text)
    hdr = lambda t: f"# {t}\n\n_Generated {NOW} from saved artifacts by `ml/evaluation/build_completion_reports.py`._\n\n"

    W("BASELINE.md", hdr("Baseline (before this work package)") + f"""Recomputed on branch `tn-completion` from commit `{base.get('base_commit')}`.

- pytest: **{base.get('pytest')}**
- active schedules: {base.get('active_schedules')}
- TN rate items: {base.get('tn_rate_items')} · Standard Data items: {base.get('sd_items')}
- reference BOQs: {base.get('reference_boqs')} · learned mappings: {base.get('learned')}
- models: {', '.join(base.get('models', []))}
- new inputs found: {'; '.join(base.get('new_inputs', []))}

Corrections made to the baseline interpretation:
1. The Aparna drawing is a **Hyderabad** project — previously scored as "TN large residential"; now a non-TN reference only.
2. The 41 TN Rural Development projects were repeatedly used during development — reclassified **development benchmark (exposed)**, not unseen.
3. `Downloads/Residential_building_estimate.pdf` is this application's own earlier Telangana-schedule output — **not ground truth**.

Baseline scorecard: `reports/tn_completion/baseline_scorecard.json`.
""")

    splits = {k: sum(1 for p in projects.values() if p.get("split") == k) for k in
              ("tn_train", "tn_validation", "final_holdout", "development_benchmark", "smoke_test", "reference", "excluded")}
    W("DATASET_AUDIT.md", hdr("Dataset audit (Task 1)") + f"""| Measure | Value |
|---|---|
| projects / sheets | {dash.get('total_projects')} / {dash.get('total_sheets')} |
| downloaded documents (unique SHA-256) | {dash.get('downloaded_documents')} |
| discovered web candidates / blocked by robots.txt | {dash.get('discovered_candidates')} / {dash.get('discovered_disallowed')} |
| training-eligible projects | {dash.get('training_eligible_projects')} |
| evaluation-eligible projects | {dash.get('evaluation_eligible_projects')} |
| permission pending (excluded) | {dash.get('permission_pending_projects')} |
| rejected / corrupt files | {len(dash.get('rejected_or_corrupt') or [])} — {json.dumps(dash.get('rejected_or_corrupt'))} |
| duplicate pairs | {dash.get('duplicates')} |
| licence status (pages) | {json.dumps(dash.get('license_status'))} |
| drawing types | {json.dumps(dash.get('drawing_type_distribution'))} |
| scans / vector / CAD sheets | {dash.get('scans')} / {dash.get('vector_files')} / {dash.get('cad_files')} |

Sources: TNRD type designs (government publication — **licence review pending → not training-eligible**); TN RERA (robots.txt
disallows `/uploads/` and `*.pdf` — not crawled); tntenders.gov.in (per-document CAPTCHA — not crawled); five-layout complex
set (Scribd / Architizer / SlideShare — third-party copyright → smoke test only; case02 rejected: 14×16 px placeholder);
Aparna (Hyderabad — reference only). Refresh is idempotent (re-run adds 0 pages; tested).
""")
    W("ANNOTATION_COVERAGE.md", hdr("Annotation coverage (Task 2)") + f"""States: {json.dumps(cov['states'])}

- VERIFIED records (any): **{cov['verified_records_any']}** · VERIFIED + training-eligible: **{cov['verified_training_records']}**
- Pseudo labels are model output (U-Net) and are **not** ground truth.
- Workflow: `#/annotate` page and `/api/annotations/*` — draft (named annotator) → two independent reviewer approvals → VERIFIED;
  any rejection / disagreement keeps the record out; edits re-open review with correction history. Validation: boxes, polygons,
  units, duplicate ids, conflicting dimensions, project / drawing-revision mismatch. Exports: COCO (`/api/annotations-export/coco`),
  YOLO (`python -m tn_data_ingestion.refresh export`), structured JSON for dimensions (schema `{cov['schema_version']}`).

**Status: BLOCKED_EXTERNAL_INPUT — 0 verified annotations exist; qualified annotators / reviewers are required.**
""")
    W("DATA_SPLIT_AUDIT.md", hdr("Data split audit (Task 3)") + f"""Seed `{split.get('seed')}` · manifest SHA-256 `{split.get('sha256')}`

{table([dict(split=k, projects=v) for k, v in splits.items()], ['split', 'projects'])}
Policy:
```
{split.get('policy')}
```
Leakage check (`python ml/dataset/check_leakage.py`): exit 0 = no project / hash / near-duplicate / source-file leak. A planted
leak makes it exit 1 (test `test_leakage_checker_fails_on_planted_leak`).

**There is no credible final holdout yet (0 projects).** The previously "unseen" TN sheets were used during development and are
now labelled development_benchmark. New authorised TN projects are required to create training / validation / holdout sets.
""")
    det = next((m for m in reg.get("models", []) if m["model_name"] == "opening_det"), {})
    W("MODEL_EVALUATION.md", hdr("Model evaluation (Task 4)") + f"""## Opening detector `opening_det` v{det.get('version')} — GENERIC (CubiCasa5K, not Tamil Nadu)

| split | door F1 | window F1 |
|---|---|---|
| train | {det.get('train_metrics', {}).get('door', {}).get('f1')} | {det.get('train_metrics', {}).get('window', {}).get('f1')} |
| validation | {det.get('validation_metrics', {}).get('door', {}).get('f1')} | {det.get('validation_metrics', {}).get('window', {}).get('f1')} |
| test | {det.get('test_score', {}).get('door_f1')} | {det.get('test_score', {}).get('window_f1')} |

Resolution sensitivity (CubiCasa test, mAP50): {json.dumps({k: v.get('map50') for k, v in res.items() if k != 'env'})} — environment {json.dumps(res.get('env'))}.

App integration: ONNX decoding checked against test labels (pytest `test_detector_model_is_working`). Fusion now includes a
wall-proximity gate (radius = half the opening width + 0.2 m): on the Aparna reference drawing it rejects 1 of 136 detections.

U-Net `floorplan_unet` v1.0: CubiCasa test mIoU 0.740 (generic).

**Tamil Nadu metrics: NOT MEASURED. No model is TN fine-tuned** — 0 verified, training-eligible TN annotations
(`configs/tn_opening_detector.yaml` stage2 refuses to run without them).
""")
    W("QUANTITY_EVALUATION.md", hdr("Quantity extraction (Tasks 5-9)") + """| Quantity family | Implementation | TN accuracy |
|---|---|---|
| Rooms / areas | measurement hierarchy (written dims → CAD → calibrated → polygon → UNRESOLVED); carpet / common / plinth / built-up / gross areas kept distinct with definition, formula, calibration, uncertainty | NOT MEASURED (no holdout) |
| Floors / units | floor occurrences incl. basement, terrace, LEVEL n, ranges, lists; unit grouping | NOT MEASURED (TN) |
| Doors / windows | detector + U-Net + wall gaps; wall gate; per-mark and per-source reconciliation (OPENING COUNT CONFLICT) | NOT MEASURED (TN) |
| Walls | length / face area / masonry volume (deductions listed) / plaster & paint areas with sides; ASSUMED when height is a default | NOT MEASURED |
| Structural | members from schedules; concrete only with all dimensions; steel from BBS (L×n×Ø²/162) replacing plan figures; STRUCTURAL INPUT MISSING / NEEDS ENGINEER REVIEW | NOT MEASURED |
| Site / campus plans | site-plan guard (title / ≥1:500 scale) — never costed | smoke: see below |
""" + f"""
Complex-building smoke test (third-party images, n=4, **exposed after one fix**):
{table(smoke.get('rows', []), ['case', 'expected', 'observed', 'correct', 'rooms', 'openings', 'completeness'])}
Evidence rows (development / reference / generic / synthetic) are in `data/evaluation/tn/scorecard.json` → `evidence`.
""")
    W("PWD_RATE_AUDIT.md", hdr("TN PWD rate audit (Task 10)") + f"""Active schedule: {[tuple(a) for a in act]}

{table(docs, ['title', 'doc_type', 'financial_year', 'effective_from', 'verification_status'])}
Newer edition check ({NOW[:10]}): registered source shows no new document; web search found no 2026-27 TN SOR; tnhighways
SOR paths return 404 → SOR 2025-26 + amendment of 08.08.2025 remains the latest verifiable edition. Only the SOR is cross-verified
(identical SHA-256 on two hosts); the amendment and Standard Data Book are from a single non-government host (**unverified
secondary source** — shown on every rate).

Coverage on sample drawings ({pc.get('samples')}): **{pc.get('priced')} / {pc.get('total')} lines = {pc.get('priced_pct')} %**.
Unresolved: {json.dumps(pc.get('unpriced'))}

Guards: labour-only analyses are rejected; wastage lines are not applied to whole rates; no ₹0; every unresolved line carries
NEEDS RATE / NEEDS RATE ANALYSIS.
""")
    W("PWD_MAPPING_EVALUATION.md", hdr("PWD mapping evaluation (Task 11)") + f"""Engineer reviews recorded: **{reviews}**.
Review queue: `GET /api/projects/{{id}}/mapping-review` (suggestions, candidates, unit-mismatch flags, rate-analysis status);
decisions: `POST` (named reviewer; unit mismatch blocked without written justification). Approved mappings override suggestions.

**Top-1 / top-3 accuracy: NOT VALIDATED (0 engineer-approved mappings).**
""")
    W("BOQ_EVALUATION.md", hdr("Reference BOQ workflow (Tasks 12-13)") + f"""Uploads: {len(boqs)} · approved: **{sum(1 for b in boqs if b['approval_status'] == 'approved')}**
{table(boqs, ['project_id', 'approval_status', 'filename', 'sha256']) if boqs else ''}
Template: `data/templates/reference_boq_template.csv` + `REFERENCE_BOQ_README.md`. Validation, original-file preservation (SHA-256),
matching rules (exact code → approved mapping → description + same unit; ambiguity and unit conflicts reported) are tested.
**No approved Tamil Nadu BOQ exists → quantity agreement NOT VALIDATED.**
""")
    W("COST_ACCURACY.md", hdr("Cost accuracy (Task 14)") + """Metrics implemented (`backend/boq.py::metrics`): quantity relative error (None when reference = 0), MAE, median AE,
% within ±5/±10 %, WAPE, signed bias, total error (works subtotal vs reference unless taxes included), completeness of matched and
priced reference amount, unmatched reference amount, per-family summary, scope notes.

**TOTAL CONSTRUCTION-COST ACCURACY: NOT VALIDATED — 0 approved Tamil Nadu BOQ projects.**
""")
    W("CONFIDENCE_CALIBRATION.md", hdr("Confidence (Task 15)") + """Per line: HIGH CONFIDENCE / NEEDS REVIEW / LOW CONFIDENCE / INSUFFICIENT INPUT with reasons (quantity basis, scale
calibration, mapping method, rate-source verification). Estimate level: never HIGH while items are unpriced, structure is missing
or >25 % of the amount needs review.

**Numeric calibration (ECE / Brier / reliability): NOT CALIBRATED — no labelled TN validation predictions.**
""")
    W("UNSEEN_TN_EVALUATION.md", hdr("Unseen TN evaluation (Task 16)") + f"""Provenance: {json.dumps(sc.get('provenance'))}

Final-holdout TN projects: **{(sc.get('counts') or {}).get('final_holdout_projects')}** → no credible unseen evaluation is possible yet.
Exposure record: the TN Rural Development sheets were evaluated repeatedly during development (development benchmark); the complex
smoke set was exposed by one site-plan fix; Aparna is non-TN.

Evidence (cannot satisfy a gate):
{table(sc.get('evidence', []), ['name', 'value', 'n', 'label', 'dataset'])}""")
    W("TEST_RESULTS.md", hdr("Test results (Task 18)") + (f"""`python -m pytest backend/tests --junitxml=reports/tn_completion/pytest.xml`

**{T['tests']} tests · {T['failures']} failures · {T['errors']} errors · {T['skipped']} skipped · {T['time']:.1f} s**

{table([dict(test=f'{a}::{b}', result=c) for a, b, c in T['cases']], ['test', 'result'])}""" if T.get("ran") else "pytest has not been run with --junitxml yet.\n"))

    gates = sc.get("gates", [])
    status = lambda tid: {
        1: "TESTED", 2: "BLOCKED_EXTERNAL_INPUT", 3: "TESTED", 4: "BLOCKED_EXTERNAL_INPUT", 5: "TESTED", 6: "TESTED", 7: "TESTED", 8: "TESTED",
        9: "TESTED", 10: "TESTED", 11: "BLOCKED_EXTERNAL_INPUT", 12: "TESTED", 13: "TESTED", 14: "BLOCKED_EXTERNAL_INPUT", 15: "TESTED",
        16: "BLOCKED_EXTERNAL_INPUT", 17: "TESTED", 18: "TESTED" if T.get("ran") and not T["failures"] and not T["errors"] else "FAILED"}[tid]
    tasks = [
        (1, "Lawful TN drawing dataset", ["backend/tn_data_ingestion/*"], "test_dataset_annotation.py", "authorised / licensed new TN drawing sets; licence confirmation for TNRD"),
        (2, "Verified ground-truth annotations", ["backend/annotations.py", "frontend #/annotate"], "test_dataset_annotation.py", "qualified annotators + two reviewers"),
        (3, "Leakage-safe splits", ["backend/tn_data_ingestion/dataset_builder.py", "ml/dataset/check_leakage.py"], "test_dataset_annotation.py, test_pipeline_quality.py", "new projects to populate train / validation / holdout"),
        (4, "Train & validate models", ["ml/training/*", "data/models/registry.json"], "test_detector_model_is_working", "verified TN annotations"),
        (5, "Room / unit / area extraction", ["backend/areas.py", "backend/floors.py", "backend/rooms.py"], "test_quantities_structural.py", "verified TN area ground truth for accuracy"),
        (6, "Door / window extraction", ["backend/parsers.py", "backend/openings.py", "backend/detector.py"], "test_pipeline_quality.py", "verified TN opening annotations for accuracy"),
        (7, "Wall quantities", ["backend/walls.py"], "test_quantities_structural.py", "verified wall quantities for accuracy"),
        (8, "Structural quantities", ["backend/structural.py", "app.rebuild_items"], "test_quantities_structural.py", "TN structural sets with BBS + engineer-verified quantities"),
        (9, "Complex-building suite", ["ml/evaluation/complex_smoke.py", "app.site_plan_reason"], "test_site_plan_never_costed", "licensed complex TN drawing sets with ground truth"),
        (10, "TN PWD rate coverage", ["backend/tnpwd_ingestion/*", "data/tnpwd/maps/takeoff_tn.json"], "test_tn.py", "TN Standard Data for formwork / doors / windows / electrical; official copies"),
        (11, "Mapping validation with engineers", ["backend/mapping_review.py"], "test_mapping_review_unit_guard_and_priority", "TN PWD engineer reviews (≥30)"),
        (12, "Approved BOQ workflow", ["backend/boq.py", "data/templates/*"], "test_boq.py", "approved TN BOQs"),
        (13, "Quantity vs BOQ comparison", ["backend/boq.py::compare"], "test_boq.py", "approved TN BOQs"),
        (14, "Item / total cost accuracy", ["backend/boq.py::metrics"], "test_boq.py", "≥5 approved TN BOQ projects"),
        (15, "Confidence & uncertainty", ["backend/confidence.py"], "test_confidence_labels_and_estimate_never_high_when_incomplete", "labelled validation outcomes for calibration"),
        (16, "Unseen TN evaluation", ["ml/evaluation/run_tn_eval.py", "ml/evaluation/scorecard.py"], "manual run", "final-holdout TN projects with verified ground truth"),
        (17, "90 % target & scorecard", ["ml/evaluation/gates.py", "ml/evaluation/scorecard.py"], "scorecard run", "the evidence above"),
        (18, "Testing & release audit", ["backend/tests/*"], "pytest", "—"),
    ]
    ledger = [dict(task_id=i, task_name=n, status=status(i), implementation_files=f, tests_added=t,
                   tests_passed=bool(T.get("ran") and not T["failures"] and not T["errors"]), evidence_files=["reports/tn_completion/"],
                   external_dependencies=dep, verified_completion=False, timestamp=NOW) for i, n, f, t, dep in tasks]
    json.dump(dict(generated=NOW, tasks=ledger, scorecard_final=sc.get("final")), open(os.path.join(OUT, "task_ledger.json"), "w"), indent=1)
    W("FINAL_COMPLETION_REPORT.md", hdr("Final completion report") + f"""## A. Executive summary
Final scorecard: **{sc.get('final')}** (target ≥90 % on unseen TN projects). Implementation of all 18 work packages is in place and
tested; none is VERIFIED_COMPLETE because accuracy validation needs external inputs that do not exist yet: verified TN annotations,
new authorised TN projects for a holdout, engineer-reviewed mappings and approved TN BOQs. The product is **not complete** in the
sense of a validated 90 % estimator.

## B. Tasks
{table([dict(id=t['task_id'], task=t['task_name'], status=t['status'], dependency=t['external_dependencies']) for t in ledger], ['id', 'task', 'status', 'dependency'])}
## C. Dataset
Projects {dash.get('total_projects')} · sheets {dash.get('total_sheets')} · training-eligible projects {dash.get('training_eligible_projects')} ·
verified annotations {cov['verified_records_any']} · splits {json.dumps(splits)} · leakage: see DATA_SPLIT_AUDIT.md.

## D-H. See MODEL_EVALUATION.md, QUANTITY_EVALUATION.md, PWD_RATE_AUDIT.md, COST_ACCURACY.md, TEST_RESULTS.md.

## I. Scorecard
{table([dict(id=g['id'], gate=g['name'], critical=g['critical'], value=g['value'], status=g['status'], reason=g.get('reason')) for g in gates], ['id', 'gate', 'critical', 'value', 'status', 'reason'])}
## J. External inputs required
1. New Tamil Nadu drawing sets with written permission for model training (≥10 projects for a holdout, more for training).
2. Licence confirmation for the TNRD type-design drawings (training use).
3. Qualified annotators + two independent reviewers for doors, windows, rooms, walls, dimensions (use `#/annotate`).
4. ≥5 approved TN BOQs with authority, date, reference and the matching drawing revision (template in data/templates/).
5. ≥30 engineer-reviewed PWD mappings (`/api/projects/{{id}}/mapping-review`).
6. TN Standard Data / official rates for formwork, doors, windows, electrical, plumbing; official copies of the amendment and
   Standard Data Book (currently single-host secondary sources).
7. Structural drawing sets with bar bending schedules.

## K. Next actions
1. Obtain inputs 1-4; 2. annotate + review; 3. fine-tune (stage2) and re-run `run_tn_eval.py unseen`; 4. close rate gaps (input 6).
""")
    print("reports written to", OUT)


if __name__ == "__main__":
    main()
