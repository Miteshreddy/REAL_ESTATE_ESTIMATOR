# 08 — Drawing processing audit

## Corpus processing (`tn_corpus/scripts/build_corpus.py`)

| Step | Implementation | Evidence / status |
|---|---|---|
| Open / validate | PyMuPDF open; `%PDF-` magic checked at download | 1 corrupt file detected (IITM, 721 B) → recorded, not extracted |
| Text / vector | PDF text; vector-path count (`get_drawings`) | per page: `vector_paths`, `content` = vector / raster / text / empty |
| Render | 150 dpi PNG master per page; `px_per_pt = 150/72` recorded; originals kept byte-identical (`raw_candidates/<sha256>.pdf`, `supplied/`) | 2,404 renders |
| Thumbnails | 400 px JPEG, separate folder | 2,404 |
| OCR fallback | RapidOCR on renders when PDF text < 40 words and ink > 1 %; cached in `ocr_cache/` | TNRD sheets have outlined text, so most need OCR |
| Classification | keyword rules + vector / raster density + **prose detector** (≥15 function words, < 1.5 numbers per function word, not a vector drawing → text) | IMPLEMENTED, **NOT VALIDATED** (see below) |
| Pseudo-labels | text spans matching dimension / floor-label patterns, boxes in PDF points | 560 pages, 3,647 labels; state PSEUDO_LABEL |
| Dedup | SHA-256; dHash at 0 / 90 / 180 / 270°; text Jaccard; declared derivation (extract page i = handbook page 312+i, printed page number checked) | 52 identical files, 72 near-duplicate page pairs |
| Personal-data guard | per-file restriction list; derived renders, OCR and labels deleted, and not re-created on rebuild | 1 file |

## Asset types

These are kept separate and linked by `page_id = <sha16>-p<n>`:
1. original PDF;
2. 150-dpi full render;
3. thumbnail;
4. pseudo-label JSON;
5. ZIP derivative (single-sheet PDF / 200-dpi PNG) → `manifests/zip_v2_derivative_inventory.csv`.

No crops or contact sheets are used as dataset items. The contact sheets in `evidence/` are review aids only.

**Limitation:** 150 dpi is adequate for viewing and for OCR of normal text, but may be low for small dimension text on
A1 sheets.
- The original vector PDFs are preserved, so any page can be re-rendered at higher dpi with the same `px_per_pt`
  bookkeeping.
- Nothing was downscaled destructively.

## Classifier quality (assistant spot-checks, not ground truth)

| Check | Result |
|---|---|
| First look, pre-fix, 6 report documents, 48 pages labelled floor plan | ≈ 9 real plans |
| Fresh random sample after fixes, 24 pages labelled architectural_floor_plan from external reports (`evidence/classifier_spot_check.csv`) | **2 / 24 real floor plans (8 %)** |
| TNRD single sheets | after the vector exemption, all 30 type-design projects keep drawing pages; not measured page by page |

**Conclusion:** use the drawing-type labels only to prioritise review. The count of 745 drawing pages is an upper
bound. Gate G07 (drawing classification) remains NOT MEASURED. It needs labelled TN pages from projects outside the
development set.

## Bugs found and fixed in this run

1. **False project merge.** Two near-empty pages (a "DRAINAGE IN RURAL ROADS" divider and a footer-only page) had
   dHash distance 8. That merged the Kauvery report with the Roads & Bridges handbook into one 1,105-page project.
   - **Fix:** pages with < 2 % ink are excluded from perceptual matching, and documents merge only when matching pages
     ≥ min(3, pages of the smaller document).
   - **Evidence:** `evidence/false_dup_roads_vs_kauvery.jpg`.
2. **Prose classified as floor plans.** OCR'd report pages contain "plan" and many words.
   - **Fix:** the prose detector.
   - **Regression it initially caused:** 20 TNRD sheets with general notes were reclassified as text. This was caught
     and fixed with the number-ratio test and the vector exemption.
3. **Slow dedup.** All-pairs comparison over ~3,000 pages took more than 10 min. Text and blank pages are now skipped
   from dedup.

## Estimator drawing pipeline (live app)

See 02 C. Results recomputed by `run_tn_eval.py scorecard` from stored evaluations:

| Measure | Value | Dataset |
|---|---|---|
| Sheet view classification | 88.9 % (n = 27) | development benchmark, **exposed** |
| Plinth area within ±10 % | 68.8 % (n = 16) | development benchmark, exposed |
| Site plan vs floor plan | 3 / 4 | smoke, third-party images, exposed after one fix |
| Synthetic exact geometry (DXF / PDF / PNG) | 100 % (n = 12 each) | **synthetic** |

**TN gates G01–G08:** NOT MEASURED. There are 0 final-holdout projects.
