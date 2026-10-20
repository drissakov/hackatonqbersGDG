# POI constraints commit and local merge handoff

## Authorization and scope

On 2026-10-20 the user authorized committing the accumulated fixes and merging
them. The selected source branch is `codex/fix-poi-constraints`, based on
`9061865`. The target is local `main`, initially `350917c`. Push, remote merge
and deployment are outside this operation. Local configuration stays ignored.

The integrated change covers the user's earlier POI constraint fixes, localized
unknown reasons and place/event corrections, source-checked feature filtering,
short visits, bounded evaluation of later candidates, and playground query
recognition. Its earlier task handoffs remain historical verification records.
The task board marks only these follow-ups complete; the missing cafe charging
dataset and later roadmap stages remain incomplete.

## Files and request flow

- `backend/app/intent.py`, `playground_intent.py`, `retrieval.py`,
  `constraints.py` and `recommend.py` retain explicit constraints, select
  eligible source-backed candidates, evaluate known time/route facts and
  preserve unknown or unavailable outcomes.
- `backend/app/poi_features.py` and `ingestion/curated.py` validate the
  separately packaged 22-playground supplement. `data/curated/` retains the
  permitted OSM projection, ODbL rights, source versions, dates and audit.
- `backend/app/event_recommend.py`, `schemas.py` and generated `contracts/`
  carry structured unknown and correction metadata for places and events.
- `frontend/src/components/SearchWarnings.tsx`, `FeatureFacts.tsx`, `App.tsx`,
  API validation/types and kk/ru/en dictionaries render that metadata locally.
  Changing language re-renders an existing result without a provider request.
- Docker packages the production catalog; CI includes ingestion validation.
  Tests cover these paths and their failure/unknown behavior.

API/corpus contract remains 1.3.0 with additive response metadata. Deploy backend
and frontend together because strict response clients must agree. There are no
new dependencies, endpoints, database migrations, corpus imports or reindexing.
Source content remains separate from generated explanations.

## Final verification

Commands ran from the source worktree using the existing Python development
runtime under the `readme-current-state` worktree and Node/npm under
`C:/Program Files/nodejs/`. No checks used production database writes.

| Check | Result |
| --- | --- |
| `python -m pytest backend/tests ingestion/tests -q` | 2008 passed, 17 skipped, 37.66 s |
| `python -m ruff check backend scripts ingestion` | passed |
| `python -m ruff format --check backend scripts ingestion` | passed, 100 files |
| `python -m compileall -q backend/app scripts ingestion` | passed |
| Import main, playground policy, features, recommendations, retrieval and curated modules | passed, six modules |
| `python -m pip check` | passed |
| `python scripts/export_contracts.py --check` | passed, 13 artifacts |
| `python -m ingestion.curated validate` | passed, 22 real records / 11 explicit public-access facts |
| `python -m pytest ingestion/tests/test_curated.py -q` | 43 passed, 2.37 s; also included in the full suite |
| `npm run lint` | passed |
| `npm run test:types` | passed |
| `npm run check:contracts` | passed |
| `npm run format:check` | passed |
| `npm test` | 461 passed across 24 files, 46.82 s |
| `npm run build` | passed, 73 modules |
| `npm run check:build` | passed, four files; no fixture payloads, environment files, server credential names, development backend URLs or source maps |
| `git diff --check` | passed |

The 17 SQL tests were skipped because `TEST_DATABASE_URL` is absent. The ordinary
database URL was not substituted for an isolated test database. Docker image
build/smoke remains not_run: the CLI is installed but its engine is unavailable.
Code review covered backend, frontend, contracts, data rights, CI and packaging;
no blocking defect was identified. The staged file list, concurrent changes and
secrets must be checked immediately before the commit.

Real external evidence from the immediately preceding configuration task is
recorded in `LOCAL-SEARCH.md`: database/PostGIS/pgvector, Responses and
1536-dimensional embeddings passed; coverage returned 985 real indexed POIs and
zero test POIs; a real museum HTTP request returned three sourced alternatives
in 14.70 seconds, and browser searches displayed real results. No additional
paid probe was needed for committing the same code.

## Known limits and next consumer

The requested mixed dataset is incomplete: the supplement contains 22
playgrounds and zero cafes with qualifying customer charging evidence. Child
age admission and safety, quietness, accessibility and other unsupported facts
remain unknown. Text landmark geocoding and general disjunctive or ambiguous
venue requirements remain follow-up work. Unknown routes, prices or hours do
not establish a confirmed fit. The supplement does not expand the measured
coverage of the existing indexed city corpus.

Next consumer: use the locally merged main branch; publishing or deploying
requires a separate request. No next feature is started by this commit.

Study topics: explicit constraints versus model extraction; evidence-backed
facts versus generated text; bounded candidate work; local rendering of stable
reason codes; fast-forward Git integration and ignored local configuration.

1. **Why can a 30-minute request offer a shorter visit?** Entry, buffer and
   known walking legs consume part of the total window; the visit estimate
   adapts without treating unknown travel as zero.
2. **Why can language change without another search?** Structured codes and
   evidence stay in result state; local dictionaries render them in kk/ru/en.
3. **Why are local credentials excluded from the merge?** They belong to each
   runtime's ignored configuration, while the repository carries safe examples
   and validation code only.
