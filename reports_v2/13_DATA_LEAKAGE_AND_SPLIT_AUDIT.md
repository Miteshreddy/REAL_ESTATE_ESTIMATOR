# 13 — Data leakage and split audit

## `data/tn_dataset` (split v2)

| Split | Projects |
|---|---|
| tn_train | 0 |
| tn_validation | 0 |
| final_holdout | **0** (frozen list empty) |
| development_benchmark | 41 |
| smoke_test | 4 |
| reference | 1 |

`check_leakage.py` exit 0: there is no project in two splits and no near-duplicate page across splits. The 41
development projects were repeatedly inspected and stay in development.

The **split v1 manifests** (`train/`, `validation/`, `unseen_test/`) are deleted in the working tree but not committed.
They are superseded and not used by any code path (`check_leakage.py` reads them only if present). The user should
commit the deletion.

## `tn_corpus` (`manifests/split_audit.json`)

- **Approved projects:** 0. **Splits created:** none. Every project is UNASSIGNED. This is correct by policy and was not
  faked to fill the report.
- **Cross-split duplicate pairs:** 0, because no splits exist.

**Leakage risks that are already recorded for future splitting:**

| Risk | Handling |
|---|---|
| Exact duplicates | SHA-256: 52 duplicate files collapse to one record |
| Same sheet re-saved rotated | dHash at 4 rotations (4 handbook ↔ extract pairs) |
| Handbook ↔ extract | declared derivation (17 pairs, printed page number checked); the extract is excluded from the annotation queue |
| Standard-design variants | IHHL leach pit ↔ septic tank (text similarity 0.93) merged into one group so they can never straddle splits |
| Same report in two files | JICA urban-health survey 12248522 ↔ 12248530: 50 matching page pairs, one group |
| Same building, many floors / sheets | SIPCOT: each building's site / floor / terrace / elevation sheets form one project (page ranges from title blocks) |
| Handbook reprints of catalogue designs | recorded in `design_reuse.csv` but **not merged**: the handbook is a reference document and must never be in a split together with catalogue sheets. Any future split must treat handbook pages 313–333 as the same design as the matching TNRD catalogue files |
| ZIP v2 crops / PNGs | 68 derivative assets linked to handbook page IDs, so they inherit the handbook's split |
| Crops / augmentation | none exist. The rule: derivatives carry the source `page_id` and inherit its project |
| Exposed projects | the 41 dev projects are already exposed. The 6 new real projects were **only viewed as thumbnails, never run through the estimator or used to tune thresholds**. The classifier prose rule was tuned on pages from the SIPCOT, CUTN, KMCH and Kauvery documents, so those *documents' page-classification* results are exposed for G07 |
