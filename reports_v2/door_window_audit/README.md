# Door / window audit: corrected synthetic labels, valid matching, YOLOv8s vs YOLOv8m (2026-10-09)

**Ground rules for this run:**
- No training job was started, and the running YOLOv8m training was not stopped.
- The production model was not replaced.
- The CubiCasa **test** split was not used: model selection uses the validation split only.
- All 20 images are SYNTHETIC: `synthetic=true`, `real_tamil_nadu_source=false`, `approved_for_real_training=false`.
  **Nothing here is Tamil Nadu or real-drawing accuracy.**

## 1. Annotation convention

| | Object definition | Evidence |
|---|---|---|
| Production detector (CubiCasa training labels) | **Opening strip**: span along the wall × wall thickness, for both doors and windows | median short/long side 0.198 (door, n = 1,780) and 0.209 (window, n = 1,367) on 200 val label files; `convention/cubicasa_training_label_example.png` |
| Original synthetic pack: doors | swing square (leaf + arc), 74–150 px | `overlays/*.jpg` (left) |
| Original synthetic pack: windows | frame symbol: wall thickness + ~9.5 px each side (34 px box on a 15 px wall) | measured on DW-001 |

**Both classes were mislabelled relative to the detector.** Windows only looked better because their boxes overlap the
wall band more.

## 2. Corrected dataset (`data/synthetic_tn20_corrected/`; original pack unchanged)

**Script:** `ml/dataset/correct_synthetic_pack.py`. Every box is re-derived from the drawing's pixels:
1. A wall mask is built: dark pixels kept by a 7 × 7 morphological opening.
2. **Door, edge case:** the swing-square edge that lies on a wall line continuing beyond both ends gives the opening, as
   edge span × measured wall band.
3. **Door, wall-through-box case:** the longest wall-free run of the wall crossing the box gives the opening.
4. **Window:** span × the wall band measured beyond both ends.
5. **Verification:** the derived strip must be a real gap. If it is more than 30 % solid wall, the object is
   **AMBIGUOUS**, never guessed.

| | Doors | Windows |
|---|---|---|
| Original boxes | 237 | 178 |
| Corrected | **181** | **178** |
| Ambiguous → ignore regions | **56**: 38 symbols drawn over uninterrupted wall (no opening exists in the drawing), the rest with 0 or 2 candidate walls | 0 |
| Corrected strip thickness / span, median | 10 px / 73 px (ratio 0.14) | 15 px / 82.5 px (ratio 0.18) |

**Ignore regions:** stored in `ignore/<split>/<name>.txt`. In evaluation, a prediction falling on one is neither a TP
nor an FP, and the region never counts as an FN.

**Files:**
- `label_validation.json`: all 415 original boxes, 359 corrected boxes and 56 ignore boxes are finite, normalised,
  positive-size and use class 0 or 1; the class order matches production.
- `manifest_original.csv`, `manifest_corrected.csv` (with SHA-256 of images and labels).
- `correction_log.json`: one record per object with method or reason.
- `overlays/`: 20 before/after images (red = ignore).

**Remaining annotation problems:**
1. 56 door symbols have no opening drawn in the wall. This is a generator defect, so they can't be labelled under the
   detector's convention.
2. Wall-through-box doors put the swing on both sides of the wall, which is not a real-drawing convention.
3. All 20 images come from one generator with identical line styles, so they don't reflect real scanned drawings.

## 3. Matching and metrics (`ml/evaluation/eval_door_window.py`)

**Matching rule:**
- Per image and per class, predictions are sorted by confidence.
- Each prediction matches the unmatched same-class ground-truth box with the highest IoU, if that IoU ≥ 0.5.
- Matching is **one-to-one**: each ground truth and each prediction is used at most once.

**Operating point:** confidence ≥ 0.35 (the app's threshold) gives TP / FP / FN, precision, recall and F1.

**AP:** computed from all predictions (confidence ≥ 0.001) with 101-point interpolation. AP50 is at IoU 0.5; AP50-95 is
the mean over IoU 0.50:0.05:0.95; mAP is the mean of the door and window values.

**Diagnostic only (not F1):** centre-hit rate, the share of ground-truth boxes containing the centre of some same-class
prediction.

**Same setup for both models:**
- CubiCasa images are used as-is at imgsz 1024.
- Synthetic images are resampled to the app's 38 px/m (one fixed pack scale from the median corrected door span ÷ 0.9 m)
  and tiled at 1024 px with 160 px overlap, then per-class NMS at 0.45, exactly as `backend/detector.py` does.

## 4. Results

| Model | Checkpoint | Note |
|---|---|---|
| YOLOv8s | `data/models/opening_det.v1.pt` | production; the ONNX in use is exported from it |
| YOLOv8m | `checkpoints/yolov8m_interim_best.pt` | snapshot of the **in-progress** run's best epoch (epoch ≤ 14 of 70), so interim |

### Model-selection set: CubiCasa validation split (400 plans; real but non-TN drawings)

| Model | Class | TP | FP | FN | Precision | Recall | F1 | AP50 | AP50-95 |
|---|---|---|---|---|---|---|---|---|---|
| YOLOv8s | door | 3,310 | 560 | 514 | 0.855 | 0.866 | **0.860** | 0.873 | 0.510 |
| YOLOv8s | window | 2,797 | 313 | 335 | 0.899 | 0.893 | **0.896** | 0.912 | 0.606 |
| YOLOv8m (interim) | door | 3,168 | 581 | 656 | 0.845 | 0.829 | 0.837 | 0.845 | 0.483 |
| YOLOv8m (interim) | window | 2,743 | 433 | 389 | 0.864 | 0.876 | 0.870 | 0.894 | 0.583 |

**Overall:** YOLOv8s mAP50 **0.892**, mAP50-95 **0.558**; YOLOv8m (interim) mAP50 0.870, mAP50-95 0.533.

### Supplementary: corrected synthetic pack (20 images, ignore regions applied)

| Model | Class | TP | FP | FN | Precision | Recall | F1 | AP50 | AP50-95 |
|---|---|---|---|---|---|---|---|---|---|
| YOLOv8s | door | 178 | 21 | 3 | 0.895 | 0.983 | 0.937 | 0.989 | 0.531 |
| YOLOv8s | window | 145 | 19 | 33 | 0.884 | 0.815 | 0.848 | 0.899 | 0.572 |
| YOLOv8m (interim) | door | 166 | 6 | 15 | 0.965 | 0.917 | 0.941 | 0.986 | 0.587 |
| YOLOv8m (interim) | window | 176 | 1 | 2 | 0.994 | 0.989 | 0.992 | 1.000 | 0.728 |

**Overall:** YOLOv8s mAP50 0.944 / mAP50-95 0.551; YOLOv8m (interim) mAP50 0.993 / mAP50-95 0.658.

**Prediction images:** `eval/predictions_<model>/`. Grey = label, red = ignore, green = door, blue = window.

## 5. Interpretation and decision

- **Selection:** on the validation split, **YOLOv8s (production) is better at this point**. YOLOv8m is 14 epochs into a
  70-epoch run, and its checkpoint will be re-evaluated with this same script when training ends. Production stays as
  is.
- **The two datasets disagree:** YOLOv8m does better on the clean synthetic schematics but worse on real CubiCasa plans.
  Synthetic results are not a valid basis for model selection.
- **The earlier "door F1 0.90 / window F1 0.92" was a centre-containment hit rate on mislabelled data, not F1.** It is
  withdrawn. On the corrected labels, YOLOv8s has real F1 **0.937 (door) / 0.848 (window)** on the synthetic pack and
  **0.860 / 0.896** on CubiCasa validation.
- **No 90 % claim is supported on real drawings.** CubiCasa validation F1 is 0.86 for doors and 0.90 for windows. No
  Tamil Nadu ground truth exists.

## 6. Use of the corrected synthetic data for training

**Not merged.** The corrected labels now follow the training convention, but:
- the images are clean vector-style schematics from one generator, unlike the scanned or photographed real plans in
  the training set;
- 56 of 237 doors (24 %) have no drawn opening;
- 20 images are too few to matter against 4,200 training plans, and can only bias the model toward this generator's
  style.

**Recommended use:** keep it as a fixed regression set. A supplementary fine-tuning experiment would only make sense
with a held-out real validation set and a pre-declared criterion, and must be authorised separately.

## 7. Final YOLOv8m result (run shortened to 25 total epochs on the user's instruction; resumed from the epoch-18 checkpoint)

**How the run ended:**
- Stopped at the epoch-18 boundary.
- Resumed with an edited copy of `last.pt` (target 25). Optimizer, EMA and epoch state were preserved.
- Ultralytics' own validation at epoch 25: mAP50 0.897, mAP50-95 0.562.

**Evaluation:** same script, same settings, CubiCasa validation split (400 plans). The test split remains unused.

| Model | Door TP / FP / FN | Door F1 | Window TP / FP / FN | Window F1 | mAP50 | mAP50-95 |
|---|---|---|---|---|---|---|
| YOLOv8s (production) | 3,310 / 560 / 514 | 0.860 | 2,797 / 313 / 335 | 0.896 | 0.892 | 0.558 |
| YOLOv8m e25 (`checkpoints/yolov8m_final_e25_best.pt`) | 3,303 / 549 / 521 | 0.861 | 2,764 / 321 / 368 | 0.889 | 0.891 | 0.559 |

**Supplementary, corrected synthetic pack:** YOLOv8m door F1 0.942 / window F1 0.918 (mAP50 0.980) vs YOLOv8s 0.937 / 0.848 (mAP50 0.944).

**Decision:** keep **YOLOv8s** in production.
- On the selection set the difference is within ±0.007 on every metric, which is not a meaningful improvement.
- YOLOv8m is about 2.4× larger and slower at inference.
- **Restore points:**
  - `checkpoints/yolov8m_final_e25_best.pt` and `_last.pt`;
  - `G:/velo/real-estate/runs/det/opening_v2_m__restore_epoch18/`;
  - `data/models/opening_det.v1.*` (YOLOv8s backup).
