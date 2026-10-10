# 12 — Training and evaluation audit

**Command run:** `python ml/evaluation/run_tn_eval.py scorecard`, which rebuilds the scorecard from stored evaluation
results (exit 0; `logs/scorecard_run.txt`). **FINAL: FAIL.**

## Gates (the threshold is 90 % unless noted; minimum 10 holdout projects)

| Gate | Name | Status |
|---|---|---|
| G01 | Room & area extraction | NOT MEASURED (0 final-holdout projects with verified GT) |
| G02 | Door detection | NOT MEASURED |
| G03 | Window detection | NOT MEASURED |
| G04 | Wall quantities | NOT MEASURED |
| G05 | Structural quantities | NOT MEASURED |
| G06 | Other construction quantities | NOT MEASURED |
| G07 | Drawing classification | NOT MEASURED |
| G08 | Floor & unit identification | NOT MEASURED |
| G09 | PWD item mapping | NOT VALIDATED (0 of 30 engineer reviews) |
| G10 | Rate coverage | **FAIL: 58.8 %** |
| G11–G14 | BOQ quantity / item cost / total cost / completeness | NOT VALIDATED (0 of 5 approved BOQs) |
| G15 | Confidence calibration | NOT MEASURED (NOT CALIBRATED) |

## Evidence rows

These cannot satisfy a gate.

**TN, exposed development data:**
- plinth area within ±10 %: 68.8 % (n = 16);
- sheet view classification: 88.9 % (n = 27);
- smoke site-plan vs floor-plan: 75 % (n = 4).

**Synthetic:** total vs exact geometry 100 % (n = 12 each for DXF, PDF and PNG).

**Generic (CubiCasa5K):** detector door / window F1 at test = 0.869 / 0.881.

**Rate coverage:** take-off lines priced: 58.8 % (n = 153).

**Non-TN references:** the scorecard also prints rows for Hyderabad, Bihar and Uttarakhand drawings, labelled
REFERENCE. Following the TN-only instruction, they are **not used as evidence in this report set**.

## Training eligibility

| Requirement | Have | Need |
|---|---|---|
| Rights-approved TN projects | 0 | ≥ 30 for meaningful fine-tuning (≥ 10 for holdout) |
| Verified annotations (two reviewers) | 0 | per class, e.g. ≥ 100 rooms, doors, windows |
| Unexposed holdout projects | 0 approved; 6 candidates (SIPCOT ×5, CMDA ×1), unexposed | ≥ 10 |

**Can training legitimately begin? No.**

**Training runs in this audit:** none. No model weights were changed.

## Evaluation commands

`20_REPRODUCIBILITY_AND_COMMANDS.md` gives the commands for:
- the full unseen evaluation (`run_tn_eval.py unseen`);
- the scorecard;
- the U-Net evaluation (`ml/training/evaluate_seg.py`);
- detector validation (Ultralytics `val`, outputs in `runs/detect/val*`).
