# Model evaluation (Task 4)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

## Opening detector `opening_det` v1.0 — GENERIC (CubiCasa5K, not Tamil Nadu)

| split | door F1 | window F1 |
|---|---|---|
| train | 0.8828 | 0.9181 |
| validation | 0.8652 | 0.8984 |
| test | 0.8688 | 0.8807 |

Resolution sensitivity (CubiCasa test, mAP50): {"640": 0.8704, "1024": 0.8976, "1280": 0.8911} — environment {"torch": "2.6.0+cu124", "ultralytics": "8.4.174", "python": "3.12.10", "device": "NVIDIA GeForce RTX 4060 Laptop GPU"}.

App integration: ONNX decoding checked against test labels (pytest `test_detector_model_is_working`). Fusion now includes a
wall-proximity gate (radius = half the opening width + 0.2 m): on the Aparna reference drawing it rejects 1 of 136 detections.

U-Net `floorplan_unet` v1.0: CubiCasa test mIoU 0.740 (generic).

**Tamil Nadu metrics: NOT MEASURED. No model is TN fine-tuned** — 0 verified, training-eligible TN annotations
(`configs/tn_opening_detector.yaml` stage2 refuses to run without them).
