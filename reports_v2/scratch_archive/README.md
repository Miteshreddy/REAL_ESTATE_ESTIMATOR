# scratch_archive

- `scratch_inventory.csv`: every scratch, historical, experimental or obsolete artefact found in the repository, with its
  original path, size, SHA-256, git state and lifecycle (see `../17_PROJECT_SCRATCH_AND_EXPERIMENTS.md`).
- `*.md`, `*.log`, `*.json`: **copies** of lightweight historical reports, logs and metrics. The file name encodes the
  original path, with `/` replaced by `__`. The originals were not moved or modified.
- Not copied (recorded by path and hash only):
  - model binaries;
  - the SQLite DB (may hold user projects);
  - uploads and previews;
  - corpus PDFs and page renders;
  - the Kauvery compliance report (personal data).
