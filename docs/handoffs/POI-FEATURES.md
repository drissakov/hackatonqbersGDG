# Source-checked POI features handoff

## Request and delivery boundary

User request: add 20–30 source-checked places for family leisure and cafes with
charging, retain sources/dates/reuse rights, connect filtering, add tests and run
checks. No commit or push was authorized.

Implemented in `codex/fix-poi-constraints` at base `9061865`, alongside preserved
earlier uncommitted constraint/UI fixes. The original checkout stays on `main`
at `350917c`, with only its pre-existing untracked demo video.

**Partial data delivery:** 22 real Astana playground records are available.
Eleven explicitly have public access; eleven have unknown access. There are
**zero qualified cafes with branch-specific customer charging evidence**.
The user confirmed they have no concrete observations and will look for open
sources. The charging filter is implemented and tested using clearly synthetic
records; no cafe or positive charging claim was invented. The mixed dataset
requirement is therefore still incomplete.

These are checks against published OSM records retrieved on 2026-10-20, not
on-site inspections, operator confirmations or age/safety guarantees. Source edit
times are separate from check/retrieval dates. Physical observation dates stay
null. No task-board stage is marked complete.

## Data, rights and repeatability

- `data/curated/poi-features.json`: 22 non-test source records, feature evidence,
  OSM versions/edit dates/check dates, original source URLs and permissions.
- `data/curated/source-audit.json`: licensed source projections and complete way
  geometry, SHA-256, Astana boundary, acquisition URLs, selection exclusions and
  charging discovery failures/zero-result metadata. Contributor usernames/UIDs
  and unlicensed operator payloads are not retained.
- `data/curated/README.md`: ODbL attribution/share-alike basis and limits,
  source-versus-physical verification, refresh/validation commands and cafe gap.
- `ingestion/curated.py`: offline deterministic replay plus bounded refresh of
  reviewed OSM IDs, with timeouts, response limits and a filesystem refresh lock.
  Network/validation failure preserves existing artifacts. File replacements are
  individually atomic; they are not a cross-file filesystem transaction.

The [OSM license statement](https://www.openstreetmap.org/copyright) and
[ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) are the reuse basis.
This derivative supplement carries attribution to © OpenStreetMap contributors.
Storage/indexing permissions do not grant rights to unrelated operator sites.

All 22 source names are absent. Display names are explicitly derived
`Unnamed playground (OSM ...)` labels, never attributed as source names.
Twenty-one ways use interior representative points, labelled approximate and not
verified entrances; one node preserves its source coordinate. Private,
customer-only, institutional and outside-boundary candidates were excluded from
the initial selection. Unknown access never becomes a positive access claim.

The recorded OSM outlet/device-charging search completed with zero results in
the Astana administrative bounding box. Official chain-wide outlet marketing
had neither branch-level proof nor an explicit reuse grant; workspace/Wi-Fi
claims were insufficient. Absence of qualifying evidence is not proof that cafes
lack sockets. No 2GIS payload was persisted or indexed.

## Runtime flow and important files

1. `backend/app/api.py` injects the read-only validated catalog loader.
   `backend/app/poi_features.py` fails closed on absent, invalid, oversized or
   synthetic production catalogs.
2. Raw requirements and extracted interests preserve child/age/charging
   conditions. Recognized negative/optional conditions, specific ages, infants,
   quietness, accessibility and unsupported charging compatibility remain unknown.
3. `backend/app/retrieval.py` examines all eligible supplement records before the
   three-route shortlist, independently of the ordinary database LIMIT 12.
   Same-place feature combinations, explicit category/name and 5 km geography
   still apply. Ordinary queries retain the existing lexical/vector search.
4. `backend/app/recommend.py` retains time, budget, indoor and independent route
   checks. Explicit private/no access excludes a place; unknown access keeps it
   conditional. Exhausting this bounded supplement yields unknown, including
   after hard-constraint rejection, rather than a city-wide no-match assertion.
5. `backend/app/schemas.py` binds feature facts to included permitted sources,
   exact supported source tags, source versions and consistent dates. Match
   reasons require positive evidence on the same card.
6. `frontend/src/components/FeatureFacts.tsx`, `ResultCard.tsx`, the API validator
   and kk/ru/en dictionaries show facts, provenance dates and derived-name
   notices. Language changes re-render existing results without a new search.
7. `Dockerfile` packages the runtime catalog. CI now explicitly includes ingestion
   tests, ingestion static/compile checks and offline source-audit validation.

Review also fixed requirement regressions exposed by newly supported family
queries: negative/optional conditions must not become positive matches; numeric
and spelled/reordered child ages must remain unknown; generic outlet evidence
must not prove USB, wireless, voltage or vehicle compatibility. No other confirmed
issue remained in the final backend/data/frontend review.

## Contracts, dependencies and state

Contract/corpus version remains **1.3.0**, consistent with the preceding
coordinated UI follow-ups. Response-only additions are optional
`feature_evidence` and `name_is_derived`, new feature/reason enum values and the
`public_access` missing-field code. Earlier responses normalize to empty/false.
Earlier strict clients require a coordinated backend/frontend release.

Canonical `POIRecord`, database schema, migrations and index snapshots are
unchanged. Existing 985-record coverage is not increased or treated as complete
by adding this separate supplement. No upsert, re-embedding, production database
write, deployment, new endpoint, request field or dependency was introduced.
The catalog is read once per process; restart after replacing it intentionally.
An enabled future source type needs a reviewed format/rights change; this
format only accepts OSM evidence (and synthetic test-fixture evidence in tests).

## Verification

Run from repository root with the existing Python development environment.
The actual interpreter was
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.
No dependency installation or lockfile change was needed.

| Command/check | Result |
| --- | --- |
| `python -m pytest backend/tests ingestion/tests -q` | **1748 passed, 17 skipped, 14.10 s** |
| `python -m pytest backend/tests/test_poi_features.py -q` | **107 passed**, before final full run |
| `python -m ruff check backend scripts ingestion` | passed |
| `python -m ruff format --check backend scripts ingestion` | passed, 93 files |
| `python -m compileall -q backend/app scripts ingestion` | passed |
| import `backend.app.main`, `backend.app.poi_features`, `ingestion.curated` | passed |
| `python -m pip check` | passed |
| `python scripts/export_contracts.py --check` | passed, 13 artifacts |
| `python -m ingestion.curated validate` | passed: 22 records, 11 known public access |
| `git diff --check` | passed |

The test subprocess explicitly removed `TEST_DATABASE_URL`; the 17 skipped
checks need an isolated SQL database, not production credentials. Pytest's
default `testpaths` only includes backend tests, so both directories are
explicit in the final command and CI.

New coverage: 107 backend feature checks, 43 ingestion checks and 45 frontend
checks. Tests cover strict rights/dates/tag semantics, source cross-references,
all-catalog selection, same-place combinations, unknown/private access, preserved
hard constraints, language changes without fetch, old response compatibility,
HTTP aliases, JSON Schema/Pydantic and real bundle replay. Synthetic positive
charging cases are labelled and cannot be loaded as production records.

Local acceptance with the actual 22-record catalog returned three non-test,
source-backed conditional cards for each kk/ru/en request; intent, explanation
and routing used synthetic test doubles. Responses passed the shared JSON Schema
and Pydantic. Database retrieval and embeddings were not called for this path.
Keyless HTTP health returned 200. This is not live OpenAI/routing acceptance.

Real external source verification: official OSM API fetch and CLI refresh of the
reviewed IDs passed. CLI refresh ran against a temporary copy, followed by offline
validation; it did not alter the shipped snapshot a second time. No live OpenAI,
2GIS or production-database acceptance was run for this change.

Frontend commands were run from `frontend/`:

| Command | Result |
| --- | --- |
| `npm.cmd test -- --reporter=dot` | **461 passed**, 24 files, 33.91 s |
| `npm.cmd run test:types` | passed |
| `npm.cmd run lint -- src scripts vite.config.ts vitest.config.ts` | passed |
| `npm.cmd run check:contracts` | passed |
| `npm.cmd run format:check` | passed |
| `npm.cmd run build` | passed, 73 modules |
| `npm.cmd run check:build` | passed, four production files |

Docker image build/smoke is **not_run**: the Docker Desktop Linux daemon pipe was
unavailable. The packaging path was reviewed, but that does not establish a
successful container build. Physical verification is **not_run**.
Nothing is staged; no commit, push or deployment was performed.

## Study topics and interview practice

Study source-record versus physical verification; evidence joins and strict
rights checks; bounded coverage and honest unknown; hard filters before route
shortlisting; deterministic ingestion replay; local rendering of stable codes.

1. **Why is a playground tag insufficient for a six-year-old admission claim?**
   It describes the mapped place type, without proving an operator age policy,
   current safety or supervision.
2. **Why keep feature evidence separate from canonical POI records?**
   A response supplement can add reviewed facts without changing existing
   database documents, corpus/index fingerprints or requiring re-embedding.
3. **Why can zero charging search results not produce no-match?**
   The searched source may omit outlets and has incomplete attribute coverage.
   Only missing evidence was established; the real-world constraint is unknown.

Next consumer: user review and acquisition of branch-specific, reusable cafe
charging evidence, then review of that evidence before extending this dataset.
An independently authorized coordinated release must still run Docker and live
provider acceptance. No next feature or deployment was started.
