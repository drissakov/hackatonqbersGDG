# Local OpenAI and database connection handoff

## Scope and state

Configured the existing local application for real place search on 2026-10-20.
The working checkout is `codex/fix-poi-constraints`, HEAD `9061865`, at
`C:/Users/Ilytsm/.codex/worktrees/poi-constraint-fixes/hackatonqbersGDG`.
Earlier uncommitted changes remain intact. No commit, push, staging, migration,
corpus write or reindex was performed. No roadmap stage was marked complete.

## Local configuration and process

- Created this checkout's ignored `backend/.env` using existing same-project
  credentials from the `current-project-run` worktree. Credential values and
  connection URLs are excluded from this handoff and the verification reports.
- Configured OpenAI Responses with `gpt-6-luna` and embeddings with
  `text-embedding-3-large`, explicitly using 1536 dimensions.
- Connected the existing database with its existing TLS configuration.
- Kept `APP_ENV=production`, fixtures disabled and optional 2GIS disabled.
- Restarted only this task's server on `http://127.0.0.1:8001/`. It serves the
  existing frontend production build and same-origin `/api` endpoints.
  The pre-existing processes on ports 8000 and 5174 were left running.
- Python runtime:
  `C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.
  Launch command from the working checkout:
  `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --no-access-log`.
  Use the runtime path above instead of a different system Python.

No application code, dependencies, API contracts or database schema changed in
this task. Current API contract version remains 1.3.0.

## Checks and observed results

- `python scripts/preflight.py --check all --output <local-report.json>`:
  all three checks passed. The database probe used a read-only transaction and
  verified PostGIS and pgvector. Real Responses and 1536-dimensional embedding
  requests passed with the configured models.
- `GET /api/health`: HTTP 200, `status=ok`.
- `GET /api/coverage`: HTTP 200; 985 production POIs, 985 located POIs,
  985 embedded POIs, zero test POIs; OSM source. City coverage remains unknown.
- Real Russian museum search through `POST /api/recommendations`: HTTP 200 in
  14.70 seconds, three museum alternatives, `status=partial`, warning
  `data_unknown`, no `provider_unavailable`. The response passed current
  Pydantic validation and had `Cache-Control: no-store`. Every alternative
  had provenance and a non-test OSM source allowing storage and indexing.
  Request ID: `cc43248d-2c87-4257-bb72-c278fe78bec3`.
- Returned database records: `osm:way:1460700597`, `osm:way:51431624` and
  `osm:way:240376692`. These are existing city records, not fixtures or the
  separate playground source supplement.
- A separate real museum search submitted from the existing browser tab
  displayed the same three source-backed alternatives and their missing facts.
  A later screenshot was captured from an isolated verification tab, which
  returned two museum alternatives, without replacing subsequent user input
  in the original tab.
- `python -m pytest backend/tests/test_settings.py backend/tests/test_preflight.py -q`:
  **11 passed** in 1.96 seconds.
- `npm run check:build` in `frontend/`: passed for four production build files;
  no fixture payloads, server credential names, development backend URLs,
  environment files or source maps were found.
- Local settings validation: OpenAI and database configured, fixtures and 2GIS
  disabled. `backend/.env` is ignored by Git, absent from tracked files, and
  excluded by the existing recursive Docker environment-file rules.
- Scanned ten local build, report, log and handoff files in memory: none
  contained either configured secret value. `git diff --check` passed and the
  staging area remained empty. The original checkout still has only its
  pre-existing untracked demo video.

Full application suites were not repeated: this task only changed local
configuration and added this handoff. Previous code verification remains in
the individual implementation handoffs.

## Evidence and limits

Sanitized `preflight.json`, `search-report.json`, `real-search-ui.png` and the
server process manifest are kept outside Git under
`C:/Users/Ilytsm/AppData/Local/Temp/qadam-local-6da558f6660f4948963ace7c2bf7eaba/`.
Reports exclude raw request payloads, coordinates, credentials and provider
exception bodies. The original browser tab remains available for the user.

Successful provider access and retrieval do not establish a complete fit.
The museum check had no starting point or visit date; travel duration and
source opening hours also remained unknown. 2GIS routing is disabled, prices
and other missing corpus facts stay unknown, and the existing charging-data
gap remains. No real event discovery or live walking route was checked here.

The next consumer can use the local application immediately. Further product
or data changes require a separate request; none were started by this task.
