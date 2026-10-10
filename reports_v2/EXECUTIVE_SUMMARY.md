# Executive summary — TN PWD Drawing-Based Cost Estimator, audit v2

| | |
|---|---|
| Generated | 2026-10-09 (IST), facts snapshot `evidence/facts.json` |
| Repository | branch `tn-completion`, HEAD `0c5964d` at audit start; uncommitted changes existed (listed in 01) |
| Scope | Tamil Nadu only (user instruction during this run: "no need of other states") |
| Reproducible | Yes: `20_REPRODUCIBILITY_AND_COMMANDS.md`. Web acquisition depends on remote servers |

## Bottom line

The software works end to end and is tested: 95 / 95 tests pass. **Construction-cost accuracy is NOT VALIDATED.**
- The gate scorecard result is **FAIL**: rate coverage is 58.8%, and every accuracy gate is NOT MEASURED or NOT VALIDATED.
- There are 0 verified annotations, 0 approved BOQs, 0 engineer-reviewed mappings and 0 rights-cleared projects.

**Training cannot legitimately begin**, and no train / validation / final-holdout split exists, because no project has
rights approval or verified labels.

## What this run added

| | Before (corpus run 1, same day) | After (this run) |
|---|---|---|
| Unique source files | 58 | **69** |
| Pages extracted | 1,183 | **2,404** (585 pages of one file withheld for personal data) |
| Pages classified as drawings (heuristic) | 482 | 745 (upper bound: unreliable on report scans, see 08) |
| Project groups | 35 | **50** |
| Independent real TN building projects | 0 | **6** (5 SIPCOT hostels + 1 CMDA-approved commercial building), identified from title blocks |
| Verified annotations / approved projects / approved BOQs | 0 / 0 / 0 | 0 / 0 / 0 |

### Supplied ZIP (v2)

The ZIP contains **no new drawings**:
- Its handbook and 21-page extract are byte-identical to files already held.
- Its 34 single-sheet PDFs and 34 PNGs are crops of handbook pages. All 34 PDF page numbers were confirmed.
- Its "structural reference" consists of generic SP 34 figures, not a project BBS.

Its useful content was the 110-row source catalogue. That catalogue was compiled offline, so I tested each of its 20
direct-PDF claims:

| Outcome | Count |
|---|---|
| Acquired | 12 |
| Blocked by robots.txt or HTTP 403 | 5 |
| Duplicate URL | 1 |
| Not Tamil Nadu, removed | 2 |

Of the 12 acquired, one was a corrupt 721-byte file, and one was a hospital compliance report containing **patient
records**. That report is now restricted and not extracted. The catalogue also had wrong labels: the "CMDA high-rise
apartment" is a stilt + 3-floor **commercial office**, and the "Kauvery water-supply layout" contained no drawings in the
pages checked.

## Coverage of the high-impact categories (real projects with drawings)

| Category | Independent projects with actual plan sheets |
|---|---|
| Hostels | **5** |
| Commercial | **1** |
| Hospitals | 1 (concept OPD plans inside a JICA report) |
| Multi-storey apartments | **0** |
| Medical colleges | **0** (campus master plan only) |
| Universities / colleges | **0** |

Everything else is TNRD standard type designs (30 generic designs, no site).

## Fixes made in this run
- **Project grouping.** A dHash false-positive (two near-blank title pages) merged a hospital report with the Roads &
  Bridges handbook. Now sparse pages never count as duplicates, and documents merge only on at least 3 matching pages.
- **Page classifier.** It labelled report prose as floor plans; the fresh-sample precision was about 2 / 24. A prose
  detector now handles this, but the rule is still heuristic.
- **Missing dependency.** `requests` was missing from `requirements.txt`, so the TN PWD refresh endpoints failed in the
  `start.bat` virtual environment. This is now fixed and verified.
- **Personal data.** A privacy restriction was added for documents containing personal data.

## Blocking external inputs
1. Rights or permission decisions per project (`manifests/licence_review_queue.csv`). The 6 real projects are the
   priority.
2. Annotators plus two reviewers (`manifests/annotation_queue.csv`, 724 pages).
3. At least 5 approved TN BOQs.
4. At least 30 engineer-reviewed PWD mappings.
5. TN rates for formwork, joinery and electrical/plumbing.
6. Manual acquisition of apartment, medical-college and university drawing sets (`manifests/manual_acquisition_queue.csv`,
   41 items).

Details are in `FINAL_MASTER_REPORT.md`.
