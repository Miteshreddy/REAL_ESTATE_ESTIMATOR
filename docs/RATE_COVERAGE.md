# Official rate-schedule coverage (status 2026-10-08)

Only official documents are loaded. Every loaded item was machine-checked against its source PDF: the code (or item name)
and the printed rate are found on the source page. Provenance and SHA-256 of each source file are recorded in
`data/sor/states/*.meta.json`. Each edition is the latest one the authority has published. No year is relabelled.

## Loaded (active in the app)

| Jurisdiction | Schedule | Edition / effective | Granularity | Items | Verified |
|---|---|---|---|---|---|
| India (central works) | CPWD Delhi Schedule of Rates (Civil) | DSR 2023 — still the current civil edition | country | 2,396 | source CSV |
| Telangana | Common SOR, Part III Building Works | **2026-27**, w.e.f. 01-06-2026 | state | 1,450 | 100 % |
| Andhra Pradesh | Buildings SoR (Civil, WS&S, Electrical) | 2025-26 (approved 16-04-2025) | state | 1,975 | 100 % |
| Tamil Nadu | SOR Vol I (PWD, Highways, WRD) | 2025-26, w.e.f. 22-07-2025 | state | 3,502 | 100 % |
| Karnataka | KPWD SR Vol 2 Buildings | 2023-24 (latest full volume) | state | 1,354 | 100 % |
| Maharashtra | PWD State SSR | 2022-23 (latest published) | state | 2,190 | 100 % |
| Odisha | Works Dept SOR | 2022 (OM 20-04-2023) | **30 districts** | ≈1,231 each (36,935) | 100 % |
| Puducherry | PSR | 2024-25, w.e.f. 14-08-2024 | **3 regions** (Puducherry, Karaikal, Mahé) | 3,339–3,428 each | 100 % |
| West Bengal | WB PWD current schedule = CPWD DSR 2023 (Civil), officially adopted | DSR 2023 | state (adoption) | 2,396 | — (adopted) |

## Downloaded but not loaded (and why)

| Jurisdiction | What exists | Blocker |
|---|---|---|
| Uttar Pradesh | 33 circle-wise SORs 2025-26 + circle revisions (Oct–Nov 2025), uppwd.gov.in | All ≈1,800 pages are **scanned images** (no text). Loading needs OCR of Hindi tables plus human checking of every rate. |
| Haryana | HSR 2021 + gazette amendments (0.893 GST factor, A&C slips) | The official PDF's text layer is broken OCR. A clean copy is needed. |
| Karnataka | 2026-27 Q1/Q2 Issue Rates (material price revisions) | Scanned images; not applied to the 2023-24 item rates. |
| Uttarakhand | Block-wise SOR 2024-25 (+ 2025-26 hill-district revisions), mis.pwduk.in | Roads & bridges (MoRTH/MoRD) only, not building works. |

## Not yet obtained

Kerala (PWD SOR 2022 rev. 2023 / PRICE portal), Gujarat (R&B district-wise via works monitoring system), Rajasthan (BSR —
online database, district-wise), Madhya Pradesh (PWD Building SOR 2024 — no official download found), Punjab (CSR 2020 +
amendments), Himachal Pradesh (SOR 2020), Jammu & Kashmir / Ladakh (SOR 2020, altitude tiers), Bihar, Jharkhand,
Chhattisgarh (live portal), Assam, Goa, Delhi, the North-Eastern states, and the other UTs.

## Notes

- **No 2026 editions exist for most states.** Most states revise every 2–5 years. A newer year cannot be produced without the authority publishing it.
- **City-level rates do not exist as separate schedules.** Telangana's SOR, for example, sets location allowances on the labour component instead: Greater Hyderabad +40%, other corporations +25%, district headquarters +20%. These are recorded in the schedule notes but not applied automatically, because the SOR does not print the labour share per item.
- **Several South Indian SORs (Telangana, Andhra Pradesh, Tamil Nadu, Puducherry) are mainly basic rates.** They cover materials, labour and specialised items. Finished-work rates such as brickwork and RCC are derived through each state's Standard Data / Analysis of Rates, which is a separate official document not yet loaded. Matching therefore marks those items for review.
