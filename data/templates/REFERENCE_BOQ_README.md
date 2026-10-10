# Reference BOQ upload

Upload: `POST /api/projects/{id}/reference-boq` (multipart): `file` (CSV or XLSX with the columns of
`reference_boq_template.csv`) plus document fields:

| Field | Required | Meaning |
|---|---|---|
| approval_status | yes | approved · provisional · user-entered · derived · incomplete · rejected |
| approval_authority | for approved | who sanctioned the BOQ (e.g. EE, PWD Buildings Division, Madurai) |
| approval_date | for approved | sanction date |
| source_reference | for approved | sanction / proceeding number or document title |
| currency | yes | INR |
| drawing_revision | recommended | the drawing revision the BOQ was prepared for |
| boq_revision, scope, inclusions, exclusions | optional | scope notes (scope differences are not model error) |
| taxes_included | optional | yes if amounts include GST / cess |

Line columns: description, quantity, unit are required; quantity × rate must equal amount (±1 %).

**Only an `approved` BOQ (with authority, date and reference) counts as validation ground truth.** Estimates produced by this
application, apartment selling / listing prices and non-Tamil Nadu projects are NOT reference BOQs.
The original file is stored unchanged (SHA-256) under `data/reference_boqs/<project>/`.
