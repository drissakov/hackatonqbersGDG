# Qadam Astana

Choose a place or event in Astana that fits your time, location and per-person
budget. Qadam Astana offers up to three independent destinations with sources,
reasons, available visit and travel estimates, and an action to check details.

The development MVP includes a Kazakh, Russian and English interface, database
POI search, source-grounded explanations, separate live event discovery and
optional walking routes. POI search needs configured providers and a populated
database; live event discovery needs its provider but can run without the POI
database. Starting the application alone does not make search available.

## What is available

- **Places:** natural-language requests plus explicit time, budget, indoor and
  location controls; lexical/vector retrieval from a permitted POI corpus.
- **Events:** transient web discovery with source links, separate listings and
  eligible sessions. A discovered listing is not a confirmed event recommendation.
- **Sources and uncertainty:** provenance, missing facts and conditional fit stay
  visible. Unknown prices, hours and routes stay unknown. Suggested POI visit
  durations are labelled estimates based on activity type, separate from source facts.
- **Location and routes:** manual coordinates, opt-in browser geolocation and an
  optional 2GIS map. Walking outbound and return legs are evaluated separately.
- **Languages:** local kk/ru/en dictionaries; switching language re-renders
  existing results without repeating provider requests.

There are no accounts, location/query history, ticket purchases or multi-stop
itineraries. Only the interface language preference is stored in the browser.

## Local start: Windows PowerShell

Use **Python 3.12** (the CI/Docker version) and **Node.js 24.15 or newer on the
24.x line**. Keep the full repository layout: the frontend imports schemas from
its sibling `contracts/` directory. The commands below avoid virtual environment
activation and the PowerShell `npm.ps1` wrapper.

### 1. Start the backend

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

No `.env`, API key or database is required for process health. In another
PowerShell terminal at the repository root:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Expected JSON: `{"status":"ok"}`. Health checks process liveness; it does not
prove database or provider readiness. Interactive API docs:
<http://127.0.0.1:8000/docs>.

### 2. Start the frontend

In a separate PowerShell terminal, starting at the repository root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open <http://127.0.0.1:5173>. Vite already proxies `/api` to the backend on
port 8000. Real API mode is the default: unavailable services remain unavailable
and are never replaced with fixtures. The development preview explicitly labels
synthetic examples, which are excluded from production builds.

Without provider/database configuration you can check startup, health and UI
failure states. Follow the next section to enable real search.

## Configure real search

Create the local backend settings file only if it is absent:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
```

Edit it locally using [the backend example](backend/.env.example). Settings read
`backend/.env` relative to the settings module, regardless of the working
directory; process environment variables take precedence. Restart the backend
after changing settings.

Ordinary place/event searches can incur OpenAI API charges, as can corpus
embedding and provider preflight probes.

| Setting                                                  | Purpose                                                                          |
| -------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `DATABASE_URL`                                           | Server-only TLS database connection for POI storage and retrieval                |
| `DATABASE_POOL_SIZE`                                     | Lazy connection pool, default 3, allowed range 1–5                               |
| `OPENAI_API_KEY`                                         | Responses intent/explanation/event discovery and embeddings                      |
| `OPENAI_MODEL`                                           | Responses model; project access must be verified independently                   |
| `OPENAI_EMBEDDING_MODEL` / `OPENAI_EMBEDDING_DIMENSIONS` | Current index: `text-embedding-3-large`, exactly 1536 dimensions                 |
| `APP_TIMEZONE` / `DEFAULT_LOCALE`                        | Default `Asia/Almaty` / `kk`                                                     |
| `TWOGIS_*`                                               | Optional server capabilities, disabled by default and gated by access and rights |

Frontend configuration is optional. Copy `frontend/.env.example` to
`frontend/.env.local` only if the latter is absent. Use `VITE_API_BASE_URL=/api`
and optionally a public domain-restricted `VITE_TWOGIS_MAP_KEY`. Manual
coordinates remain available without a map key; a browser map key does not
enable server routing.

Never expose database URLs, OpenAI keys or server 2GIS keys through a `VITE_`
variable. Real env files are excluded from Git and Docker build contexts.

### Database and corpus setup

1. In Supabase, use the **Session pooler on port 5432** for `DATABASE_URL`.
   Percent-encode reserved password characters and require TLS. The backend
   rejects Supabase direct/transaction-pooler URLs and insecure TLS modes.
   With a configured CA, prefer `sslmode=verify-full` and a local `sslrootcert`.
2. Disable the Supabase **Data API** and exclude `app` from exposed schemas.
   Browsers call FastAPI only. SQL revokes client-role access and enables RLS
   without client policies; Dashboard settings still need operator verification.
3. Check connectivity, then explicitly apply pending migrations:

   ```powershell
   .\.venv\Scripts\python.exe scripts/preflight.py --check db
   .\.venv\Scripts\python.exe scripts/migrate.py
   ```

   Migrations create POI/source/fact/import tables and search indexes using
   PostGIS and pgvector. Checksums detect changes to applied migrations; do not
   edit them. Use the migration owner or a trusted role with the required grants.

4. Populate the database through the permitted OSM importer, or use an approved
   snapshot as described in [the ingestion guide](ingestion/README.md):

   ```powershell
   .\.venv\Scripts\python.exe -m ingestion.cli import-osm --city astana
   ```

   This fetches real data, exports the corpus and persists through
   `PostgresPOIRepository.upsert_pois`. Inspect source/quality reports and partial
   failures. Raw/normalized corpus files are ignored by Git: a fresh clone has
   reports, not a ready database. Transfer JSONL and manifest together when
   using an existing export.

5. Prepare the search index only with a compatible, approved corpus export.
   **Current compatibility blocker:** the importer writes manifest version
   `1.3.0`, but `scripts/embed_pois.py` currently accepts only `1.1.0`/`1.2.0`.
   A fresh import can populate the database, but its default indexing step fails
   with `invalid_corpus_or_configuration`. For this export-based workflow, use
   an approved `1.1.0`/`1.2.0` JSONL/manifest pair matching the database records.
   Do not change a manifest version to bypass validation.

   With that compatible pair at `data/normalized/pois.jsonl` and
   `data/normalized/manifest.json`:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.embed_pois --dry-run
   .\.venv\Scripts\python.exe -m scripts.embed_pois
   ```

   The dry run reports eligible work without embedding calls or index writes.
   The second command writes search documents and may incur embedding API
   charges. Unchanged embeddings are reused; see [S03 evidence](docs/handoffs/S03.md).

Startup never runs migrations, imports or embeddings. Use one backend worker
unless the total database connection budget has been adjusted. Event discovery
uses live web search; the POI corpus optionally enriches exact venue matches.

## API and response states

Current API/contract version: **1.3.0**. Schemas and synthetic examples live in
[contracts/](contracts/); see [the API reference](contracts/api-v1.md).

| Method | Path                   | Behavior                                                          |
| ------ | ---------------------- | ----------------------------------------------------------------- |
| GET    | `/api/health`          | Process liveness, 200, no external calls                          |
| GET    | `/api/coverage`        | Real database counters; 503 if unavailable or unmigrated          |
| POST   | `/api/recommendations` | Up to three independent POI alternatives; unavailable is HTTP 503 |
| POST   | `/api/events/search`   | Transient event cards/listings/sources; unavailable is HTTP 503   |
| POST   | `/api/route`           | Walking legs; known/unknown is HTTP 200, unavailable is 503       |

`/api/v1/recommendations` and `/api/v1/route` are aliases.
`/api/v2/events/search` aliases the transient event response;
`/api/v1/events/search` preserves the legacy persistent-event shape and returns
503 unavailable. These event versions are not interchangeable.

For search responses, `ok` means completed results, `partial` retains usable
results with caveats, `unknown` means insufficient evidence, and `unavailable`
means a required service failed or is unconfigured. `no_match` is a completed
POI search with no eligible results within the searched corpus; it never proves
that the whole city has no suitable destination. Bounded event discovery cannot
establish `no_match` or complete coverage.

Without a requested date, event discovery searches the next 30 days instead of
restricting results to today. A supplied date preserves the selected local day
and earliest start; explicit time and budget limits still apply. Event identity,
city and explicit date/year/time stay grounded in the same cited source. Source
citation titles cannot supply missing session facts. Formatting differences in
quoted dates are accepted only when the actual source facts agree unambiguously.
See [the event discovery follow-up](docs/handoffs/event-discovery.md).

Clients must inspect non-2xx JSON, including unavailable envelopes. Invalid input
returns sanitized JSON 422; unexpected failures return generic JSON 500 with a
correlation ID. Unknown `/api` paths return JSON 404 and never enter the SPA
fallback. Search and route responses use `Cache-Control: no-store`.

## Data and current limits

The recorded **2026-10-19** OSM import contains **985 POIs**; the S03 handoff
records 985 indexed embeddings. These are checkpoint counts, not fresh database
telemetry. [The source report](data/source-report.json) records 642 POIs without
hours and all 985 without numeric prices; city completeness remains `unknown`.
A completed source query is not proof of complete coverage.

Fresh-export indexing is currently blocked by the manifest-version mismatch
described in the setup steps. The earlier successful S03 indexing checkpoint
does not prove that a new `1.3.0` export can be indexed.

Persistent sources need explicit storage rights; indexed sources also need
indexing rights. Keep attribution, provenance and source timestamps. OSM data is
attributed to OpenStreetMap contributors under the rights basis recorded in
[the source registry](data/source-registry.json) and [ingestion guide](ingestion/README.md).
Synthetic files in `contracts/examples/` are never the real city corpus.

2GIS is optional and disabled by default. Enable a server capability only after
confirming endpoint access and recording a reviewed project-specific runtime
rights basis. `TWOGIS_ENABLED` alone is insufficient. Runtime 2GIS payloads stay
ephemeral; they are not persisted, cached into the corpus, embedded or indexed.
Event discovery sources likewise prohibit storage/indexing in the runtime contract.

The [runtime integration follow-up](docs/handoffs/runtime-integration.md) records
hosted UI/API checks and the walking adapter correction. The event follow-up
confirmed a real linked Astana event with its explicit date, year and start time
on Render on 2026-10-19. This is discovered source evidence, not confirmed ticket
availability or a fully verified event recommendation. Unknown session ends,
prices, tickets or travel times do not become a confirmed fit. Weather integration
is planned in S05. See [the task board](docs/task-board.md) and [S04 handoff](docs/handoffs/S04.md)
for status and remaining checks.

## Architecture and repository

React/Vite/TypeScript calls the same-origin FastAPI/Pydantic API. The backend
retrieves permitted POIs from Supabase Postgres using PostGIS and pgvector,
uses the shared OpenAI Responses/embedding client, and optionally requests live
2GIS routes. Source facts stay separate from generated explanations.

| Path                   | Responsibility                                                 |
| ---------------------- | -------------------------------------------------------------- |
| `frontend/`            | Search UI, kk/ru/en dictionaries, maps and API transport       |
| `backend/app/`         | API, validation, retrieval, constraints and provider adapters  |
| `contracts/`           | Shared API reference, generated JSON Schemas and test examples |
| `database/migrations/` | Ordered, checksum-tracked SQL migrations                       |
| `ingestion/` / `data/` | Permitted OSM import, provenance and coverage reports          |
| `scripts/`             | Migration, indexing, preflight and smoke-check entrypoints     |
| `docs/`                | Roadmap, project brief and handoffs with verification evidence |

## Verification

Run Python checks from the repository root. Dependencies are pinned in the
requirements and constraints files. The explicit ingestion path matters:
plain `pytest` discovers only `backend/tests` in the current configuration.

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q backend/app scripts ingestion
.\.venv\Scripts\python.exe -m pytest backend/tests ingestion/tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts ingestion
.\.venv\Scripts\python.exe -m ruff format --check backend scripts ingestion
.\.venv\Scripts\python.exe scripts/export_contracts.py --check
```

Database integration tests run only with `TEST_DATABASE_URL` pointing to a
**disposable TLS test database** with the required DDL/extension permissions.
They create random isolated schemas and remove them afterward; missing test
configuration skips them. They never fall back to the production database URL.

Run frontend checks from `frontend/` after `npm.cmd ci`:

```powershell
npm.cmd test
npm.cmd run test:types
npm.cmd run lint
npm.cmd run check:contracts
npm.cmd run format:check
npm.cmd run build
npm.cmd run check:build
```

Live checks are separate from offline verification:

```powershell
.\.venv\Scripts\python.exe scripts/preflight.py --check all
.\.venv\Scripts\python.exe scripts/twogis_smoke.py
```

Preflight database probes are read-only. Responses and embedding probes use
synthetic text and may incur charges; 2GIS smoke requires confirmed access and
rights. Missing credentials/connectivity are recorded as `not_run`, not success.
Record actual live outcomes in the relevant handoff.

## Docker and deployment

Build from the repository root so Docker can access frontend and contracts:

```powershell
docker build -t qadam-astana:local .
docker run --rm -p 8000:8000 --env-file backend/.env -e PORT=8000 qadam-astana:local
```

The multi-stage image builds the frontend, installs Python dependencies and
serves SPA and `/api` from one non-root process at <http://127.0.0.1:8000>.
For a keyless health/UI smoke, omit `--env-file backend/.env`. The process binds
`0.0.0.0` and honors `PORT`. Only the optional public map key is supported as
`--build-arg VITE_TWOGIS_MAP_KEY=...`; server secrets belong in runtime settings.

[render.yaml](render.yaml) defines the Docker service with `/api/health` and
automatic deploys off. Configure runtime database/provider secrets, apply the
database/data setup explicitly and verify HTTPS UI, API and coverage after a
deployment. The Blueprint file alone is not evidence of a live deployment.

## Project documentation and collaboration

- [Working agreement and ownership](AGENTS.md)
- [Project brief](docs/project-brief.md) and [task board](docs/task-board.md)
- [Shared API contract](contracts/api-v1.md)
- [Ingestion and corpus transfer](ingestion/README.md)
- [Frontend guide](frontend/README.md) for component details; its pending-integration
  notes describe the earlier D04 checkpoint
- Backend evidence: [S00](docs/handoffs/S00.md), [S01](docs/handoffs/S01.md),
  [S02](docs/handoffs/S02.md), [S03](docs/handoffs/S03.md), [S04](docs/handoffs/S04.md)
- Frontend/data evidence: [D00](docs/handoffs/D00.md), [D01](docs/handoffs/D01.md),
  [D02](docs/handoffs/D02.md), [D03](docs/handoffs/D03.md), [D04](docs/handoffs/D04.md)

Sabyrzhan owns shared files, contracts, database, API and integrations. Damir owns
the frontend, translations, ingestion/data and event services. Use separate
branches/worktrees and follow the working agreement before changing shared files.
