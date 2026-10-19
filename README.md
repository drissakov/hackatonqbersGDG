# Qadam Astana

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
