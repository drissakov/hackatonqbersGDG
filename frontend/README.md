# Qadam Astana frontend

D04 React/Vite/TypeScript single-page place and event search in kk/ru/en.
Consumes [shared API v1.2](../contracts/api-v1.md) plus the pending S03/D03
event-discovery v1.3 extension described below. Node.js 24 was tested;
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

The client calls `POST /api/recommendations`, `POST /api/events/search` and, only
after selecting an alternative with a known origin/destination, `POST /api/route`.
No failed API request is replaced with fixtures. On this committed base
(`origin/main ba6039e`) search handlers are still 503 scaffolds. Real searches
require Sabyrzhan's pending S03/D03 integration, currently running separately on
port 8006. D04 does not modify that backend or claim S04 constraint evaluation.

`src/lib/event-search-response.schema.json` is a frontend-owned, semantic copy
of that existing integration's v1.3 response schema. It validates ephemeral D03
listings/session evidence without editing the shared contracts. The contract
check verifies the shared v1.2 definitions and fields remain compatible with this
snapshot. Sabyrzhan must review/publish v1.3, then the snapshot should be replaced
with the shared generated schema. No event-source storage/indexing rights follow
from this adapter.

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

Changing language re-renders existing facts and local reason/activity codes. It
does not repeat a search, rebuild a route or reload the optional map. Free
explanations appear only when `generated_locale` matches; otherwise a local
template uses the codes. The next explicit search sends the current locale.
Source names, addresses and source schedule wording retain their original text;
generated citation paragraphs and raw server warning messages are not UI copy.

Editing query, origin or any filter cancels the old search and route and clears
their results. Request generations and abort signals reject late completions.
Only up to three alternatives appear. Their known coordinates and the origin
are shown on a coordinate map, with optional 2GIS basemap when configured. No
route line is invented. The route panel reports outbound/return separately,
provider attribution and approximate destination; card route values are labelled
as the search snapshot. Ambiguous event-session venues have no routed point.
GPS denial leaves manual coordinates available. Only language preference is
persisted; results, queries and route data stay in memory.

Ticket actions open a confirmed source (or sourced booking URL) to check details;
availability remains unknown and the app does not offer a purchase.

## Development fixtures

The expandable development preview deliberately loads synthetic examples from
`contracts/examples/`. It labels their test status and original English content;
source names and facts are not invented translations. Real API mode is the
default. Fixture controls and fixture JSON are excluded from production builds.

See [D04 handoff](../docs/handoffs/D04.md) for commands, actual checks, live API
scenarios, integration dependencies and the next consumer.
