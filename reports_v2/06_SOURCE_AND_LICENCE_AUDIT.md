# 06 — Source and licence audit

**Evidence:**
- `manifests/document_source_registry.csv`: 31 rows;
- `manifests/licence_review_queue.csv`;
- `logs/acquisition_log.jsonl`: every allow / deny decision with timestamp, HTTP status and bytes;
- `tn_corpus/raw_candidates/*.json`: one sidecar per document.

## Permission states used

| State | Meaning | Count (projects) |
|---|---|---|
| UNKNOWN / REVIEW_REQUIRED | public access only; ML-training and evaluation rights not established | **47** |
| PUBLIC_ACCESS_ONLY | (all 47 above are also public access only; the rows say "none - public URL only" or the TNRD policy text) | — |
| PERMISSION_REQUESTED | none sent (template prepared: `evidence/PERMISSION_REQUEST_TEMPLATE.md`) | 0 |
| PERMISSION_CONFIRMED / TRAINING_ALLOWED / EVALUATION_ALLOWED | — | **0** |
| ATTRIBUTION_REQUIRED | TNRD material (policy: attributed reproduction allowed, third-party excluded; ML use not addressed) | 32 TNRD projects |
| RESTRICTED | personal data (Kauvery compliance report) | 1 |
| REJECTED | corrupt (IITM), no drawings (RERA listing) | 2 |
| REJECTED_NON_TN | Nagaland medical college, Maharaj hospital (JICA) | 2 documents, outside the corpus |

A successful download never changes these states. Only a person can approve a project, by adding a row with an approver
and evidence reference to `tn_corpus/registry/approvals.csv`. Rows without both are ignored, and the code never writes
that file.

## Per-source findings

| Source | Robots / access | Result | Licence evidence |
|---|---|---|---|
| TNRD buildings_design (54 PDFs) | allowed (only `/rdweb_newsite/` disallowed) | 54 acquired | TNRD website policy: attributed reproduction, third-party excluded. The policy page itself sits under the disallowed path and was **not fetched**; its wording was taken from the user's pack |
| SIPCOT (2 PDFs) | allowed | 2 acquired | none found; the hostel plans carry an architect's title block (third-party copyright likely) → permission from SIPCOT **and** the architect |
| CMDA approved plan | allowed | 1 acquired | public approval record. The drawing is the applicant's / architect's work → permission needed |
| JICA Open Report (ICH, AIIMS Madurai, urban health ×2) | allowed (`/Weblog/` only disallowed) | 4 acquired (1 duplicate of run-1 lead) | JICA report terms not reviewed |
| CUTN (2 PDFs) | allowed | 2 acquired (context only) | none |
| TN urbantree (TNCDBR 2019 rules) | allowed | 1 acquired | public gazette |
| Kauvery Hospital site | allowed | 1 acquired → **RESTRICTED_PERSONAL_DATA** | contains patient lab and radiology reports with names, invoices and insurance documents. Not rendered or OCR'd; the original stays in quarantine only. **Recommend the user delete it**: I did not delete it (deletion is the user's call) |
| IIT Madras tenders | allowed | 721-byte truncated PDF → REJECTED (corrupt) | — |
| GHTC-India (3 PDFs) | **robots.txt disallows** | BLOCKED, logged | manual request |
| MoHUA (2 PDFs) | **HTTP 403** | BLOCKED, logged; not retried with other headers | manual request |
| tntenders.gov.in | per-download CAPTCHA | not automated | manual queue |
| TN RERA | robots disallows `/uploads/` and `*.pdf` | not crawled | builder drawings are proprietary |
| Builder / architect sites (SSPDL, KG, Prestige, Godrej, TVS, Seyon), Scribd, Slideshare, LinkedIn, Architizer | not attempted | PROPRIETARY_REVIEW_REQUIRED | written permission required |
| Non-TN catalogue rows (Nalanda, AP school portal, RMLH, Nagaland, Maharaj) | — | not used (TN-only scope) | — |

## Discrepancies found in the supplied v2 catalogue

The catalogue was compiled without network access, as its own notes say.

| Catalogue claim | What the file actually is |
|---|---|
| `TN_PWD_APPROVED_HIGHRISE_PLAN` / `CHENNAI_APARTMENT_PLAN_CMDA`: "multi-storey apartment / high-rise" (the same URL listed twice) | **stilt + 3-floor commercial office building**, 17.97 m, non-high-rise |
| `KAUVERY_HOSPITAL_WATER_SUPPLY_LAYOUT`: "first-floor water supply layout" | a 585-page environmental-clearance compliance report; sampled pages are invoices, insurance documents, TNPCB consent orders and patient reports |
| `IITM_2000_BED_HOSTEL_TENDER_DOC` | 721-byte truncated file |
| `JICA_CHILDRENS_HOSPITAL_CHENNAI` | identical bytes to the run-1 lead `jica_ich_chennai` |
| AIIMS Madurai report | campus master plans; one figure in the report is the **AIIMS Raipur** master plan (non-TN), p58 |
