# Qadam Astana task board

Each contributor has **24 active hours** (48 person-hours total). Windows are
relative to that contributor's start; they are not promises of wall-clock time.
S00, S01, the amended S02, S03 and D02 were explicitly authorized in their task chats.
Later rows are coordination plans, not authorization to implement them. Owners
must confirm scope at handoff.

| Stage | Active hours | Sabyrzhan task and ownership | Damir task and ownership | Dependency / exit gate |
| --- | --- | --- | --- | --- |
| 00 | 0–1 (1h) | S00: shared contract, server/settings/client interfaces, safe preflight, keyless health | D00: frontend scaffold and kk/ru/en foundation | Common contract + runnable health delivered for D01 |
| 01 | 1–3 (2h) | S01: Supabase schema, PostGIS/pgvector migrations, POI repository implementation | D01: contract-based search form/cards, API transport and fixture states | Use S00 upsert and HTTP contracts; health already belongs to S00 |
| 02 | 3–6 (3h) | S02: optional 2GIS Places and independent walking routes, per the user's scope amendment | D02: automatic permitted Astana-wide ingestion/data and coverage report | D02 persists through upsert_pois; S02 runtime rights/access gates and route contract v1.2; no unlicensed 2GIS corpus |
| 03 | 6–9 (3h) | S03: embedding/RAG retrieval and source grounding | D03: frontend recommendations and language rendering | Real records and 1536-dimension embeddings; no invented facts |
| 04 | 9–12 (3h) | S04: constraints, independent route alternatives, safe explanations and transient event API integration | D04: event ingestion/services and separate event/session view | Shared contracts owned by Sabyrzhan; event service owned by Damir |
| 05 | 12–16 (4h) | S05: weather/indoor handling and constraint integration | D05: live API wiring, location/time/budget controls and states | Preserve unknown/unavailable/no_match and explicit constraints |
| 06 | 16–19 (3h) | S06: end-to-end backend integration and failure handling | D06: frontend/event integration and localization checks | Shared smoke scenarios for kk/ru/en, events and POIs |
| 07 | 19–22 (3h) | S07: deployment and operational smoke checks | D07: responsive UX, accessibility and demo data quality | Secrets separated; production provider gates recorded |
| 08 | 22–24 (2h) | S08: final verification, backend documentation and handoff | D08: final UI/demo verification and handoff | Reproducible demo, known limitations and coverage disclosed |

## Current status

- [x] S00 — shared foundation delivered; 64 tests pass, health works, real Responses/1536-dimension embedding pass. DB preflight is failed and remains an explicit blocker; see `handoffs/S00.md`.
- [ ] D00 — in parallel according to the user; no completion evidence available here.
- [x] S01 — database/API implementation and deployment configuration delivered; REVIEW passed 129 tests including isolated SQL checks. Real Supabase migrations/upsert/coverage passed. First HTTPS deployment and managed Data API/exposed-schema verification remain explicit not_run gates; see `handoffs/S01.md`.
- [ ] D01 — frontend and HTTP 503 fix are published in origin/main; live acceptance with S01 remains pending. This S01 commit does not mark Damir's task complete.
- [x] S02 — amended 2GIS adapter and walking route contract v1.2 delivered and reviewed. Real walking/Places/discovery remain not_run without confirmed keys/rights; Astana IDs remain unknown. Implementation checkpoint: 183 passed, 11 skipped; tests were not rerun after REVIEW fixes at the user's request. See `handoffs/S02.md`.
- [x] D02 — repeatable Astana OSM importer, canonical export and coverage/quality reports delivered; 985 real POIs loaded through S01. Contract 1.2.0 test-fixture follow-up completed and reviewed: 290 tests passed and 11 isolated SQL tests skipped. See `handoffs/D02.md` for original delivery, follow-up checks, replay evidence, transfer artifacts and known limits.
- [x] S03 — real-corpus intent and retrieval delivered and reviewed: 985 OSM POIs indexed with 1536-dimensional embeddings; unchanged replay skipped all 985 without API calls. REVIEW fixed constraint preservation and concurrent index/import issues with focused checks; full SQL/provider checks were not repeated at the user's request. See `handoffs/S03.md`.
- [x] S04 — constraint checks, independent POI alternatives, safe localized explanations and transient event API v1.3 delivered and reviewed; commit preflight: 912 passed, 17 isolated SQL tests skipped without TEST_DATABASE_URL. Real POI output was verified; a positive live event card and D04 UI acceptance remain unverified. D03 dependency files are imported unchanged; see `handoffs/S04.md`.
- [ ] S05–S08 / D03–D08 — remaining stages are not marked complete here. D03 is available as an unchanged dependency; D04 integration/acceptance remains pending.

The user's 2026-10-19 S02 request replaces the original stage-02 backend scope
with optional 2GIS Places/walking integration previously listed under S04. This
delivery does not mark S04 complete or authorize further stages. The D02 handoff
is now available; S03 implementation, review, commit and push were explicitly
authorized on 2026-10-19. The user's amended S04 scope adds constraint checks,
explanations and the transient event API through the unchanged D03 normalizer;
S04 commit and push were subsequently authorized. Remaining stage allocation
needs coordination. No S05 work is included.

## User-requested POI follow-ups (2026-10-20)

- [x] POI-CONSTRAINTS / UNKNOWN-UI / CONSTRAINT-CLARIFICATIONS — preserve explicit place/event constraints, explain child/age/charging uncertainty and field corrections in kk/ru/en, and switch result language without another search.
- [x] POI-VISIT-FALLBACK / PLAYGROUND-SEARCH — adapt short walks and source-checked playground visits, evaluate later candidates within bounded work, and recognize generic playground/family-walk requests while retaining explicit restrictions.
- [x] POI-FEATURES implementation — validate and package a separate 22-playground source supplement, retain rights/provenance/check dates, and filter by supported facts. This completes the implemented supplement, not the original mixed family/cafe data request.
- [x] LOCAL-SEARCH — configure ignored local OpenAI/database settings and verify real Responses, embeddings, database retrieval and browser search.
- [ ] Mixed family/cafe data request — branch-specific customer charging evidence is still absent. The implemented catalog has no qualifying cafe; age, safety and other unsupported facts remain unknown.

Commit verification: **2008 backend/ingestion tests and 461 frontend tests passed**;
17 SQL tests require an isolated test database. Formatting, static/type checks,
contract generation, curated validation and the frontend production build passed.
Docker image verification is not_run because the local engine is unavailable.
See `handoffs/POI-CONSTRAINTS-COMMIT.md`. This follow-up does not complete any
additional S05–S08 or D03–D08 roadmap stage.

## Shared-file coordination

Sabyrzhan owns root configuration, shared backend dependencies and contracts.
Damir owns `frontend/`, `ingestion/`, `data/`, UI translations and
`backend/app/services/events/`. Keep ingestion/provider implementation out of
shared schema files. Ask the owner for changes via handoff notes, including
required fields, migration/API impact and a fixture showing the need.

Use separate branches/checkouts. Before each task read instructions and status;
never stage another contributor's changes. Commit each approved task separately.
Do not push or merge without an explicit command. No next-stage work begins
automatically from an approved task.
