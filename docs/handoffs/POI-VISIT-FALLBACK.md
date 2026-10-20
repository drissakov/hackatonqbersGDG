# POI short playground visits and progressive candidate checks

## Scope and state

User request: fix short playground visits and check later candidates when the
first three do not fit; add tests and run checks, without commit or push.

Worktree: `codex/fix-poi-constraints`, HEAD `9061865`. Earlier uncommitted
constraint, localization and source-supplement work was preserved. The original
checkout stays on `main` at `350917c` with only its pre-existing untracked demo
video. This task does not mark a roadmap stage complete.

## Changes and flow

- `backend/app/constraints.py` adds a keyword-only `playground=False` policy
  argument to suggested visit calculation, cheap rejection and final evaluation.
  `recommend.py` sets it only from positive source-checked
  `family_playground` evidence on the candidate. A generic entertainment
  category, name or user phrase cannot activate it.
- Source-checked playground visits keep the existing 45-minute default but can
  shrink to 10 minutes. The available window reserves five minutes for entry,
  five minutes buffer and the rounded-up sum of known requested route seconds.
  A 30-minute total with two minutes outbound allows an 18-minute visit; two
  outbound plus three return minutes allow 15. Missing legs remain unknown.
  Opening checks use the shortened visit. Source duration fields and other
  non-walking activity policies remain unchanged.
- `backend/app/recommend.py` removes known cheap conflicts, deduplicates POI IDs
  and then evaluates candidates in retrieval order until three non-rejected
  alternatives are available. A rejected time/opening candidate no longer
  prevents a later candidate from being checked. Unknown conditional cards count
  as alternatives, with their existing missing facts and warnings.
- Work is bounded to twelve candidate evaluations and a 54-second aggregate
  route deadline, preserving the old worst-case three-by-18-second route wait.
  Each destination retains its 18-second timeout and independent requested
  return leg. There are no route retries; at most 24 legs can be requested.
- A count/deadline limit preserves completed cards as partial with a localized
  kk/ru/en data-unknown warning, or returns unknown when no completed card exists.
  A canceled in-progress route does not publish an unchecked card. A completely
  evaluated ordinary retrieved pool can return no-match; the limited source
  supplement still returns unknown if exhausted without an alternative.
- `contracts/api-v1.md` and `docs/limitations.md` describe the new visit and
  search behavior. The earlier `POI-FEATURES.md` is historical; this handoff
  supersedes its fixed three-route-shortlist description.

No frontend implementation, API/schema/codes, contract version, data snapshot,
database migration, embedding index, event selection or dependency changes were
needed. Contract **1.3.0** remains unchanged. The existing API/card/UI already
accept the suggested duration and data-unknown warnings.

## Tests and review

Three new files add **68 regressions**:

- `backend/tests/test_short_playgrounds.py`: 32 checks for visit floors, travel
  seconds/rounding, independent return, missing geography/legs, opening windows,
  explicit minimum time and unchanged source/default policies.
- `backend/tests/test_candidate_fallback.py`: 19 checks for the fourth and later
  candidates, filling/stopping at three, duplicate IDs, preserved hard filters,
  unknown cards, full versus limited exhaustion, count/deadline limits, route
  cancellation, independent return and both HTTP aliases.
- `backend/tests/test_playground_recommendations.py`: 17 service/HTTP checks
  using the real 22-record catalog and explicitly synthetic providers. Includes
  kk/ru/en, both aliases, JSON Schema/Pydantic, no-store, source preservation and
  unchanged age/quiet/private guards.

The existing five-closed-place regression now expects no-match only after all
five routes are checked. New cap/deadline cases retain unknown for an unexamined
tail. No assertion was weakened to conceal an untested remainder.

Independent read-only reviews of visit/proof integration, bounded fallback and
new tests found no remaining confirmed issue. Initial tests were red before
integration and passed after the production fixes. Initial Ruff reported one
overlong English message; splitting the identical string fixed it.

## Commands and results

Run from repository root with the existing development environment. Actual
interpreter:
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.

| Command/check | Result |
| --- | --- |
| `python -m pytest backend/tests/test_candidate_fallback.py backend/tests/test_playground_recommendations.py backend/tests/test_recommend.py backend/tests/test_short_walks.py backend/tests/test_short_playgrounds.py backend/tests/test_poi_features.py -q` | 229 passed, 3.64 s |
| `python -m pytest backend/tests ingestion/tests -q` | **1816 passed, 17 skipped, 13.80 s** |
| `python -m ruff check backend scripts ingestion` | passed after message wrapping |
| `python -m ruff format --check backend scripts ingestion` | passed, 96 files |
| `python -m compileall -q backend/app scripts ingestion` | passed |
| import `backend.app.main`, `backend.app.recommend`, `backend.app.constraints` | passed |
| `python -m pip check` | passed |
| `python scripts/export_contracts.py --check` | passed, 13 artifacts |
| `python -m ingestion.curated validate` | passed: 22 records, 11 known public access |
| `npm.cmd run check:contracts`, from `frontend/` | passed, v1.3.0 and legacy snapshot |
| `git diff --check` | passed |

The final pytest subprocess removed `TEST_DATABASE_URL` from its own environment;
the 17 skipped SQL integration checks require an isolated test database. Nothing
connected to a production database. JSON Schema/Pydantic and observable HTTP
behavior were exercised by the new tests.

No live OpenAI/2GIS request was made. Real catalog acceptance used deterministic
intent, explanation and route doubles; it is not live-provider or on-site
verification. Full frontend tests/build and Docker smoke were not repeated for
this backend-only follow-up. The previous frontend run remains historical,
and the previously unavailable Docker daemon was not reconfigured.

## Limits, next consumer and study

The 10-minute playground minimum and 45-minute default are product estimates,
not source facts or age/safety guarantees. Unknown route/access/price/hours stay
conditional. The twelve-candidate cap is deliberate; a suitable later candidate
can remain unexamined when the count/time budget expires. The route budget does
not include intent, embedding or explanation time. No quietness, cafe charging,
age eligibility, landmark geocoding or broader family venue data was added.

Study: evidence-controlled policy selection; immutable source facts versus
suggested duration; cheap hard filters before provider calls; count and monotonic
time budgets; cancellation; honest exhaustion and incomplete-search states.

1. **Why does an ordinary entertainment venue keep 45 minutes?**
   Its category does not prove a playground. Only a candidate's positive
   source-backed playground evidence enables the flexible policy.
2. **Why does an unknown return leg not make a 30-minute trip fit?**
   Known travel can reduce the upper visit budget, but the missing leg prevents
   a confirmed total. It stays unknown and cannot be replaced with zero.
3. **Why is exhausting the first three no longer enough for no-match?**
   More retrieved candidates may fit. The loop checks later candidates within
   its budget and distinguishes a fully checked pool from an unexamined tail.

Next consumer: user review and separately authorized publication/live acceptance.
The separately identified location-from-text and richer data/explanation work
remains outside this change. Nothing is staged; no commit, push or deployment
was performed.
