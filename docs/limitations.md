# Release limitations

- Weather is omitted. No accounts, location history, ticket purchases or multi-stop routes.
- The hosted 2026-10-19 coverage check found 985 real OSM POIs and 985 embeddings, zero test POIs. This is not complete city coverage.
- Missing prices, hours, entrance accuracy and travel stay unknown. Visit duration is a labelled activity estimate, not a source fact.
- A request needs visit time plus five minutes for entry, five minutes buffer and all requested walking legs. The current minimum visit is 30 minutes; a 30-minute total window cannot fit.
- Return travel is independent. Missing/unavailable legs cannot produce a confirmed total or time fit.
- Child/age suitability, charging, quietness and accessibility are unsupported facts. Matching requests require clarification instead of confirmed fit.
- Event discovery is a bounded live sample. Missing year/time/end, ticket inventory and unsupported prices stay unknown; discovered facts are not independently verified session guarantees.
- OpenAI intent failure returns unavailable, not no_match. Explanation failure uses a safe localized template; embedding failure can retain lexical candidates with a warning.
- Local provider access may fail without VPN. The hosted backend performs provider calls; browser/server credentials stay separate. Free Render can cold-start; provider/demo quotas remain external limits.
- 2GIS payloads and runtime event evidence are ephemeral and are not added to the persistent corpus or embeddings.
- BQ-03 raw clarification field labels remain a known cosmetic localization limitation. No new weather or optional feature is included in this release.
