# Qadam Astana frontend

D01 React/Vite/TypeScript screen for place and event searches in kk/ru/en.
Consumes [API contract v1.0.0](../contracts/api-v1.md). Node.js 24 was tested;
`package-lock.json` locks the installed dependency tree.

## Setup and development

Keep the repository layout: `frontend/` must sit beside `contracts/`. The
frontend imports shared JSON Schemas and development fixtures from that sibling
directory; copying only `frontend/` is insufficient for a build.

Start the backend using the [root instructions](../README.md), then run from
the repository root in another PowerShell terminal:

```powershell
cd frontend
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies relative `/api` requests to
`http://127.0.0.1:8000`. `VITE_API_BASE_URL` defaults to `/api`; the transport
rejects other origins. `GET /api/health` checks process health, not search or
database readiness.

The supplied backend implements health. The reserved search paths
`POST /api/v1/recommendations` and `POST /api/v1/events/search` still return 404
in this checkout. The UI reports that the endpoint is unavailable; it never
replaces a failed API request with mock results. A real successful search remains
blocked until Sabyrzhan supplies the implemented API.

## Checks and build

Run inside `frontend/`:

```powershell
npm run test
npm run test:types
npm run lint
npm run check:contracts
npm run format:check
npm run build
npm run check:build
npm run preview
```

`test` runs Vitest once; `test:watch` is available for development. `test:types`
checks test TypeScript, and `check:contracts` checks frontend enums, field names
and supported schema keywords against the shared contract. `build` typechecks
application code and creates `dist/`. `preview` serves that build locally at
`http://127.0.0.1:4173`, with the same development API proxy.

`check:build` verifies built assets and rejects fixture payloads, server credential
names, environment files and source maps in production output. `format` applies
the pinned Prettier version; `format:check` checks without editing.

For deployment, serve `frontend/dist/` as static assets and route same-origin
`/api` to FastAPI. Production routing and Docker belong to Sabyrzhan. Use the
**repository root as the Docker build context** so the frontend build can read
both `frontend/` and `contracts/`; D01 does not change Docker files. The Vite
development/preview proxy does not configure production routing.

## Configuration, location and language

Frontend configuration is limited to `VITE_API_BASE_URL=/api` and optional
`VITE_TWOGIS_MAP_KEY`. Vite embeds these values at build time. The map key is a
public, domain-restricted MapGL key, separate from the server 2GIS API key. Never
put OpenAI keys, database URLs or server 2GIS keys in frontend variables.

With a map key, MapGL loads on demand and allows selecting a point. Without a
key, or if the optional map fails, manual WGS84 latitude/longitude inputs remain
available. The initial map viewport does not select a starting point. Browser
geolocation runs once only after the person's button action; denial preserves
manual entry. No GPS or query history is stored.

Local dictionaries ship with the application. Language resolution uses
`localStorage.qadam.language`, then the browser language, with kk fallback.
Only `qadam.language` is persisted. The active language updates `html.lang`.
Dates use Astana wall time (`Asia/Almaty`), amounts use KZT per person, and
unknown values remain unknown. Default form values are not explicit constraints
until the person changes them.

## Development fixtures

The expandable development preview deliberately loads synthetic examples from
`contracts/examples/`. It labels their test status and original English content;
source names and facts are not invented translations. Real API mode is the
default. Fixture controls and fixture JSON are excluded from production builds.

See [D01 handoff](../docs/handoffs/D01.md) for actual verification results,
remaining integration blockers and the deployment handoff.
