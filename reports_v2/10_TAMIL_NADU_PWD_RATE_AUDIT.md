# 10 — Tamil Nadu PWD rate audit

**Verified directly from `data/estimate.db` on 2026-10-09.**

## Active pricing basis

There is exactly **1 active schedule**:

| | |
|---|---|
| Schedule ID | `tn-pwd-sor-2025-26-amd-2025-08-08` |
| Name | Tamil Nadu PWD SOR 2025-26 Vol I, incl. amendment |
| Effective from | 2025-08-08 |
| Rate items | 3,502 |

- **Version record:** `tn_versions` holds one active row, built from 3 documents: the SOR, the amendment and Standard
  Data, identified by SHA-256.
- **Standard Data:** 514 rate analyses (`tn_sd_items`). Searchable through FTS5 (4,834 rows).
- **Other schedules:** 41 schedules are **inactive** (CPWD DSR 2023, and other states including Telangana, AP,
  Karnataka, Maharashtra, Odisha ×30 districts, Puducherry ×3, WB, Kerala), plus the superseded TN SOR 2025-26 without
  the amendment.
- **Isolation:** `tn_scope.py` refuses non-TN locations and schedules, and pricing resolves only to the active TN
  schedule. The inactive rows are leftovers from the earlier multi-state version. They are kept for audit of legacy
  projects, and the DB currently holds 0 projects. Deleting them is a user decision: it is a one-line SQL change, and I
  did not make it.

## Source documents

| Document | FY | Effective | Verification |
|---|---|---|---|
| Schedule of Rates 2025-26 Vol I | 2025-26 | 2025-07-22 | **cross-verified** (identical SHA-256 on two hosts) |
| SOR 2025-26 tiles amendment | 2025-26 | 2025-08-08 | unverified secondary source (single non-government host) |
| Standard Data Book | — | 2025-03-26 | unverified secondary source |
| SOR 2021-22, SOR 2012-13, "SOR" | old | — | unverified secondary; not active |

No 2026-27 TN SOR was found in the previous session's check, and no new search was made in this run. The rate data was
**not modified** in this run: corpus acquisition is separate from rate activation by design.

## Coverage of take-off items

**G10 rate coverage = 58.8 %** (90 of 153 take-off lines on 3 sample drawings) → **FAIL**. The target is 90 %.

**Unresolved items:**

| Status | Items |
|---|---|
| NEEDS RATE ANALYSIS | excavation, formwork (foundation / slab / beam / column), granite, putty, door shutter, door frame, aluminium window, grills, sink, tank |
| NEEDS RATE | anti-termite, electrical (light / power / DB), basin, CPVC, SWR, modular kitchen |

**Guards** (each has a test): no ₹0 rates; labour-only analyses rejected; no other-state fallback; every line carries
provenance (code, document, page, version).

## Mapping review

- **Engineer reviews:** 0 (`mapping_reviews` table). G09 → NOT VALIDATED (needs 30).
- **Learned mappings:** 0. **Reference BOQs:** 0.
