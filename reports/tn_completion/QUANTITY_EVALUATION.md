# Quantity extraction (Tasks 5-9)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

| Quantity family | Implementation | TN accuracy |
|---|---|---|
| Rooms / areas | measurement hierarchy (written dims → CAD → calibrated → polygon → UNRESOLVED); carpet / common / plinth / built-up / gross areas kept distinct with definition, formula, calibration, uncertainty | NOT MEASURED (no holdout) |
| Floors / units | floor occurrences incl. basement, terrace, LEVEL n, ranges, lists; unit grouping | NOT MEASURED (TN) |
| Doors / windows | detector + U-Net + wall gaps; wall gate; per-mark and per-source reconciliation (OPENING COUNT CONFLICT) | NOT MEASURED (TN) |
| Walls | length / face area / masonry volume (deductions listed) / plaster & paint areas with sides; ASSUMED when height is a default | NOT MEASURED |
| Structural | members from schedules; concrete only with all dimensions; steel from BBS (L×n×Ø²/162) replacing plan figures; STRUCTURAL INPUT MISSING / NEEDS ENGINEER REVIEW | NOT MEASURED |
| Site / campus plans | site-plan guard (title / ≥1:500 scale) — never costed | smoke: see below |

Complex-building smoke test (third-party images, n=4, **exposed after one fix**):
| case | expected | observed | correct | rooms | openings | completeness |
|---|---|---|---|---|---|---|
| case01 | floor_plan | floor_plan | True | 16 | 130 | 30 / 48 items priced |
| case03 | floor_plan | floor_plan | True | 21 | 147 | 30 / 48 items priced |
| case04 | site_plan | site_plan | True | 0 | 0 | 0 / 0 items priced |
| case05 | floor_plan | other | False | 0 | 0 | 0 / 0 items priced |

Evidence rows (development / reference / generic / synthetic) are in `data/evaluation/tn/scorecard.json` → `evidence`.
