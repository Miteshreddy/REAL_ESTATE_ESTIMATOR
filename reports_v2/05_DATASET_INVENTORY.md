# 05 — Dataset inventory (recomputed from files, 2026-10-09)

There are two datasets. They are kept separate on purpose and linked only through manifests.

| Dataset | Purpose | Location |
|---|---|---|
| **A. `data/tn_dataset`** (split v2) | development dataset used by the estimator's evaluation scripts | `data/tn_dataset/metadata/*.json` |
| **B. `tn_corpus/`** | governed candidate corpus: acquisition, quarantine, inventory | `tn_corpus/registry/*`, mirrored in `manifests/` |

## A. `data/tn_dataset` (unchanged in this run)

| Measure | Value |
|---|---|
| Projects / pages | 46 / 114 |
| Sources | TNRD 109 pages; third-party smoke images 4; non-TN reference 1 |
| Licence status | government_publication_review 109; restricted 5 |
| Splits | development_benchmark **41**, smoke_test 4, reference 1, tn_train **0**, tn_validation **0**, final_holdout **0** (frozen list empty) |
| Pseudo-labels / verified annotations | 110 / **0** |
| Leakage check | `ml/dataset/check_leakage.py` exit 0 (`logs/leakage_check_tn_dataset.txt`) |

The 41 TNRD development projects were inspected many times during development. They stay in development and can never
become holdout.

## B. `tn_corpus` (this run)

**Build:** `tn_corpus/scripts/build_corpus.py`. Timestamps: `tn_corpus/registry/dataset_build_summary.json` `created`,
and `evidence/facts.json` `generated`.

### Files

| Measure | Count | Definition |
|---|---|---|
| Source registry rows | 31 | 11 curated sources + 20 v2-catalogue direct-PDF leads |
| TNRD catalogue links | 54 | live page `tnrd.tn.gov.in/buildings_design.html` |
| Download records (quarantine sidecars with a file) | 68 | 54 TNRD + 2 leads (run 1) + 12 v2 catalogue (this run) |
| Unique downloaded files | 67 | the JICA ICH report was reached by two URLs (same SHA-256) |
| Bytes downloaded | 169,249,511 | sum over download records (the duplicate counted twice) |
| User-supplied files | 3 | Buildings.pdf, 21-page extract, TN RERA listing |
| Local seed files | 50 | an earlier copy of TNRD files; all identical to downloads |
| **Unique files overall** | **69** | by SHA-256 |
| Identical-file duplicates | 52 | 50 seeds + handbook + JICA |
| Corrupt files | 1 | IIT Madras `Tendeedoc.pdf` (721 bytes; PDF header but truncated) |
| Blocked / failed / rejected acquisitions | 8 | 5 blocked (robots ×3, HTTP 403 ×2), 1 duplicate URL, 2 non-TN rejected |
| Personal-data restricted | 1 file (585 pages) | not rendered, OCR'd or labelled; see 06 |
| ZIP v2 derivative assets | 68 | 34 single-sheet PDFs + 34 PNGs, linked to handbook pages, not counted as new |
| Corpus storage | 1.13 GB | everything under `tn_corpus/` incl. 150-dpi renders |

### Pages and classification

**Pages extracted: 2,404.** Each has a 150-dpi PNG master, a 400-px thumbnail and a recorded px-per-pt factor.

| Type (heuristic) | Pages |
|---|---|
| unrelated_text | 1,208 |
| architectural_floor_plan | 465 |
| boq_specification | 237 |
| blank_unknown | 214 |
| foundation | 80 |
| services_mep | 77 |
| slab_plan | 37 |
| section | 33 |
| elevation | 25 |
| site_plan | 14 |
| reinforcement_bbs | 11 |
| beam_schedule | 3 |

The "drawing pages" total of **745** is an *upper bound*. On scanned reports, a fresh sample of 24 pages labelled
architectural_floor_plan contained only 2 real plans. On TNRD sheets the labels look right, but they have not been
measured. See 08.

### Projects (50 groups)

| Nature | Count |
|---|---|
| **Independent real TN building projects** (title-block evidence) | **6**: SIPCOT hostels ×5, CMDA commercial ×1 |
| Report containing concept plans of a real project | 1 (ICH Chennai OPD building) |
| Survey reports with campus master plans / few drawings | 2 (AIIMS Madurai; JICA urban-health survey, 2 files merged) |
| TNRD standard type designs (generic, no site) | 30 (the IHHL leach-pit and septic-tank sheets are merged as one design: text similarity 0.93) |
| Handbooks | 2 (Buildings: reference; Roads & Bridges: out of scope) |
| Context / rules / programme / registry / pre-bid / RFP-text documents | 8 |
| Corrupt | 1 |

### Status counts

| Status | Count |
|---|---|
| REVIEW_REQUIRED | 47 |
| RESTRICTED_PERSONAL_DATA | 1 |
| REJECTED | 2 |
| APPROVED_FOR_TRAINING / APPROVED_FOR_EVALUATION | **0 / 0** |
| Annotation queue | 724 pages, all NOT_STARTED |
| PSEUDO_LABEL | 560 pages / 3,647 text-span labels (dimension text, floor labels) |
| PII-suspected pages (excluded from queue and labels) | 2 |
| VERIFIED | **0** |
| BOQs | 0 candidate, 0 approved |

## Why counts differ from earlier reports

| Report | Unique files | Pages | Drawing pages | Projects | Reason for change |
|---|---|---|---|---|---|
| `tn_corpus/DATASET_BUILD_REPORT.md`, run 1 (commit 0c5964d) | 58 | 1,183 | 482 | 35 | — |
| this run | 69 | 2,404 | 745 | 50 | see below |

1. **New acquisitions:** +12 v2-catalogue files, +1,806 pages before restriction.
2. **Kauvery compliance report restricted for personal data:** −585 pages.
3. **Classifier change:** a prose rule moved report prose out of "drawing"; the vector exemption keeps TNRD sheets as
   drawings.
4. **Grouping corrections:**
   - SIPCOT split into 5 building projects plus RFP text;
   - a false Kauvery ↔ Roads & Bridges merge removed;
   - the two JICA urban-health survey files merged on 50 matching page pairs.
5. **Non-TN removal:** 2 non-TN JICA reports were downloaded and then moved to `tn_corpus/rejected/non_tn/` on the
   user's TN-only instruction.

The ZIP's own `05_EXISTING_CORPUS_AUDIT/*` is an earlier copy of run-1 output. It is superseded and kept unchanged
inside the extracted ZIP.
