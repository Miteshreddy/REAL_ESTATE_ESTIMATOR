# TN Drawing Corpus — Dataset Build Report

Generated 2026-10-09T14:41:33+00:00 by `tn_corpus/scripts/build_corpus.py` (idempotent).

**Status: candidate corpus, NOT a validated training dataset.** 0 projects are approved for training or evaluation, 0 annotations are verified and 0 approved BOQs exist. Everything below is REVIEW_REQUIRED until a person with rights evidence approves it in `tn_corpus/registry/approvals.csv`.

## Exact counts

| Measure | Count |
|---|---|
| Sources in registry | 31 |
| TNRD catalogue PDF links (live page) | 54 |
| tnrd_catalogue_unique_urls | 54 |
| Documents downloaded into quarantine | 68 |
| …of which unique (SHA-256) | 67 |
| Bytes downloaded | 169,249,511 |
| User-supplied files | 3 |
| Earlier local seed files | 50 |
| Unique files overall | 69 |
| Bytes (unique files) | 164,948,520 |
| Identical-file duplicates | 52 |
| Pages extracted (150 dpi + thumbnails) | 2,404 |
| Pages classified as drawings | 745 |
| Near-duplicate page pairs (dHash/text) | 72 |
| Design reuse pairs across catalogue entries/handbook | 2 |
| Projects after grouping | 50 |
| Projects with ≥1 drawing page | 47 |
| Corrupted files | 1 |
| Blocked / failed acquisitions | 8 |
| pii_suspected_pages | 2 |
| Pages with pseudo-labels | 560 |
| Pseudo-labels (text spans) | 3,647 |
| Pages in annotation queue | 724 |
| Verified annotations | 0 |
| Projects APPROVED_FOR_TRAINING | 0 |
| Projects APPROVED_FOR_EVALUATION | 0 |
| Projects REVIEW_REQUIRED | 47 |
| Projects REJECTED (no drawings) | 2 |
| Approved BOQ projects | 0 |

The request mentioned 70 catalogue entries. The live TNRD page lists **54 PDF links** (26 table rows); the 70-entry CSV from the starter ZIP was not on disk, so the catalogue was rebuilt from the live page.

## Page classification (heuristic, not validated)

| Type | Pages |
|---|---|
| unrelated_text | 1208 |
| architectural_floor_plan | 465 |
| boq_specification | 237 |
| blank_unknown | 214 |
| foundation | 80 |
| services_mep | 77 |
| slab_plan | 37 |
| section | 33 |
| elevation | 25 |
| site_plan | 14 |
| reinforcement_bbs | 11 |
| beam_schedule | 3 |

By file role:

- **external_lead**: {'architectural_floor_plan': 402, 'blank_unknown': 122, 'unrelated_text': 709, 'site_plan': 14, 'boq_specification': 113, 'section': 16, 'foundation': 15, 'services_mep': 61, 'elevation': 10, 'slab_plan': 1}
- **tnrd_catalogue_candidate**: {'foundation': 34, 'architectural_floor_plan': 56, 'slab_plan': 26, 'section': 12, 'services_mep': 11, 'beam_schedule': 1, 'elevation': 10, 'blank_unknown': 48, 'unrelated_text': 292, 'boq_specification': 82}
- **original_handbook**: {'unrelated_text': 194, 'architectural_floor_plan': 7, 'boq_specification': 42, 'blank_unknown': 43, 'section': 5, 'foundation': 13, 'slab_plan': 9, 'elevation': 5, 'services_mep': 3, 'reinforcement_bbs': 11, 'beam_schedule': 2}
- **registry_listing**: {'unrelated_text': 13, 'blank_unknown': 1}
- **derived_extract**: {'foundation': 18, 'slab_plan': 1, 'services_mep': 2}

## Building categories (projects)

- hostel: 10
- school: 8
- hospital: 5
- community_hall: 4
- sanitation: 4
- medical_college: 2
- university: 2
- office: 2
- house: 2
- panchayat_office: 2
- commercial: 1
- reference_only: 1
- registry_listing: 1
- anganwadi: 1
- handbook: 1
- warehouse: 1
- shed: 1
- cooperative: 1
- shelter: 1
- shop: 1
- roads_bridges_handbook_out_of_scope: 1
- library: 1
- community: 1
- open_structure: 1

Missing categories (no lawful source found yet): multi-storey apartments, hospitals with drawings, medical colleges, universities, commercial buildings, hostels with drawings. All TNRD material is rural single/two-storey public buildings.

## Sources

| Source | Class | Robots | Status | Discovered | Acquired |
|---|---|---|---|---|---|
| TNRD Type Design Drawings for Buildings | official_portal | allowed (only /rdweb_newsite/ disallowed) | CRAWLED | 54 | 54 |
| TNRD website policies | official_portal | DISALLOWED (/rdweb_newsite/) | BLOCKED_BY_SOURCE_RULES — read manually by a person | 1 | 0 |
| Tamil Nadu eProcurement | official_portal | robots.txt 404 | BLOCKED_BY_SOURCE_RULES — CAPTCHA not bypassed; manual acquisition queue (tender id, BOQ stage) required | 1 | 0 |
| Example tender with arch/structural/MEP drawings + BOQ | official_portal | n/a | MANUAL_ACQUISITION — BOQ would be TENDERED stage, not final | 1 | 0 |
| Tamil Nadu Health System Project | official_portal | no robots.txt (error page) | LEAD — only a completion report is linked; no drawing packages found | 1 | 1 |
| JICA report — ICH & Hospital for Children, Chennai | third_party_public_report | allowed | QUARANTINED | 1 | 7 |
| TN PWD Engineers Association downloads | secondary_host | robots.txt 404 | LEAD ONLY — rate documents (handled by backend/tnpwd_ingestion), not drawings | 1 | 0 |
| TN RERA | official_portal | DISALLOWS /uploads/ and *.pdf | BLOCKED_BY_SOURCE_RULES — only the user-supplied listing printout is inventoried | 1 | 0 |
| TN PWD Buildings policy notes / citizen charters (cms.tn.gov.in) | official_portal | not checked (host not on allowlist) | LEAD — text reports (confirm PWD type designs exist for PHC/HSC/schools/hostels; drawings via Chief Architect, PWD Chepauk — permission request needed) | 6 | 0 |
| TN Gazette — Multistoried & Public Building Rules notices | official_portal | not checked | LEAD — rules text, no drawings | 7 | 0 |
| Architects / builders / structural consultants / QS / contractors in TN | permissioned_private | n/a | EXTERNAL — outreach + data-sharing agreement required | 0 | 0 |
| SIPCOT hostel building plans - Annexure X | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| SIPCOT hostel pre-bid queries with CAD drawings reference | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| Improvement of OPD & diagnosis service - Institute of Child Health, Chennai | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| Data collection survey on urban health care in Tamil Nadu - Chapter I | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| AIIMS Madurai development and health infrastructure report | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| GHTC-India Chennai Light House Project Compendium | v2_catalogue_lead | checked at fetch | BLOCKED_BY_SOURCE_RULES — robots.txt disallows | 1 | 0 |
| GHTC Chennai project brief webinar PDF | v2_catalogue_lead | checked at fetch | BLOCKED_BY_SOURCE_RULES — robots.txt disallows | 1 | 0 |
| IIT Madras hostel project - 2,000 bed G+11 concept/tender document | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| CMDA online PPA approved plan - high-rise/non-high-rise building | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| Kauvery hospital first-floor water supply layout (KMC Chennai) | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| MoHUA Tamil Nadu CSMC project type-design presentation | v2_catalogue_lead | checked at fetch | BLOCKED_BY_SOURCE_RULES — HTTP 403 | 1 | 0 |
| MoHUA Tamil Nadu housing project presentation | v2_catalogue_lead | checked at fetch | BLOCKED_BY_SOURCE_RULES — HTTP 403 | 1 | 0 |
| Tamil Nadu Combined Development and Building Rules 2019 - Gazette PDF | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| CMDA approved-plan PDF for high-rise/non-high-rise Chennai building | v2_catalogue_lead | checked at fetch | DUPLICATE_URL | 1 | 0 |
| Medical college/hospital design report - non-TN reference | v2_catalogue_lead | checked at fetch | REJECTED_NON_TN — state = Other Indian state (TN-only scope) | 1 | 0 |
| Tamil Nadu Combined Development and Building Rules - government gazette copy | v2_catalogue_lead | checked at fetch | BLOCKED_BY_SOURCE_RULES — robots.txt disallows | 1 | 0 |
| Maharaj Hospital site plan - non-TN reference | v2_catalogue_lead | checked at fetch | REJECTED_NON_TN — state = Other region (TN-only scope) | 1 | 0 |
| Kilpauk Medical College Hospital campus, Chennai - JICA urban health report | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| CUTN academic building and hostel construction package - PMC EOI | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |
| CUTN Building Committee minutes - hostel project status | v2_catalogue_lead | checked at fetch | RAW_CANDIDATE | 1 | 1 |

## Usage / permission states

- REVIEW_REQUIRED: 47
- RESTRICTED_PERSONAL_DATA: 1
- REJECTED: 2

## Annotation states

- NOT_STARTED: 724
- PSEUDO_LABEL_pages: 560
- VERIFIED: 0
- IN_REVIEW: 0

## Split / leakage audit

- Approved projects: 0
- Split counts: {'UNASSIGNED': 50}
- Cross-split duplicate pairs: 0 → OK
- 0 projects approved → no train/validation/holdout split created (correct by policy).

## Blocked / failed

- None: None
- None: robots.txt disallows
- None: robots.txt disallows
- None: state = Other region (TN-only scope)
- None: HTTP 403
- None: HTTP 403
- None: state = Other Indian state (TN-only scope)
- None: robots.txt disallows

## Pipeline safeguards

Host allowlist; SSRF guard (public IPs, http/s only, redirects re-checked); robots.txt with wildcards; 3 s per-host delay; 45 s timeout; 80 MB cap; PDF magic-byte check; SHA-256 content addressing; sidecar metadata; idempotent re-runs; kill switch `tn_corpus/STOP_CRAWL`; allow/deny log `logs/fetch_decisions.jsonl`. Crawling is offline from the estimator: nothing here changes rates or model weights.

## External permissions / inputs still needed

1. Written TNRD confirmation that type-design drawings may be used for ML training (queue: `license_review_queue.csv`).
2. Manual eProcurement downloads (CAPTCHA) of building tenders, recorded as TENDERED-stage BOQs.
3. Permission from PWD Chief Architect (Chepauk) for PHC / school / hostel type designs.
4. Data-sharing agreements with TN architects/builders/consultants for apartments, hospitals, commercial buildings.
5. Annotators + two independent reviewers per high-impact label.
6. Approved (FINAL_APPROVED / PAID) BOQs with authority, reference, date and drawing revision.
