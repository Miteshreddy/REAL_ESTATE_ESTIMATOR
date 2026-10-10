# Data split audit (Task 3)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

Seed `tn-v2` · manifest SHA-256 `43d1c1ae4a545be47747808567922ac488351c0d1202aca35c29c56b31f05e74`

| split | projects |
|---|---|
| tn_train | 0 |
| tn_validation | 0 |
| final_holdout | 0 |
| development_benchmark | 41 |
| smoke_test | 4 |
| reference | 1 |
| excluded | 0 |

Policy:
```
Split policy v2 (seed recorded):
- development_benchmark: TN projects already used by evaluation scripts during development (tn_eval sheets). They have been
  looked at while building the system, so they are NOT a credible final holdout and are never trained on.
- smoke_test: third-party copyrighted drawings (e.g. the five-layout complex set) — run blind, no ground truth, never trained on.
- reference: non-Tamil Nadu drawings (Aparna Hyderabad, Uttarakhand, Nalanda) — reference results only.
- excluded: licence review pending / rejected / disallowed — not used at all.
- new training-eligible TN projects: deterministic hash split by PROJECT → tn_train 70 / tn_validation 15 / final_holdout 15.
- final_holdout membership is FROZEN (metadata/final_holdout.frozen.json): members never move, and the holdout is excluded
  from training, threshold tuning and model selection.
```
Leakage check (`python ml/dataset/check_leakage.py`): exit 0 = no project / hash / near-duplicate / source-file leak. A planted
leak makes it exit 1 (test `test_leakage_checker_fails_on_planted_leak`).

**There is no credible final holdout yet (0 projects).** The previously "unseen" TN sheets were used during development and are
now labelled development_benchmark. New authorised TN projects are required to create training / validation / holdout sets.
