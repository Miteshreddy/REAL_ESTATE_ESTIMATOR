# Unseen TN evaluation (Task 16)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

Provenance: {"code_commit": "a3b72ce", "uncommitted_changes": true, "dataset_manifest_sha256": "43d1c1ae4a545be47747808567922ac488351c0d1202aca35c29c56b31f05e74", "split_seed": "tn-v2", "models": {"floorplan_unet": "1.0", "room_label / room_geom classifiers": "5", "opening_det": "1.0"}, "evaluated_at": "2026-10-09T16:43:31"}

Final-holdout TN projects: **0** → no credible unseen evaluation is possible yet.
Exposure record: the TN Rural Development sheets were evaluated repeatedly during development (development benchmark); the complex
smoke set was exposed by one site-plan fix; Aparna is non-TN.

Evidence (cannot satisfy a gate):
| name | value | n | label | dataset |
|---|---|---|---|---|
| Plinth area within ±10 % | 68.8 | 16 | DEVELOPMENT (exposed) | TN Rural Development type-design sheets |
| Sheet view classification | 88.9 | 27 | DEVELOPMENT (exposed) | TN Rural Development type-design sheets |
| Floor occurrences (refuge floor) | 100.0 | 1 | REFERENCE (non-TN: Hyderabad) | Aparna Block-A refuge floor |
| Apartments found | 100 | 1 | REFERENCE (non-TN: Hyderabad) | Aparna Block-A refuge floor |
| Openings detected (no reference) | — | 1 | REFERENCE (non-TN: Hyderabad) | Aparna |
| Site-plan vs floor-plan classification | 75.0 | 4 | SMOKE (third-party images, exposed after one fix) | TN complex-architecture set (4 usable images) |
| Door count within ±10 % of tags | 20.8 | 24 | REFERENCE (non-TN: Bihar) | Nalanda commercial |
| Window count within ±10 % of tags | 0.0 | 24 | REFERENCE (non-TN: Bihar) | Nalanda commercial |
| Room area within ±10 % | 78.5 | 242 | REFERENCE (non-TN: Uttarakhand) | Uttarakhand Govt CAD |
| Detector door F1 (train) | 88.3 | 4200 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Detector window F1 (train) | 91.8 | 4200 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Detector door F1 (val) | 86.5 | 400 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Detector window F1 (val) | 89.8 | 400 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Detector door F1 (test) | 86.9 | 400 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Detector window F1 (test) | 88.1 | 400 | GENERIC (CubiCasa5K — not TN) | CubiCasa5K |
| Total vs exact geometry (dxf) | 100.0 | 12 | SYNTHETIC | generator |
| Total vs exact geometry (pdf) | 100.0 | 12 | SYNTHETIC | generator |
| Total vs exact geometry (png) | 100.0 | 12 | SYNTHETIC | generator |
| Take-off lines priced from TN data | 58.8 | 153 | COVERAGE (sample drawings) | villa_g1.dxf, compact_home.dxf, bungalow.dxf |
