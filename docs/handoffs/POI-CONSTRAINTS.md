# POI-CONSTRAINTS: short walks and unsupported requirements

Date: 2026-10-20, Asia/Qyzylorda. Contract: **1.3.0**, unchanged.
Branch: `codex/fix-poi-constraints`. Base: `9061865` (`origin/main` at creation).
Status: implemented, reviewed and checked locally; uncommitted and unpushed.

## Scope and baseline

The user requested fixes for 30-minute walks and lost child/charging requirements,
with checks but no commit or push. The managed worktree uses the newer remote
main, which already includes partial child/charging guards and their tests.
This change preserves that work, narrows false positives, improves messages and
adds adaptive walk duration. The original checkout and its local video are untouched.
No roadmap stage is marked complete.

## Behavior and flow

- `constraints.py` uses one suggested-duration helper before and after routing.
  Walks retain the default 30-minute visit when it fits, but may shorten to a
  minimum of 10 minutes. Entry and buffer each remain five minutes.
- Available time is the **total** interval. With a 30-minute cap and five minutes
  of known travel, the suggested visit is 15 minutes. Ten minutes of travel still
  fits with a 10-minute visit; ten minutes and one second does not.
- Requested outbound/return seconds are summed before rounding up once. Route
  metrics require an origin and sourced destination location. Unknown required
  legs leave total/travel unknown; a known leg can still prove a conflict.
- Other activity durations, explicit total-time lower bounds, source record
  durations, budgets, hours and indoor checks are preserved.
- Recognized child/age and charging phrases in kk/ru/en stop POI/event selection
  before provider/repository/routing methods. The extractor also retains explicit
  child/charging conditions in `interests` using canonical codes. A second guard
  consumes those interests before POI routing/card composition, and before event
  web discovery. The POI fallback runs after intent, embedding and retrieval; it
  does not claim those calls are avoided. Responses contain `unknown`, empty
  results and a localized API message naming the detected condition. Missing
  POI client configuration still returns unavailable under the existing policy.
- Device charging is distinguished from morning exercise/admission charges.
  Name-only searches such as `Children's Museum`, `Family Park`, `Балалар` and
  ballet remain searchable. Detection is bounded phrase matching, not a general
  semantic or negation parser.
- `recommend.py` supplies the same condition-specific messages to
  `event_recommend.py`. At this backend checkpoint the API, response schemas and
  frontend were unchanged, and condition-specific prose was API-only. The
  subsequently authorized [UNKNOWN-UI follow-up](UNKNOWN-UI.md) adds structured
  fields and localized UI explanations without changing the response shape.

## Files and dependencies

Production files: `backend/app/constraints.py`, `backend/app/recommend.py`,
`backend/app/event_recommend.py`, `backend/app/intent.py`.

Regression files: `backend/tests/test_short_walks.py` and
`backend/tests/test_requirement_preservation.py`, plus the review additions
`backend/tests/test_extracted_requirements.py` and
`backend/tests/test_requirement_event_http.py`. Tests cover inclusive second
boundaries, return legs, missing geography, opening windows, unchanged source
facts, service composition, both recommendation HTTP aliases, request IDs,
no-store, both event HTTP aliases, client cleanup, shared event behavior,
extracted requirements, language variants and ordinary named venues.

Current policy documentation: `docs/limitations.md`.
Dependencies, migrations, source data and public contracts: no changes.

## Verification

Commands ran from this worktree with the existing Python 3.12 environment at
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.
`python` below denotes that executable. No packages were installed.

```text
python -m pytest backend/tests ingestion/tests -q
  1336 passed, 17 skipped in 10.49 seconds
python -m ruff check backend scripts ingestion
  passed
python -m ruff format --check backend scripts ingestion
  passed, 87 files
python -m compileall -q backend/app scripts ingestion
  passed
import changed modules plus backend.app.api and backend.app.main
  passed
python scripts/export_contracts.py --check
  passed, 13 artifacts
python -m pip check
  no broken requirements
git diff --check
  passed
```

`TEST_DATABASE_URL` was removed only from the test subprocess environment;
17 isolated SQL tests skipped. The production database was not substituted.
HTTP integration used the ASGI app with synthetic provider/repository/route
doubles; it did not call live services. Live OpenAI/2GIS/database acceptance and
hosted deployment are **not_run**. Frontend files were not edited; no new full
frontend check is claimed.

Initial requirement regressions produced 14 expected failures on the inherited
baseline (child messages and overly broad name/exercise matching). The first
implementation checkpoint passed 1279 tests with 17 SQL skips. Its independent
checks found missing smartphone and explicit family phrases and covered them.

## Requested review and corrections

The subsequent review covered correctness, scope, errors, source/route handling,
concurrency, tests, readability, contract drift, secrets and documentation. No
SQL, migration, dependency, persistence or resource-lifecycle changes were needed.

- **P1, corrected:** narrowing charging detection lost ordinary requests without
  a device name, including `Кафе с зарядкой`, `Есть ли зарядка в кафе?` and
  `charging required`. With other synthetic facts known, these could acquire
  `ok/fits`. Contextual nominal phrases now retain the requirement while morning
  exercise and venue-name negatives remain searchable.
- **P2, corrected:** the narrowed age guard missed `6 жасқа лайық` and
  `Алты жасқа сай`. Both now produce the same child-suitability uncertainty as
  explicit child mentions, with service and HTTP regressions.
- **Requirement preservation, corrected:** model-extracted `interests` were not
  checked before fit evaluation. The second guard now consumes canonical codes
  and bounded aliases (space/hyphen/underscore), so indirectly phrased explicit
  conditions cannot be ignored after extraction. Named venues alone do not
  imply either condition. Clarification and unavailable branches keep priority.
- Independent review found no confirmed defect in adaptive walk arithmetic;
  145 focused walk/constraint tests passed. A second review of extracted guards
  passed 211 focused tests and found no additional confirmed issue.
- Event HTTP coverage now verifies both current aliases in kk/ru/en, no-store,
  correlation, empty unknown envelopes and client-context cleanup, without live
  discovery or database calls. The final full suite and all static checks above
  were repeated after the code corrections.

**Consumer limitation at this review checkpoint:** the frontend's `App.tsx` warning renderer
ignores API message prose and shows only generic localized codes/fields. That
behavior also exists on the base commit and was not changed by this backend
task. The documentation now says API explicitly instead of implying that the
new details appear in the UI. Next frontend consumer: Damir, to design localized
condition-specific display without replaying backend/provider prose or losing
language switching. This limitation is now addressed by the separately requested
[UNKNOWN-UI follow-up](UNKNOWN-UI.md). No teammate delivery or acknowledgement is claimed.

## Risks, study topics and next consumer

Source prices, opening hours and child/charging facts remain incomplete. This
change cannot establish those missing facts, and it does not guarantee that a
live route/provider is available. The ten-minute minimum is a product estimate,
not a sourced venue rule. Explicit total-time constraints are never increased.

Study topics: lower bounds under partial information; inclusive time arithmetic
and rounding; preserving requirements across raw text and structured extraction;
HTTP contract tests with deterministic doubles.

Three interview questions:

1. Why can a 30-minute request suggest only a 15-minute visit? The request caps
   the entire outing; travel, entry and buffer use the remaining 15 minutes.
2. Why can an unknown return leg reject a destination but never prove it fits?
   Its duration is unknown, while the already known duration can exceed the cap.
3. Why return unknown for a child-friendly cafe with charging? The corpus has no
   supported facts to verify either condition, even if category/time/budget fit.

Next consumer: the user for local review and a separately authorized live smoke
or commit. No commit, push, deployment or next roadmap task was started.
