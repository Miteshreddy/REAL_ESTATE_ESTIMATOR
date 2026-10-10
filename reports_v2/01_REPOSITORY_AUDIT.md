# 01 — Repository audit

## Run details

- **Date:** 2026-10-09.
- **Branch / HEAD at start:** `tn-completion` @ `0c5964d`; the repository has 21 commits since the first (`bc44407`).
- **Repo root:** `C:\Users\Mitesh Reddy\Desktop\assignment\real estate`.
  - Git's top level is the user's home folder, so `git status` also lists unrelated personal files. These were ignored
    and not inventoried.
- **Commands:**
  - `git log`, `git status --porcelain`;
  - `python ml/evaluation/build_reports_v2.py`, which walks the tree and writes `manifests/repository_file_inventory.csv`.

## State before this run (preserved, nothing reverted)

| Path | State | Interpretation |
|---|---|---|
| `data/real_eval_results.json`, `data/tn_eval_results.json` | modified, uncommitted | re-written by evaluation scripts in the previous session |
| `data/tn_dataset/{train,validation,unseen_test}/manifest.json` | **deleted**, uncommitted | split v1 manifests superseded by split v2 (`tn_train/`, `tn_validation/`, `final_holdout/`, `development_benchmark/`, ...). Left as-is; the user should commit or restore them deliberately |
| `data/evaluation/tn/scorecard.json` | modified (this run) | rebuilt by `run_tn_eval.py scorecard` from stored results; values unchanged (FINAL: FAIL) |
| `PROJECT_OVERVIEW.md`, `.venv/` | untracked, user-owned | not touched |
| `data/models/*.onnx, *.joblib, *.pt` | untracked binaries | model artefacts (see 04); deliberately not in git |
| `data/estimate.db` (+ 2 `.bak`) | untracked | application DB: 0 projects, 1 active + 41 inactive rate schedules (see 10). Not archived |
| `data/dbg_*.png`, `data/t*.png`, `data/real_*.png`, `data/tn_*.png`, `data/dl_*.png`, `data/planbox.png` | untracked | debug renders from earlier sessions (scratch, see 17) |

## Inventory result (non-bulk files, excluding `.git`, `.venv`, caches)

There are **671 files**, each recorded with size, SHA-256, git state, category, lifecycle and role. Bulk derived folders
(page renders, thumbnails, OCR cache, pseudo-labels, previews, test drawings) are summarised as a single row each, with
file count and byte size.

| Category / lifecycle | Files |
|---|---|
| dataset / quarantine (corpus PDFs + sidecars) | 143 |
| dataset / active | 130 |
| evaluation / active | 63 |
| tool / active (bundled LibreDWG) | 63 |
| source / active | 57 |
| other / unknown | 50 |
| evaluation / historical | 50 |
| source / offline (training, eval, corpus scripts) | 24 |
| scratch / debug output | 23 |
| report / historical | 27 |
| test | 10 |
| model (active 7, historical 2, checkpoints 2, base weights 2) | 13 |

## Other checks

- **Secret scan:** a regex for api_key / secret / password / token assignments found **0** hits after excluding the
  scanner's own pattern.
- **Size:** the TN corpus folder holds **1.13 GB** (renders included); `data/models` holds 175 MB.
- **Unrelated files:** the git top level is `C:\Users\Mitesh Reddy`, so `git status` lists hundreds of personal
  files. A repository rooted at the project folder would avoid accidental commits of personal data. This is
  **recommended, not done**: changing it is the user's decision.
