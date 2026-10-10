# Dataset audit (Task 1)

_Generated 2026-10-09T16:43:31 from saved artifacts by `ml/evaluation/build_completion_reports.py`._

| Measure | Value |
|---|---|
| projects / sheets | 46 / 114 |
| downloaded documents (unique SHA-256) | 55 |
| discovered web candidates / blocked by robots.txt | 129 / 65 |
| training-eligible projects | 0 |
| evaluation-eligible projects | 41 |
| permission pending (excluded) | 0 |
| rejected / corrupt files | 1 — [{"file": "case02.png", "sha256": "5a5c939fdb21c6ad7f1411244ee5d310b7cba2984e0a36b2c808c2c314111ced", "reason": "image too small to be a drawing 14x16"}] |
| duplicate pairs | 0 |
| licence status (pages) | {"government_publication_review": 109, "restricted": 5} |
| drawing types | {"OTHER": 65, "BEAM PLAN": 5, "ARCHITECTURAL PLAN": 4, "SECTION": 9, "DETAIL": 9, "FOUNDATION PLAN": 13, "SERVICES": 5, "ELEVATION": 2, "REBAR / BBS": 1, "STAIRCASE": 1} |
| scans / vector / CAD sheets | 61 / 53 / 0 |

Sources: TNRD type designs (government publication — **licence review pending → not training-eligible**); TN RERA (robots.txt
disallows `/uploads/` and `*.pdf` — not crawled); tntenders.gov.in (per-document CAPTCHA — not crawled); five-layout complex
set (Scribd / Architizer / SlideShare — third-party copyright → smoke test only; case02 rejected: 14×16 px placeholder);
Aparna (Hyderabad — reference only). Refresh is idempotent (re-run adds 0 pages; tested).
