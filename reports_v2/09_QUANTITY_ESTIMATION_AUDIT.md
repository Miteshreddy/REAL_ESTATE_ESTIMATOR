# 09 — Quantity estimation audit

**Code:**
- `backend/takeoff.py` (`compute_quantities`, `derive_params`, `plan_multipliers`, `other_elements`);
- `areas.py`, `walls.py`, `structural.py`, `floors.py`, `openings.py`;
- item recipes in `data/tnpwd/maps/takeoff_tn.json`: 53 take-off items, each mapped to a TN SOR code or a Standard Data
  analysis with a plausibility band.

**Tests:** `backend/tests/test_quantities_structural.py` (16), `test_pipeline_quality.py` (18), `test_tn.py` (29). All
pass. These are **software-behaviour tests on synthetic inputs**, not accuracy evidence.

## What is implemented

| Quantity | Method | Units | Missing-input handling | Status |
|---|---|---|---|---|
| Room areas | measurement hierarchy: written dimensions → CAD geometry → calibrated raster → polygon → UNRESOLVED | m² | assumed scale gives NEEDS REVIEW; fallback scale gives UNRESOLVED | IMPLEMENTED, TESTED |
| Carpet / common / plinth / built-up / gross floor area | separate definitions and formulas | m² | GFA needs a storey count, else "STOREY COUNT REQUIRED" | IMPLEMENTED, TESTED |
| Floors | basement, terrace (not a storey), LEVEL n, ranges "FLOORS 10-20" | — | — | IMPLEMENTED, TESTED |
| Walls | length × (floor height − slab) → face area; masonry volume minus openings; plaster / paint by side | m, m², m³ | default height gives ASSUMED; no thickness gives UNRESOLVED | IMPLEMENTED, TESTED |
| Doors / windows | geometry + schedule + detector, compared; conflicts flagged | nos, m² | never auto-resolved | IMPLEMENTED, TESTED |
| Masonry, plaster, painting, flooring, skirting, DPC, earthwork, PCC, RCC | recipes in `takeoff.py` | per SOR unit | each line carries basis / assumption | IMPLEMENTED, TESTED |
| Concrete (structural) | only when the schedule gives all dimensions; column height = storeys × floor height + foundation depth + plinth | m³ | otherwise NEEDS ENGINEER REVIEW / STRUCTURAL INPUT MISSING | IMPLEMENTED, TESTED |
| Reinforcement | BBS rows → L × n × Ø² / 162; replaces plan-ratio steel; unmapped member types (lintel, stair) flagged | kg | no BBS gives NEEDS ENGINEER REVIEW | IMPLEMENTED, TESTED |
| Site / campus plans | `site_plan_reason`: never costed | — | — | IMPLEMENTED; smoke 3 / 4 |

## What is measured

| Measure | Result | Status |
|---|---|---|
| Synthetic exact geometry | 100 % for DXF, PDF and PNG (n = 12 each) | SYNTHETIC, proves arithmetic consistency only |
| Plinth area within ±10 % | 68.8 % (n = 16) | development benchmark, exposed |
| Complex smoke (4 third-party images) | 3 / 4 sheet classes correct; case05 missed | SMOKE, exposed |
| **TN quantity accuracy vs verified reference** | — | **NOT MEASURED**: 0 verified TN quantities, 0 approved BOQs |

## Limitations

- **Heights and storeys:** floor height, slab thickness, foundation depth and plinth height default to parameters unless
  read from sections. Lines using defaults are labelled ASSUMED.
- **Structural content:** structural drawings with schedules or BBS are rare in the corpus.
  - The 6 new real projects are architectural only.
  - The SIPCOT and CMDA sheets carry no BBS.
- **Openings:** detector performance on TN drawings is unknown (see 04).
