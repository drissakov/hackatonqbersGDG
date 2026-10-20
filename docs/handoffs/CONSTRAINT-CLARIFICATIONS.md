# CONSTRAINT-CLARIFICATIONS: actionable input corrections

Date: 2026-10-20, Asia/Qyzylorda. Branch: `codex/fix-poi-constraints`.
Base commit: `9061865`. This task preserves the existing uncommitted
POI-CONSTRAINTS and UNKNOWN-UI changes. No commit, push or deployment is authorized.

## Problem and resulting flow

POI and transient event searches previously put clarification field names only
inside `warning.message`. The UI deliberately hides this untrusted prose, leaving
only a generic warning with no indication of what the user should correct.

1. Structured intent conflicts now use the six bounded `ExplicitField` codes.
   The prompt requires these codes for ambiguity as well as contradictions,
   including unsupported budget units and unresolved date/time expressions.
2. `IntentResult` retains the clarification fields and internally distinguishes
   numerical fields still missing after the two allowed extraction attempts.
   Known conflicts are preserved when a numerical field was not parsed. If both
   reasons apply to the same field, the known conflict takes priority.
3. The shared helper creates deduplicated `ConstraintClarification` entries:
   `field` plus `conflicting_constraints` or `unparsed_constraint`. No query,
   coordinate, numerical value or provider prose is added to this metadata.
4. Both search services return `unknown`, no cards, and `missing_input` with
   `warnings[].clarifications`. Retrieval, embedding, routes and event discovery
   stop after intent clarification. No constraint is changed or discarded.
5. The frontend validates the wire response before applying missing list
   defaults, then renders actionable dictionary sentences and resubmit guidance.
   Translations are derived during render, so kk/ru/en switching uses the existing
   response and makes no additional network request.

## Important files

- `backend/app/intent.py`: typed conflict codes, combined clarification reasons
  and shared metadata helper.
- `backend/app/schemas.py`: `ClarificationReason`, `ConstraintClarification` and
  optional/default-empty `Warning.clarifications` (at most six entries).
- `backend/app/recommend.py` and `event_recommend.py`: both consumer paths;
  generic backend prose no longer embeds raw internal field labels.
- `scripts/export_contracts.py`, `contracts/`: generated models and vocabulary.
- `frontend/src/lib/types.ts`, `api.ts`, legacy schema snapshot and
  `frontend/scripts/check-contracts.mjs`: strict parsing, default normalization,
  shared enum/model parity and complete locale sentence coverage.
- `frontend/src/components/SearchWarnings.tsx` and kk/ru/en dictionaries:
  field-specific corrections, independent of backend prose.
- `backend/tests/test_constraint_clarifications.py`,
  `frontend/src/App.clarifications.test.tsx` and
  `frontend/src/lib/api.clarifications.test.ts`: regressions at the intent,
  service, HTTP and complete UI boundaries. Existing expected response defaults
  and synthetic fixture helpers were updated without modifying raw examples.
- `contracts/api-v1.md` and `docs/limitations.md`: current behavior and limits.

## Contract, dependencies and compatibility

Contract/corpus version remains **1.3.0**. No endpoints, requests, dependencies,
migrations, persistent records or source rights change. This adds one optional
warning property and a reason-code vocabulary. Missing `clarifications` on older
responses becomes `[]`; explicit null, unknown codes, unexpected properties and
more than six entries are rejected. `Warning.fields` remains missing-fact
metadata, including the already implemented child/age/charging explanations.

The legacy persistent-event schema snapshot retains its discovery-only
definitions and receives the shared clarification definitions. Route warning
parsing also accepts the shared default shape without inventing corrections.

Older strict clients reject the new warning property. Backend and frontend must
be released together. This task makes no live deployment or provider claim.

## Verification

Run from the worktree root using the existing Python 3.12 executable at
`C:/Users/Ilytsm/.codex/worktrees/readme-current-state/hackatonqbersGDG/.venv/Scripts/python.exe`:

```text
python -m pytest backend/tests ingestion/tests -q
  1598 passed, 17 skipped in 19.21 seconds
python -m ruff check backend scripts ingestion
  passed
python -m ruff format --check backend scripts ingestion
  passed, 89 files
python -m compileall -q backend/app scripts ingestion
  passed
imports of backend.app.intent, schemas, recommend, event_recommend and main
  passed
python scripts/export_contracts.py --check
  passed, 13 generated artifacts
python -m pip check
  passed, no broken requirements
git diff --check
  passed
```

From `frontend/`, using the existing lockfile-matched dependency junction:

```text
npm.cmd test -- --reporter=dot
  406 passed, 22 files in 18.31 seconds
npm.cmd run test:types
  passed
npm.cmd run lint -- src scripts vite.config.ts vitest.config.ts
  passed; explicit paths avoid traversing the dependency junction
npm.cmd run check:contracts
  passed; shared/legacy schema parity, new model/reason codes and locale coverage
npm.cmd run format:check
  passed
npm.cmd run build
  passed
npm.cmd run check:build
  passed, four production files; no fixtures, server credential names, environment
  files, source maps or development backend URLs
```

The new focused files add 149 backend regressions and 86 frontend checks
(10 complete HTTP/UI scenarios plus 76 parser cases). HTTP tests exercise both
POI aliases and both current transient event aliases with request correlation,
no-store headers and client cleanup. Raw JSON examples are validated by the
full schema/Pydantic suite and remain unchanged.

Initial checks found old assertions that expected no clarification property or
read internal field names from prose; they now assert the normalized default and
structured codes. An ambiguous list selector in the new event UI test was fixed
to select the warning list. A verification wrapper hit a Windows console encoding
error while printing an already successful build; build integrity then ran
separately and passed. The final application checks listed above passed.

All request/response test data is synthetic. The test subprocess removes
`TEST_DATABASE_URL` so it cannot substitute a production database for isolated
SQL integration. External OpenAI/2GIS/database checks are **not_run**; this change
does not alter their adapters or require paid calls.

## Review, limits and handoff

Independent review checked both backend clarification paths, combined reasons,
enum/schema bounds, zero/false preservation, locale rendering, strict malformed
response rejection and old-response compatibility. The early numeric-audit exit
that hid other conflicts was fixed and regression-tested during this task.

Clarification depends on the existing bounded extraction and presence audit; it
does not make unsupported source facts known. The user must reconcile the query
and form, then submit again. No automatic relaxation or new provider retry is
introduced. Historical data/provider acceptance reports remain historical.

Study topics: structured diagnostics versus untrusted prose, request-field enums
versus missing source facts, per-field reasons, rendering derived translations,
schema defaults and backward compatibility.

Three interview questions:

1. Why add structured clarification metadata instead of displaying `message`?
   Stable codes produce tested local instructions without exposing provider prose
   or stale-language text.
2. Why keep conflicts when a number was not parsed? Correcting the number alone
   would leave other known contradictions hidden; every detected field must stay
   visible, with conflict priority when reasons overlap.
3. Why can the interface change language without searching? It stores the same
   validated codes and translates them during render; neither the request nor
   its constraints changes.

Next consumer: user review of this focused change, followed by a separately
authorized coordinated backend/frontend release and live acceptance. No roadmap
task is marked complete and no next feature is started.

## Review follow-up: correction hints survive editing

Date: 2026-10-20. The user requested review, task-related fixes and repeated
checks, without commit or push. The same branch and existing working changes
were preserved.

One **P2** issue was confirmed: `SearchForm` called `resetSearch` on every edit.
This correctly removed stale cards/routes but also erased every clarification
after the first corrected field. A time-and-budget clarification therefore lost
the budget instruction as soon as the user edited time.

`App.tsx` now retains only deduplicated `field`/`reason` codes when an edit clears
the current result. The separate lifetime is intentional: search results become
stale immediately, while the previous request's correction checklist remains
useful until resubmission. Conflict takes priority when a field has both reasons.
The checklist stores no backend message, source, card, route or input value.

The interface explicitly labels these as corrections from the previous search,
whose edits have not been checked yet. `ConstraintClarificationMessages` renders
both received and retained codes using the same local dictionaries. The checklist
survives further edits and kk/ru/en changes without a network request. New submit,
mode change and preview/live transitions clear it. Existing request cancellation
and generation guards continue to discard late responses.

Backend and shared-contract review found no additional confirmed defect. The
installed OpenAI SDK was checked locally: `TextIntent` generates the strict
six-value conflict enum correctly. No external provider call was made.

Repeated backend verification passed: **1598 passed, 17 SQL checks skipped in
12.79 seconds**. Ruff check, Ruff format (89 files), compile/import, generated
contracts (13 artifacts) and pip check passed.

Frontend repeat verification, using the same commands listed above:

- `npm.cmd test -- --reporter=dot`: **416 passed, 22 files in 32.72 seconds**.
- `npm.cmd run test:types`: passed.
- `npm.cmd run lint -- src scripts vite.config.ts vitest.config.ts`: passed.
- `npm.cmd run check:contracts`: passed.
- `npm.cmd run format:check`: passed.
- `npm.cmd run build`: passed, 72 modules.
- `npm.cmd run check:build`: passed, four production files.
- `git diff --check`: passed; the index remains empty.

The correction-flow follow-up adds 10 App regressions across both modes:
sequential edits, local kk/ru/en changes without fetches, resubmission of changed
values, replacement/clearing of previous diagnostics, mode changes, preview/live
actions and ignored late responses after cancellation. A targeted run including
the existing stale-card/route tests passed 122 checks in four files before the
full run. Independent cross-review found no additional confirmed issue in the
new state lifetime, metadata retention or cancellation behavior.

The original checkout remains on `main` at `350917c` with only its pre-existing
untracked demo video. This worktree remains on `codex/fix-poi-constraints` at
`9061865`, with all requested work uncommitted. No deployment, commit or push was
performed. No contract, dependency, database or persistent-data change was needed
for this review fix. External provider/database verification remains **not_run**.

Study follow-up: result and correction-diagnostic lifetimes, explicit stale-data
labels, local rendering from bounded codes, and request-generation cancellation.
Next consumer: user review, then a separately authorized coordinated release
and live acceptance. No next feature was started.
