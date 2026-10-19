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

## Citation provenance correction

The second live checkpoint still returned `web_search_citations_missing`.
Review identified another reproducible parser mismatch: completed page-open
and find actions were ignored even though they explicitly identify a consulted
page. These URLs now join the bounded source set, while a completed search
remains mandatory. Failed/incomplete page actions cannot add provenance.

Only the known provider attribution markers `utm_source=openai` and
`utm_source=chatgpt.com` may differ between an observed and displayed citation
URL. The original citation URL is retained. Other query parameters, paths,
fragments and domains remain exact; at most 100 combined sources/aliases are
accepted. Missing citations emit only integer counters for rejected URL,
offset and title fields. No provider bodies are logged.

This correction passed **1077 tests, 17 skipped**, compileall, Ruff check,
Ruff format (79 files), contract drift (13 artifacts) and diff checks.

## Detail-page extraction follow-up

The third checkpoint retained real linked events, but a yearless date remained
unknown as intended, and an individual concert detail was extracted as a
calendar listing. The focused prompt correction separates page structure from
verification status, retains observed occurrences with null unknown fields,
and requires aware ISO timestamps rather than natural-language dates in
`starts_at`/`ends_at`. The source quote remains literal and never acquires a
year from the query.

The first Ticketon query now includes its public Russian date/time field
labels, the requested city/year and topic. This finds explicit source dates
instead of relying only on yearless calendar rows. No real event URL/title is
hardcoded. City must belong to the session venue, not a contact footer, hotel
name or another tour stop. Pre-publication suite: **1077 passed, 17 skipped**.

## Literal schedule conversion

The fourth live checkpoint found a real event with an explicit date/year/clock
in its source quote, but structured extraction returned null `starts_at`.
The safe log code `extracted_datetime_missing` isolated this remaining cause.

Missing ISO values can now be derived deterministically from a literal source
quote, only after the session city is grounded as Astana. The parser reads the
year from that quote and clocks only from it or the next 80 source characters.
It checks at most 32 date/clock pairs through the existing strict validator
and accepts only one unique moment. It does not use the request date, current
year, visit duration or another source. Unknown ends and unsupported time zones
remain unknown. Existing nonempty model timestamps still require validation.

Common ru/kk city forms share the same Astana alias set. A venue name containing
Astana cannot supply the city fact. Typographic title quotes compare equally
without changing the original display title. Additional
rejection logs contain only static codes. Pre-publication checks:
**1124 passed, 17 skipped**; compileall, Ruff check/format (81 files), 13
generated contract artifacts and diff checks passed. Independent synthetic
edge-case review found no actionable issues in the timestamp fallback.

## Equivalent schedule facts

The fifth live checkpoint still found a real linked event but rejected its
start with `source_quote_not_literal`: structured extraction reformatted the
source date/time labels. Literal substring equality alone therefore lost
otherwise explicit schedule facts. This checkpoint was not a successful dated
event acceptance.

The focused follow-up compares explicit schedule facts against the actual
same-URL citation context. It preserves date/clock binding and requires the
event year in the evidence. Markdown formatting cannot supply or alter a fact;
ambiguous dates, other-source facts and unsupported timezone suffixes remain
unknown. No query date or current year is used as source evidence.

## Final hosted acceptance and PR preparation

On 2026-10-19, Render commit `fd6e506` reached `live`. A browser search for
`Concert Sezim in Astana` (Russian query) rendered the real event, its Ticketon
source link, start `2026-10-30T19:00:00+05:00` and a starting price of 3000 KZT.
End time and ticket availability remained unknown, and the UI did not claim a
confirmed fit. A generic concert query also retained a yearless listing as
unknown rather than inventing its year. No provider prose or corpus was stored.

The final quoted-field patch passed 20 targeted date tests and Ruff checks;
GitHub Actions run 39250622393 passed for that exact commit. The preceding
source-equivalence patch passed 31 targeted tests. The earlier full checkpoint
passed 1124 tests with 17 local SQL skips without TEST_DATABASE_URL. Full local
suites were not repeated after the focused patches at the user's request.
The inherited runtime integration checkpoint passed 285 frontend tests plus
build, type, lint, format and contract checks.

PR preparation preserves main's updated README and meaningful branch commits.
Only documentation changes were needed to resolve the README conflict; provider
calls and test suites were not repeated for that resolution. Contract version,
API endpoints, database schema and production dependencies are unchanged.
