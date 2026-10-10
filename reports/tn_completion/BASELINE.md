# Baseline (before this work package)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

Recomputed on branch `tn-completion` from commit `5deae95`.

- pytest: **57 passed**
- active schedules: [['tn-pwd-sor-2025-26-amd-2025-08-08', 'Tamil Nadu']]
- TN rate items: 3502 · Standard Data items: 514
- reference BOQs: 0 · learned mappings: 0
- models: floorplan_unet, room_label / room_geom classifiers, opening_det
- new inputs found: Downloads/createpdf_683689c2-….pdf: 5 TN complex drawings (case02 image is a 14x16 placeholder); Downloads/Residential_building_estimate.pdf: this app's own old Telangana estimate — NOT ground truth

Corrections made to the baseline interpretation:
1. The Aparna drawing is a **Hyderabad** project — previously scored as "TN large residential"; now a non-TN reference only.
2. The 41 TN Rural Development projects were repeatedly used during development — reclassified **development benchmark (exposed)**, not unseen.
3. `Downloads/Residential_building_estimate.pdf` is this application's own earlier Telangana-schedule output — **not ground truth**.

Baseline scorecard: `reports/tn_completion/baseline_scorecard.json`.
