# 18 — Final dataset build report (tn_corpus, TN-only)

**Build:** `python tn_corpus/scripts/build_corpus.py` (idempotent; renders and OCR are cached).

**Outputs:**
- `tn_corpus/registry/`;
- `tn_corpus/DATASET_BUILD_REPORT.md`, auto-generated;
- mirrored here in `manifests/`.

**Status:** a candidate corpus. **Not a training dataset.**

## Build pipeline

1. **Acquire:** `tnrd_discover.py`, `fetch_leads.py` and `fetch_catalog_v2.py`, all through `safe_fetch`. Files go to
   quarantine as `raw_candidates/<sha256>.pdf` with a JSON sidecar.
2. **Collect:** supplied files (copied byte-identical to `tn_corpus/supplied/`), quarantine sidecars and the local seed
   folder.
3. **Extract each file:**
   - SHA-256, and open with PyMuPDF; corrupt files are logged;
   - files on the personal-data list are skipped;
   - per page: 150-dpi render, thumbnail, text and vector count, OCR fallback;
   - classification, then the PII screen, then text-span pseudo-labels.
4. **Dedup:** SHA-256, rotation-aware dHash (non-sparse pages only), text Jaccard, declared derivation.
5. **Group:** catalogue entry / inferred TNRD multi-sheet set; per-building page ranges (SIPCOT); merges supported by
   ≥3 matching pages (or all pages of a single-sheet design); verified project metadata from title blocks.
6. **Record state:** `approvals.csv` (human) gives the usage state. With none, the state is REVIEW_REQUIRED, or REJECTED
   / RESTRICTED. Splits are created only for approved projects.
7. **Queues:** licence review, annotation (1 row per drawing page; extract and PII pages excluded; priority 1 = plans,
   foundations, schedules, BBS).
8. **ZIP v2 derivatives** linked to handbook pages.

## Exact counts (final build)

| Measure | Count |
|---|---|
| Sources in registry | 31 |
| TNRD catalogue links | 54 |
| Download records / unique downloaded files | 68 / 67 |
| Bytes downloaded (records) | 169,249,511 |
| Unique files overall | 69 (164,948,520 bytes) |
| Identical-file duplicates | 52 |
| Corrupt files | 1 |
| Blocked / failed / rejected acquisitions | 8 |
| Pages extracted | 2,404 |
| Classified drawing pages (upper bound) | 745 |
| PII-suspected pages | 2 |
| Near-duplicate page pairs | 72 |
| Cross-project reuse pairs | 2 (both merged; handbook reprints recorded separately) |
| Project groups | 50, of which 47 have drawing pages |
| Independent real TN building projects | **6** |
| Pseudo-labelled pages / labels | 560 / 3,647 |
| Annotation queue | 724 pages (NOT_STARTED) |
| Verified annotations | **0** |
| APPROVED_FOR_TRAINING / APPROVED_FOR_EVALUATION | **0 / 0** |
| REVIEW_REQUIRED / RESTRICTED / REJECTED | 47 / 1 / 2 |
| Approved BOQ projects | **0** |
| Splits | none (0 approved projects) |
| Storage (tn_corpus) | 1.13 GB |

**Rule-change effect:** the final PII rule removed only 2 pages, so pseudo-label and queue counts equal the pre-PII
build.

## Recommended next annotation batch (priority)

1. SIPCOT hostel sheets: pages 32–49 of `SIPCOT-RFP-…pdf`, 5 buildings, 18 sheets.
2. CMDA approved plan: 2 vector sheets.
3. TNRD type designs: 30 designs.
4. ICH OPD concept plans.

Real projects come first because they can become holdout once rights are cleared.
