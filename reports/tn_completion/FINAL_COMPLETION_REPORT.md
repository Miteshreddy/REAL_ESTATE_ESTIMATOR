# Final completion report

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

## A. Executive summary
Final scorecard: **FAIL** (target ≥90 % on unseen TN projects). Implementation of all 18 work packages is in place and
tested; none is VERIFIED_COMPLETE because accuracy validation needs external inputs that do not exist yet: verified TN annotations,
new authorised TN projects for a holdout, engineer-reviewed mappings and approved TN BOQs. The product is **not complete** in the
sense of a validated 90 % estimator.

## B. Tasks
| id | task | status | dependency |
|---|---|---|---|
| 1 | Lawful TN drawing dataset | TESTED | authorised / licensed new TN drawing sets; licence confirmation for TNRD |
| 2 | Verified ground-truth annotations | BLOCKED_EXTERNAL_INPUT | qualified annotators + two reviewers |
| 3 | Leakage-safe splits | TESTED | new projects to populate train / validation / holdout |
| 4 | Train & validate models | BLOCKED_EXTERNAL_INPUT | verified TN annotations |
| 5 | Room / unit / area extraction | TESTED | verified TN area ground truth for accuracy |
| 6 | Door / window extraction | TESTED | verified TN opening annotations for accuracy |
| 7 | Wall quantities | TESTED | verified wall quantities for accuracy |
| 8 | Structural quantities | TESTED | TN structural sets with BBS + engineer-verified quantities |
| 9 | Complex-building suite | TESTED | licensed complex TN drawing sets with ground truth |
| 10 | TN PWD rate coverage | TESTED | TN Standard Data for formwork / doors / windows / electrical; official copies |
| 11 | Mapping validation with engineers | BLOCKED_EXTERNAL_INPUT | TN PWD engineer reviews (≥30) |
| 12 | Approved BOQ workflow | TESTED | approved TN BOQs |
| 13 | Quantity vs BOQ comparison | TESTED | approved TN BOQs |
| 14 | Item / total cost accuracy | BLOCKED_EXTERNAL_INPUT | ≥5 approved TN BOQ projects |
| 15 | Confidence & uncertainty | TESTED | labelled validation outcomes for calibration |
| 16 | Unseen TN evaluation | BLOCKED_EXTERNAL_INPUT | final-holdout TN projects with verified ground truth |
| 17 | 90 % target & scorecard | TESTED | the evidence above |
| 18 | Testing & release audit | TESTED | — |

## C. Dataset
Projects 46 · sheets 114 · training-eligible projects 0 ·
verified annotations 0 · splits {"tn_train": 0, "tn_validation": 0, "final_holdout": 0, "development_benchmark": 41, "smoke_test": 4, "reference": 1, "excluded": 0} · leakage: see DATA_SPLIT_AUDIT.md.

## D-H. See MODEL_EVALUATION.md, QUANTITY_EVALUATION.md, PWD_RATE_AUDIT.md, COST_ACCURACY.md, TEST_RESULTS.md.

## I. Scorecard
| id | gate | critical | value | status | reason |
|---|---|---|---|---|---|
| G01 | Room & area extraction | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G02 | Door detection | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G03 | Window detection | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G04 | Wall quantities | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G05 | Structural quantities | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 5 required. Development-benchmark / reference results are shown as evidence only. |
| G06 | Other construction quantities | True | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 5 required. Development-benchmark / reference results are shown as evidence only. |
| G07 | Drawing classification | False | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G08 | Floor & unit identification | False | — | NOT MEASURED | 0 final-holdout TN project(s) with verified ground truth; 10 required. Development-benchmark / reference results are shown as evidence only. |
| G09 | PWD item mapping | True | — | NOT VALIDATED | 0 engineer-approved mapping(s); 30 required |
| G10 | Rate coverage | True | 58.8 | FAIL | coverage of applicable take-off lines on the sample drawings (needs no ground truth) |
| G11 | Quantity agreement vs approved BOQs | True | — | NOT VALIDATED | 0 approved Tamil Nadu BOQ project(s); 5 required |
| G12 | Item-cost accuracy | True | — | NOT VALIDATED | 0 approved Tamil Nadu BOQ project(s); 5 required |
| G13 | Total project-cost accuracy | True | — | NOT VALIDATED | 0 approved Tamil Nadu BOQ project(s); 5 required |
| G14 | Estimate completeness | True | — | NOT VALIDATED | 0 approved Tamil Nadu BOQ project(s); 5 required |
| G15 | Confidence calibration | False | — | NOT MEASURED | NOT CALIBRATED — no labelled TN validation predictions |

## J. External inputs required
1. New Tamil Nadu drawing sets with written permission for model training (≥10 projects for a holdout, more for training).
2. Licence confirmation for the TNRD type-design drawings (training use).
3. Qualified annotators + two independent reviewers for doors, windows, rooms, walls, dimensions (use `#/annotate`).
4. ≥5 approved TN BOQs with authority, date, reference and the matching drawing revision (template in data/templates/).
5. ≥30 engineer-reviewed PWD mappings (`/api/projects/{id}/mapping-review`).
6. TN Standard Data / official rates for formwork, doors, windows, electrical, plumbing; official copies of the amendment and
   Standard Data Book (currently single-host secondary sources).
7. Structural drawing sets with bar bending schedules.

## K. Next actions
1. Obtain inputs 1-4; 2. annotate + review; 3. fine-tune (stage2) and re-run `run_tn_eval.py unseen`; 4. close rate gaps (input 6).
