# Final master report — TN PWD Drawing-Based Construction Cost Estimator (audit v2)

## Run details

| | |
|---|---|
| Date | 2026-10-09 |
| Branch / commit at start | `tn-completion` / `0c5964d` |
| Uncommitted changes | yes (01) |
| Scope | Tamil Nadu only |
| Evidence | `evidence/facts.json`, `manifests/*`, `logs/*` |

## Overall status

| Area | Status |
|---|---|
| Software pipeline (drawings → quantities → TN PWD rates → cost → review → report) | IMPLEMENTED, TESTED (95 / 95) |
| TN drawing corpus | IMPLEMENTED, TESTED. 69 unique files, 2,404 pages, 50 project groups, **6 independent real TN projects**; all REVIEW_REQUIRED |
| Model accuracy on TN | NOT MEASURED |
| Quantity accuracy on TN | NOT MEASURED |
| PWD mapping | NOT VALIDATED |
| Rate coverage | **FAILED** (58.8 % vs 90 %) |
| Cost accuracy | NOT VALIDATED |
| Training | BLOCKED_EXTERNAL_INPUT |
| Final holdout | does not exist |
| **Overall** | **NOT COMPLETE: BLOCKED_EXTERNAL_INPUT. Scorecard FAIL** |

## The 20 required answers

**1. What the application contains.** A FastAPI backend (57 routes) and a vanilla-JS SPA:
- drawing parsers for PDF (vector and raster), images, DXF and DWG;
- 2 deep-learning vision models, 3 classical ML models, 2 TF-IDF text models, FTS5 retrieval and RapidOCR;
- deterministic quantity engines;
- TN PWD document ingestion and rate analysis;
- BOQ comparison, annotation and mapping-review workflows;
- governed offline dataset tooling.

See 02 and 03.

**2. End to end.** An upload flows through these stages:

| Stage | Module |
|---|---|
| Parse | `parsers.parse_any` |
| Exclude site plans | site-plan guard |
| Floors | `floors` |
| Openings | `openings.reconcile` |
| Areas | `areas` |
| Take-off | `takeoff` |
| Structural (BBS) | `structural` |
| Walls | `walls` |
| Pricing | TN pricing: active TN SOR 2025-26 + amendment, plus Standard Data |
| Confidence and quality | `confidence`, `quality` |
| Review / lock | review and confirm |
| Report | HTML / PDF / XLSX |

See `diagrams/cost_estimation_pipeline.mmd`.

**3. Active modules.** All backend modules listed in 03 as "yes". Evaluation harnesses and `learning.py` (0 data) are
present but not part of an estimate. `models_v3`/`v4` are historical.

**4. ML / NLP models.**

| Model | Purpose |
|---|---|
| U-Net ResNet-34 (ONNX) | segmentation |
| YOLOv8s (ONNX) | doors / windows |
| RandomForest | vector primitives |
| GradientBoosting | room geometry |
| TF-IDF + logistic regression | room labels |
| TF-IDF cosine | SOR matching |
| SQLite FTS5 | PWD search |
| RapidOCR | OCR |

All are trained on CubiCasa, synthetic data or pretrained weights. **None is TN-fine-tuned.** See 04.

**5. How the dataset was collected.** Governed fetchers sharing one guarded HTTP layer: allowlist, SSRF guard,
robots.txt, delay, size cap, PDF magic check, kill switch and decision log. Files are content-addressed in quarantine
with sidecars. Then: extraction, classification, dedup, grouping, queues. See 18.

**6. Documents acquired in this run.**
- 12 TN PDFs from the v2 catalogue (1 corrupt, 1 personal-data restricted).
- 2 non-TN PDFs downloaded and then rejected.
- 5 blocked (robots ×3, HTTP 403 ×2).
- The supplied ZIP added **0 new drawings**: 68 derivative assets of handbook pages.

**7. Unique independent projects.**
- **6 real TN buildings:** SIPCOT hostels ×5 (Irungattukottai, Sriperumbudur ×2, Tiruppur ×2) and a CMDA-approved
  stilt + 3-floor commercial office.
- Plus 1 report with concept plans of a real hospital building (ICH Chennai OPD).
- The remaining groups are 30 standard type designs, 2 handbooks and 11 non-drawing or context documents.

**8. Categories.**

| Category | Real projects |
|---|---|
| Hostels | 5 |
| Commercial | 1 |
| Hospitals | 0 with working drawings (1 with concept plans) |
| Apartments | **0** |
| Medical colleges | **0** |
| Universities / colleges | **0** |
| Real structural / BBS packages | **0** |

Schools, offices, houses and public buildings exist only as TNRD type designs. See 07.

**9. Unresolved permissions.** All 47 drawing-bearing groups are REVIEW_REQUIRED. 0 permissions have been requested or
confirmed. A template is ready. See 06.

**10. Duplicates and grouping.**
- 52 identical files; 72 near-duplicate page pairs; 2 merges (the IHHL design pair, and the JICA survey split across 2
  files).
- Handbook reprints are recorded but not merged.
- SIPCOT is split into 5 buildings by sheet-title page ranges.
- A false merge was found and fixed.

See 08 and 13.

**11. Verified annotations.** **0.** There are 560 pseudo-labelled pages (3,647 text-span labels), and 724 pages wait in
the queue.

**12. Can training begin?** **No.** There are 0 rights-approved projects and 0 verified labels.

**13. Valid train / validation / final-holdout splits?** **No.**
- `data/tn_dataset`: 0 / 0 / 0, with 41 development projects.
- `tn_corpus`: no splits (correct by policy).

**14. What the metrics demonstrate.**
- **Generic CubiCasa:** the detector reaches F1 0.87 / 0.88 and the U-Net mIoU 0.74.
- **Synthetic geometry:** 100 %.
- **Exposed TN development data:** plinth area 68.8 % within ±10 %; sheet views 88.9 %.

**No TN accuracy has been measured on unseen, verified data.**

**15. Incomplete PWD items.** 21 take-off items have no TN rate:
- formwork ×4;
- doors, door frames, aluminium windows, grills;
- electrical ×3;
- basin, sink, CPVC, SWR, tank;
- anti-termite, granite, putty, excavation, modular kitchen.

Rate coverage is 58.8 %. The amendment and the Standard Data Book come from an unverified secondary host.

**16. Approved BOQs.** **0.**

**17. Total cost accuracy validated?** **No** (G11–G14 NOT VALIDATED).

**18. Remaining bugs and failure cases.**
- The page classifier is unreliable on scanned reports (about 8 % floor-plan precision in a spot check).
- Rate coverage FAIL.
- Smoke case05 misclassified.
- No authentication and no parser sandbox.
- Non-PWD finish uplift / cost index multipliers are available in pricing.

Fixed in this run:
- the false dedup merge;
- the prose classifier and its regression;
- PII screen false positives;
- the missing `requests` dependency.

**19. Relevant scratch / experiments.** 172 items are inventoried (17). Debug renders, historical non-TN evaluations,
split v1 manifests and `models_v3`/`v4` are obsolete. Checkpoints and base weights are needed for retraining.

**20. Next external inputs and decisions.**
1. Permissions for the 6 real projects, TNRD and JICA.
2. Annotators plus 2 reviewers.
3. At least 5 approved BOQs.
4. At least 30 engineer mapping reviews.
5. Missing TN rates.
6. Manual acquisition of apartments, medical colleges, universities and BBS sets (41 queue items).
7. A decision on the quarantined personal-data document.
8. Commit or restore the split v1 deletions.
9. Optionally purge the 41 inactive non-TN schedules from the DB.

## Major source file table

See 03.

## Report index

See `README.md`.
