# D00 contract notes: original draft superseded by S00 v1.0.0

Publication addendum (2026-10-19): the user later authorized publishing D00/D01
source and documentation. The no-commit and implementation-state statements
below are historical D00 observations; shared contract ownership is unchanged.

Date: 2026-10-19. Author: Damir's side. Recipient: Sabyrzhan.

**Status:** the original D00 draft was written before application code arrived.
It is superseded by the S00 baseline delivered in commit `8ad0546`
(`feat(foundation): establish S00 contracts and keyless health`). This note
records the reviewed baseline and remaining questions; it is not a new shared
contract. Delivery through repository files does not establish personal
acknowledgement or agreement by both contributors.

The original Russian draft remains unchanged in Damir's original checkout at
`C:\Users\Ilytsm\Documents\GitHub\hackatonqbersGDG\docs\damir-contract-proposal.md`.
This updated copy belongs to the isolated D00 worktree on
`feature/d00-preparation`.

## Authority and change process

- [API/data contract v1.0.0](../contracts/api-v1.md), owned by Sabyrzhan.
- [Pydantic models](../backend/app/schemas.py): Python source of truth;
  [generated schemas/codes](../contracts/) and
  [synthetic examples](../contracts/examples/README.md) must stay synchronized
  through [the exporter](../scripts/export_contracts.py) and `--check`.
- [POI repository interface](../backend/app/repository.py),
  [HTTP implementation](../backend/app/main.py), [README](../README.md),
  [project brief](project-brief.md), and [working agreement](../AGENTS.md).
- [Task board](task-board.md) and [S00 handoff](handoffs/S00.md): planned stages
  and historical results. Current D00 observations belong in the
  [Damir worklog](damir-worklog.md); another machine's results do not verify this
  environment or current provider access.

Sabyrzhan alone changes shared schemas, contracts, dependencies and API files.
Damir requests changes through `docs/handoffs/<TASK-ID>.md`, explaining the need,
consumer, fixture and API/migration impact. Owner review and synchronized
examples/artifacts are required. This note changes no shared contract.

## Retired assumptions

The original missing-code, unknown-stack and missing-contract blockers are
resolved by the delivered baseline. The first draft's camelCase, `LocalizedText`
and fallback order, server-assigned import IDs, `lat`/`lon`, `cityId`,
`categoryIds`, `bbox`, flat event/date-only model, generic `SourceRef`, export
envelope, POI list/detail operations, pagination and former error codes are not
v1 agreements. Do not implement against them.

The minimum scenario is constrained search for 1-3 independent single
destinations with sources, reasons, visit estimates and source/map actions;
event/session search is separate. Accounts, GPS history, ticket purchases and
multi-stop itineraries are excluded. The architecture is React/Vite/TypeScript,
FastAPI/Pydantic and target Supabase Postgres/PostGIS/pgvector, with shared
OpenAI Responses/embedding access.

## Confirmed baseline and actual implementation

| Operation | Delivered contract | S00 implementation |
| --- | --- | --- |
| `GET /api/health` | `{"status":"ok"}`; process health only | Implemented without settings, keys or database calls |
| `POST /api/v1/recommendations` | Recommendation request/response schemas | Reserved; not mounted, currently 404 |
| `POST /api/v1/events/search` | Event request/response schemas | Reserved; not mounted, currently 404 |
| `POIRepository.upsert_pois(records)` | Async Python ingestion boundary | Protocol only; SQL persistence belongs to S01 |

No frontend, import pipeline, real city corpus or event service exists in S00.
Later fixture-based frontend work can proceed without live search/database.
`VITE_API_BASE_URL=/api` means append `/v1/recommendations` or
`/v1/events/search`; the planned Vite proxy targets `http://127.0.0.1:8000`.
Server secrets never belong in `VITE_` variables.

### Requests, responses, language and time

Bodies use snake_case JSON; extra fields are forbidden. Query is required and
nonblank (1-2000 characters); omitted request_id generates a UUID. Locale is
kk/ru/en, default kk. Nullable origin uses WGS84 `{latitude, longitude}`.
Available minutes are nullable integers 1-1440; per-person budget is nullable,
nonnegative integer KZT. Zero is free-only; null is not zero. Return/indoor flags
default false. date_time is nullable and offset-aware. Unique explicit_fields
must actually be supplied; explicit null/false/zero override later inference.
Normalization/inference are not implemented by S00.

Responses contain exactly status/items/warnings/sources/request_id, with at most
three distinct cards. ok/partial/unknown/unavailable/no_match remain separate;
partial requires warnings and known hard-constraint violations are excluded.
Cards expose provenance, reason/activity codes, visit/travel estimates,
route_status, fit_status, missing_fields, explanation, generated_locale and an
external source/map action. Only known/estimated routes have numeric travel.
Unknown facts stay null/unknown; estimates must be labeled.

Damir owns local kk/ru/en UI dictionaries. Source names stay sourced strings;
generated explanations/warnings use the requested locale with no silent fallback.
APP_TIMEZONE is Asia/Almaty. For events, date_time is the earliest session start.
Time evaluation includes arrival, visit and return when requested.

Planned searches use HTTP 200 for domain statuses; invalid input is 422 and
unexpected errors generic 500. The planned error envelope contains
`error: {code, fields}` plus request_id; codes are invalid_request/internal_error.
These errors are not implemented by health or an active search route in S00.

### Records, identity, sources and ingestion

POIs require id, primary_source_id, external_id, string name, activity_code,
sources and provenance. Description/location/address/indoor/price/visit estimate/
raw opening-hours text can be null. Identifiers are nonempty strings up to 200
characters. Ingestion supplies a stable canonical POI ID; updates preserve the
existing stored ID. Opening-hours text is not proof of being open at a given time.

Events contain identity/title/description/activity/sourcing. Sessions are separate:
id/event_id, nullable poi_id/location, required aware starts_at, nullable end/price/
booking URL, and scheduled/cancelled/unknown status. A known end strictly follows
the start. Unknown start means retain the event without inventing a session;
cancelled sessions are excluded. No recurrence engine is delivered.

Sources retain provider/URL/retrieved_at/license/rights_basis_url, permissions and
is_test. Provenance references included sources, external IDs, supported fields
and nullable observed_at. Retrieval time never substitutes for observation time.
Every persistent source requires documented storage rights; indexing also
requires indexing rights. Permission flags require reviewed evidence. Persistent
2GIS sources are rejected in S00; optional runtime payloads remain ephemeral.
Synthetic fixtures never become the real Astana corpus.

`upsert_pois(records: Sequence[Mapping[str, object]]) -> UpsertResult` validates
records and rights. Stable identity is `(primary source provider, external_id)`.
First valid identity in a batch wins; later duplicates are rejected. Stale
primary-source observations cannot overwrite newer records; S01 still needs
transactional comparison/null rules. Result counts are inserted/updated/rejected,
with original zero-based rejection indexes and invalid_record,
duplicate_in_batch, storage_not_permitted or stale_record codes. Each input
contributes to exactly one count. Accepted writes are atomic; infrastructure
failure rolls back and raises. Ingestion does not write SQL directly.

## Remaining questions and proposals for Sabyrzhan

These requests need owner decisions; they are not accepted contract changes.

1. Before real ingestion: identify permitted POI/event sources and reviewed
   storage/indexing rights; define the Astana/suburb boundary, measurable
   geographic coverage and freshness criteria. Querying a source alone does not
   prove coverage.
2. For S01/D02: supply the concrete repository adapter/import entry point, batch
   transport/limits, canonical ID convention, provider namespaces (especially
   other), and tested primary-source stale/null rules. No new export envelope or
   HTTP ingestion route is assumed here.
3. Before D04 event persistence: define the event/session repository boundary,
   deduplication, stable identities, update/cancellation handling and POI links.
   S00 includes record schemas but no event persistence interface.
4. Before live API wiring: provide implemented search readiness and safe example
   responses/errors. Later D01 may use synthetic fixtures; missing live API is
   not evidence of no real-world matches.
5. Supply external submission requirements, judging rubric and demo format
   beyond the project brief, including disclosure of synthetic data. Fixtures
   and historical S00 probes do not prove current live provider readiness.
6. Reconcile the shared roadmap through its owner: the task board describes D00
   as frontend scaffold/locales. The user's explicit D00 instruction here limits
   work to inspection, existing-project setup, launch verification and handoff
   documents, and forbids starting D01. The explicit user instruction wins.
   This D00 creates no frontend/next-stage feature, changes no shared task board
   and does not mark later work complete.

Recipients are Sabyrzhan for shared decisions and Damir for a later explicitly
authorized D01. This note starts no next stage, claims no teammate
acknowledgement, and authorizes no commit or push.
