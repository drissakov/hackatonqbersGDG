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
[Run locally](#install) ·
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
- **Location and routes:** manual coordinates and opt-in browser geolocation.
  The results map shows interactive OpenStreetMap streets without a key.
  Optional 2GIS supports map-based origin selection and separately gated server
  walking routes. Outbound and return legs are evaluated separately.
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

| Layer                         | Technology                                         | Role in the prototype                                                           |
| ----------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------- |
| Frontend                      | React 19, TypeScript 6, Vite 8                     | Search form, result cards, explicit constraints and API transport               |
| Localization                  | i18next, react-i18next                             | Local kk/ru/en dictionaries and language switching                              |
| Backend                       | Python 3.12, FastAPI, Pydantic                     | HTTP API, validation, constraint evaluation and response contracts              |
| Configuration                 | pydantic-settings, Uvicorn                         | Server environment settings and ASGI process                                    |
| Database                      | Supabase PostgreSQL, psycopg                       | POI records, source provenance and bounded database connections                 |
| Spatial search                | PostGIS                                            | WGS84 coordinates and geographic candidate retrieval                            |
| Semantic retrieval            | pgvector, OpenAI embeddings                        | Vector search with the configured 1536-dimensional index                        |
| AI                            | Official OpenAI SDK, Responses API                 | Intent extraction, grounded explanations and event discovery                    |
| Place data                    | OpenStreetMap                                      | Permitted POI import with attribution, timestamps and quality reports           |
| Street map                    | OpenStreetMap tiles                                | Interactive streets and destination markers without a map key, with attribution |
| Optional origin picker/routes | 2GIS MapGL and server adapters                     | Map-based origin selection and walking routes with separate keys/access/rights  |
| Verification                  | Vitest, Testing Library, pytest, Ruff, JSON Schema | UI behavior, backend checks and shared-contract validation                      |
| Delivery                      | Docker, GitHub Actions, Render                     | Frontend build, isolated verification and same-origin hosting                   |

Exact versions come from [the frontend lockfile](frontend/package-lock.json)
and [backend requirements](backend/requirements.txt) with
[constraints](backend/constraints.txt). The recorded corpus contains 985 POIs
across seven categories; this count does not imply complete city coverage.

## Env

From the repository root, create local files only if absent:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
if (-not (Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
```

Edit `backend/.env` locally. Process environment variables take precedence.

| Setting                                    | Value/purpose                                                          |
| ------------------------------------------ | ---------------------------------------------------------------------- |
| `DATABASE_URL`                             | Supabase Session pooler, port 5432, TLS required; trusted backend role |
| `OPENAI_API_KEY`                           | Server key for intent, explanations, event search and embeddings       |
| `OPENAI_MODEL`                             | Responses model available to your OpenAI project                       |
| `OPENAI_EMBEDDING_MODEL`                   | `text-embedding-3-large`                                               |
| `OPENAI_EMBEDDING_DIMENSIONS`              | `1536`                                                                 |
| `DATABASE_POOL_SIZE`                       | `3`; run one backend worker                                            |
| `TWOGIS_API_KEY`                           | Optional server Routing API key                                        |
| `TWOGIS_ENABLED`, `TWOGIS_ROUTING_ALLOWED` | Enable only with confirmed access and runtime rights                   |
| `TWOGIS_RIGHTS_BASIS`                      | Reference to the reviewed runtime-use decision                         |

Frontend: `VITE_API_BASE_URL=/api`; optional public `VITE_TWOGIS_MAP_KEY`.
Never put server keys/database URLs in `VITE_` variables or commit real env files.
2GIS Places/discovery stay disabled unless separately entitled and approved.

## Install

Use Python 3.12 and Node.js 24.15+ on the 24.x line. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
cd frontend
npm.cmd ci
cd ..
```

## Migrations

Configure `DATABASE_URL`, disable Supabase Data API and exclude `app` from exposed
schemas. Apply migrations explicitly using a trusted migration role:

```powershell
.\.venv\Scripts\python.exe scripts/migrate.py
```

Startup does not migrate, import or generate embeddings.

## Run backend

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Health: <http://127.0.0.1:8000/api/health>; API docs: <http://127.0.0.1:8000/docs>.
Health needs no keys/database; real search needs configured providers and corpus.
Restart the backend after changing settings.

## Run frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm.cmd run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to backend port 8000.
For a production bundle, run `npm.cmd run build` and `npm.cmd run check:build`.

## Importer

From the repository root, with database access configured:

```powershell
.\.venv\Scripts\python.exe -m ingestion.cli import-osm --city astana
```

This imports permitted real OSM POIs and exports JSONL plus manifest under
`data/normalized/`. Keep both files together. Do not import synthetic contract
examples as a city corpus. See [ingestion/README.md](ingestion/README.md).

## Embeddings

Use the matching imported JSONL/manifest and database records. Export versions
1.1.0, 1.2.0 and 1.3.0 are accepted; checksum and indexing rights remain required.

```powershell
.\.venv\Scripts\python.exe -m scripts.embed_pois --dry-run
.\.venv\Scripts\python.exe -m scripts.embed_pois
```

The dry run makes no embedding calls or index writes. The second command can
incur API charges; unchanged embeddings are reused. Fresh clones do not include
the ignored real corpus or production credentials.

## Demo preview and one-process mode

### Local addresses

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

## Local troubleshooting

| Symptom                         | First check                                                                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| UI opens but searches fail      | Check backend port 8000, `/api/health`, then provider/database setup; health alone is not search readiness                       |
| HTTP 503 or `unavailable`       | A required provider/corpus is unavailable or unconfigured; inspect safe server diagnostics rather than treating this as no match |
| Unknown route or total time fit | Keep the uncertainty visible; routing is optional and a visit estimate alone does not confirm the total trip                     |
| Port already in use             | Stop the previous dev, preview or backend process before starting another on the same port                                       |
| PowerShell blocks `npm.ps1`     | Use the documented `npm.cmd` commands; no execution-policy change is needed                                                      |
| Backend reads no settings       | Configure `backend/.env` or process environment variables, then restart the backend                                              |

## Project documentation

- [Demo script and exact A/B/C inputs](docs/submission/demo-script.md)
- [Seven-slide submission outline](docs/submission/slides-outline.md)
- [Current limitations](docs/limitations.md) and [technical submission notes](docs/submission/technical-notes.md)
- [Frontend guide](frontend/README.md) and [ingestion guide](ingestion/README.md)
- [API contract](contracts/api-v1.md), [task board](docs/task-board.md) and [working agreement](AGENTS.md)
