# 17 — Project scratch artefacts and experiments

**Full list:** `scratch_archive/scratch_inventory.csv`: 172 rows with path, bytes, SHA-256, git state and lifecycle.

**What was copied:** lightweight historical documents and logs, copied into `scratch_archive/`. The originals are
untouched; `evidence/facts.json` → `scratch_copied` lists them with their hashes.

**What was deliberately not copied:** large binaries, the application DB, uploads and previews.

## Groups

| Group | Items | Purpose | Lifecycle | Safe to use? |
|---|---|---|---|---|
| Debug renders `data/dbg_*.png`, `data/dl_ang_*.png`, `data/t*.png`, `data/planbox.png`, `data/real_*.png`, `data/tn_*.png` | 21 | earlier sessions' visual debugging of the Anganwadi / office / toilet TNRD sheets and resolution tests (1024 / 1600 / 2200) | debug output, untracked | reference only; not data |
| Earlier evaluation outputs `data/*.json`, `data/accuracy_eval.log`, `data/evaluation/**` | ~110 | accuracy, benchmark, commercial, south-compare, TN eval runs | active (scorecard inputs) or historical | `data/evaluation/tn/*` is a scorecard input. `south_compare.json`, `real_eval_uk.json` and the Aparna result files are **non-TN** experiments: historical, not TN evidence |
| Old split v1 manifests `data/tn_dataset/{train,validation,unseen_test}/manifest.json` | 3 | first split, superseded by v2 | deleted in the working tree, uncommitted | obsolete |
| Historical model bundles `models_v3.joblib`, `models_v4.joblib` | 2 | earlier classifier versions | not loaded | obsolete; do not load (pickle) |
| Training checkpoints `ml/weights/floorplan_unet_r34.pt`, `data/models/opening_det.pt` | 2 | source weights for the ONNX exports | needed to retrain / fine-tune | keep |
| Base weights `yolov8s.pt`, `weights/yolo26n.pt` | 2 | Ultralytics pretrained bases | yolov8s used for detector training; yolo26n unused | keep yolov8s; yolo26n is an experiment leftover |
| Ultralytics `runs/detect/val*` | empty dirs | validation runs (outputs already moved into `data/models/*.json`) | scratch | safe to delete (user's decision) |
| Root reports `ACCURACY_REPORT.md`, `TN_ESTIMATOR_FINAL_REPORT.md`, `PROJECT_OVERVIEW.md` (user's, untracked) | 3 | earlier summaries | **historical**. `ACCURACY_REPORT.md` predates the TN-only scope and mixes non-TN results | superseded by this report set |
| `reports/tn_completion/*` | 21 | previous completion run (14 reports, ledger, pytest, scorecard) | historical (same day) | numbers re-derived here. Changes: 86 → 95 tests (+8 corpus tests, +1 PII test); dataset counts moved to `tn_corpus` |
| Downloads-folder reports (`TN_FINAL_COMPLETION_REPORT.md`, `TN_ESTIMATOR_FINAL_REPORT.md`, `TN_PWD_OVERHAUL_REPORT.md`, `CONSTRUCTION_ESTIMATE_AUDIT_REPORT.md`, `PROJECT_REPORT_*.md`, `Downloads/report/*`) | outside the repo | earlier deliverables | historical | `Downloads/report/` holds corpus run-1 outputs (58 files / 35 projects): superseded by `manifests/` here |
| Supplied ZIP v2 (`tn_corpus/sources/zip_v2/`) | 104 files | starter pack: seed PDFs (handbook derivatives), source catalogue, scripts, earlier audit copies | preserved unchanged | its `download_public_direct_candidates.py` was **inspected, not run**. Its `__pycache__` contains a `.pyc` for Python 3.13 (not executed). The repo's tested `safe_fetch` was reused instead |

## Discrepancies between historical reports

| Topic | Older claim | Current truth (source) |
|---|---|---|
| TNRD catalogue size | "70 entries" (starter-pack guide) | 54 PDF links on the live page (`tn_corpus/catalog/tnrd_type_design_catalog.csv`) |
| Corpus size | 58 files / 1,183 pages / 35 projects (run 1) | 69 / 2,404 / 50 (05 explains each change) |
| CMDA lead | "multi-storey apartment / high-rise" (v2 catalogue) | commercial office, stilt + 3 floors |
| Tests | 86 (tn_completion) | 95 (this run) |
| TN evidence | early reports counted the Aparna Hyderabad drawing as TN | non-TN reference; excluded from TN evidence here |

## Failed experiments with lessons

1. **dHash on sparse pages** produced false duplicates. Lesson: do not use perceptual hashing on near-empty pages.
2. **A word-count threshold** could not separate prose from drawing notes. Lesson: the ratio of numbers to function
   words, plus vector density, works much better.
3. **The 12-digit ID regex** collided with dimension strings.
4. **A U-Net-only opening count** found too few openings on brochure plans. The detector was added (earlier session).
