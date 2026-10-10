# 14 — Test and runtime audit

## Test suite

**Command:** `python -m pytest backend/tests -q -rA --junitxml=reports_v2/evidence/pytest_junit.xml`

**Environment:** Python 3.12.10 (system interpreter), Windows 11.

**Result:** **95 passed, 0 failed, 0 errors, 0 skipped** in 26.1 s (exit 0).
- Full log: `logs/test_execution_log.txt`.
- Per-test results: `manifests/test_run_manifest.json`.

| Test file | Tests | Covers |
|---|---|---|
| test_tn.py | 29 | TN scope, ingestion, rate analysis, pricing guards, floors, Aparna regression (non-TN reference) |
| test_pipeline_quality.py | 18 | parsing, upload validation, quality flags, regex control-character guard |
| test_quantities_structural.py | 16 | areas, walls, structural / BBS, site plans, mapping review, confidence, review-fix regressions |
| test_audit.py | 8 | basis labels, no silent zero, provenance |
| test_tn_corpus.py | 9 | crawler SSRF / allowlist / robots wildcards / kill switch, catalogue parser, page classifier, PII screen |
| test_dataset_annotation.py | 7 | dataset split policy, annotation two-reviewer workflow |
| test_boq.py | 5 | BOQ validation / compare / metrics |
| test_learning.py | 2 | learning votes |
| test_legacy_migration.py | 1 | DB migration |

**What the tests prove:** the software behaves as specified on synthetic and fixture inputs. **They do not prove
construction-cost accuracy.**

## Other executed commands

| Command | Exit | Result |
|---|---|---|
| `python ml/dataset/check_leakage.py` | 0 | no leakage in data/tn_dataset |
| `python ml/evaluation/run_tn_eval.py scorecard` | 0 | FINAL: FAIL (see 12) |
| `python tn_corpus/scripts/fetch_catalog_v2.py` | 0 | 12 acquired, 5 blocked, 1 duplicate, 2 non-TN rejected |
| `python tn_corpus/scripts/build_corpus.py` | 0 | see 18 (the final build after fixes) |
| `python ml/evaluation/build_reports_v2.py` | 0 | manifests regenerated |
| start.bat venv: `uvicorn app:app` on a fresh temp data dir; GET /api/health, /api/rate-schedules/applicable, /api/tnpwd/status, / | — | all 200; health `{"ok":true,"active_rate_schedules":1}`; the fresh DB bootstraps only the TN schedule (`logs/runtime_smoke_venv.txt`) |
| start.bat venv: `from tnpwd_ingestion import refresh_service` | 1 → 0 | **failed** with `ModuleNotFoundError: requests`; **fixed** by adding `requests>=2.31` to requirements.txt and re-checked |

## Gaps

- **Environment mismatch:** tests run with the system interpreter. The start.bat venv lacks pytest and httpx (dev
  dependencies), so the suite has not been run inside the production venv. Suggested: add `requirements-dev.txt` usage
  to the docs (the file exists).
- **No browser / E2E tests.**
- **No performance benchmarks:** large-PDF parse time was not measured in this run.
