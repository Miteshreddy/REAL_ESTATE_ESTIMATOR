# TN drawing corpus (candidate collection — not a training set)

```
python tn_corpus/scripts/tnrd_discover.py --catalog-only          # resolve live TNRD catalogue
python tn_corpus/scripts/tnrd_discover.py --download-candidates   # quarantine PDFs (idempotent)
python tn_corpus/scripts/fetch_leads.py                           # other robots-permitted leads
python tn_corpus/scripts/build_corpus.py                          # inventory, classify, dedup, group, queues, reports
```

* `raw_candidates/` — original bytes, `<sha256>.pdf` + JSON sidecar (URL, final URL, HTTP status, MIME, bytes, SHA-256,
  time, policy URL, permission evidence, state). Everything is `RAW_CANDIDATE` / `REVIEW_REQUIRED`.
* `registry/` — `source_registry.csv`, `file_inventory.csv`, `project_manifest.csv`, `page_inventory.csv`,
  `license_review_queue.csv`, `annotation_queue.csv`, `duplicates.csv`, `design_reuse.csv`, `split_audit.json`.
* `registry/approvals.csv` — the ONLY way to approve usage: a person adds `project_id, usage_state
  (APPROVED_FOR_TRAINING | APPROVED_FOR_EVALUATION | REJECTED), approved_by, evidence_ref, date`. Rows without approver and
  evidence are ignored. Splits are created only for approved projects.
* `pages/` 150 dpi renders (`px = pt × 150/72`, recorded per page), `thumbs/` 400 px, `pseudo_labels/` text-span
  pseudo-labels in PDF points (never ground truth), `templates/` approved-BOQ schema (stage-separated quantities) and
  annotation template.
* Kill switch: create `tn_corpus/STOP_CRAWL`. Decisions: `logs/fetch_decisions.jsonl`.
* The estimator never reads this folder: rates and models are unaffected until data is approved and trained offline.
