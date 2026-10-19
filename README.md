<div align="center">

<img src="frontend/public/favicon.svg" alt="Qadam Astana logo" width="80" height="80" />

# Qadam Astana

**One destination in Astana, chosen around your time and starting point.**

[![Live demo on Render](https://img.shields.io/badge/Live_demo-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://qadam-astana.onrender.com/)
[![CI](https://github.com/drissakov/hackatonqbersGDG/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/drissakov/hackatonqbersGDG/actions/workflows/ci.yml)
[![Languages: kk, ru, en](https://img.shields.io/badge/Languages-kk%20%2F%20ru%20%2F%20en-F4D267?style=for-the-badge)](#what-is-available)

![React 19](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)
![TypeScript 6](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![Vite 8](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white)
![OpenAI Responses](https://img.shields.io/badge/OpenAI-Responses-412991)

[Open live demo](https://qadam-astana.onrender.com/) ·
[Run locally](#local-start-windows-powershell) ·
[Technology stack](#technology-stack) ·
[Demo script](docs/submission/demo-script.md) ·
[API contract](contracts/api-v1.md)

</div>

## About the project

Choose a place or event in Astana that fits your time, location and per-person
budget. Qadam Astana offers up to three independent destinations with sources,
reasons, available visit and travel estimates, and an action to check details.

The development MVP includes a Kazakh, Russian and English interface, database
POI search, source-grounded explanations, separate live event discovery and
optional walking routes. POI search needs configured providers and a populated
database; live event discovery needs its provider but can run without the POI
database. Starting the application alone does not make search available.

## Live deployment

**[Open Qadam Astana on Render](https://qadam-astana.onrender.com/)**

| Link                                                           | Purpose                                      |
| -------------------------------------------------------------- | -------------------------------------------- |
| [Application](https://qadam-astana.onrender.com/)              | Public frontend and same-origin API          |
| [Health](https://qadam-astana.onrender.com/api/health)         | Process liveness, expected `{"status":"ok"}` |
| [Interactive API docs](https://qadam-astana.onrender.com/docs) | FastAPI endpoint reference                   |

The application and health endpoint returned HTTP 200 when checked on
**2026-10-19**. This check does not establish provider readiness or a complete
recommendation fit. Render automatic deployment is disabled in
[the Blueprint](render.yaml), so the deployed revision can differ from GitHub
`main`. Deployment evidence is recorded in
[the runtime integration handoff](docs/handoffs/runtime-integration.md).

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

## How a request works

1. **Describe an activity.** Choose a place or event search, then supply a
   starting point, available minutes and any explicit constraints.
2. **Retrieve candidates.** POI search combines lexical matching and vector
   retrieval over the permitted corpus. Event discovery uses a separate live
   web-search flow with transient sources.
3. **Evaluate known facts.** The backend checks the stated constraints and
   available route/session evidence. Missing facts remain unknown.
4. **Choose one destination.** Inspect up to three alternatives, their reasons,
   visit estimates and source links. Select a card to inspect its walking route
   when origin, destination and the optional provider are available.

Generated explanations describe retrieved evidence. They do not establish
opening hours, prices, route times or ticket availability.

## Technology stack

| Layer                | Technology                                         | Role in the prototype                                                  |
| -------------------- | -------------------------------------------------- | ---------------------------------------------------------------------- |
| Frontend             | React 19, TypeScript 6, Vite 8                     | Search form, result cards, explicit constraints and API transport      |
| Localization         | i18next, react-i18next                             | Local kk/ru/en dictionaries and language switching                     |
| Backend              | Python 3.12, FastAPI, Pydantic                     | HTTP API, validation, constraint evaluation and response contracts     |
| Configuration        | pydantic-settings, Uvicorn                         | Server environment settings and ASGI process                           |
| Database             | Supabase PostgreSQL, psycopg                       | POI records, source provenance and bounded database connections        |
| Spatial search       | PostGIS                                            | WGS84 coordinates and geographic candidate retrieval                   |
| Semantic retrieval   | pgvector, OpenAI embeddings                        | Vector search with the configured 1536-dimensional index               |
| AI                   | Official OpenAI SDK, Responses API                 | Intent extraction, grounded explanations and event discovery           |
| Place data           | OpenStreetMap                                      | Permitted POI import with attribution, timestamps and quality reports  |
| Optional maps/routes | 2GIS MapGL and server adapters                     | Map selection and walking routes, gated by separate keys/access/rights |
| Verification         | Vitest, Testing Library, pytest, Ruff, JSON Schema | UI behavior, backend checks and shared-contract validation             |
| Delivery             | Docker, GitHub Actions, Render                     | Frontend build, isolated verification and same-origin hosting          |

Exact versions come from [the frontend lockfile](frontend/package-lock.json)
and [backend requirements](backend/requirements.txt) with
[constraints](backend/constraints.txt). The recorded corpus contains 985 POIs
across seven categories; this count does not imply complete city coverage.

## Local start: Windows PowerShell

Use **Python 3.12** (the CI/Docker version) and **Node.js 24.15 or newer on the
24.x line**. Keep the full repository layout: the frontend imports schemas from
its sibling `contracts/` directory. The commands below avoid virtual environment
activation and the PowerShell `npm.ps1` wrapper.

### 0. Clone the repository

Skip this step if you already have a checkout:

```powershell
git clone https://github.com/drissakov/hackatonqbersGDG.git
cd hackatonqbersGDG
```

The following quick start opens the UI and keyless health endpoint. For real
place/event searches, also complete [Configure real search](#configure-real-search).

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

Keep the backend terminal running while using the frontend.

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

### 3. Open the right local URL

| Address                            | What runs there                                       |
| ---------------------------------- | ----------------------------------------------------- |
| <http://127.0.0.1:5173>            | Vite development UI                                   |
| <http://127.0.0.1:8000/api/health> | Backend process health                                |
| <http://127.0.0.1:8000/docs>       | Interactive API documentation                         |
| <http://127.0.0.1:4173>            | Production frontend preview, after the commands below |

For demo recording, keep the backend running and use a production build. From
`frontend/`, stop the Vite development process if needed, then run:

```powershell
npm.cmd run build
npm.cmd run check:build
npm.cmd run preview
```

Open <http://127.0.0.1:4173>. Both Vite development and preview forward `/api` to
port 8000. The production build excludes development fixture controls.

### Alternative: serve the built UI and API in one process

After building the frontend, stop the existing backend on port 8000 and run
from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.serve
```

Open <http://127.0.0.1:8000>. This serves `frontend/dist/` and `/api` together,
without a separate Vite process. The production entrypoint honors `PORT`
(default 8000) and binds `0.0.0.0`; the two-terminal development setup above
binds to localhost.

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

| Capability               | Required setup                                                                     |
| ------------------------ | ---------------------------------------------------------------------------------- |
| UI and health            | Installed dependencies; no provider keys or database needed                        |
| POI recommendations      | Configured OpenAI access plus a migrated, populated and indexed database           |
| Live event discovery     | Configured OpenAI/web-search access; POI database optionally enriches exact venues |
| Walking routes           | Optional server 2GIS capability with confirmed access and reviewed runtime rights  |
| Interactive 2GIS basemap | Optional public MapGL key; independent of server routing access                    |

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

## Local troubleshooting

| Symptom                         | First check                                                                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| UI opens but searches fail      | Check backend port 8000, `/api/health`, then provider/database setup; health alone is not search readiness                       |
| HTTP 503 or `unavailable`       | A required provider/corpus is unavailable or unconfigured; inspect safe server diagnostics rather than treating this as no match |
| Unknown route or total time fit | Keep the uncertainty visible; routing is optional and a visit estimate alone does not confirm the total trip                     |
| Port already in use             | Stop the previous dev, preview or backend process before starting another on the same port                                       |
| PowerShell blocks `npm.ps1`     | Use the documented `npm.cmd` commands; no execution-policy change is needed                                                      |
| Backend reads no settings       | Configure `backend/.env` or process environment variables, then restart the backend                                              |
| Fresh corpus cannot be indexed  | Check the manifest-version compatibility blocker documented above; do not relabel an export to bypass validation                 |

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

- [Demo script and exact A/B/C inputs](docs/submission/demo-script.md)
- [Seven-slide submission outline](docs/submission/slides-outline.md)
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
