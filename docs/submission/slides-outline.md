# Qadam Astana — seven-slide submission outline

Use the existing visual style. This is content for a manually assembled deck;
no new presentation system is required. Demo inputs and the 2–3 minute video
script are in [demo-script.md](demo-script.md).

## 1. Problem

- People need a feasible next destination, not another long list of pins.
- Time, starting location, budget and incomplete venue facts complicate a visit.
- Local discovery should work in Kazakh, Russian and English.

Speaker line: "Where can I go in Astana with the time I actually have?"

## 2. Solution

- One request yields up to three independent single-destination alternatives.
- Cards explain the choice and expose visit estimates, sources and missing facts.
- Manual coordinates and optional geolocation support a practical starting point.

Visual: one current app screenshot, with no redesigned mockup or invented facts.

## 3. Demo

- A: Russian museum request; public point near Baiterek; 120 minutes.
- B: English coffee request at the same origin; reduce time to 60 minutes.
- C: English Astana Ballet event request; 24 October 2026, 18:00; current
  provider failure is shown honestly. An official schedule can be opened
  manually and labelled as an external-source fallback.
- Briefly switch the existing POI results to Kazakh without another search.

Use the exact inputs in [demo-script.md](demo-script.md). A/B passed positive API
smoke; C has no returned event or source and remains blocked, not a third success.

## 4. Dataset + RAG

- Recorded corpus: **985 real OSM POIs / seven categories**; 985 indexed with
  1536-dimensional embeddings in historical S03/S04 evidence.
- Lexical/vector retrieval → source-grounded candidates → constraint evaluation
  → up to three independent alternatives with localized explanations.
- Preserve source identity, timestamps, provenance and permitted storage/indexing.
- Attribution: **© OpenStreetMap contributors**, ODbL 1.0.

Evidence: [source report](../../data/source-report.json),
[quality report](../../data/quality-report.json), [S03](../handoffs/S03.md).
Query completion does not establish complete city coverage; completeness is unknown.

## 5. Constraints + sources

- Time, location, per-person budget, indoor preference and optional return leg.
- Suggested visit duration is an estimate; route, price and opening hours may be unknown.
- Provider unavailability stays distinct from no match; conflicting known facts
  must not silently relax the user's constraints.
- Open the source; a citation does not verify every venue fact.

Visual: one actual card's estimate, uncertainty label and source action.

## 6. Multilingual + events

- kk/ru/en local interface; language changes render existing results without
  repeating a provider call. The next search sends the selected locale.
- Separate transient event discovery: listings and eligible sessions have
  different meanings; uncertain ticket/price/end facts remain explicit.
- GPS denial leaves manual coordinates available; no location/query history.

Do not present synthetic previews or an unverified event card as live acceptance.

## 7. Limitations + future/business

- Current data is uneven: recorded snapshot has **642 missing hours / 985 missing
  prices / 193 approximate centers**; entrances and total city coverage are unverified.
- Fresh event smoke: provider `web_search_citations_missing`, zero returned
  events/sources; positive event acceptance remains blocked. Fresh A/B routes
  were unavailable and their trip fit unknown.
- No accounts, ticket purchase or multi-stop itinerary in this MVP.
- Next: improve permitted data completeness and provider reliability; validate
  venue/tourism partner pilots and a possible referral model with real users.

These are future hypotheses, not shipped features, partnerships or proven revenue.
Historical quality evidence is in [D05 audit](../handoffs/D05-data-audit.md);
current demo verification is recorded in the companion script.
