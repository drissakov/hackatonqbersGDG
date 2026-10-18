# Qadam Astana project brief

## Input and goal

The supplied S00 Smart City brief is the available source of requirements. No
separate case PDF or previous implementation was present in the local checkout.
Help a person choose one realistic activity in Astana using their query, language,
origin, time, date, indoor preference and per-person budget.

MVP output is 1–3 alternatives with traceable sources, a reason, estimated visit
duration and a source/map action. Each alternative is independent, not a stop in
an itinerary. A separate event search exposes events and their scheduled sessions.

## Scope

- Automatically collect a permitted POI corpus covering the whole Astana area;
  record retrieval failures and geographic coverage. A few fixtures or a manually
  curated shortlist are not the corpus. Coverage completeness is not guaranteed.
- Ground recommendations in retrieved records. Respect explicit structured input
  over text inference. Unknown price, opening hours, location, travel duration or
  session data must remain unknown. Never manufacture facts to fit constraints.
- Consider outbound travel, visit, and return travel when requested. If any
  required duration is unknown, do not claim confirmed time fit.
- Support kk/ru/en. Default kk; generated_locale makes output language explicit.
- Separate POI suggestions from event/session search. Booking links only open
  external information; ticket purchase is outside the application.
- No accounts, GPS tracking/history, ticket checkout or multi-stop routes.

## Architecture

React/Vite/TypeScript frontend (Damir) -> same-origin `/api` -> FastAPI/Pydantic
backend -> Supabase Postgres with PostGIS for geography and pgvector for retrieval.
OpenAI Responses and `text-embedding-3-large` with explicit `dimensions=1536`
are shared through `backend/app/openai_client.py`. No integration is initialized
by health. Persistent database/retrieval/search implementation belongs to later
tasks; S00 supplies contracts and interfaces, not fabricated working search.

2GIS is conditional, `TWOGIS_ENABLED=false` by default. Server API access and a
public map key are different credentials. Without suitable documented rights,
do not save or index 2GIS data or use it as the corpus. S00 fails closed on
persistent 2GIS records. Use only licensed/authorized sources for ingestion and
embeddings. Source permission flags record a reviewed decision; flags themselves
are not evidence that rights exist.

Weather and route providers may fail independently. `unknown` is insufficient
information, `unavailable` is a required provider/corpus outage, and `no_match`
requires a completed search with no eligible results. Partial results carry
warnings and cannot silently weaken constraints.

## People and time

Sabyrzhan: database, shared schemas/contracts/dependencies, API, RAG, 2GIS,
weather, deployment. Damir: frontend, kk/ru/en, ingestion/data and
`backend/app/services/events/`. Each person has 24 active hours; breaks and
calendar time are separate. Stages and dependency gates are in `task-board.md`.

The first-hour delivery is a shared contract and a working keyless
`GET /api/health`. Health moved from S01 to S00 by user instruction. The handoff
is published as repository files and a common S00 commit; teammate receipt must
not be claimed without acknowledgement.

## Acceptance for S00

Import all Python modules; run the health server and HTTP smoke check without
keys/database; validate all synthetic JSON examples against JSON Schema and
Pydantic; check generated artifacts and static analysis; record independent live
DB/Responses/embedding statuses with reasons. Responses project access is only
confirmed by the real API. An actual embedding probe must return 1536 finite
values; a mock is not a live success. No frontend is created in this stage.
