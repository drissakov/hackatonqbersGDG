# D05 — source and data sample audit

Date: 2026-10-19, Asia/Qyzylorda. Owner: Damir. Supporting evidence for
`D05.md` and `docs/scenarios.md`; this is not the shared evaluation report.
No claim of teammate delivery or acknowledgement is made.

## Scope and result

The sample contains **20 real D02 POIs**, all seven activity categories, two
same-brand Del Papa branches, two Starbucks branches, and central, northern,
western, southern and eastern areas. It is a deliberately diverse sample,
not a random estimate of city completeness or venue accuracy.

- **20/20 passed source-mapping checks** against the live primary OSM API:
  object identity/version, chosen source name, category tags, retained facts
  and available opening-hours text agree with the saved source assertions.
- **12/12 node coordinate pairs passed** exact equality with live OSM nodes.
  The other **8 coordinate entrance checks are not_run**: their exported
  Overpass centers remain explicitly approximate. Matching source versions
  does not independently verify an entrance, current physical operation or
  the accuracy of a contributor's map point.
- One independent operator comparison **failed**: Khan Shatyr hours conflict
  with the OSM assertion. The source-correction note below remains open.
- National Museum identity and the conservative retention of unknown hours
  passed an independent operator comparison. Ailand's published facility
  schedules also support keeping a single undifferentiated schedule unknown.
- Three Astana Ballet event titles / four day-and-clock listing hints were
  inspected on primary pages. They pass a **listing-only** check. Their full
  session checks remain **not_run**, including explicit year, end, admission
  price and ticket availability. Astana Opera session verification is
  **not_run** because rendered source evidence was incomplete/inconsistent.

These counters describe different checks and must not be added into a single
venue pass rate. Most sampled venues have no independent operator comparison.
Source consistency is not fact verification. No `verified_at` was promoted.

## Dataset and provenance

Read-only original pair:
`C:/Users/Ilytsm/.codex/worktrees/d02-osm-corpus/hackatonqbersGDG/data/normalized/{pois.jsonl,manifest.json}`.
Original D02 import: `osm-20261019T002412Z-5476f94c2d93`.
JSONL SHA-256:
`acfd1406ff9e976a672712fa58798b814685e49474dd2b70dedfc47efda9324a`.
The source observation anchor remains `2026-10-19T00:17:48.702014Z`;
it is the D02 acquisition-session timestamp, not per-fact verification.

All sampled records retain an OSM object URL, provider `osm`, source ID,
retrieval time, non-test status, field provenance and explicit ODbL
storage/indexing permissions. The mandatory manifest retains source edit time
and version, explicit name-language tags, aliases without inferred language,
derived-field markers and center accuracy. Attribution remains
**© OpenStreetMap contributors**. The rights basis is
[OSM copyright and license](https://www.openstreetmap.org/copyright).
No 2GIS payload, licensed operator feed, new dependency or synthetic city
record was introduced.

The old export manifest declares contract **1.1.0**. Read-only validation with
the current **1.3.0** validator correctly failed `invalid_export_manifest`.
The validator was not weakened and the original pair was not edited.
An export-only replay of the permitted saved raw snapshot into ignored
`data/reports/d05-replay/` produced a current **1.3.0** manifest, passed both
JSON Schema and Pydantic plus identity/NFC/sidecar/checksum/polygon checks for
**985 records**, and retained the identical JSONL hash. Replay ID:
`osm-20261019T081418Z-15805a27e42d`. Database upsert: **not_run/export_only**.
No production data or embedding was changed.

The generated structural report still says `human_verification.sample_size=0`:
that generator does no manual review. This separate audit records the actual
20-record source sample; it does not silently relabel the structural report
or mark all 985 facts verified.

## POI sample

Coordinates below are public QA fixtures in **latitude, longitude** order,
not a real user's location. `N` means exact live node-coordinate equality;
`C` means approximate exported way/relation center, entrance check not_run.
`M` means the source-mapping check passed; it is not an operational guarantee.
The `hours` column is the retained unverified OSM assertion; `unknown` is null.

| OSM record / source                                                                                              | Activity / area              | Coordinates            | Live version / coordinate check | Hours / outcome                                                 |
| ---------------------------------------------------------------------------------------------------------------- | ---------------------------- | ---------------------- | ------------------------------- | --------------------------------------------------------------- |
| [osm:node:10570309737 — Читальный зал ЕНУ](https://www.openstreetmap.org/node/10570309737)                       | culture / right bank east    | 51.1602909, 71.4654320 | 7 / N                           | `Mo-Fr 09:00-20:00; Sa 09:00-17:00; Su off`; M                  |
| [osm:node:5951327485 — Кабанбай батыр](https://www.openstreetmap.org/node/5951327485)                            | culture / southern periphery | 50.8725627, 71.4097936 | 3 / N                           | unknown; M                                                      |
| [osm:node:10168968309 — Ailand](https://www.openstreetmap.org/node/10168968309)                                  | entertainment / river area   | 51.1479426, 71.4158765 | 4 / N                           | unknown; M                                                      |
| [osm:node:5880883097 — Chaplin Cinema](https://www.openstreetmap.org/node/5880883097)                            | entertainment / EXPO area    | 51.0883192, 71.4097300 | 3 / N                           | `Mo-Su 10:00-02:00`; M                                          |
| [osm:node:10064384671 — Del Papa](https://www.openstreetmap.org/node/10064384671)                                | food / right bank            | 51.1603117, 71.4295220 | 9 / N                           | `Fr-Sa 11:00-01:00; Mo-Th,Su 11:00-24:00`; M                    |
| [osm:node:10064384673 — Del Papa](https://www.openstreetmap.org/node/10064384673)                                | food / left bank             | 51.1304777, 71.4154218 | 11 / N                          | same source schedule; M; distinct branch retained               |
| [osm:node:10976892637 — Starbucks](https://www.openstreetmap.org/node/10976892637)                               | food / airport area          | 51.0268214, 71.4613139 | 3 / N                           | `24/7`; M; operator hours not verified                          |
| [osm:node:9047331879 — Starbucks](https://www.openstreetmap.org/node/9047331879)                                 | food / EXPO area             | 51.0890092, 71.4089158 | 8 / N                           | `Mo-Su 08:00-22:00`; M; exact operator branch match unknown     |
| [osm:node:4894937300 — Қазақстан Республикасының Ұлттық Мұражайы](https://www.openstreetmap.org/node/4894937300) | museum / east of center      | 51.1182297, 71.4693823 | 19 / N                          | unknown; M; independent identity check passed                   |
| [osm:node:4933998230 — Коктал 2](https://www.openstreetmap.org/node/4933998230)                                  | shopping / northwest         | 51.1942364, 71.3361409 | 1 / N                           | unknown; M; source edit is from 2017, current operation unknown |
| [osm:node:10581496518 — Шанхай](https://www.openstreetmap.org/node/10581496518)                                  | shopping / north             | 51.2051160, 71.4785643 | 1 / N                           | unknown; M                                                      |
| [osm:node:10242167716 — Fitnation](https://www.openstreetmap.org/node/10242167716)                               | sport / river area           | 51.1536012, 71.4179785 | 1 / N                           | unknown; M                                                      |
| [osm:way:230401645 — Бәйтерек](https://www.openstreetmap.org/way/230401645)                                      | culture / center             | 51.1282882, 71.4304546 | 33 / C                          | unknown; M; address source retained                             |
| [osm:way:917478479 — Астана Опера](https://www.openstreetmap.org/way/917478479)                                  | culture / left bank          | 51.1354512, 71.4107530 | 3 / C                           | unknown; M; address source retained                             |
| [osm:way:240376692 — Сәкен Сейфуллин музейі](https://www.openstreetmap.org/way/240376692)                        | museum / old city            | 51.1714825, 71.4235922 | 8 / C                           | unknown; M; address source retained                             |
| [osm:way:460703779 — Хан Шатыр](https://www.openstreetmap.org/way/460703779)                                     | shopping / west of center    | 51.1325089, 71.4038726 | 16 / C                          | `Mo-Su,PH 10:00-23:00`; M; **failed operator hours comparison** |
| [osm:way:1102228687 — Baqytbek Arena](https://www.openstreetmap.org/way/1102228687)                              | sport / far west             | 51.1289349, 71.2564542 | 3 / C                           | unknown; M                                                      |
| [osm:way:1196402246 — Ботаникалық бақ](https://www.openstreetmap.org/way/1196402246)                             | walk / south of center       | 51.1061652, 71.4165705 | 15 / C                          | unknown; M                                                      |
| [osm:relation:15957444 — Астана саябағы](https://www.openstreetmap.org/relation/15957444)                        | walk / right bank            | 51.1548152, 71.4195693 | 4 / C                           | unknown; M                                                      |
| [osm:relation:16002498 — Жерұйық саябағы](https://www.openstreetmap.org/relation/16002498)                       | walk / east                  | 51.1455747, 71.4899608 | 3 / C                           | unknown; M                                                      |

Both Del Papa records and both Starbucks records keep separate type/ID
identities and coordinates. No same-brand merge or translated-name guess was
used. Category checks compare the explicit allowlisted OSM tag; for example
`tourism=museum`, `amenity=library`, `leisure=park`, `shop=mall` and
`amenity=cafe`, rather than classifying by the source name.

All 20 prices and indoor flags remain null. Unknown sockets, quietness,
accessibility, visit length and opening at the requested visit remain unknown.
A park name does not manufacture `indoor=false`; a cafe name does not establish
sockets. Sampled Kazakh letters are retained in NFC, including `Бәйтерек`,
`Жерұйық`, `Ботаникалық бақ` and `Сәкен Сейфуллин музейі`. Missing explicit
`name:kk/ru/en` values remain null; the source name is available for fallback.

## Independent sources and source-correction queue

| Check / primary source                                                            | Actual comparison                                                                                                                                                                                                                                    | Status and consequence                                                                                                                                                           |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Khan Shatyr [operator contacts](https://www.khanshatyr.com/index.php/en/contacts) | Operator address is Turan 37, agreeing with the source-derived address. Operator public hours close at 22:00 except Friday/Saturday at 23:00. OSM says 23:00 every day and holidays. Direct read returned HTTP 200 at `2026-10-19T08:15:36.078428Z`. | **failed — D05-SRC-01** for hours. Monday 22:30 is an explicit conflict; do not claim this source assertion is independently verified. Public-holiday exceptions remain unknown. |
| National Museum [operator home](https://www.nmrk.kz/)                             | Operator identity and Astana address support the sampled museum. It publishes Tue–Sun 10:00–18:00 and Monday closure. The corpus has no hours, so retaining null is honest. Direct read returned HTTP 200 at `2026-10-19T08:15:52.507018Z`.          | **passed** identity/unknown preservation. No operator hours were manually imported into OSM records.                                                                             |
| Ailand [operator schedule](https://ailand.kz/ru/schedule-ru/)                     | Primary rendered page separates aquarium, jungle, exotarium and wheel schedules and last ticket-sale times. The sample is tagged `water_park`; no matching water-park schedule was shown.                                                            | **passed** conservative unknown handling; facility-specific water-park hours and last admission are **not_run**. Never borrow another facility's schedule.                       |
| Chaplin [operator cinema page](https://chaplin.kz/astana/cinemas/5)               | Search-indexed operator text describes the Mega Silk Way branch and daily 10:00–02:00, agreeing with OSM. Direct rendered open exposed only an iframe, no usable facts.                                                                              | **not_run** fresh operator fact verification. The indexed text is a lead, not an independently confirmed pass.                                                                   |
| Starbucks [operator stores](https://www.starbucks.com.kz/stores)                  | Indexed content lists several branches, inconsistent city labels for Mega Silk Way, and an ambiguous `00:00-00:00` airport schedule. Direct open returned 403. Canonical sampled addresses are null.                                                 | **not_run** independent branch/hours verification. No branch selected from name alone, no conversion of `00:00-00:00` into 24/7, no access-control workaround.                   |
| Del Papa operator search                                                          | A targeted `site:del-papa.kz` query returned no usable operator result.                                                                                                                                                                              | **not_run** operator branch/address/hours verification; OSM source consistency alone passed.                                                                                     |

**D05-SRC-01 is a source conflict, not a normalization bug.** The normalizer
preserves the exact permitted OSM assertion and its source; no repeated
transformation defect was found in this sample. Overwriting the OSM fact with
operator content would require explicit compatible storage/indexing rights
and source provenance, or a reviewed correction to the source. Neither is
established here. The correction queue is this minimal audit note, not a new
fact corpus. No operator page payload is saved, embedded or indexed.

For Sabyrzhan's acceptance check, use the sampled Khan Shatyr source record
with a Monday visit at 22:30 in `Asia/Almaty`: expected behavior is no claim of
independently verified opening or guaranteed fit from that OSM assertion.
Actual **record** is `opening_hours_text="Mo-Su,PH 10:00-23:00"`,
`provenance.observed_at=null`, sidecar `verified_at=null`, source version 16.
An HTTP response for this exact source-targeted case was **not_run** by this
audit; the API does not expose a direct POI-ID recommendation filter. This is
not presented as an observed backend defect or fabricated response.

## Event sample and source uncertainty

No event-site storage/indexing rights were added. The following is minimal
manual QA evidence, not an event corpus or a feed to ingest/embed. Research
page timestamps are not guaranteed origin-server fetch times. No purchase or
inventory request was made.

| Primary source / sample                                                                                                                                              | Observed support                                                                                                                                                                                        | Passed scope / not_run scope                                                                                                             |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| [Astana Ballet schedule](https://astanaballet.com/en/posters) and [The Heritage of the Great Steppe](https://astanaballet.com/en/stagings/nasledie-velikoy-stepi)    | The listing has the source title and a 24 October / 18:00 hint; venue address is Uly Dala 43, Astana. Detail page preserves title and venue but contains no session date/year.                          | Listing identity/title/venue **passed**. Full session/date/year/end/price/ticket checks **not_run**; never borrow the retrieval year.    |
| [Astana Ballet schedule](https://astanaballet.com/en/posters) and [Music Through Generations](https://astanaballet.com/en/stagings/muzyka-skvoz-pokoleniya)          | Listing has the source title and 28 October / 19:00 hint. Detail page supports title/venue, no explicit session year.                                                                                   | Listing-only check **passed**; confirmed session/budget/time fit **not_run**.                                                            |
| [Astana Ballet schedule](https://astanaballet.com/en/posters) and [Romeo and Juliet](https://astanaballet.com/en/stagings/premera-romeo-i-dzhuletta-v-astana-ballet) | Listing has 30 October / 19:00 and 31 October / 18:00 hints for the same production. Detail text contains historical premiere dates, not dates of those sessions.                                       | Listing-only check **passed**. Historical premiere year must not populate current sessions; full sessions **not_run**.                   |
| [Astana Opera event page](https://astanaopera.kz/afisha/676) and [schedule](https://astanaopera.kz/ru/afisha?lang=en)                                                | Search-indexed metadata mentions a production/date; direct detail rendering returned support/donation UI instead of the event. The schedule open timed out. Indexed weekday/date text was inconsistent. | **not_run** accepted-session verification. Donation amounts are not ticket prices, and search snippets do not resolve conflicting dates. |

No positive accepted session, confirmed ticket availability or event-city
coverage is claimed. Existing event tests exercise conservative date/price
grounding, branch matching, cancellations and unknowns; those are automated
checks with synthetic inputs, separate from this manual source audit.

## Reproduction and actual commands

Working directory:
`C:/Users/Ilytsm/.codex/worktrees/d05-language-quality/hackatonqbersGDG`.
Existing runtime reused without package changes:

```powershell
$d05Python = 'C:/Users/Ilytsm/.codex/worktrees/damir-d00/hackatonqbersGDG/.venv/Scripts/python.exe'
& $d05Python -m pytest ingestion/tests backend/tests/test_events.py -q
& $d05Python -m ruff check ingestion backend/app/services/events
& $d05Python -m ruff format --check ingestion backend/app/services/events
& $d05Python -m ingestion.cli import-osm --city astana --from-snapshot 'C:/Users/Ilytsm/.codex/worktrees/d02-osm-corpus/hackatonqbersGDG/data/raw/osm-20261019T001732Z-c09eeb10adbb.json' --data-dir data/reports/d05-replay --export-only
& $d05Python -m ingestion.validate --data-dir data/reports/d05-replay
git check-ignore data/reports/d05-replay/normalized/pois.jsonl data/reports/d05-replay/source-report.json
```

Results: **241 tests passed in 5.24s**, Ruff check passed, Ruff formatting
passed for 19 files, replay/validation exit 0, both output paths ignored.
The replay has no provider fetch or database write. No code, shared contract,
dependency, backend API, SQL migration or persistent corpus correction was
needed for the observed checks.

Live primary OSM comparison used standard-library `urllib.request` with
`User-Agent: QadamAstana-D05-source-audit/1.0`, a 30-second timeout and three
bulk GETs. Each returned **HTTP 200**; no raw API payload was written:

- [12 nodes](https://api.openstreetmap.org/api/0.6/nodes?nodes=10570309737,5951327485,10168968309,5880883097,10064384671,10064384673,10976892637,9047331879,4894937300,4933998230,10581496518,10242167716)
- [6 ways](https://api.openstreetmap.org/api/0.6/ways?ways=230401645,917478479,240376692,460703779,1102228687,1196402246)
- [2 relations](https://api.openstreetmap.org/api/0.6/relations?relations=15957444,16002498)

The actual comparison reads `pois.jsonl` and the matching manifest,
joins by `osm:<type>:<id>`, parses XML with `xml.etree.ElementTree`, and
compares `version`, the manifest's `name_source_tag`, `opening_hours` and
every retained sidecar fact. For nodes it also compares both coordinate
floats exactly. Source mapping passes only if the object exists and every
compared value matches. The retained name is compared after source NFC
normalization; the sample's strings already match exactly.

Research browsing opened the operator/event URLs linked above and followed
the three Ballet detail links. Initial research-tool opens of four ordinary
OSM object pages failed as inaccessible; the documented public primary API
was then used successfully. Two initial PowerShell/Python diagnostics failed
to print Kazakh characters with the default cp1251 console codec. Repeating
with `sys.stdout.reconfigure(encoding='utf-8')` passed; no source string or
corpus record was altered to accommodate the console.

## Freeze and next consumer

This audit freezes the source/data observations above on 2026-10-19 after
13:15 Asia/Qyzylorda. Active-hour T+16 timing was not measured and is not
claimed. The root D05 handoff owns the overall task freeze.

Remaining limits: 965 POIs outside this sample; no operator survey of most
sampled venues; 8 unverified entrances; stale-but-current OSM assertions such
as the 2017 Koktal record; incomplete multilingual source names; all source
prices unknown; sockets/indoor/accessibility and actual visit fit unknown;
Khan Shatyr hours conflict; unavailable/ambiguous operator pages; no accepted
event session or live ticket/route guarantee; city completeness unknown.

Next consumer: D05 scenario/report integration, then Sabyrzhan for shared
constraint/source-verification acceptance and Damir's **D06 only after a
separate authorization**. No commit, push, provider configuration change,
database mutation or D06 implementation was performed.
