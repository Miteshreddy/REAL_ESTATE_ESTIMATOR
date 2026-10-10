# 19 — Source catalogue report

## Catalogues examined

| Catalogue | Rows | Use in this run |
|---|---|---|
| Live TNRD page `buildings_design.html` | 54 PDF links (26 table rows, 3 columns) | all 54 acquired (run 1, re-verified by SHA-256) |
| ZIP `04_SOURCE_CATALOGS/expanded_source_catalog.csv` | 110 rows: 105 TN, 5 non-TN | 54 TNRD rows = the same URLs as above; 20 non-TNRD direct-PDF rows attempted; 36 manual / permission rows → manual queue |
| ZIP `tnrd_54_direct_pdf_catalog.csv` | 54 | identical URL set to the live catalogue |
| ZIP `target_category_acquisition_queue.csv` | (39 KB) | inspected; its leads are a subset of the expanded catalogue |
| `tn_corpus/registry/source_registry.csv` | 31 | 11 curated sources + 20 v2 leads with real outcomes |
| Web discovery in this run (searches) | TNUHDB / TNHB, TN hospital tenders, Anna University tenders | **no new directly downloadable TN drawing set found**. Anna University issues tender drawings only on payment at the Registrar; tender aggregators list BOQs without drawings. Added to the manual queue |

## Outcomes of the 20 v2 direct-PDF leads

| Source ID | Category (catalogue) | Outcome | What it actually is |
|---|---|---|---|
| SIP_COT_HOSTELS_RFP | hostel | acquired, 9.2 MB | O&M RFP + Annexure X: **5 hostel buildings' plans** |
| SIP_COT_HOSTELS_QUERY | hostel | acquired, 18 KB | pre-bid queries (no drawings) |
| JICA_CHILDRENS_HOSPITAL_CHENNAI | hospital | acquired (= run-1 lead) | survey with OPD concept plans |
| JICA_TN_URBAN_HEALTH_CH1 | hospital | acquired, 7.8 MB | survey; merged with the KMCH file (same report family) |
| AIIMS_MADURAI_JICA_REPORT | hospital / medical college | acquired, 17.5 MB | survey; campus master plans |
| GHTC_CHENNAI_COMPENDIUM / PROJECT_BRIEF / TNCDBR_2019_ALT | apartment / rules | **blocked: robots.txt** | — |
| IITM_2000_BED_HOSTEL_TENDER_DOC | hostel | acquired: **corrupt** (721 B) | — |
| TN_PWD_APPROVED_HIGHRISE_PLAN | "apartment" | acquired, 1.06 MB | **commercial** S+3 office, CMDA approved |
| CHENNAI_APARTMENT_PLAN_CMDA | "apartment" | duplicate URL | — |
| KAUVERY_HOSPITAL_WATER_SUPPLY_LAYOUT | hospital MEP | acquired, 19.5 MB | EC compliance report with **personal data** → RESTRICTED |
| MOHUA_TN_HOUSING_TYPE_DESIGNS / PRESENTATION_2 | apartment | **blocked: HTTP 403** | — |
| TN_BUILDING_RULES | rules | acquired, 2.8 MB | TNCDBR 2019 gazette |
| NAGALAND_MEDICAL_COLLEGE_JICA, JICA_MAHARAJ_HOSPITAL_SITEPLAN | non-TN | downloaded, then **rejected and moved out** on the TN-only instruction | — |
| JICA_KILPAUK_MEDICAL_COLLEGE_HOSPITAL | hospital / medical college | acquired, 6.4 MB | survey (few drawings) |
| CUTN_PMC_EOI_ACADEMIC_HOSTELS, CUTN_BUILDING_COMMITTEE_HOSTELS | university | acquired | context documents, no working drawings |

**Manual-acquisition queue:** `manifests/manual_acquisition_queue.csv` (41 rows). It records the blocker and the
required human action for each:
- tntenders tender IDs;
- RGNIYD;
- CUTN EPC;
- the CMDA archive;
- builder portfolios (permission);
- RERA;
- GHTC / MoHUA (blocked);
- Anna University;
- the PWD Chief Architect;
- TNUHDB / TNHB.
