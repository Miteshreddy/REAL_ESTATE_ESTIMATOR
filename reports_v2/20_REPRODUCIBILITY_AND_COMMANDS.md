# 20 — Reproducibility and commands

Run all commands from the repository root (`Desktop\assignment\real estate`).

**Environment:** Python 3.12.10 on Windows 11. The app dependencies are in `requirements.txt`; dev / test dependencies
(pytest, httpx) are in `requirements-dev.txt`. Training needs torch and ultralytics (offline GPU), which are not
installed by `start.bat`.

## Start the app

```
start.bat
```
or
```
python -m uvicorn app:app --app-dir backend --port 8000
```

## Tests

```
python -m pytest backend/tests -q -rA --junitxml=reports_v2/evidence/pytest_junit.xml
```
Result: 95 passed.

## Dataset acquisition and build (network needed for steps 1–3)

1. `python tn_corpus/scripts/tnrd_discover.py --catalog-only`
2. `python tn_corpus/scripts/tnrd_discover.py --download-candidates` — idempotent; existing sidecars are skipped
3. `python tn_corpus/scripts/fetch_leads.py`
4. `python tn_corpus/scripts/fetch_catalog_v2.py` — TN-only; needs the extracted ZIP at `tn_corpus/sources/zip_v2/`
5. `python tn_corpus/scripts/build_corpus.py --report-dir tn_corpus/registry/_export`
6. **Stop any crawl:** create the file `tn_corpus/STOP_CRAWL`

## Evaluation and reports

1. `python ml/dataset/check_leakage.py`
2. `python ml/evaluation/run_tn_eval.py scorecard` — use `unseen` for the full re-run
3. `python ml/evaluation/build_reports_v2.py` — regenerates `reports_v2/manifests`, `logs`, `evidence/facts.json` and
   `scratch_archive` copies

The Markdown narrative in `reports_v2/*.md` was written from those outputs. If the counts change, re-read
`evidence/facts.json` and update the narrative.

## What is not reproducible

- **Remote sources:** they may change, disappear or start blocking. The SHA-256 values in the sidecars identify exactly
  what was used.
- **Visual spot-checks:** classifier precision and project identity from title blocks are recorded as evidence files,
  not computed by code.
- **Absolute timestamps** in logs.
