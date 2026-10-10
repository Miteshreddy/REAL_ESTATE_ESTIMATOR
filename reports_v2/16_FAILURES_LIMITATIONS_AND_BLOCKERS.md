# 16 — Failures, limitations and blockers

## Failures measured or observed in this run

| # | Failure | Status |
|---|---|---|
| 1 | G10 rate coverage 58.8 % < 90 % | FAILED (open; needs TN rates / Standard Data for 21 items) |
| 2 | Page classifier: floor-plan labels on scanned reports ≈ 8 % precision (2 / 24 fresh sample) | FAILED for reports; mitigated by the prose rule; G07 NOT MEASURED |
| 3 | dHash false-duplicate merged two unrelated documents | fixed (sparse-page guard, ≥3-page merge rule) |
| 4 | Prose rule initially removed 20 TNRD sheets from drawings | fixed (number ratio + vector exemption) |
| 5 | PII screen v1 flagged 62 drawing pages | fixed (removed the numeric pattern) |
| 6 | `requests` missing from requirements: TN PWD refresh fails in the start.bat venv | fixed, verified |
| 7 | v2 catalogue mislabels (CMDA "apartment" is commercial; Kauvery "water supply layout" is a compliance report) | recorded (06) |
| 8 | Corrupt download (IITM, 721 B) | REJECTED; needs manual acquisition |
| 9 | Complex smoke case05 (floor plan read as "other") | open (earlier finding, still in the scorecard) |

## Remaining limitations

- **No TN-trained models.** All vision models come from CubiCasa (Finnish). TN performance is NOT MEASURED.
- **Annotations and pseudo-labels:** 0 verified annotations. Pseudo-labels are text-span patterns only; there are no
  wall, room or opening polygons.
- **No holdout:** 0 final-holdout projects.
- **No BOQs:** 0 approved BOQs, so cost accuracy is NOT VALIDATED.
- **Rate provenance:** the amendment and Standard Data Book are from a single non-government source.
- **Defaults:** quantities use default heights and assumed scales unless the drawing provides them (labelled ASSUMED /
  NEEDS REVIEW).
- **Production readiness:** no authentication; no sandbox for file parsing (15).

## External blockers (BLOCKED_EXTERNAL_INPUT)

1. **Rights:** written permission for the 6 real projects (SIPCOT ×5, with the architect; CMDA plan owner / architect),
   for the TNRD type designs, and for JICA reports.
   - Queue: `manifests/licence_review_queue.csv`.
   - Template: `evidence/PERMISSION_REQUEST_TEMPLATE.md`.
2. **Annotation:** annotators plus two independent reviewers. 724 pages are queued, all NOT_STARTED. Start with the 18
   SIPCOT sheets and 2 CMDA sheets.
3. **BOQs:** at least 5 FINAL_APPROVED or PAID TN BOQs matching the drawing revision. SIPCOT and the CMDA owner are the
   first asks.
4. **Mappings:** at least 30 engineer-reviewed PWD mappings.
5. **Rates:** TN rates or Standard Data for formwork, joinery, aluminium windows, electrical, CPVC / SWR plumbing,
   anti-termite and granite; plus official copies of the amendment and the Standard Data Book.
6. **Missing categories, needing manual acquisition** (`manifests/manual_acquisition_queue.csv`, 41 items):
   - multi-storey apartments (TNUHDB / TNHB);
   - medical colleges / universities (tntenders CAPTCHA; Anna University challan bundles; CUTN working drawings);
   - structural sets with BBS.
7. **Kauvery report:** the user should decide whether to delete the quarantined compliance report that contains patient
   data.
