# UNKNOWN-UI: localized unsupported-condition reasons

Date: 2026-10-20, Asia/Qyzylorda. Branch: `codex/fix-poi-constraints`.
Base commit: `9061865`; this follow-up preserves the existing uncommitted
POI-CONSTRAINTS work. Implemented and checked, without commit, push or deployment.

## Scope and flow

The user requested concrete unknown reasons for child suitability, age and device
charging in kk/ru/en, including language switching without another search.

1. The backend uses the same bounded detector for guard groups and detailed
   reasons. Age eligibility is distinguished from general child suitability;
   both can apply to one request. Raw text and extracted interests are supported.
2. `MissingField` gains `child_suitability`, `age_restrictions`, `power_outlets`.
   These travel through existing `Warning.fields` on POI and transient events;
   `status=unknown`, `code=missing_input` and object shapes remain unchanged.
3. `SearchWarnings` renders local dictionary text from the codes, with a common
   suggestion to confirm the conditions with the venue/organizer. It never parses
   or displays backend `warning.message`. Ordinary warning fields remain visible;
   duplicate fields within a warning are removed.
4. `useTranslation` derives text during render. Language changes keep the received
   response, use no new effect/state copy and make no search/route/provider call.
5. Older responses with absent/empty fields keep a safe generic warning. These
   responses are not reinterpreted from their prose or the user's query in the UI.

Age phrases such as `six-year-old child`, `для детей 6 лет`, `ребёнком шести лет`
and `6 жасар баламен` retain both child and age fields. Age-only requests retain
only age, and a generic child request does not invent an age condition. The UI
does not extract, transmit or store a numerical age separately.

## Important files

- `backend/app/constraints.py`: shared detailed detector and stable fields;
  `recommend.py` / `event_recommend.py`: populate warnings before card creation;
  `intent.py`: preserve three explicit condition codes; `schemas.py`: enum;
  `explain.py`: labels for the expanded missing-field vocabulary.
- `contracts/*.schema.json`, `contracts/codes.json`, `contracts/api-v1.md`:
  generated enum vocabulary and documented client behavior.
- `frontend/src/components/SearchWarnings.tsx`, `App.tsx`, `lib/types.ts`,
  the legacy `lib/event-search-response.schema.json` and kk/ru/en dictionaries.
- `backend/tests/test_unknown_requirement_fields.py`:
  113 helper/service/HTTP regressions, all four current HTTP aliases,
  combinations, extracted conditions, negatives, correlation and cleanup.
- `frontend/src/App.unknown-reasons.test.tsx`: nine complete HTTP/UI tests for
  separate/combined reasons, POI/events, language cycling, unchanged fetch/POST
  counts, older response fallback and hiding untrusted backend prose.

## Contract and dependencies

Contract/corpus version stays **1.3.0**. The warning enum extension adds no new
properties, endpoints, dependencies, migrations or persistent records. Existing
examples remain valid. Current generated schemas and the frontend's legacy
MissingField snapshot agree. The separate transient session-field vocabulary is
unchanged because these reasons belong to warnings, not event session facts.

An older strict UI may reject new enum values: deploy the updated backend and
frontend together. The new UI accepts older responses with generic warnings.
No live deployment or provider acceptance is claimed.

No packages were installed. The frontend lockfile matches the original checkout
(SHA-256 checked); its existing `node_modules` is reused through an ignored
worktree junction. Backend checks use the existing Python 3.12 environment at
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`.
The original checkout and its untracked demo video remain untouched.

## Checks

Run from the worktree root (`python` means the existing executable above):

```text
python -m pytest backend/tests ingestion/tests -q
  1449 passed, 17 skipped in 13.62 seconds
python -m ruff check backend scripts ingestion
  passed
python -m ruff format --check backend scripts ingestion
  passed, 88 files
python -m compileall -q backend/app scripts ingestion
  passed; imports of changed modules and backend.app.main passed
python scripts/export_contracts.py --check
  passed, 13 generated artifacts
git diff --check
  passed
```

From `frontend/`:

```text
npm.cmd test
  320 passed, 20 files in 19.38 seconds
npm.cmd run test:types
  passed
npm.cmd run lint -- src scripts vite.config.ts vitest.config.ts
  passed; explicit paths cover source, scripts and configs without traversing the junction
npm.cmd run check:contracts
  passed, including legacy schema compatibility
npm.cmd run format:check
  passed
npm.cmd run build
  passed, 72 modules
npm.cmd run check:build
  passed, four output files, no development fixtures or server credential names
```

`TEST_DATABASE_URL` was removed only from the test subprocess environment;
17 isolated SQL checks skipped. No production DB was substituted. Provider and
repository doubles are synthetic. OpenAI/2GIS/live database checks are **not_run**.

A temporary loopback server served the production bundle with synthetic backend
dependencies. Browser QA submitted a clearly marked TEST ONLY request and showed
all three Russian reasons plus the next-action guidance, without real GPS or
provider calls. The preview was closed after inspection. The full UI tests cover
kk/ru/en translation and prove no additional fetch/search on language changes.

Independent review checked schema/type/dictionary parity, event adaptation,
local rendering and raw-message isolation. It found four age formulations where
only the child reason was retained; these were fixed and regression-tested before
the final full checks. No other confirmed issue remained in this scope.

## Limits, study and next consumer

The change explains missing evidence; it does not prove child admission, age
eligibility or the existence/type of charging. Phrase detection is bounded and
indirect phrasing still depends on model extraction. No source facts are invented.

Study topics: structured error metadata, local translation from stable codes,
derived React rendering, schema compatibility and HTTP/UI integration tests.

Three interview questions:

1. Why does changing language need no search? The response stores stable codes;
   rendering translates them using the current local dictionary.
2. Why ignore `warning.message`? Server prose can be in the previous language or
   contain untrusted content; a controlled code maps to tested local UI text.
3. Why can one request have two child-related reasons? General suitability and
   age admission rules are independent facts, and either may remain unconfirmed.

Next consumer: user review, then a separately authorized coordinated backend/UI
release. No roadmap task is marked complete and no next feature was started.
