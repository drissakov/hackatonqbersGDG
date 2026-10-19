# Runtime integration and Render handoff

Date: 2026-10-19, Asia/Tashkent. Contract: 1.3.0.

## Authorized scope and working copy

The user requested verification of the latest GitHub version, then authorized
the remaining runtime fixes and deployment so the application can work without
a VPN on the user's computer. Existing local credentials were provided through
ignored files. No credential value is included in this handoff.

The original checkout remains on `feature/s04-constraints-explanations` at
`a20e14e`. Implementation is isolated on `fix/runtime-integration`, based on
`origin/main` at `181e012`. No roadmap item is marked complete. No migration,
import, embedding generation or new dependency is part of this implementation.
After review and successful checks, the user explicitly authorized one focused
commit, push of `fix/runtime-integration` and Render deployment on 2026-10-19.
Merging into main remains outside this authorization.

## Confirmed runtime defects and fixes

- The frontend validated `/api/events/search` against its older integration
  snapshot, rejecting the published flat transient v1.3 response. It now checks
  the shared generated schema, preserves the real transient source rights and
  displays conditional sessions, separate listings and unavailable/unknown states.
- The frontend contract checker now checks the actual published transient wire
  schema. Shared fixtures exercise HTTP status, correlation, locale, citations,
  unknown tickets, lower-bound prices and source references.
- Every non-null `price_from`, including regular and promotional prices, remains
  a lower bound in the UI. Extra listing sessions/diagnostics are preserved;
  fully represented listings are not duplicated.
- Walking response parsing now accepts the live provider's summary response
  (`length` and `duration`) and the documented detailed metric pair. Incomplete
  or mixed pairs remain invalid; timeout and resource-cleanup behavior is unchanged.
- Route provider attribution uses `2ГИС` and the provider's developer website.

## Map behavior

`DestinationMap.tsx` provides a local SVG coordinate plot of the origin and up to
three destinations. It contains no road tiles or route geometry. Manual WGS84
entry and one-shot browser geolocation do not require a map key. There is no
Leaflet, MapLibre or locally stored OpenStreetMap basemap in this frontend.

`VITE_TWOGIS_MAP_KEY` is optional and remains empty. It only enables the external
street basemap and click-to-select interaction. The OSM POI corpus is independent
of map rendering. A browser map key is not a server routing key.

## 2GIS demo runtime decision

The owner confirmed in this chat on 2026-10-19 that the supplied server key is
a demo key with Routing API enabled and a limit of 1000 requests per month.
The review uses that project-specific confirmation together with the provider's
[key documentation](https://docs.2gis.com/platform-manager/subscription/keys),
[Routing API documentation](https://docs.2gis.com/api/navigation/routing/overview)
and [published offer](https://law.2gis.ru/offer-license-agreement-webapi).

The enabled scope is bounded, ephemeral pedestrian route summaries for the
Qadam Astana demo. `TWOGIS_ENABLED` and `TWOGIS_ROUTING_ALLOWED` are enabled in
the hosted runtime with this evidence recorded in `TWOGIS_RIGHTS_BASIS`.
Places and discovery remain disabled. No catalog storage, caching into the POI
corpus, embeddings or indexing rights are inferred. Route payloads, coordinates,
key-bearing URLs and provider exception bodies are not written to reports.
No provider account/tariff purchase or change was performed.

## Render deployment

- URL: https://qadam-astana.onrender.com
- Workspace: Qbers.
- Service: `srv-dbav9fmq1p3s73d8e410`, Docker, Frankfurt, explicitly free plan.
- Source: `https://github.com/drissakov/hackatonqbersGDG`, branch `main`.
- Automatic deployment: disabled. Database pool: three connections, one process.
- Health path: `/api/health`. Server reads Render's actual `PORT`.
- Server credentials are runtime environment variables, never frontend values.
- The Render management token stays in the ignored original `.env.deploy.local`.

The first image built successfully, but its temporary compound diagnostic command
was interpreted incorrectly by Render and exited 127. The override was cleared;
the normal image CMD then started successfully. Live bootstrap deployment:
`dep-dbavad6q1p3s73d8heq0`, commit `181e012`, status `live`.

This bootstrap uses the existing remote main. The local event and walking fixes
are not claimed to be published until they are committed, pushed and deployed.
The repository's separate commit/push authorization was received before publication.

## Actual verification so far

- Hosted `/api/health` and SPA: HTTP 200.
- Hosted coverage: HTTP 200; 985 real OSM POIs, all located and embedded, zero
  test POIs, and `city_coverage=unknown`.
- Hosted unknown API and invalid query: sanitized HTTP 404 and 422.
- Hosted Russian museum, Kazakh park and English cafe/budget queries: HTTP 200,
  three real alternatives each, valid shared response contracts and partial fit
  where hours, prices, travel or user inputs are unknown.
- Hosted one-minute museum request: HTTP 200 `no_match`.
- Hosted explicit/text time conflict: HTTP 200 `unknown`, clarification required.
- First hosted event query: safe HTTP 503 `web_search_citations_missing`.
  A second English opera query completed web search with 19 transient sources,
  HTTP 200 `unknown/no_grounded_events`, no confirmed session/card. No positive
  live event card is claimed.
- Bootstrap walking HTTP: safe 503 `invalid_response`; live shape diagnostics
  identified summary field names as the parser mismatch. A second direct live
  call through the corrected adapter returned `known`, valid metrics and ephemeral
  provenance. Those diagnostics used two Routing API calls in total, with no raw
  response storage. Corrected hosted route verification awaits publication.
- Local corrected frontend against hosted API: a real museum search rendered
  three cards and the keyless coordinate map.

## Commands and checks

Run from the isolated worktree using the existing Python 3.12 environment:

```powershell
C:\Users\Admin\hackatonqbersGDG\.venv\Scripts\python.exe -m compileall -q backend/app scripts ingestion
C:\Users\Admin\hackatonqbersGDG\.venv\Scripts\python.exe -m pytest -q backend/tests ingestion/tests
C:\Users\Admin\hackatonqbersGDG\.venv\Scripts\python.exe -m ruff check backend scripts ingestion
C:\Users\Admin\hackatonqbersGDG\.venv\Scripts\python.exe -m ruff format --check backend scripts ingestion
C:\Users\Admin\hackatonqbersGDG\.venv\Scripts\python.exe scripts/export_contracts.py --check
```

After the walking parser fix, the complete Python suite passed 917 tests;
17 real SQL integration tests skipped without `TEST_DATABASE_URL`. The focused
2GIS suite passed 69 tests. Compile, Ruff, formatting, generated-contract drift
and whitespace checks passed. Windows sandbox socketpair restrictions require an
authorized test run outside the sandbox; this is not an app failure.

Frontend checks, run from `frontend/`:

```powershell
npm.cmd run test
npm.cmd run test:types
npm.cmd run check:contracts
npm.cmd run lint -- src scripts vite.config.ts vitest.config.ts
npm.cmd run format:check
npm.cmd run build
npm.cmd run check:build
git diff --check
```

All frontend checks passed; full suite: 285 tests in 16 files. Targeted contract,
UI, route, price and listing regressions: 52 passed. The explicit lint paths
avoid traversing the reused node_modules junction in this isolated worktree.

## Limits and next consumer

The free Render instance can sleep when idle. Unknown facts and provider failures
remain visible; event search is a bounded sample, not complete city coverage.
The demo key's quota and lifetime remain external service limits. No weather,
multi-stop itinerary, account, persistent event corpus or later roadmap feature
was added. The next consumer is publication/redeployment of this reviewed fix,
followed by the same hosted HTTP/browser checks.
