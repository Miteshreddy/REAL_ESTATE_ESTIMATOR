# Tamil Nadu PWD Estimator — Final Report

**Evaluation date:** 2026-10-09  
**Commit:** see `git log`  
**Scorecard source:** `data/evaluation/tn/scorecard.json`, produced by `ml/evaluation/run_tn_eval.py unseen`

Every number in this report was produced by a script in this repository on this date. Results are labelled as follows:

| Label | Meaning |
|---|---|
| **REFERENCE ONLY** | measured on non-TN data |
| **SYNTHETIC** | measured on generated drawings |
| **NOT MEASURED** | no Tamil Nadu ground truth exists for this metric |
| **NOT VALIDATED** | no approved BOQ exists |

---

## 1. Architecture

```
DRAWING ─┬─ vector/CAD parser (DXF / vector PDF, bigplan for large hatched PDFs)
         ├─ OCR (RapidOCR; feet-inch & metric dimensions, floor labels, unit tags)
         └─ raster CV: U-Net segmentation + YOLO door/window detector + wall-interruption geometry
                     │
              GEOMETRY FUSION (openings fused at 0.7 m; scale calibrated from written room dimensions;
                               downscale-safe px/m)
                     │
   DRAWING UNDERSTANDING: sheet class, floors (occurrences), rooms (normalised, typed, open zones),
                          apartment units, opening types / rooms either side / unit / floor
                     │
   QUANTITY ENGINE (deterministic formulas; every line: formula, basis, source, assumption ids)
                     │
   TN PWD PRICING: SOR 2025-26 + amendment (3,502 items, page + SHA-256) → Standard Data analysis
                   via the reviewed item map → suggestions / NEEDS RATE (never ₹0)
                     │
   QUALITY: sanity checks, cross-checks (schedule vs geometry vs detector), assumptions, completeness,
            review colours
                     │
   HUMAN REVIEW + LEARNING (confirmed choices reused) → REPORTS (HTML / PDF / Excel)
```

**Data side:**
- `backend/tn_data_ingestion` builds the drawing dataset: robots.txt / licence check → SHA-256 + perceptual-hash dedup → project grouping → project-level split → leakage check → annotation queue (pseudo labels kept separate).
- `backend/tnpwd_ingestion` builds the pricing knowledge base.

## 2–3. Files changed and added (this phase)

**Added:**
- `backend/tn_data_ingestion/`: `source_registry`, `license_check`, `downloader`, `crawler`, `parsers` (pdf / ocr / table / drawing / metadata / classifier), `dedup`, `dataset_builder`, `annotation_queue`, `refresh`.
- Backend modules: `backend/detector.py`, `openings.py`, `quality.py`, `learning.py`.
- ML: `ml/dataset/check_leakage.py`, `ml/evaluation/run_tn_eval.py`, `ml/training/build_opening_dataset.py`, `train_detector.py`, `register_model.py`.
- Configs: `configs/tn_opening_detector.yaml` (also copied as `tn_door.yaml` and `tn_window.yaml`).
- Data folders: `data/tn_dataset/…`, `data/ground_truth/tn/registry.json`, `data/evaluation/tn/<class>/`.
- Tests: `tests/test_pipeline_quality.py`, `tests/test_learning.py`.

**Changed:**
- `app.py`: quality outputs, upload validation, learning, the detector, auto-refresh.
- `parsers.py`: detector fusion.
- `rooms.py`: area hierarchy, open zones.
- `nlp.py`: scale parsing, including 1/100 and NTS.
- `reports.py`: completeness, checks and assumptions sections and sheets.
- `tnpwd_ingestion/downloader.py`: robots.txt wildcard support.
- `tnpwd_ingestion/rate_analysis.py`: main-data divisor; labour-only guard.
- `frontend/app.js`: quality banner, review dots.

## 4. Non-TN features removed or deactivated

- CPWD, Telangana, Andhra Pradesh, Karnataka, Kerala, Maharashtra, Odisha, Puducherry and West Bengal schedules are **inactive**. They are kept only so legacy projects stay auditable.
- The resolver and UI offer Tamil Nadu only, and other states are rejected with HTTP 400.

## 5. TN sources

| Source | Use | Status |
|---|---|---|
| tnpwdea.org: SOR 2025-26 Vol I, tiles amendment (08.08.2025), Standard Data Book | pricing | ingested. The SOR is cross-verified by an identical SHA-256 on tnebes.org. |
| TNRD type-design drawings | drawing dataset | 50 PDFs, 110 sheets; licence status: government publication, review pending |
| TN RERA | drawings | **robots.txt disallows `/uploads/` and `*.pdf`, so not crawled.** 65 links blocked. |
| tntenders.gov.in | BOQs | per-document CAPTCHA, so not crawled. BOQs must be uploaded by a person. |

## 6–9. Dataset, annotations, split, leakage

| | Value |
|---|---|
| TN projects | 42 (110 sheets) |
| Sheet types | 53 vector, 57 scanned / raster, 19 structural |
| Duplicate pairs | 0 (SHA-256 + 256-bit dHash + text similarity) |
| **Split** | **train 0 · validation 0 · unseen_test 42** |
| Verified TN annotations | **0** |
| Pseudo labels | 110 pages: 491 doors, 844 windows, 476 rooms — **NOT ground truth** |
| Leakage check (`ml/dataset/check_leakage.py`) | **PASS** (exits 1 on a planted leak; covered by a test) |

- **Why the split is all unseen-test:** every TN drawing we hold is used by an evaluation script (`tn_eval`, Aparna). Training on any of them would be training on the test set.
- **Consequence:** no TN-trained model exists, and none can honestly exist until new TN drawings are collected and verified annotations are made for them.

## 10–13. Models

| Model | Training data | Train | Validation | Test | Unseen TN |
|---|---|---|---|---|---|
| U-Net (segmentation) | CubiCasa5K | mIoU 0.731 | 0.741 | 0.740 | NOT MEASURED |
| **opening_det v1.0** (YOLOv8s, 1024 px, 40 epochs, seed 0) | CubiCasa5K, official split (generic pretraining, NOT TN) | door F1 0.883 · window F1 0.918 | door 0.865 · window 0.898 | door 0.869 · window 0.881 · mAP50 0.898 | **NOT MEASURED** |

Detector checks:
- **Generalisation:** test is close to validation, so the model does not overfit.
- **App integration:** the app's ONNX decoding was checked against test labels (12 plans: P 0.969, R 0.952). It runs in every pytest run (`test_detector_model_is_working`).
- **Fusion A/B:** on synthetic PNGs there was no change (the U-Net already finds everything).
- **Aparna:** openings went from **16 to 136** (83 doors, 53 windows).
- **Visual spot check, one flat:** all 8 doors found. Errors: casement windows sometimes typed as doors, and one wardrobe detected as a window. This is a **spot check, not a scored metric**.

The registry refuses to replace a model with a worse one (`register_model.py`, covered by a test).

## 14–24. Results by area

| Area | Result | Type |
|---|---|---|
| **Doors** | TN: NOT MEASURED (no annotations). Non-TN commercial reference: 20.8% of sheets within ±10%. | — |
| **Windows** | TN: NOT MEASURED. Non-TN commercial reference: 0%. | — |
| **Rooms / area, basic** | TN plinth area: 68.8% within ±10% (median 2.54%). Non-TN reference: Uttarakhand rooms 78.5% within ±10%. | REAL |
| **Rooms / area, large** | Aparna unit carpet area: **20% within ±10%**; errors −3%, −11%, −27%, −29%, −30%. | REAL, printed reference |
| **Floors** | Aparna floors 18/28/38: correct. | n = 1 |
| **Units** | 5 / 5 apartments found. | n = 1 |
| **Walls** | NOT MEASURED against TN ground truth. | — |
| **Structural** | NOT MEASURED. No TN structural ground truth; without drawings the system shows STRUCTURAL INPUT MISSING. | — |
| **Commercial (TN)** | NOT MEASURED. No TN commercial set. | — |
| **PWD mapping** | Accuracy NOT VALIDATED (needs engineer review). | — |
| **Rate completeness** | 58.8% of take-off lines priced from TN data (villa sample). Formwork, doors and windows, electrical and plumbing remain NEEDS RATE / NEEDS RATE ANALYSIS. A labour-only formwork rate was **rejected** by a new guard. | coverage, not accuracy |
| **BOQ / cost** | **NOT VALIDATED.** 0 approved TN BOQs. The upload-and-score endpoint is ready. | — |

## 25. Remaining failures

1. **No TN training data or annotations.** Detector and segmentation are not TN-adapted.
2. **Unit and room areas on rendered plans** are under-read by up to 30%.
3. **Door/window type confusion** (casement windows vs doors) and furniture false positives.
4. **Pricing gaps:** formwork, doors/windows and services lack complete TN rate analyses.
5. **No approved BOQ**, so cost accuracy and confidence calibration cannot be measured.

### Code audit

A code review of `dc07cdc..HEAD` found 10 issues; 9 were fixed:
- licence rule allowed unconfirmed files for training;
- weekly refresh re-downloaded everything on fresh installs;
- the refresh thread could cause "database is locked";
- learning counts were inflated by re-confirming a project;
- learned codes were applied without a unit check;
- metrics were stale after the room-area change;
- the detector ran twice on recalibrated images;
- assumption cost impact was double-counted;
- reference-BOQ unit aliases were too narrow.

One was skipped: O(n²) dedup, acceptable at the current dataset size.

Earlier in this phase I also found and fixed:
- the robots.txt `*`/`$` wildcards being ignored;
- schedule reconciliation miscounting windows as doors;
- an over-aggressive perceptual hash.

**Tests:** `pytest` reports **57 passed**.

## 26. Commands

Start the app:
```bash
python -m uvicorn app:app --app-dir backend --port 8000
```

Build, validate and check the dataset, run from `backend`:
```bash
python -m tn_data_ingestion.refresh build
```
```bash
python -m tn_data_ingestion.refresh dashboard
```
```bash
python ../ml/dataset/check_leakage.py
```

Pseudo-label and export verified annotations, run from `backend`:
```bash
python -m tn_data_ingestion.refresh pseudo 200
```
```bash
python -m tn_data_ingestion.refresh export
```

Train the door / window model (generic stage), run from the repo root:
```bash
G:/velo/real-estate/trainenv/Scripts/python.exe ml/training/train_detector.py configs/tn_opening_detector.yaml stage1
```

TN fine-tune, once verified TN labels exist:
```bash
G:/velo/real-estate/trainenv/Scripts/python.exe ml/training/train_detector.py configs/tn_opening_detector.yaml stage2
```

Room / wall segmentation:
```bash
G:/velo/real-estate/trainenv/Scripts/python.exe ml/training/train_seg.py
```

Structural model: **not trainable**. No structural annotations exist; structural sheets are read by rules (`docparse.parse_structural`).

Refresh TN PWD data, run from `backend`:
```bash
python -m tnpwd_ingestion.refresh_service refresh
```

Evaluations, run from the repo root:
```bash
python ml/evaluation/run_tn_eval.py basic
```
```bash
python ml/evaluation/run_tn_eval.py large
```
```bash
python ml/evaluation/run_tn_eval.py commercial
```
```bash
python ml/evaluation/run_tn_eval.py unseen
```

Run the tests:
```bash
python -m pytest backend/tests
```

## 27. Final target status

```
================================================
TAMIL NADU ESTIMATOR SCORECARD   (target ≥90% on unseen TN)
================================================
TRAIN (TN):        NOT AVAILABLE (0 TN training projects)
VALIDATION (TN):   NOT AVAILABLE
UNSEEN (TN):       measured metrics below
ROOM / AREA:       basic plinth 68.8% · large unit area 20.0%
WALL:              NOT MEASURED
DOOR:              NOT MEASURED (TN)   [detector CubiCasa test F1 86.9% — reference]
WINDOW:            NOT MEASURED (TN)   [detector CubiCasa test F1 88.1% — reference]
FLOOR:             100% (n=1)
UNIT:              100% (n=1)
SHEET VIEW:        88.9%
STRUCTURAL:        NOT MEASURED
CONCRETE … PAINT:  NOT MEASURED (no TN BOQ quantities)
PWD MAPPING:       NOT VALIDATED   (rate completeness 58.8%)
BOQ:               NOT VALIDATED
TOTAL COST:        NOT VALIDATED
TARGET:            ≥90%
FINAL:             FAIL
================================================
```

To change this verdict, the next inputs are:
- new TN drawing sets with permission;
- verified door / window / room annotations on them;
- approved TN BOQs uploaded through `/api/projects/{id}/reference-boq`.

The pipeline then trains (stage 2), evaluates and registers the model with no rebuild.
