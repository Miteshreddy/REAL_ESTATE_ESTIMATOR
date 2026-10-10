# 11 — BOQ and cost validation

## Implemented

| Component | Code | Tests |
|---|---|---|
| BOQ validation | `boq.validate`: required approval metadata; units; duplicate key = description + unit | `test_boq.py` (5) |
| Estimate ↔ BOQ matching | item key + description; ambiguity reported, not resolved arbitrarily | yes |
| Item-wise, total and completeness metrics | `boq` metrics endpoint | yes |
| Templates | `data/templates/reference_boq_template.csv`; corpus schema `tn_corpus/templates/approved_boq.schema.json` | — |

**Stage separation:** quantities are kept separate as tendered / awarded / revised / final / paid. A tender file is
never FINAL_APPROVED, and selling price is forbidden as a cost basis.

## Data available

**Approved TN BOQs: 0.** Candidate BOQs in the corpus: **0**.
- The SIPCOT RFP is an O&M (operation) tender with a rental price bid. It is not a construction BOQ.
- The CMDA plan carries FSI and area statements, not costs.

## Gates

| Gate | Status | Reason |
|---|---|---|
| G11 quantity agreement | NOT VALIDATED | 0 approved BOQs (5 required) |
| G12 item-cost accuracy | NOT VALIDATED | 0 approved BOQs |
| G13 total project-cost accuracy | NOT VALIDATED | 0 approved BOQs |
| G14 completeness | NOT VALIDATED | 0 approved BOQs |

**Total construction-cost accuracy is NOT VALIDATED.** No claim of 90 % or 95 % accuracy can be made.

## Taxes and allowances

`takeoff.price` (backend/takeoff.py, around line 595) computes:

- subtotal × `cost_index` × finish uplift, where the uplift is economy 0.92 / standard 1.0 / premium 1.28;
- contingency % and cess % on the subtotal;
- GST % on (subtotal + contingency).

**Finding:** the finish uplift and cost index are **not part of the TN PWD schedule**. Any value other than 1.0 departs
from SOR rates. For PWD-conformant estimates, keep `standard` and `cost_index = 1`, and disclose any other value as a
user assumption. No validated reference exists for any of these allowances.

**To proceed:** obtain at least 5 FINAL_APPROVED or PAID BOQs, each with the same drawing revision. The best route is to
ask SIPCOT or CMDA-project owners for the 6 real projects' construction BOQs (see the permission template).
