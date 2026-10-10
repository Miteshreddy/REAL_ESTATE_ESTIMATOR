# 07 — Building-category coverage (Tamil Nadu only)

**Sources:**
- `manifests/category_coverage.csv`, computed by `build_reports_v2.py:coverage` from the project manifest, the page
  inventory and the v2 catalogue;
- an assistant visual spot-check of the new documents. This is a check, **not** an annotation.

Every category below has these values: 0 projects with BOQs, 0 with permission confirmed, 0 eligible for training,
0 eligible for final evaluation, and 0 verified annotations.

## Column definitions

| Column | Meaning |
|---|---|
| **Leads** | catalogue / registry rows naming the category |
| **Files** | unique downloaded files in projects of the category |
| **Groups** | project groups (documents or buildings) |
| **Real projects** | independent real buildings, confirmed from title blocks |
| **Classifier pages** | pages the heuristic classifier labelled as drawings: an **upper bound**, inflated on reports |
| **Confirmed plan sheets** | plan sheets confirmed by eye or by OCR'd sheet titles |

## Coverage table

| # | Category | Leads | Files | Groups | Real projects | Classifier pages | Confirmed plan sheets |
|---|---|---|---|---|---|---|---|
| 1 | Multi-storey apartments | 18 | 0 | 0 | **0** | 0 | 0 |
| 2 | Hospitals | 15 | 6 | 5 | **0 with working drawings**; 1 with concept plans (ICH OPD, JICA report) | 417 | ≥2 floor plans + 1 site plan (ICH p72, p131, p172) |
| 3 | Medical colleges | 8 | 3 | 2 | **0** | 315 | 0 floor plans; campus master plans only (AIIMS Madurai) |
| 4 | Universities | 12 | 2 | 2 | **0** | 45 | 0 (CUTN documents are EOI / minutes) |
| 5 | Colleges | 3 | 0 | 0 | **0** | 0 | 0 (IITM file corrupt) |
| 6 | Commercial buildings | 8 | 3 | 3 | **1** (CMDA PP-NHRB-S-0167-2025) | 4 | 2 sheets (site-cum-stilt plan; typical / terrace plans + section + elevation) |
| 7 | Hostels | 19 | 5 | 10 | **5** (SIPCOT packages 1–5) | 72 | 18 sheets (pp. 32–49: site, GF, typical / FF, terrace plans, elevations) |
| 8 | Schools | 25 | 9 | 9 | 0 (type designs only) | 9 | 9 TNRD type-design sheets |
| 9 | Government offices | 11 | 25 | 4 | 0 (type designs) | 25 | TNRD multi-sheet office package (22 sheets) + VAO / AEE / panchayat sheets |
| 10 | Residential houses | 11 | 2 | 2 | 0 (IAY / green-house type designs) | 2 | 2 type-design sheets |
| 11 | Public / institutional | 36 | 36 | 14 | 0 (type designs) | 36 | TNRD community halls, library, shelters, sheds, sanitation |
| 12 | Structural drawing packages | 2 | 0 | 0 | **0** | 0 | 0 project BBS; generic SP 34 details in the handbook (pp. 227–239) and TNRD office-package beam / plinth / portico sheets only |

Commercial, row 6, also counts TNRD "shop" and "warehouse" type designs; the one real project is the CMDA building.

## Gaps (exact)

- **Apartments: 0 real projects, 0 drawings.** Every apartment lead is a builder site (proprietary), TN RERA (robots
  blocks PDFs), GHTC (robots blocked) or MoHUA (HTTP 403).
- **Medical colleges and universities: 0 working-drawing sets.**
- **Structural packages with a real BBS: 0.**
- **BOQs: 0 in any category.**

## High-impact candidates

The 6 independent real projects (5 hostels, 1 commercial) are the most valuable acquisitions. They were **not run
through the estimator** in this audit, so they remain unexposed and can serve as final-holdout candidates once
permission and two-reviewer annotations exist.
