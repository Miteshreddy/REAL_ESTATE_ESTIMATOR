# 15 — Security and production readiness

## Acquisition safeguards (`tn_corpus/scripts/safe_fetch.py`)

These are reused by every fetcher; there is no second implementation.

| Safeguard | Implemented | Tested |
|---|---|---|
| Host allowlist (catalogue hosts only) | yes | yes |
| SSRF guard: http/https only; DNS must resolve to public IPs; redirects re-checked | yes | yes (private IP, file://, ftp://, localhost) |
| robots.txt with `*` / `$` wildcards; rules before any User-agent apply to all; unreachable robots → deny | yes | yes |
| Per-host delay 3 s; timeout 45 s; retries with back-off | yes | — |
| Response cap 80 MB (streamed); `%PDF-` magic check | yes | magic caught by the corrupt-file path; the cap is untested |
| 401 / 403 / 429 / CAPTCHA → deny, never retried with other headers | yes | observed live (MoHUA 403) |
| Kill switch `tn_corpus/STOP_CRAWL` | yes | yes |
| Decision log (allow / deny, status, bytes) | yes | `logs/acquisition_log.jsonl` |
| Content-addressed output paths `<sha256>.pdf` (no attacker-controlled filenames); sidecar names sanitised | yes | — |
| Quarantine; never training-eligible; human approval file only | yes | yes |
| Separation from production | corpus code never writes the rate DB, model files, splits or estimates | by design + code inspection |

## Data protection

- **Personal data:** a patient-record-bearing document (Kauvery compliance report) was found by inspection.
  - Derived renders, OCR text and labels were deleted, and are blocked from being recreated.
  - The original PDF stays in quarantine (gitignored).
  - **Recommendation:** the user should delete it.
- **Automatic PII screen (added this run):** `build_corpus.pii_suspected` checks for "patient name / id", "age/sex",
  UHID, "referring doctor", "date of birth" and "Aadhaar".
  - A flagged page gets no pseudo-labels, no sheet title and no annotation-queue entry.
  - **Result:** 2 pages flagged (JICA survey tables).
  - A first version also matched bare 12-digit numbers and wrongly flagged 62 drawing pages, because dimension runs look
    like ID numbers. That pattern was removed, and a regression test covers it.
  - This is a keyword screen, not a guarantee: a person must still review documents from hospitals and other
    sensitive sources.
- **Evidence images:** contact sheets showing that document were removed from `reports_v2/evidence/`.
- **Secret scan of the repository:** 0 findings.

## Application (production readiness): NOT production-ready

| Area | Finding |
|---|---|
| Authentication / authorisation | **none.** Every API, including SOR edit / import, schedule activation and the TN PWD refresh, is open to anyone who can reach the port. It binds to 127.0.0.1 by default, which is acceptable for single-user local use only |
| Upload handling | 200 MB cap, type validation (tests exist); files stored under `data/uploads/<pid>` |
| Untrusted file parsing | PyMuPDF, ezdxf and a bundled third-party `dwg2dxf.exe` parse user files in-process with no sandbox. Malicious-file risk is not mitigated |
| Model files | `.joblib` pickles execute code on load. They are local-only; never accept external ones |
| Dependencies | lower-bound pins only, no lock file; `requests` was missing (fixed) |
| Licensing | bundled LibreDWG is GPL-3: review before any redistribution of the app |
| Observability | stdout logs only; no metrics; synchronous processing (large PDFs block the request) |
| Backups | ad-hoc `.bak` copies of `estimate.db` exist; no backup procedure |
| Git hygiene | the git repo root is the user home directory; risk of committing personal files |
