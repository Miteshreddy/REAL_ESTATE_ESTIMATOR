# Annotation coverage (Task 2)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

States: {"PSEUDO-LABEL": 110, "UNANNOTATED": 4}

- VERIFIED records (any): **0** · VERIFIED + training-eligible: **0**
- Pseudo labels are model output (U-Net) and are **not** ground truth.
- Workflow: `#/annotate` page and `/api/annotations/*` — draft (named annotator) → two independent reviewer approvals → VERIFIED;
  any rejection / disagreement keeps the record out; edits re-open review with correction history. Validation: boxes, polygons,
  units, duplicate ids, conflicting dimensions, project / drawing-revision mismatch. Exports: COCO (`/api/annotations-export/coco`),
  YOLO (`python -m tn_data_ingestion.refresh export`), structured JSON for dimensions (schema `tn-annot-1`).

**Status: BLOCKED_EXTERNAL_INPUT — 0 verified annotations exist; qualified annotators / reviewers are required.**
