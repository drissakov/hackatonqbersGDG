# Playground query recognition handoff

## Scope and working state

User request: fix playground searches for generic playground phrases and walks
with a child, preserve explicit constraints, add kk/ru/en tests and run checks.
No commit or push was authorized.

Implemented in `codex/fix-poi-constraints`, HEAD `9061865`. Previous uncommitted
constraint, source-data, localization, short-visit and progressive-candidate
changes remain intact. The original checkout stays on `main` at `350917c`,
with only its pre-existing untracked demo video. No roadmap stage is marked
complete and nothing is staged.

## Behavior and files

1. New `backend/app/playground_intent.py` recognizes direct playground phrases
   and generic walks with a child from bounded kk/ru/en raw wording. These do not
   depend on extraction retaining the child-interest code. Extracted interests
   alone cannot introduce a playground request absent the corresponding raw text.
2. `backend/app/retrieval.py` uses the source supplement for these requests.
   Compatible empty/walk/entertainment categories may gain entertainment as a
   destination category, while keeping the walk activity. The copied resolved
   intent is used consistently in both retrieval and final constraint evaluation.
   Time, budget, date, origin, indoor and return fields are unchanged.
3. Explicit park, museum, cafe and other venue types remain restrictive even if
   extraction lost their category. Non-walk extracted categories remain strict.
   The guard includes Kazakh cafe inflections such as `кафеде`. These requests
   are not silently replaced with a generic playground.
4. Exact generic playground descriptors accidentally placed in extracted name
   filters can be removed only without an explicit naming construction. Actual
   names remain filters; an explicit name lost entirely by extraction yields
   unknown. Double, guillemet, ASCII single and curly-single quote guards are
   consistent. Names such as a cafe called Playground do not independently
   introduce a positive playground requirement.
5. `backend/app/poi_features.py` requires a non-derived source-backed name for
   named-place matching. A technical `Unnamed playground` label cannot prove
   that the user-requested name matched.
6. `backend/app/recommend.py` requires positive source-backed playground evidence
   for direct queries, including when the raw child guard missed the phrase.
   A missing catalog never falls back to treating generic entertainment as a
   playground. Recognized playground exclusions return localized unknown before
   providers rather than an unrelated positive match from ordinary retrieval.
7. `backend/app/intent.py` clarifies the extraction instruction: a generic type
   is not a venue name; a walk activity and a playground destination can coexist;
   explicit other venue requirements must be kept.
8. `README.md`, `contracts/api-v1.md` and `docs/limitations.md` describe the
   updated behavior and bounded-language limitations.

Age, quietness, charging and accessibility remain unknown without evidence.
Known private access, distance, time, price, indoor, opening and independent
return checks are preserved. Source records, suggested short-visit policy and
the twelve-candidate/54-second progressive-check limits are unchanged.

## Regression coverage and review

New tests add **192 cases**:

- `backend/tests/test_playground_intent.py`: **105** phrase, exclusion, category,
  naming, quote-style and morphology checks.
- `backend/tests/test_playground_search.py`: **54** real-catalog/service checks,
  including generic and family-walk requests, names, explicit venue types,
  missing catalog, negative queries with a nonempty ordinary database, ordinary
  named-cafe retrieval and all other hard constraints.
- `backend/tests/test_playground_search_http.py`: **33** checks for both HTTP
  aliases, kk/ru/en, actual 22-record source data, JSON Schema/Pydantic,
  no-store and unchanged explicit form controls.

The real catalog tests use deterministic extraction/explanation/routing doubles;
they do not simulate source places as fictional city data. A 30-minute request
with a two-minute route gives an 18-minute suggested visit; a two-plus-three-minute
requested return trip gives 15 minutes. Unknown price/indoor values remain
missing fields, not confirmed budget/indoor reasons.

Review found and closed related constraint gaps: a lost explicit name; derived
labels satisfying a named search; negative queries falling through to nonempty
ordinary retrieval; a venue name containing Playground becoming a type request;
single-quoted names escaping the name guard; and an inflected Kazakh cafe type
being dropped. Tests failed before the corresponding fixes and passed afterward.
An initial overlong Kazakh message was wrapped without changing its value.
No remaining confirmed issue was found in the final reviewed paths.

## Contracts and dependencies

API/corpus contract remains **1.3.0**. No request/response schema, enum, endpoint,
frontend implementation, dependency, migration, source snapshot, database write
or re-embedding was introduced. Response contract artifacts have no generated
drift. The frontend already displays the existing cards, durations and unknown
warnings; no frontend implementation or translation file changed in this task.

## Verification

Run from repository root using the existing Python development environment:
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.

| Command/check | Result |
| --- | --- |
| `python -m pytest backend/tests/test_playground_intent.py backend/tests/test_playground_search.py backend/tests/test_playground_search_http.py -q` | **192 passed**, 3.26 s |
| `python -m pytest backend/tests ingestion/tests -q` | **2008 passed, 17 skipped**, 16.02 s |
| `python -m ruff check backend scripts ingestion` | passed |
| `python -m ruff format --check backend scripts ingestion` | passed, 100 files |
| `python -m compileall -q backend/app scripts ingestion` | passed |
| import main, playground_intent, retrieval and recommend modules | passed |
| `python -m pip check` | passed |
| `python scripts/export_contracts.py --check` | passed, 13 artifacts |
| `python -m ingestion.curated validate` | passed, 22 records / 11 known public access |
| `npm.cmd run check:contracts` from `frontend/` | passed, v1.3.0 and legacy snapshot |
| `git diff --check` | passed |

The final pytest subprocess removed `TEST_DATABASE_URL` only from its own
environment. The 17 skipped SQL checks need an isolated test database; there
were no production database connections. Full runs were repeated after actual
review fixes, not counted as additional test coverage.

Live OpenAI/2GIS, Docker and on-site acceptance are **not_run** for this change.
Full frontend tests/build were not repeated because implementation and wire
shape are unchanged; the shared frontend contract check passed. No commit,
push, deployment, provider reconfiguration or production data mutation occurred.

## Limits, study and next consumer

This is bounded phrase normalization, not general language understanding.
Ambiguous combinations of venue types, free-form naming and unsupported
requirements may remain unknown. A playground source tag does not prove a
child's age admission or safety. Missing cafe charging facts, richer family
venue data, landmark geocoding and place-specific explanations remain separate
work.

Study: activity versus destination category; preserving immutable raw input and
explicit constraints; exact generic aliases versus proper names; source-backed
matching; conservative unknown; behavior-level multilingual HTTP tests.

1. **Why may a walk with a child return a playground?**
   Walking describes the outing, and a playground is one compatible destination.
   A literal park, museum or cafe requirement still blocks that substitution.
2. **Why can a derived name not satisfy a named-place restriction?**
   It was created for display and is not evidence of the source's actual name.
   Matching it would replace the requested place with an unrelated object.
3. **Why return unknown when a requested name or negative constraint is lost?**
   The system has not established that an alternative obeys the request.
   Returning generic places would silently weaken an explicit condition.

Next consumer: user review and separately authorized publication/live acceptance.
No next feature was started.
