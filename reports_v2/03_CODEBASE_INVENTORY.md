# 03 — Codebase inventory

**Full file list:** `manifests/repository_file_inventory.csv`, with path, bytes, SHA-256, git state, category, lifecycle,
role and secret-scan result. The classification rules are in `ml/evaluation/build_reports_v2.py:classify_path`.

## Major modules and their actual role

| File | Lines | Actual role | Reached from live workflow? | Status |
|---|---|---|---|---|
| backend/app.py | 1466 | FastAPI app, routes, pipeline orchestration, site-plan guard, upload validation (200 MB cap) | entry point | IMPLEMENTED, TESTED |
| backend/parsers.py | 1160 | PDF / raster / DXF / DWG parsing, OCR, mask analysis, scale calibration | yes | IMPLEMENTED, TESTED (synthetic + exposed TN dev set) |
| backend/takeoff.py | 657 | quantity take-off lines, rate mapping, pricing | yes | IMPLEMENTED, TESTED |
| backend/rates.py | 459 | rate schedules, SOR store, import / export | yes | IMPLEMENTED, TESTED |
| backend/reports.py | 413 | HTML / PDF / XLSX estimate report with disclosures | yes | IMPLEMENTED, TESTED |
| backend/bigplan.py | 413 | large vector sheets: view splitting, room labels | yes (vector PDFs) | IMPLEMENTED, TESTED |
| backend/sheetreader.py | 335 | sheet-view titles / classification | yes | IMPLEMENTED; 88.9 % on exposed dev set |
| backend/docparse.py | 278 | schedules (door / window, structural), notes | yes | IMPLEMENTED, TESTED |
| backend/tnpwd_ingestion/* | ~1,100 | TN PWD discover / download / SHA / parse SOR and Standard Data / validate / version / activate / FTS retrieval / rate analysis | admin routes + pricing | IMPLEMENTED, TESTED |
| backend/boq.py | 233 | reference BOQ upload, validation, compare, metrics | yes (route) | IMPLEMENTED, TESTED; 0 real BOQs |
| backend/annotations.py | 236 | annotation states, two-reviewer review, COCO export | yes (`#/annotate`) | IMPLEMENTED, TESTED; 0 verified labels |
| backend/nlp.py | 222 | length parsing, room-label TF-IDF LR, SORMatcher TF-IDF | yes | IMPLEMENTED |
| backend/tn_data_ingestion/* | ~600 | data/tn_dataset builder: licence, dedup, split v2, annotation queue | offline / admin | IMPLEMENTED, TESTED |
| backend/structural.py | 132 | schedule-derived concrete, BBS steel Ø²/162 | yes | IMPLEMENTED, TESTED (synthetic) |
| backend/walls.py, areas.py, floors.py, openings.py, confidence.py, quality.py, mapping_review.py, tn_pricing.py, tn_scope.py | 60–180 each | as named | yes | IMPLEMENTED, TESTED |
| backend/ml.py, segmodel.py, detector.py | 160 / ~90 / ~120 | model loading and inference | yes | IMPLEMENTED (see 04) |
| backend/learning.py | 154 | votes from confirmed estimates → learned mappings | wired; 0 rows | IMPLEMENTED, NOT USED YET |
| backend/{accuracy_eval, aparna_regression, benchmark, commercial_eval, real_eval, south_compare, tn_eval, opening_ab, analysis}.py | — | evaluation / dev harnesses | no (offline) | evaluation scripts; `south_compare.py` and the Aparna regression involve **non-TN** material (reference only) |
| ml/training/* (12 files) | — | U-Net and YOLO training, ONNX export, model registration, SOR / DSR importers | offline | historical runs recorded in `ml/metrics`, `data/models/*.metrics.json` |
| ml/evaluation/* | — | TN eval, gates, scorecard, smoke, completion reports, **build_reports_v2 (new)** | offline | IMPLEMENTED |
| ml/dataset/check_leakage.py | — | leakage check of data/tn_dataset | offline | exit 0 this run |
| tn_corpus/scripts/* | ~1,000 | governed acquisition (`safe_fetch`, `tnrd_discover`, `fetch_leads`, **`fetch_catalog_v2` (new)**) + `build_corpus` | offline | IMPLEMENTED, TESTED (8 tests) |
| frontend/app.js | 795 | SPA | yes | IMPLEMENTED; no UI tests |
| tools/libredwg | 63 files | DWG→DXF converter (third-party binary) | yes, for .dwg | bundled; licence GPL-3 (LibreDWG): check before redistribution |

## Changes to code in this run

| File | Change | Reason |
|---|---|---|
| `tn_corpus/scripts/fetch_catalog_v2.py` | new | v2 catalogue acquisition through the existing tested `safe_fetch` guards, not a second downloader; TN-only filter |
| `tn_corpus/scripts/build_corpus.py` | modified | prose / text-page rule; sparse-page dedup guard; ≥3-page merge rule; per-building sub-projects; verified project metadata; personal-data restriction; ZIP derivative linking; faster dedup |
| `ml/evaluation/build_reports_v2.py` | new | regenerates every manifest and count in this report set |
| `requirements.txt` | + `requests>=2.31` | the app's TN PWD ingestion imports `requests`; the start.bat venv lacked it, so refresh failed (reproduced, fixed) |
| `.gitignore` | + `tn_corpus/rejected/**/*.pdf` | keep rejected binaries out of git |
