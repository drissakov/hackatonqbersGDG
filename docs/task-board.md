# Qadam Astana task board

Each contributor has **24 active hours** (48 person-hours total). Windows are
relative to that contributor's start; they are not promises of wall-clock time.
S00, S01 and the amended S02 were explicitly authorized in this chat. Later rows
are coordination plans, not authorization to implement them. Owners must confirm
scope at handoff.

| Stage | Active hours | Sabyrzhan task and ownership | Damir task and ownership | Dependency / exit gate |
| --- | --- | --- | --- | --- |
| 00 | 0–1 (1h) | S00: shared contract, server/settings/client interfaces, safe preflight, keyless health | D00: frontend scaffold and kk/ru/en foundation | Common contract + runnable health delivered for D01 |
| 01 | 1–3 (2h) | S01: Supabase schema, PostGIS/pgvector migrations, POI repository implementation | D01: contract-based search form/cards, API transport and fixture states | Use S00 upsert and HTTP contracts; health already belongs to S00 |
| 02 | 3–6 (3h) | S02: optional 2GIS Places and independent walking routes, per the user's scope amendment | D02: automatic permitted Astana-wide ingestion/data and coverage report | Runtime rights/access gates; route contract v1.2; no unlicensed 2GIS corpus |
| 03 | 6–9 (3h) | S03: embedding/RAG retrieval and source grounding | D03: frontend recommendations and language rendering | Real records and 1536-dimension embeddings; no invented facts |
| 04 | 9–12 (3h) | S04: optional 2GIS route integration and time-fit checks | D04: event ingestion/services and separate event/session view | Shared contracts owned by Sabyrzhan; event service owned by Damir |
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
- [ ] S03–S08 / D02–D08 — planned, not implemented here.

The user's 2026-10-19 S02 request replaces the original stage-02 backend scope
with optional 2GIS Places/walking integration previously listed under S04. This
delivery does not mark S04 complete or authorize further stages. S03 waits for
D02 and separate authorization; remaining stage allocation needs coordination.

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
