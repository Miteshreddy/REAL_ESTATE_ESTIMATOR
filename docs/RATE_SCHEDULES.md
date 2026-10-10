# Jurisdiction-aware rate schedules

The system estimates the **cost to construct** the building in the drawings. Location is used for one thing only:
choosing which **official rate schedule** applies. It never changes quantities, and no market or property price is used.

```
Drawing ──► quantities (drawings + parameters only)
Project location ──► jurisdiction ──► applicable rate schedule ──► rate items
quantity × schedule rate = item cost ──► category totals ──► contingency / cess / GST ──► total
```

## Concepts

| Entity | Where | Holds |
|---|---|---|
| Project location | `projects.loc` (JSON) | country, region (state/UT), district, city, municipality, executing authority level |
| Rate schedule | `rate_schedules` | authority, department, scope (country / region / district / city — empty = whole parent level), authority level (central / state / local / department), type, item numbering (`code_system`), year, financial year, revision, effective from/to, currency, source, source reference, status (draft / active / inactive), imported on/by |
| Rate item | `rate_items` (PK schedule_id + code) | code, description, unit, rate, category, analysis, source |
| Project's schedule | `projects.rate_schedule_id`, `projects.rate_selection` | the schedule applied, how it was chosen (auto / manual / legacy / none), reason, history of changes |

## How the applicable schedule is chosen (`backend/rates.py: resolve`)

1. Only **active** schedules of the project's country whose scope contains the location and whose effective dates contain today.
2. If the project names its executing authority level, only schedules of that level.
3. Of several revisions of the same schedule, the latest.
4. The most specific scope wins (city > district > region > country). A **country-wide** schedule (e.g. CPWD DSR) is applied
   automatically only when the executing authority is given (central works). Otherwise it is offered and the user must choose.
5. Several equally specific schedules → the user chooses. **No match → "No official rate schedule is configured for this
   jurisdiction."** Items stay unpriced. The system never borrows rates from another jurisdiction.

Changing the location re-runs this. A change of schedule re-prices every item (quantities unchanged) and is recorded. A PWD item
or rate the user picked under one schedule is not carried into another. A confirmed estimate must be reopened first.

## Adding a new official schedule (e.g. a State PWD SOR)

1. **Rate schedules → New rate schedule.** Enter the metadata exactly as printed on the official document: authority,
   state (leave empty for a country-wide schedule), authority level, type, financial year, revision, effective dates, source
   reference (G.O. / document title / URL). If the schedule uses CPWD DSR item numbering, set *Item numbering* to `CPWD-DSR`
   so the expert mapping table can be used. Otherwise matching is by description (TF-IDF) only. It is created as a **draft**.
2. **Import items** from Excel or CSV with columns `code, description, unit, rate, category` (optional `analysis`).
   The whole file is rejected, and nothing is written, if any row has:
   - a missing code, description, unit or rate;
   - a non-numeric or non-positive rate;
   - a duplicate code.

   The rejection lists every problem.
3. **Activate.** Activation is refused if:
   - the schedule has no items;
   - its metadata is incomplete;
   - another active schedule of the same authority, type and jurisdiction overlaps it in time.

   To replace a schedule with a new revision, set `effective_to` on the old one or deactivate it.

The same steps are available through the API:
`POST /api/rate-schedules`, `POST /api/rate-schedules/{id}/import`, `PATCH /api/rate-schedules/{id}` `{"status": "active"}`.

**Only official data should be imported. The system does not create or adjust rates.** The user-set *cost index* and *finish*
settings on the estimate screen multiply schedule rates. They default to 1 / standard, and any non-default value is printed in
the report as a user adjustment.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/locations` | Countries, states/UTs, district/city suggestions, authority levels (all from the backend) |
| GET | `/api/rate-schedules?country&region&authority&authority_level&year&status` | List / filter schedules |
| GET | `/api/rate-schedules/applicable?country&region&district&city&authority_level&on` | Resolve: `selected` / `ambiguous` / `unavailable` with candidates and reason |
| GET | `/api/rate-schedules/{id}` | Metadata + item count |
| POST | `/api/rate-schedules` | Create a draft schedule (duplicate identity rejected) |
| PATCH | `/api/rate-schedules/{id}` | Edit metadata (identity locked while active), activate / deactivate (validated) |
| POST | `/api/rate-schedules/{id}/import` | Validated import (all-or-nothing) |
| PATCH | `/api/projects/{id}/location` | Change project location → re-resolve, re-price, `notice` explains the effect |
| PATCH | `/api/projects/{id}/rate-schedule` | `{"schedule_id", "reason"}` manual choice (a reason is required outside the jurisdiction) or `{"auto": true}` |
| `/api/sor…` | existing rate-library routes | Now take `schedule_id` (default CPWD DSR 2023) |

## Migration of existing data

On the first start after the upgrade:
- the database is copied to `estimate.db.pre-schedules-<timestamp>.bak`;
- the old `sor` table (CPWD DSR 2023 plus any edits and rate analyses) is moved into schedule `in-cpwd-dsr-2023-civil` and kept as `sor_legacy_backup`;
- every existing project is marked `legacy`, keeps CPWD DSR 2023 and keeps its overrides, so totals are unchanged.

## Tests

`python -m pytest backend/tests` (pytest and httpx, see `requirements-dev.txt`). The tests run on a temporary database.
The "state" schedules they create are labelled TEST FIXTURE and exist only inside that temporary database.
