# Qadam Astana API contract v1.0.0

Owner: Sabyrzhan. Consumers: Damir's frontend, ingestion and event service.
Python source of truth: `backend/app/schemas.py`; generated JSON Schema and
`codes.json` live here. Regenerate using `scripts/export_contracts.py`; CI/local
checks must run it with `--check`. JSON Schema enforces structure and formats;
Pydantic additionally checks source references, rights, temporal order and
response consistency. Contract changes need the owner's review and synchronized
examples. Codes are stable machine values; UI labels belong to Damir's kk/ru/en
translations.

## HTTP surface and S00 implementation boundary

| Method | Path | Request / response | S00 state |
| --- | --- | --- | --- |
| GET | `/api/health` | No body -> `{"status":"ok"}` | Implemented; process health only |
| POST | `/api/v1/recommendations` | recommendation-request / recommendation-response | Reserved; currently 404 |
| POST | `/api/v1/events/search` | event-search-request / event-search-response | Reserved; currently 404 |

All wire bodies are JSON, snake_case. `/api/health` has no request_id envelope,
does not read settings, and performs no provider/database calls. Search routes
are not mounted by S00; frontend development uses explicitly synthetic fixtures.
`VITE_API_BASE_URL=/api` means the frontend appends `/v1/recommendations` or
`/v1/events/search`. The Vite dev proxy forwards `/api` to port 8000. Production
should use the same origin; no permissive CORS is added in S00.

For later search implementations: valid searches return HTTP 200 even for
unknown/unavailable/no_match, with the status in the body. Invalid JSON/input
returns 422; unexpected internal failures return a generic 500 without SQL,
provider bodies, secrets or raw input values. Error responses use
`{"error":{"code":"invalid_request","fields":["origin"]},"request_id":"<uuid>"}`
(500 code `internal_error`, empty fields). These error responses are planned,
not implemented by health. Invalid request_id is replaced by a generated UUID
for error correlation. Never expose a raw Pydantic/SDK exception in that route.

## Search request

POI recommendations and event search share the following fields.

| Field | Type / default | Meaning |
| --- | --- | --- |
| request_id | UUID string; generated when omitted | Echo unchanged in a valid response; correlation only, not an account, idempotency key or stored GPS history |
| query | Nonblank string, 1–2000 characters; required | User intent; treat text and retrieved content as untrusted data |
| locale | `kk`, `ru`, `en`; default `kk` | Requested generated language |
| origin | `{latitude, longitude}` or null; default null | WGS84 degrees, latitude -90..90, longitude -180..180; unknown is not city center or `(0,0)` |
| available_minutes | Integer 1–1440 or null; default null | Total available time, including travel and optional return |
| return_to_start | Boolean; default false | Include return travel to the same origin when true |
| budget_kzt_per_person | Nonnegative integer KZT or null; default null | 0 means free-only; null means no numeric budget supplied, never zero or verified affordability |
| indoor_only | Boolean; default false | True excludes known outdoor places; unknown indoor status cannot be a confirmed fit |
| date_time | ISO-8601 timestamp with offset or null; default null | Preferred instant. Later normalization resolves null to server now in APP_TIMEZONE once per request; naive local timestamps are rejected |
| explicit_fields | Unique list of constraint field names; default `[]` | Keys deliberately set by the person; each listed key must actually be present, even if null/false/0 |

`explicit_fields` may contain origin, available_minutes, return_to_start,
budget_kzt_per_person, indoor_only and date_time. For example explicit false must
not be replaced by true inferred from text; explicit budget null clears a numeric
budget rather than inferring one again. For fields not listed, the backend may
infer constraints from the query later. Contradictions with explicit constraints
must be surfaced rather than silently overridden. Missing coordinates must not
be inferred from an IP address. No inference is implemented by S00.

For events, date_time is the earliest acceptable session start. If time is
available, an eligible session must start no earlier than arrival and finish
before the departure/return deadline. All comparisons use aware instants, with
APP_TIMEZONE (`Asia/Almaty`) for display/default normalization, not a hardcoded
server-local timezone. Event end/duration unknown means no confirmed time fit.

## Envelope and honest states

Every search response contains exactly `status`, `items`, `warnings`, `sources`
and `request_id`. `items` has at most three cards. A warning contains `code`,
`message` and optional `fields` (default empty). Messages/explanations must use
the requested locale. Record names may retain their source language; generated
translations are not original source facts.

| Status | Items | Meaning |
| --- | --- | --- |
| ok | 1–3 | All returned cards fit the evaluated hard constraints, using explicitly labeled estimates where necessary |
| partial | 1–3; warnings required | Usable alternatives exist but data or an optional provider is incomplete; unverified fit is labeled unknown |
| unknown | 0 | Necessary input/facts are unknown, so a defensible result cannot yet be determined |
| unavailable | 0 | A required provider or searchable corpus cannot be used; no claim about the existence of matches |
| no_match | 0 | A search actually completed against an available corpus and found no eligible alternatives |

Do not return a known hard-constraint violation as an alternative. `does_not_fit`
is available to internal candidate evaluation; such candidates are filtered from
search items. Partial results may contain unknown fits only with missing_fields
and clear limitations. `ok` is not a guarantee of real-world admission or route
timing. It describes fit against the stated facts/estimates, whose provenance and
uncertainty remain visible. Never map a timeout/empty corpus failure to no_match.

`route_status` distinguishes `known`, `estimated`, `unknown`, `unavailable` and
`not_requested`. Only known/estimated routes carry a nonnull
`travel_minutes_estimate`; do not use zero as an unknown. A provider route is
known in the sense of an obtained provider result, not guaranteed traffic truth.
Fallback travel estimates must say estimated. `fit_status`: fits, does_not_fit,
unknown. Unknown fit identifies missing constraint data; a fits card has no
missing_fields. Missing field and reason/warning enums are in `codes.json`.

## Cards, sources and actions

POI cards contain `poi` plus these common fields (event cards contain `event`
and `session` instead of `poi`):

- `provenance`: nonempty list of source references for the card's factual claims.
- `reason_codes`: stable reasons; `activity_code`: stable activity category.
- `visit_minutes_estimate`: positive minutes or null; explicitly an estimate,
  not an observed fact. Includes a visit-duration reason when estimated.
- `route_status`, `travel_minutes_estimate`: travel for this one destination,
  including return when return_to_start is true. Visit and travel stay separate.
- `fit_status`, `missing_fields`: constraint evaluation and its unknown facts.
- `explanation`: sourced explanation; `generated_locale`: actual kk/ru/en output
  language, equal to the requested locale. No silent locale fallback.
- `action`: `{code: "open_source" | "open_map", url: "https://..."}`; navigation
  only, never an in-app purchase. Only HTTP(S) URLs are valid.

Calculate time fit as travel + visit <= available_minutes, with the return leg
included in travel when requested. Missing origin, route, hours or relevant
session/price data cannot be replaced by a confident numeric result. Do not use
the LLM as the source of price, opening hours, routes or weather.

A Source has source_id, provider, url, retrieved_at, license, rights_basis_url,
storage_allowed, indexing_allowed and is_test. Permissions default to false.
Storage/indexing requires documented license and rights basis; indexing also
requires storage. These are ingestion assertions to review, not an automatic
legal decision. Source URLs and timestamps are retained for inspection.

Provenance has source_id, external_id, a nonempty `fields` list identifying the
facts supported, and nullable observed_at (unknown observation time stays null).
It must reference an included source. The
envelope includes every nested record source unchanged, plus any transient
route/weather source cited by card provenance. Source IDs are unique within the
envelope. Generated text must cite these factual sources rather than becoming
a source itself. Retrieval date does not prove a fact's observation date.

2GIS runtime payloads may be used transiently only when configured/authorized;
they do not enter persistent records or the vector index in S00. Disabling 2GIS
must preserve a usable non-2GIS path with honest uncertainty warnings.

## Persistent POI, event and session

`poi.schema.json`: a POIRecord has id, primary_source_id, external_id, name,
description, nullable location/address, activity_code, nullable indoor,
price_kzt_per_person, visit_minutes_estimate and opening_hours_text; it includes
sources, provenance and is_test. Unknown structured data uses null. Opening
hours text is raw sourced text, not proof the place is open at a requested time.
Every persistent source must permit storage. Only records whose relevant sources
also permit indexing may be embedded in later stages. Missing geometry is
allowed in ingestion but prevents confident distance/route filtering.

`event.schema.json`: an EventRecord describes the event itself (id, title,
description, activity_code and sourcing). It does not invent a session time.

`event-session.schema.json`: an EventSession is one occurrence (id, event_id,
nullable poi_id/location, starts_at, nullable ends_at/price/booking_url, status
scheduled/cancelled/unknown and sourcing). starts_at is required and aware;
unknown start means retain the event without a fabricated session. ends_at, if
known, must follow starts_at. Multiple sessions may share event_id. A card's
session must belong to its event; cancelled sessions are not recommendations.
No recurrence engine or ticket purchase is introduced by S00.

## Ingestion repository interface

```python
class POIRepository(Protocol):
    async def upsert_pois(
        self, records: Sequence[Mapping[str, object]]
    ) -> UpsertResult: ...
```

Damir owns producing records; Sabyrzhan implements persistence in S01. Import
the interface from `backend.app.repository`. No fake in-memory database or
working SQL repository is shipped in S00. Do not let ingestion construct its own
database writes or alter shared models to bypass validation.

- Validate each mapping as POIRecord and enforce rights before any write or
  embedding. Normalization failures reject a record without returning raw input.
- Stable upsert identity: `(primary source provider, external_id)`, not name or
  coordinates. primary_source_id references one of sources. id is a stable
  canonical ID supplied by ingestion; updates preserve the existing stored ID
  and must never create another row merely because a new ID was proposed.
- Repeated valid records across calls are updates (including unchanged content);
  within a batch the first valid occurrence of an identity wins and subsequent
  occurrences are rejected as duplicate_in_batch. A row older than the stored
  primary-source observation is stale_record, not an overwrite. S01 must define
  and test the matching primary-source provenance comparison and null handling
  transactionally; never substitute retrieval time as a known observation time.
- Return `{inserted: int, updated: int, rejected: int, rejections: [{index, code}]}`.
  Each input record contributes to exactly one count, so their sum equals batch
  size. `index` is zero-based in the original input. Rejection count equals the
  number of unique rejection indexes. Codes: invalid_record,
  duplicate_in_batch, storage_not_permitted, stale_record. No raw data/errors.
- Persist accepted writes atomically within the batch. Infrastructure failure
  rolls back and raises a repository-level error; it is not a successful batch
  with fake rejection counts. Connection cleanup/timeouts belong to S01.

## Provider configuration and preflight

Backend loads `backend/.env` relative to settings.py, independent of cwd. Runtime
env wins; local files are ignored by Git and Docker contexts. Defaults:

```dotenv
DATABASE_URL=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-luna
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=1536
TWOGIS_API_KEY=
TWOGIS_ENABLED=false
APP_TIMEZONE=Asia/Almaty
DEFAULT_LOCALE=kk
```

Frontend: `VITE_API_BASE_URL=/api`, optional public `VITE_TWOGIS_MAP_KEY`.
Everything prefixed VITE_ is public. Do not expose server credentials there.
An enabled flag alone is neither API access nor permission to store 2GIS data.

Use the shared AIClient protocol (`create_response`, `embed`) rather than creating
new SDK instances per feature. Concrete OpenAIClient is an async context manager,
uses a 20-second timeout, no automatic retries, Responses `store=false`, and
explicit embedding dimensions/float encoding. It validates finite 1536-value
vectors. It does not implement RAG, business prompts or event extraction in S00.

From the root in PowerShell, after installing backend/requirements-dev.txt:

```powershell
.\.venv\Scripts\python.exe scripts/preflight.py --check db
.\.venv\Scripts\python.exe scripts/preflight.py --check responses
.\.venv\Scripts\python.exe scripts/preflight.py --check embedding
.\.venv\Scripts\python.exe scripts/preflight.py --check all --output docs/handoffs/S00-preflight.json
```

DB probe performs SELECT 1 and checks postgis/vector extensions, read-only with
connection/statement timeouts. It never enables extensions or runs migrations.
Responses/embedding each independently check project model access with
`models.retrieve`, then execute their own synthetic probe. No provider payloads,
connection URLs, vectors, prompt text or API error bodies are printed.

Probe statuses: passed, failed, not_run. Missing credentials and connection
unavailability/timeouts are not_run with a safe reason; invalid config,
authentication/permission/model errors, missing extensions and incorrect vector
dimensions are failed. A network timeout does not prove that a remote API never
received a request. Exit codes: 0 all selected checks passed, 1 any failed,
2 no failures but at least one not_run. Mocks never count as live verification.

Official OpenAI documentation was opened on 2026-10-19 (Asia/Tashkent):
[GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) explicitly
lists API ID gpt-6-luna and Responses support. The
[embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
documents text-embedding-3-large's default 3072 dimensions and reduction through
the dimensions parameter. The
[text generation guide](https://developers.openai.com/api/docs/guides/text),
[embedding API reference](https://developers.openai.com/api/reference/resources/embeddings/methods/create)
and [model access API](https://developers.openai.com/api/reference/resources/models/methods/retrieve)
support the adapter and probes. Documentation does not establish project access;
that requires real keys/network and is recorded separately in the handoff.
Changing OPENAI_MODEL requires rechecking its own official page and project
access; never infer an API model ID from Codex's model selector or auto-substitute
another model.
