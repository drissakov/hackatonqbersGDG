# README refresh

Date: 2026-10-19, Asia/Qyzylorda. Task: README-REFRESH.
Branch: `codex/readme-current-state`, based on `origin/main` at `181e012`.
API/contract version: **1.3.0**, unchanged.

## Scope and changes

The user requested improving the project README at the current stage. Updated
the root README against the merged S04 backend and D04 frontend implementation,
rather than the original checkout's S00 snapshot. The original checkout remains
on its existing branch with its two untracked documentation files untouched.

The README now covers product behavior, keyless backend/frontend startup,
configuration, database/corpus preparation, API states, source rights, known
acceptance gates, repository structure, Python/ingestion/frontend checks and
Docker/Render configuration. Historical stage/checkout narratives were replaced
with links to their evidence. No roadmap task is marked complete.

Only `README.md` and this handoff change. No application, contract, dependency,
lockfile, migration, frontend-owned documentation or data file changes. Installed
the existing pinned dependencies into this worktree's ignored `.venv` and
`frontend/node_modules`; built output is ignored. At the implementation
checkpoint, no staging, commit or push had been performed.

## Existing blockers discovered

- `ingestion/cli.py` copies `contracts/codes.json` version `1.3.0` into new
  export manifests. `scripts/embed_pois.py:load_corpus` accepts only `1.1.0` and
  `1.2.0`. The documented fresh-import/index sequence therefore has a compatibility
  gate. This was verified from the actual version and validation code; no live
  import or database/index write was performed. README discloses the failure code
  and the approved matching legacy-pair prerequisite, without suggesting a
  manifest-version bypass. The shared owner must resolve compatibility separately.
- `frontend/README.md` still describes pre-S04 scaffolds and pending integration.
  The root README labels those notes as the earlier D04 checkpoint; changing
  Damir's guide is outside this task.
- Positive live event-card acceptance, integrated S04/D04 acceptance, reviewed
  live 2GIS access, managed Supabase Dashboard settings and HTTPS deployment
  retain their recorded verification gates. No new external success is claimed.

The reviewer also caught an inaccurate draft statement about unknown visit
durations. The final README distinguishes category-based suggested POI durations
from sourced facts. It also distinguishes event provider requirements from the
POI database requirement and mentions ordinary search API charges.

## Commands and actual results

From this worktree's repository root, Python 3.12.10:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q backend/app scripts ingestion
.\.venv\Scripts\python.exe -c "import backend.app.main; print('API import passed, version', backend.app.main.app.version)"
.\.venv\Scripts\python.exe -m pytest backend/tests ingestion/tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts ingestion
.\.venv\Scripts\python.exe -m ruff format --check backend scripts ingestion
.\.venv\Scripts\python.exe scripts/export_contracts.py --check
```

All passed: **912 tests passed, 17 skipped** in 21.13 seconds; pip reported no
broken requirements; API import reported 1.3.0; Ruff reported 75 formatted files;
13 contract artifacts had no drift. `TEST_DATABASE_URL` was removed from the
test process environment, so the 17 database integration tests were skipped.

From `frontend/`, Node.js 24.18.1 and npm 11.16.0:

```powershell
npm.cmd ci --no-audit --no-fund
npm.cmd test
npm.cmd run test:types
npm.cmd run lint
npm.cmd run check:contracts
npm.cmd run format:check
npm.cmd run build
npm.cmd run check:build
```

All passed: **243 tests across 14 files**, test TypeScript, lint, contract
compatibility, formatting, production build (69 modules) and build-isolation
checks (four output files). No package/lockfile edits were made.

Additional documentation/startup checks:

- Inline standard-library validation resolved all **27 local README links**.
- PowerShell's parser accepted all **11 PowerShell code blocks** without
  executing migration/import/index/provider/deployment commands.
- A temporary subprocess smoke cleared provider/database environment settings
  and confirmed no `backend/.env` exists in this worktree. On temporary loopback
  ports 22245/22246, health returned `{"status":"ok"}`, Swagger loaded, FastAPI
  served the built SPA, an unknown API path returned JSON 404, and Vite served
  the development entrypoint. Both temporary servers were terminated afterward.
  The development proxy was checked in source, not exercised against port 8000.
- The initial root README Prettier check reported formatting differences;
  the pinned formatter corrected them. Final README/handoff format and Git
  whitespace checks passed.
- An independent read-only source/diff review checked setup prerequisites,
  source rights, API semantics and historical acceptance evidence.

Final documentation commands from the repository root:

```powershell
.\frontend\node_modules\.bin\prettier.cmd --write README.md docs/handoffs/README-REFRESH.md
.\frontend\node_modules\.bin\prettier.cmd --check README.md docs/handoffs/README-REFRESH.md
git diff --check
git status --short --branch
```

Live database, import, embedding, Responses, web discovery, 2GIS, Docker and
deployment checks: **not_run in this task**. Existing provider results are
historical evidence linked from README, not repeated success. Offline suites do
not prove the fresh-export indexing sequence or final product acceptance.

## Next consumer and study notes

The repository maintainer can review this isolated documentation diff. The
shared backend owner is the next consumer of the manifest compatibility finding;
no teammate notification, delivery or acknowledgement is claimed. Fixing code,
updating frontend-owned documentation and starting S05/D05 require separate scope.

Study: liveness versus readiness, explicit corpus preparation, versioned metadata
validation, unknown versus unavailable, source facts versus visit estimates.

1. **Why can health pass while search is unavailable?** Health initializes no
   providers; POI search needs configured services and a populated/indexed corpus.
2. **Why does the earlier 985-row index not prove a fresh setup works?** That
   checkpoint used an accepted export; new manifests now carry a rejected version.
3. **Why are visit estimates different from unknown source facts?** Activity-based
   suggestions are explicitly labelled product estimates; they do not establish
   a venue's price, opening hours or actual required visit duration.

## Authorized publication

The user subsequently requested sending this README to GitHub, authorizing one
focused documentation commit and a push of `codex/readme-current-state` to
`origin`. Scope remains exactly the root README and this required handoff.
The README task is complete; roadmap feature statuses are unchanged. No merge,
force-push, application change or next-stage work is included.

Publication preflight fetched origin and confirmed `origin/main` remains at
`181e012`, the documentation branch does not yet exist on origin and the index
is empty. Independent read-only review confirmed the two intended documentation
paths, no credential-like values and no remaining actionable factual findings.
README/handoff formatting and Git whitespace checks passed. Full Python/frontend
checks above apply to the same unchanged application source; they were not
repeated for publication. Final content/path checks precede staging and commit.

Publication commands:

```powershell
git add -- README.md docs/handoffs/README-REFRESH.md
git diff --cached --check
git diff --cached --stat
git commit -m "docs(readme): document current MVP and local setup"
git push --set-upstream origin codex/readme-current-state
git status --short --branch
git ls-remote --heads origin refs/heads/codex/readme-current-state
```

The resulting commit and confirmed remote publication are reported in the chat
and can be verified from Git refs; no commit identifier is embedded in its own
handoff. Existing manifest compatibility and live acceptance blockers remain
unchanged.
