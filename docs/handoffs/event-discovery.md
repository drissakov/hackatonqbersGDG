# Event discovery runtime correction

## Scope and evidence

This task fixes the user's reported empty/unknown event search. It does not
start S05 or change the public v1.3.0 schema, database, dependencies or 2GIS
configuration. The next consumer is the existing transient-event UI.

The deployed baseline `ae039c7` returned `unknown/no_grounded_events` for a
specific real Ticketon concert and selected date: one extracted event was
rejected, with 14 consulted sources. A separate request returned
`web_search_citations_missing`. These are observed failures, not evidence that
Astana has no events.

Synthetic regressions reproduce three implementation failures:

- A separate Markdown event heading is excluded from its citation paragraph,
  so the title check can discard the whole event.
- Extraction may retain the date/year without its clock. Normalization
  previously rejected that date even when the immediate source phrase
  contained the exact requested clock. Ordinary Russian punctuation also
  failed the date/time pattern.
- With no requested date, both discovery and evaluation silently restricted
  results to the current local day.

## Behavior

- Search instructions request self-contained, cited event paragraphs and
  individual event/session pages with explicit years.
- The same URL's citation title can support the event name. Its city, venue,
  date and price remain grounded only in that URL's cited response context.
  This does not represent independent verification of the original page.
- Date-only quotes can use only their immediately following clock. Years are
  never inferred; unrelated sessions, prose gaps, unsupported precision and
  unsupported explicit time zones/AM-PM remain unknown.
- An empty date uses a bounded upcoming 30-day discovery sample. An explicit
  date retains the selected local day. Past events, arrival buffers, explicit
  available time, budget, cancellation and source conflicts remain enforced.
- Ticket inventory and incomplete source verification still prevent a
  confirmed fit. A dated, sourced card may correctly have `fit_status=unknown`
  and an overall `partial` response.
- Provider content stays ephemeral, with no corpus writes or new cache.

## Verification checkpoint

Commands use Python 3.12 from the existing workspace virtual environment:

```powershell
python -m pytest -q backend/tests ingestion/tests
python -m compileall -q backend ingestion scripts
python -m ruff check backend scripts ingestion
python -m ruff format --check backend scripts ingestion
python scripts/export_contracts.py --check
```

Pre-publication results: **1031 passed, 17 skipped**; compileall, Ruff check,
Ruff format (78 files), generated-contract check (13 artifacts) and
`git diff --check` passed. Isolated SQL checks require `TEST_DATABASE_URL`;
production `DATABASE_URL` is never reused as a test database. The test suite
includes future dated card composition in kk/ru/en, source-title isolation,
explicit selected-day/time/budget preservation and unsupported clock suffixes.

## Live acceptance and limitations

Local OpenAI preflight returned `network_unavailable_or_timeout`; the hosted
application remains the place for live provider acceptance. Official Ticketon
search results expose real future event dates including years, while direct
page requests may return 403 or time out. No access controls are bypassed.

At the commit checkpoint, a positive live event card for this correction is not
yet verified. The user explicitly authorized COMMIT, PUSH and deployment on
2026-10-19 after reviewing the preflight results. After publication, verify both the default upcoming query and
an exact dated event, confirm source/date rendering, and repeat a constrained
query without weakening its restrictions. No claim of complete city coverage
or guaranteed ticket availability is made.

## First live checkpoint and focused follow-up

Commit `76731c7` passed all four GitHub CI jobs and reached Render `live`.
The default query returned two calendar listings (`partial`); the exact
Ticketon concert was retained, but its extracted start still normalized to
unknown. A repeat returned `web_search_citations_missing`. A positive dated
card was therefore not claimed at that checkpoint.

The authorized follow-up adds known date/time label layouts (for example,
`date year. Time: 19:00`) without accepting arbitrary prose between them.
Search now targets individual event pages first and permits one additional
bounded tool action (three total) for missing session evidence. The existing
discovery and UI timeouts are unchanged. Rejected timestamps emit only static
diagnostic codes; no source text, dates, queries, GPS or exception bodies are
logged. The follow-up passed **1063 tests, 17 skipped**, Ruff checks and format.
