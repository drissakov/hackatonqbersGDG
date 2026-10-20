# Qadam Astana API contract v1.3.0

Owner: Sabyrzhan. Consumers: Damir's frontend, ingestion and event service.
Python sources of truth: `backend/app/schemas.py` and the additive transient
event models in `backend/app/event_schemas.py`; generated JSON Schema and
`codes.json` live here. Regenerate using `scripts/export_contracts.py`; CI/local
checks must run it with `--check`. JSON Schema enforces structure and formats;
Pydantic additionally checks source references, rights, temporal order and
response consistency. Contract changes need the owner's review and synchronized
examples. Codes are stable machine values; UI labels belong to Damir's kk/ru/en
translations.

S02's route-only v1.2 extension and summary output were explicitly approved by
the user on 2026-10-19. Search, POI, event, coverage and route request shapes are
unchanged. Existing unavailable route examples remain valid. D04 must consume
the expanded route response; teammate acknowledgement is not claimed.

S04's v1.3 extension adds a separate transient event discovery response, explicitly
approved by the user on 2026-10-19. Existing persistent schemas remain byte-for-byte
unchanged. `codes.json` advances its version and adds `transient_event_missing_fields`;
existing enum members are unchanged. Runtime event discoveries gain no storage,
embedding or indexing rights. See the transient event section below before wiring D04.

## HTTP surface and current implementation boundary

| Method | Path | Request / response | Current state |
| --- | --- | --- | --- |
| GET | `/api/health` | No body -> `{"status":"ok"}` | Implemented; process health only |
| GET | `/api/coverage` | No body / coverage-response | Real DB counters, 200; DB unavailable 503 |
| POST | `/api/recommendations` | recommendation-request / recommendation-response | S04 independent POI alternatives; 200 or 503 unavailable |
| POST | `/api/events/search` | event-search-request / transient-event-search-response | S04 runtime event discovery; same response as v2 |
| POST | `/api/v2/events/search` | event-search-request / transient-event-search-response | Explicit transient v1.3 response; 200 or 503 unavailable |
| POST | `/api/v1/events/search` | event-search-request / event-search-response | Preserved persistent-wire scaffold, 503 unavailable |
| POST | `/api/route` | route-request / route-response | S02 optional walking; 200 known/unknown, 503 unavailable |
| GET | `/api/dev/pois` | Explicit synthetic POI fixture | Only APP_ENV=development/test AND DEV_FIXTURE_MODE=true; otherwise 404 |

All wire bodies are JSON, snake_case. `/api/health` has no request_id envelope,
does not read settings, and performs no provider/database calls. S00's reserved
`/api/v1/recommendations` and `/api/v1/route` remain compatible aliases.
The event v1 endpoint preserves its old unavailable body; unversioned and v2 event
search use the new transient response. Clients must select the matching schema.
`VITE_API_BASE_URL=/api` means new callers append `/recommendations`,
`/events/search` or `/route`. Existing D01 `/v1/...` calls still work. The Vite
dev proxy forwards `/api` to port 8000. Production uses the same origin.
No permissive CORS is added. Unknown `/api` paths always return JSON 404,
including when the SPA is present. A wrong HTTP method returns JSON 405.

S01 amends S00's planned HTTP behavior: an unavailable service returns HTTP 503,
with `status=unavailable` in search/route bodies. Later completed searches use
HTTP 200 for ok/partial/unknown/no_match. A 503 must never be treated as no_match.
Invalid JSON/input
returns 422; unexpected internal failures return a generic 500 without SQL,
provider bodies, secrets or raw input values. Error responses use
`{"error":{"code":"invalid_request","fields":["origin"]},"request_id":"<uuid>"}`
(500 code `internal_error`, empty fields). Coverage infrastructure failure uses
503 code `database_unavailable`. Invalid request_id is replaced by a generated UUID
for error correlation. Never expose a raw Pydantic/SDK exception in that route.

## Transient event discovery (S04, v1.3)

`POST /api/events/search` and `/api/v2/events/search` accept the unchanged
EventSearchRequest and return `transient-event-search-response.schema.json`.
`/api/v1/events/search` keeps the unchanged persistent EventSearchResponse scaffold.
The new response is a separate type, not a union and not a persistent EventRecord.
The legacy POI, event, session, request and route schemas are unchanged.

| Envelope field | Meaning |
| --- | --- |
| `request_id` | Original caller UUID |
| `contract_version` | Exactly `1.3.0` |
| `status` | `partial` for conditional cards/listings, `unknown` without defensible data, `unavailable` for required-provider failure |
| `provider_status`, `provider_code` | D03 provider state and a bounded safe code; no raw provider errors |
| `live_web_search` | `not_run`, `passed` or `failed`; discoveries require completed search evidence |
| `items` | At most three independent TransientEventCard alternatives |
| `listings` | At most ten unchanged D03 NormalizedEvent objects; these are discoveries, not confirmed recommendations |
| `sources` | At most 100 transient source references; every nested session/listing/venue URL is included |
| `warnings` | Existing warning codes and localized messages; partial responses require warnings |
| `excluded_sessions`, `rejected_events` | Nonnegative discarded-row counts; these do not measure city coverage |

A bounded live search cannot prove complete absence: this response rejects
`no_match`. Current D03 always has unknown ticket availability, so cards remain
`fit_status=unknown`, and `ok` cannot be produced. Provider failure is never
converted to no_match. A partial response can contain only listings, unlike the
persistent search envelope. No raw SearchEvidence text, citation context, tool
payload or normalization prompt is returned through HTTP.

TransientEventSource contains `source_id`, `url`, `retrieved_at`, nullable
`source_updated_at`, and literal false `storage_allowed`/`indexing_allowed` flags.
`retrieved_at` is the caller's observation anchor from D03, not a guaranteed
origin-page fetch time or source modification time. Unknown modification times
stay null. These flags describe the transient event payload; a linked permitted
OSM POI does not grant rights over the event site's content. Source IDs are unique;
a URL may retain both its original POI source identity and a runtime URL identity.
Runtime identities use `event-source:` plus the first 24 SHA-256 hex characters
of the exact normalized URL string. Source URLs cannot contain credentials.

Each card contains an `event` header (`id`, `title`, nullable `city`, `venue_name`,
`venue_address`, and its actual parent `source_id`), one unchanged D03
NormalizedSession in `session`, `source_ids`, existing `reason_codes` and
`activity_code` (`other` when no category is established), nullable
`visit_minutes_estimate`, `route_status`, `travel_minutes_estimate`, `fit_status`,
`missing_fields`, `explanation`, `generated_locale`, and `action`. The header has
no duplicate sessions list. The session retains its own independently grounded
city/venue/source, nullable starts/ends, `price_from`, currency/kind/conditions,
field verification and unknown ticket availability. Parent venue facts are not
silently inherited by a session page.

Card sources must include the actual event parent source and the session source;
the navigation action must point to a cited source URL. Venue source URLs also
appear in the envelope; nested venue `source_ids` keep their original permitted
POI identities. A field check must reference the same session, source URL, exact
field value and an observation at least as recent as its evidence anchor.
`verification_status=verified` covers only the listed checks, not the whole event.

Unknown `ends_at`, travel and source verification remain explicit missing fields.
`ticket_availability` is always missing in current D03. `price_from` is a lower
bound, including when its kind is regular; it never establishes a hard budget
fit. Absent indoor facts do not support `indoor_match`. Missing-field strings are
bounded to 32 and checked against `codes.json.transient_event_missing_fields`;
the existing persistent missing-field enum remains unchanged. Optional visit
allowances are backend suggestions labelled with `visit_duration_estimate`,
separate from actual session start/end facts.

Pydantic additionally enforces source references, eligibility, distinct session
cards, session/event parent IDs, temporal ordering and DTO count bounds. Only
scheduled Astana sessions with a known start and no exclusion reasons become
cards. The runtime service, using an explicit aware clock, also excludes past,
wrong-date, cancelled and unreachable-in-time sessions; a schema alone cannot
establish that a session is still in the future. Listings may retain incomplete
sessions for inspection without representing them as recommendations. No runtime
event payload is written to the corpus, cached for indexing or embedded.

Before the route shortlist, S04 deduplicates only a fully known exact identity:
normalized title, venue name, venue address and start instant. Source-scoped
listings remain separate. A source-bound explicit cancellation adds
`source_cancellation` to session `exclusion_reasons`; a cancellation conflicting
with an identical session from another source adds `unresolved_cancellation` to
that copy. Neither can become a recommendation. Extracted status and source
references remain visible. These are exclusion diagnostics, not new reason-code
enum members. The narrow text guard does not recognize every cancellation phrase
or independently verify source truth; conditional policies, negations and other
dated sessions are not treated as proof of cancellation.

All `transient-event-*.test.json` examples are explicitly synthetic. They verify
wire structure and honest uncertainty, never live web access or real event facts.
Existing frontend consumers need D04 wiring for this new response; no frontend
or Damir-owned event module is changed by the contract addition.

## Walking route (S02, v1.2)

`POST /api/route` and `/api/v1/route` accept the unchanged RouteRequest:
`request_id` (UUID, generated when absent), optional `origin`, required
`destination`, `return_to_start=false`, `locale=kk|ru|en` (default kk).
Coordinates are named `{latitude, longitude}` in WGS84 degrees. A null origin
never becomes a city center. Unknown extra fields are rejected with 422.

| Response field | Meaning |
| --- | --- |
| request_id | Echoed UUID |
| status | `known`: all requested legs succeeded; `unknown`: route/input could not be determined; `unavailable`: at least one required provider leg could not run |
| travel_minutes_estimate | `ceil(sum(duration_seconds) / 60)` only when all requested legs are known; otherwise null |
| outbound | Leg from origin to selected destination |
| return_route | Independent reversed request when return_to_start=true; otherwise `not_requested` with null metrics |
| destination_precision | `approximate`: the coordinate is not a verified accessible entrance |
| warnings | Localized warnings; data_unknown marks approximate destination, missing_input marks absent origin |

Each leg contains `status=known|unknown|unavailable|not_requested`, nullable
`distance_meters`, `duration_seconds`, `provenance`, `reason`. Known legs require
nonnegative integer metrics and provenance. Other legs require a reason and
null metrics/provenance. Provider meter/second values are rounded upward if
fractional; the total is rounded upward once after summing leg seconds. Zero is
valid. Safety bounds reject a leg over 1,000 km or seven days as invalid_response.
No straight-line estimate or doubled outbound time is used. A successful leg
remains visible when another fails, but no complete trip total is reported.
`known` means a provider result, not guaranteed travel time or entrance access.

Provenance contains provider=twogis, a fixed keyless endpoint, retrieved_at,
transport=walking, provider_locale=ru|en and storage_allowed/indexing_allowed/
ai_allowed=false. No request coordinates or provider body is included.
No geometry is returned: S02 explicitly uses output=summary. A future geometry
extension needs separate agreement; WKT must never be passed off as GeoJSON.

| Condition | HTTP / response |
| --- | --- |
| All requested walking legs succeed | 200 known, total minutes |
| ROUTE_NOT_FOUND / ROUTE_DOES_NOT_EXISTS | 200 unknown, leg reason=route_not_found |
| Origin absent, routing enabled and approved | 200 unknown, reason=missing_origin |
| Disabled / missing key / unconfirmed rights / invalid settings | 503 unavailable, reason=disabled / key_missing / rights_unconfirmed / invalid_settings |
| Timeout / network error / 401 or 403 / 429 / other HTTP failure | 503 unavailable, reason=timeout / network_error / access_denied / rate_limited / http_error |
| HTTP 200 FAIL/POINT_EXCLUDED/ATTRACT_FAIL/unrecognized status | 503 unavailable, reason=provider_fail |
| HTTP 200 OK without a valid result/metrics | 503 unavailable, reason=invalid_response |

Unavailability takes precedence over unknown when combining requested legs.
When disabled and origin is absent, 503 is preserved and a missing_input warning
is added. Provider failures never become no_match. Raw provider messages are
discarded. No automatic retries, Origin/Referer spoofing or alternative provider.

Server configuration requires TWOGIS_ENABLED=true, the separate capability
TWOGIS_ROUTING_ALLOWED=true and a nonblank TWOGIS_RIGHTS_BASIS identifying a
reviewed project-specific grant, plus TWOGIS_API_KEY. A working key alone does
not establish use rights. Defaults are off. The adapter never reads
VITE_TWOGIS_MAP_KEY. Before displaying live 2GIS-derived output, D04 must apply
the agreed provider attribution and confirm its runtime display scenario is
covered; enabling the backend is not frontend acceptance.

Routing maps ru -> ru, en -> en and kk -> ru explicitly. Places uses the
documented ru_KZ, en_RU, kk_KZ values (no blind kk or undocumented en_KZ).
This is provider language selection, not translation of source facts.

Places is an internal live adapter method, not a new public endpoint or
recommendation/ranking source. It independently requires PLACES and DISCOVERY
capabilities and reviewed runtime rights. Region discovery uses the separately
entitled TWOGIS_REGION_API_KEY; category/Places calls use TWOGIS_API_KEY. Region
IDs come only from an unambiguous Astana region search, never example constants.
Additional Places fields are limited to items.point,items.region_id,items.rubrics;
at most three results are projected to name/id/point/rubric IDs and separate
ephemeral provenance. Coordinates are approximate and unknown coordinates stay
null. Storage, indexing, ranking and AI use remain disallowed. No catalog data
is sent to the repository, OpenAI, fixtures, dumps or logs.

For Places searches only, HTTP 200 with meta.code=404,
meta.error.type=itemNotFound and no result is a documented empty search and
returns no_match. A successful meta.code=200/items=[] search is also no_match.
Other HTTP/provider errors remain unavailable. Region discovery stays strict:
failure to confirm Astana must never become an empty city corpus. See
[Places troubleshooting](https://docs.2gis.com/en/api/search/places/troubleshooting).

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
`message`, optional `fields` and optional `clarifications` (both default empty).
Messages/explanations must use
the requested locale. Record names may retain their source language; generated
translations are not original source facts.

### Structured unknown reasons

The coordinated UI follow-up extends `MissingField` with three stable codes in
`warnings[].fields`, without changing the envelope or `Warning` object shape:

| Field | Meaning |
| --- | --- |
| `child_suitability` | The source data cannot confirm suitability for children |
| `age_restrictions` | The source data cannot confirm the requested age eligibility or admission restrictions |
| `power_outlets` | The source data cannot confirm power outlets or device charging |

The unsupported-fact guard returns `unknown` with `missing_input`. A request
about a child of a stated age may contain both child and age fields, and charging
is independent. The same fields are available on POI and current transient-event
responses, including conditions retained by structured intent extraction.

Clients translate these codes from local dictionaries and keep them when the
interface language changes. They must not infer codes from `message`, re-run a
search just to translate a warning, or treat absent fields as proof of support.
Older responses with empty or omitted `fields` retain the generic warning.

Contract/corpus version remains `1.3.0`. This is an additive enum extension, but
previous strict clients may reject new values. Deploy the updated backend and
frontend together; current and legacy frontend schema snapshots are synchronized.
No per-person age value or provider prose is added to the structured reasons.
The source-checked playground supplement described below can now resolve generic
child play for a selected record; unsupported ages and absent charging evidence
continue to use these unknown-reason fields.

### Structured constraint clarifications

When an explicit input constraint needs correction, POI and current transient
event searches return `unknown`, no cards and a `missing_input` warning with
`clarifications`. Each entry contains only a bounded request `field` and `reason`:

```json
{
  "code": "missing_input",
  "message": "Clarify conflicting or unrecognized constraints.",
  "fields": [],
  "clarifications": [
    {"field": "available_minutes", "reason": "conflicting_constraints"},
    {"field": "budget_kzt_per_person", "reason": "unparsed_constraint"}
  ]
}
```

`field` uses the existing explicit-field vocabulary: `origin`,
`available_minutes`, `return_to_start`, `budget_kzt_per_person`, `indoor_only`
or `date_time`. At most six entries are allowed; producers deduplicate fields.
`conflicting_constraints` asks the user to resolve incompatible or ambiguous
requirements. `unparsed_constraint` means an explicit numerical time/budget
condition could not be extracted after the bounded retry. The application must
not silently choose a value or drop the condition. Retrieval, routing and event
discovery do not run after an intent clarification.

Clients render actionable kk/ru/en dictionary text from these codes, without
parsing `message`, exposing query values or making another request on language
changes. Omitted `clarifications` on older responses normalize to `[]`; explicit
null, unknown codes or malformed entries are invalid. Existing missing-fact
`fields` keep their separate meaning. A generic warning remains safe when an
older response has no structured clarification metadata.

Contract/corpus version remains `1.3.0`; no request, endpoint or persistent data
changes are introduced. This optional warning property requires a coordinated
backend/frontend release because older strict clients reject extra properties.

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

### Source-checked POI features

POI cards optionally include `feature_evidence` (default `[]`, at most three
entries) and `name_is_derived` (default `false`). Each evidence entry contains
`field`, strict boolean `value`, `source_id`, `source_field`, `source_value`,
positive integer `source_version`, `source_updated_at`, `checked_at` and nullable
`observed_at`. The current source-record format requires `observed_at=null`;
source retrieval/check is not a physical observation.

Supported feature fields are `family_playground`, `public_access` and
`power_outlets`. Positive playground evidence is exactly `leisure=playground`.
Public access uses explicit `access=yes/public` or `no/private`. Outlet evidence
uses explicit `service:electricity=yes/limited/no` or `power_supply=yes/no`,
never Wi-Fi, a grid connection or an EV tag. It does not prove device, connector,
voltage or wireless compatibility. Source edit time must precede check time,
which must not exceed the included source's retrieval time. Feature sources must
belong to the same POI and have documented storage and indexing permissions.
Runtime production loading rejects synthetic records and sources.

`family_playground_match` and `power_outlets_match` reasons require matching
positive evidence on that card. `public_access` is also a missing-field code;
unknown access keeps a card conditional, while explicit private/no access
excludes it. UI labels, fact dates and derived-name notices use local kk/ru/en
dictionaries and can change language without another search.

The checked-in `data/curated` supplement contains 22 OSM playgrounds (eleven
explicit public-access records and eleven with unknown access) and zero
qualified cafes with customer charging evidence. Its ODbL source audit stores
source versions, timestamps, licensed projections and rights. The offline
ingestion validator compares every published fact with this audit. Runtime
loads only the validated packaged catalog; it performs no network refresh.

Feature requirements select from all supplement records before route
evaluation, preserving category/name/geographic and other hard constraints. No
eligible supplement candidate yields `unknown`, not city-wide `no_match`.
Specific age, safety, quietness and accessibility claims remain unsupported.
Negative or optional conditions that the bounded guard cannot resolve remain
unknown. Ordinary searches continue to use the existing indexed corpus.

Direct playground queries and generic walks with a child are recognized by a
bounded kk/ru/en raw-text policy independently of the extracted child-interest
code. For a compatible empty/walk/entertainment category set, playground
selection may add the entertainment destination category while retaining the
walk activity. Explicit park, museum, cafe and other venue requirements block
that substitution, including when extraction missed the requested venue type.
No budget, time, origin, indoor, date or return constraint is cleared.

Exact generic playground descriptors accidentally extracted as names can be
removed only when the raw query has no explicit naming construction. Actual
names remain filters, and losing an explicitly requested name yields unknown.
Derived or unsourced names cannot satisfy a named-place restriction. Recognized
playground exclusions return unknown before providers; this does not introduce
general negative-place search. A missing source supplement does not allow a
generic entertainment venue to stand in for a requested playground.

Source-checked playgrounds have flexible suggested visits from 10 to 45 minutes,
reserving five minutes for entry, five minutes buffer and all known requested
route legs. Their source duration is unchanged. Unknown travel remains unknown;
an entertainment category or name alone cannot activate this policy. Other
non-walking activity estimates retain their existing durations.

POI evaluation continues after rejected candidates until three non-rejected
alternatives are collected or the available pool is exhausted. Conditional
unknown cards count as alternatives. Work is bounded to twelve unique eligible
candidate evaluations and a 54-second aggregate route deadline; each destination
retains its 18-second route timeout. No leg is retried. A count/deadline limit
with unexamined candidates returns unknown with no cards or partial with retained
cards and a data-unknown warning. A completely evaluated ordinary retrieved pool
can return no-match; an exhausted bounded feature supplement remains unknown.
These limits describe this search's candidates, not complete city coverage.
Event selection is unchanged.

The canonical `POIRecord`, database schema and index snapshot remain unchanged.
Contract/corpus version stays `1.3.0`; these response-only properties and enum
values require the matching backend and frontend to be released together,
because earlier strict clients reject new properties or enum values. No new
endpoint, request property or production dependency is introduced.

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

Damir owns producing records. S01 supplies `PostgresPOIRepository` and
`DatabasePool`; the protocol import remains `backend.app.repository.POIRepository`.
Do not construct separate ingestion SQL or bypass shared validation. Call this
Python boundary from a trusted backend/import process, never directly from the
browser. It is not a public HTTP write endpoint.

```python
from backend.app.database import DatabasePool
from backend.app.repository import PostgresPOIRepository
from backend.app.settings import Settings

settings = Settings()
pool = DatabasePool(settings.database_url.get_secret_value(), settings.database_pool_size)
repository = PostgresPOIRepository(pool, allow_test=settings.fixtures_enabled)
try:
    result = await repository.upsert_pois(records)
    coverage = await repository.coverage()
finally:
    pool.close()
```

`await repository.geo_search(Coordinates(...), radius_m=5000, limit=20)` uses
WGS84 geography and meter distances, excludes unknown coordinates, and returns
nearest records in a stable order. It does not claim a route or a time/budget
fit. Storage-only records without indexing permission are excluded. Normal
reads exclude test rows. Dev fixture mode explicitly allows them.

- Validate each mapping as POIRecord and enforce rights before any write or
  embedding. PostgreSQL-incompatible NUL and invalid Unicode text are rejected
  as invalid_record before SQL and before batch identity deduplication.
  Normalization failures reject a record without returning raw input.
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
  S01 compares only provenance matching both primary_source_id and external_id.
  It uses the oldest matching observed_at; missing matches or any matching null
  yield unknown. Known stored time rejects an older or unknown incoming time;
  equal times update; unknown stored time accepts unknown or known incoming time.
- Return `{inserted: int, updated: int, rejected: int, rejections: [{index, code}]}`.
  Each input record contributes to exactly one count, so their sum equals batch
  size. `index` is zero-based in the original input. Rejection count equals the
  number of unique rejection indexes. Codes: invalid_record,
  duplicate_in_batch, storage_not_permitted, stale_record. No raw data/errors.
- Persist accepted writes atomically within the batch. Infrastructure failure
  rolls back and raises a repository-level error; it is not a successful batch
  with fake rejection counts. Connection cleanup/timeouts belong to S01.

## Provider configuration and preflight

S01 coverage reports production/test counts separately, located/missing-location
records, embedded production records, production counts by primary provider and
import run failure/rejection counts. Empty but available tables return 200 with
zero counts. Unavailable/unmigrated tables return 503, never zero-count success.
`city_coverage` remains `unknown`: counters are not a measured city-area ratio.
`is_production_dataset` indicates the presence of non-test records only, not
completeness, freshness or a quality guarantee. See coverage-response.schema.json.

RouteRequest has request_id, nullable origin, required destination coordinates,
return_to_start and locale. S02 replaces the S01 scaffold with the optional
[walking route v1.2](#walking-route-s02-v12): approved enabled calls can return
200 known/unknown; disabled or unavailable routing returns 503 with null total.
The request_id is preserved. No straight-line fallback time is generated.

S01 database access uses TLS, Session pooler on Supabase port 5432 and a lazy
bounded pool (default three connections per process). Migrations are an explicit
operator action. The managed Data API must be disabled and app must not appear
in exposed schemas; this Dashboard setting requires separate verification.

Backend loads `backend/.env` relative to settings.py, independent of cwd. Runtime
env wins; local files are ignored by Git and Docker contexts. Defaults:

```dotenv
DATABASE_URL=
DATABASE_POOL_SIZE=3
APP_ENV=production
DEV_FIXTURE_MODE=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-luna
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=1536
TWOGIS_API_KEY=
TWOGIS_ENABLED=false
TWOGIS_PLACES_ALLOWED=false
TWOGIS_ROUTING_ALLOWED=false
TWOGIS_DISCOVERY_ALLOWED=false
TWOGIS_REGION_API_KEY=
TWOGIS_RIGHTS_BASIS=
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
