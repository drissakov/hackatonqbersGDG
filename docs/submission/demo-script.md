# Qadam Astana demo and video script

Rehearsal date: 2026-10-19, Asia/Qyzylorda. API contract: 1.3.0.
This is a short demo rehearsal, not another run of the 30 D05 scenarios.

## Before recording

Start the configured backend and frontend using the [README](../../README.md).
Use real API mode and manual public coordinates. Allow popups/new tabs for
source links. Keep API keys, terminals with credentials and browser permission
settings out of the recording. Record manually; target **2 minutes 40 seconds**.

For each case, enter both coordinates and the minutes explicitly. Leave budget
empty, return-to-start off and indoor-only off. Set the date/time explicitly;
the input uses Astana wall time (UTC+05:00). A language change alone does not
repeat a search: press Search for the next case.

## Exact rehearsal cases

Coordinates are latitude, longitude. They are public QA points, not user GPS.
Result names and ordering can vary with retrieval and source freshness.

| Case | Mode | Coordinates | Query (copy exactly) | Locale | Minutes | Astana date/time |
| --- | --- | --- | --- | --- | --- | --- |
| A — ordinary POI | Places | `51.1282882, 71.4304546` | `Предложи музей рядом с Байтереком.` | `ru` | `120` | `2026-10-24 14:00` |
| B — changed time and activity | Places | `51.1282882, 71.4304546` | `Suggest a coffee shop near Baiterek.` | `en` | `60` | `2026-10-24 14:00` |
| C — event and source, blocked | Events | `51.1282882, 71.4304546` | `Find ballet performances at Astana Ballet.` | `en` | `360` | `2026-10-24 18:00` |

**A:** Submit once. Show 1–3 independent place cards, the recommended visit
duration, missing facts and a cited source. Select one destination and show the
route panel. Travel time must stay unknown if routing is unavailable; a visit
estimate does not establish arrival time or total fit. Open the actual source.

**B:** Change language to English, query and minutes to the exact values above.
Old results and route must disappear on editing. Submit, then show the changed
activity/result and time constraint. Different results are a rehearsal check,
not a promise about live ranking. Do not claim that every constraint is verified
when the card says conditional/unknown.

**C:** Switch to Events, fill the exact controls, then submit. The fresh attempt
returned unavailable with no source; the positive event-plus-source demo is
**blocked / not_run**. Show the honest state, then optionally open the
[official Astana Ballet schedule](https://astanaballet.com/en/posters) manually
as an external-source fallback, labelled **"manual source; not an API result"**.
The fallback page opened successfully in the browser; this verifies the link,
not a session's year, availability or fit with the selected date.
Do not substitute a fabricated event or development fixture. If a later rehearsal
returns a grounded session or listing, inspect its own returned source before
using it: a listing alone is not a confirmed session, ticket or total trip fit.

## Verification evidence

- Historical S04 evidence: real-corpus museum queries returned three POIs in
  ru/kk/en; see [S04](../handoffs/S04.md). Those inputs/receipts do not prove
  that the three exact rehearsal inputs above currently succeed.
- Historical D05 evidence: core results were **3 passed / 27 not_run**; event
  discovery and ordinary positive POI cases were blocked by provider
  unavailability. See [D05](../handoffs/D05.md). D05 was not rerun here.
- Fresh local smoke on `origin/main` `086b61b`: health passed; coverage reported
  **985 production/located/embedded POIs**, zero test POIs, city coverage unknown.
  A returned **200 / partial / 3 museums / 3 sources** in 18.8 seconds; B returned
  **200 / partial / 3 coffee places** in 21 seconds. Both kept unknown fit and
  unavailable routes; travel time was null. Browser A/B displayed the returned
  cards, editing cleared the previous result, and A's OSM source opened in a new
  tab. No horizontal overflow was observed at 375 px. A process-health response
  alone does not establish demo readiness.
- Fresh C returned **503 / unavailable**, `web_search_citations_missing`,
  `live_web_search=failed`, zero cards/listings/sources in 13.7 seconds. Its
  positive semantic outcome is **not_run**. An earlier date-in-query Opera
  attempt returned unknown/constraint clarification; it is not the chosen C.
  Further external retries were stopped. There are **two positive API cases,
  not three stable positive flows**.
  The browser also rendered the event unavailable state in English and Kazakh.
- Fresh frontend build passed (`npm.cmd run build`); the focused UI checks
  passed **15 tests**, with 19 unrelated tests intentionally skipped. The full
  suite and 30-scenario D05 runner were not rerun. `npm.cmd run check:build`
  also passed. GPS denial/manual fallback and stale-response handling passed
  controlled tests; an actual OS location permission prompt was not exercised.

Focused test command (inside `frontend/`):

```powershell
npm.cmd test -- src/App.d04.test.tsx src/App.transient.test.tsx src/i18n.test.tsx --testNamePattern 'keeps received place|preserves card reasons|localizes loading|keeps incomplete|invalidates pending|lets a person deny GPS|has matching base keys|switches kk/ru/en'
```

Fresh A destinations: `osm:way:51431624`, `osm:way:240376692`,
`osm:node:4894937300`, with a **45-minute suggested visit**. Fresh B destinations:
Coffee Stories (`osm:node:12990081601`), MasterCoffee (`osm:node:13858040201`),
Global coffee (`osm:way:1376443434`), with a **30-minute suggested visit**.
These disjoint sets verify the changed result for B; they do not verify an
entrance, price, opening hours or total trip fit.

## Short failure-state rehearsal

Before recording, once only: deny the location permission and enter A's manual
coordinates; confirm search remains usable. While one search is loading,
change its query and confirm a late reply does not restore old cards. Check
kk/ru/en labels, one source link and one unknown route/time display. A provider
error must be shown as unavailable, not as "no places/events exist".

If an external blocker lasts more than five minutes, stop retrying and mark
the positive flow `not_run`. Keep the unavailable/unknown UI as an honest
fallback. A source page opened separately can illustrate the external source;
it does not prove successful API discovery. Do not record synthetic data as
the real city corpus.

## Manual video timeline and narration (2–3 minutes)

| Time | Screen action | Narration |
| --- | --- | --- |
| 00:00–00:20 | Show the app and available controls. | "A map can show hundreds of places, but it does not answer a practical question: where can I go with the time I have? Qadam Astana helps people choose one destination in Astana, with reasons and links to the underlying sources." |
| 00:20–00:55 | Run A; show cards, visit estimate and source. | "I start from a public point near Baiterek, choose Russian and give the app one hundred and twenty minutes. It searches our permitted city corpus and returns up to three alternatives. These are separate choices. Each card keeps source facts separate from generated explanations and a suggested visit duration." |
| 00:55–01:25 | Select a destination; run B with 60 minutes and English. | "Here I can inspect the route and its status. An unknown route is labelled unknown. Now I change the activity and reduce the time to sixty minutes. The old response clears, and the next search uses the new constraints. A source link lets me inspect the original information." |
| 01:25–02:00 | Switch B's interface to Kazakh without another search, then select English and run C. Show its unavailable state; optionally open the official schedule manually. | "The same interface also works in Kazakh. Events use a separate live search. In this rehearsal the event provider is unavailable, so there is no event result or returned citation. This official schedule is a manual source fallback, not proof of API discovery. A listing alone would not confirm a session or ticket." |
| 02:00–02:25 | Show source/unknown labels; use slides 4–5 if desired. | "The recorded dataset contains nine hundred and eighty-five OpenStreetMap places across seven categories, with attribution and provenance. Retrieval combines lexical and vector search. This is measured coverage of one corpus, not proof of complete coverage of Astana. Live events remain transient." |
| 02:25–02:40 | Return to the app; show the limitations slide. | "The MVP focuses on one useful destination, three interface languages and honest uncertainty. Our next work is provider reliability and better source completeness. Future partner pilots could support local venues and tourism services; this is a direction, not demonstrated revenue." |

If A, B or C is unavailable during recording, replace that segment's success
narration with: **"The required provider is unavailable in this run. The app
preserves that state and does not invent results. This positive flow remains
unverified."** Record any provider wait briefly; do not spend the video on
retries or describe edited waiting time as measured latency.
