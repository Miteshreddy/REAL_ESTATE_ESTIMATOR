# Door / window synthetic pack: audit and smoke test (2026-10-09)

| | |
|---|---|
| Pack | `TN_Door_Window_20_Synthetic_Samples.zip`, extracted to `data/synthetic_tn20/` |
| Contents | 20 generated schematic plans: 237 doors, 178 windows |
| Recorded as | `synthetic=true`, `real_tamil_nadu_source=false`, `approved_for_real_training=false` |
| Model tested | production `data/models/opening_det.onnx` (YOLOv8s, CubiCasa5K). Not trained on this pack |
| Command | `python ml/evaluation/eval_synthetic_pack.py` |

## Label validation

**All 20 label files are valid.** Every box is finite, normalised to [0, 1], has positive size and uses class 0 or 1
(`label_validation.json`).

**Class order is compatible:** pack 0 = door, 1 = window; production `detector.NAMES = ("door", "window")`.

## Results (confidence 0.35, one fixed scale for the whole pack: 85.6 px/m from median door box 77 px / 0.9 m)

| Matching rule | Door P / R / F1 | Window P / R / F1 |
|---|---|---|
| Box overlap IoU ≥ 0.5 | 0 / 0 / 0 | 0.25 / 0.28 / 0.27 |
| Box overlap IoU ≥ 0.3 | 0 / 0 / 0 | 0.79 / 0.89 / 0.84 |
| **Convention-neutral** (predicted box centre inside the labelled box) | **0.91 / 0.89 / 0.90** (211 / 237) | **0.87 / 0.98 / 0.92** (174 / 178) |

## Annotation-convention mismatch

The two label sets draw door boxes differently:
- **This pack:** the door box covers the leaf **and swing arc**, a roughly square box.
- **Production model** (CubiCasa convention): the door box covers the **opening in the wall**, a thin box.

Both mark the same doors, but their boxes barely overlap, so overlap-based scores are 0 for doors. The thin green boxes
inside the grey label boxes show this; see `crop_001.png` and `predictions/*.png` (grey = label, green = predicted door,
blue = predicted window).

Window boxes follow similar conventions, so they match at IoU 0.3 but not at 0.5 (frame thickness differs).

## Decision

- **Not merged into training.** The pack's own rule (instruction 10) applies: "if the annotation convention conflicts,
  do not merge". Training on square swing boxes would teach the production model a second, conflicting definition of
  "door".
- **Not used as accuracy evidence.** These are 20 synthetic schematics from one generator. They show that the pipeline
  works end to end (scale, tiling, class mapping and counting) and that the detector finds about 90 % of schematic doors
  and windows. **They are not real-drawing or Tamil Nadu accuracy.**
- **Useful next step:** relabel the pack's door boxes to the opening convention and keep it as a fixed regression set
  for future model versions.

> **SUPERSEDED (2026-10-09):** the "F1 0.90 / 0.92" figures above are a centre-containment hit rate on mislabelled boxes,
> not F1. See `reports_v2/door_window_audit/README.md` for corrected labels and one-to-one matching results.
