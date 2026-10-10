# 04 — Model, AI, NLP and OCR audit

**Evidence:**
- `manifests/model_registry_snapshot.json`: the registry plus every artefact's size and SHA-256;
- `data/models/*.json`;
- `ml/metrics/*`;
- `ml/training/*`;
- the inference code paths.

Each model is counted once, regardless of how many modules import it.

**Status of every model below: TN performance NOT MEASURED.** No model has been fine-tuned on Tamil Nadu data. The
blockers are 0 verified TN annotations and 0 rights-approved TN projects.

## Inventory

| # | Component | Category | Architecture | Artefact (SHA-256 in snapshot) | Inference entry point |
|---|---|---|---|---|---|
| 1 | Floor-plan segmentation | deep learning (vision) | U-Net, ResNet-34 encoder (ImageNet init), 5 classes (bg / wall / room / door / window) | `data/models/floorplan_unet.onnx` (97.7 MB); training weights `ml/weights/floorplan_unet_r34.pt` | `segmodel.segment` ← `parsers.analyze_image_array` (raster pages) |
| 2 | Door / window detector | deep learning (vision) | YOLOv8s, 1024 px, 2 classes | `data/models/opening_det.onnx` (45 MB); checkpoint `opening_det.pt`; base `yolov8s.pt` | `detector.detect` ← parsers (raster); wall-gate filter (radius w/2 + 0.2 m) |
| 3 | Primitive classifier | classical ML | RandomForest on vector-path features | inside `models_v5.joblib` | `parsers.parse_pdf` (vector PDFs) |
| 4 | Room-geometry classifier | classical ML | GradientBoosting on room geometry | inside `models_v5.joblib` | rooms without readable labels |
| 5 | Room-label model | NLP | TF-IDF (char 2–4 + word) + logistic regression | inside `models_v5.joblib` (`nlp.RoomLabelModel`) | OCR / PDF text → room type |
| 6 | SOR matcher | text retrieval | TF-IDF (word 1–2 + char 3–5, sublinear) cosine | built at runtime from the active TN SOR | `nlp.SORMatcher` → mapping *suggestions* (engineer-approved map wins) |
| 7 | TN PWD full-text search | retrieval | SQLite FTS5 (`tn_fts`, 4,834 rows) | `data/estimate.db` | `/api/tnpwd/search`, rate analysis |
| 8 | OCR | pretrained OCR | RapidOCR (PaddleOCR-derived ONNX det + rec) | pip package `rapidocr-onnxruntime` | `parsers.ocr`; corpus OCR fallback |
| — | Deterministic engines | rules | areas, walls, structural (Ø²/162), floors, openings reconcile, site-plan guard, confidence labels | code | not ML: never reported as "model accuracy" |

**Not active:**
- `models_v3.joblib` and `models_v4.joblib`: historical, not loaded (`ml.py MODEL_VERSION = 5`).
- `weights/yolo26n.pt`: unused base checkpoint.
- `runs/detect/val*`: Ultralytics validation outputs (scratch).

## Training data, separation and metrics

**U-Net (#1):**
- **Data:** CubiCasa5K (4,199 Finnish plans) plus synthetic sheet-clutter augmentation. Training and validation follow the
  official CubiCasa split.
- **Test results:**

| Measure | Value |
|---|---|
| mIoU (foreground) | 0.740 |
| IoU: wall / room / door / window | 0.729 / 0.898 / 0.616 / 0.715 |
| Object F1: room / door / window | 0.772 / 0.867 / 0.822 |

- **Training command:** `ml/training/train_seg.py`, then `export_onnx.py`.
- **Logs:** `ml/metrics/train.log` (copied to `scratch_archive/`).

**YOLOv8s (#2):**
- **Data:** CubiCasa5K converted to boxes (4,200 / 400 / 400 plans). Trained 40 epochs at seed 0 on an RTX 4060.
- **Results:**

| Split | mAP50 | Door F1 | Window F1 |
|---|---|---|---|
| Train | 0.926 | 0.883 | 0.918 |
| Validation | 0.902 | 0.865 | 0.898 |
| Test | 0.898 | 0.869 | 0.881 |

- **Resolution study (test mAP50):** 0.870 at 640 px, 0.898 at 1024 px, 0.891 at 1280 px.
- **Training command:** `ml/training/build_opening_dataset.py`, `train_detector.py`, `register_model.py`.

**#3–#5:**
- **Data:** a synthetic plan generator (`samples.py`), rendered through the same extraction path used at inference.
- **Evaluation:** no held-out real-drawing evaluation exists. `registry.json` honestly records `test_score: null` for the
  room classifiers.

**OCR (#8):** pretrained only. No TN OCR character or word accuracy has been measured.

## What the metrics demonstrate, and what they don't

- **What they show:** the vision models work on a *generic Finnish residential dataset*.
- **Doors and windows on real non-TN drawings (reference only, a different domain):**
  - Bihar / Nalanda door count within ±10% of tags: 20.8% (n = 24);
  - window count within ±10%: 0% (n = 24).

  These show a large domain gap on institutional drawings.
- **Tamil Nadu:** no TN door, window, wall or room ground truth exists, so TN performance is NOT MEASURED. Gates G01–G08
  in 12 cover this.

## Known failure cases

These come from earlier reports and were re-confirmed in code comments and tests:
- Casement windows are confused with doors on brochure plans.
- On a rendered marketing plan (Aparna, non-TN reference), 16 openings were found before the detector and 136 after it.
  This was spot-checked, not scored (`registry.json` note).
- Scale is often assumed from wall thickness, so quantities are flagged NEEDS REVIEW.

## Training decision for this run

**Not trained.** Training would only populate the registry, and it is not justified because:
- 0 rights-approved projects exist;
- 0 verified labels exist;
- the 6 new real projects should be kept unseen as future holdout candidates.

**Prerequisites:** see 12 and 16.

## Security note

The `.joblib` files are pickles, and loading them executes code. They are generated locally by `ml.py`. Never load a
`.joblib` received from outside.
