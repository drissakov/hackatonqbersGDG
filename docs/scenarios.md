# D05 — multilingual scenarios and observed results

Date: 2026-10-19, Asia/Qyzylorda. Branch: `codex/d05-language-quality`.
Product base: `181e012` (merged D04/S04); shared API contract **1.3.0**.
The direct D05 user brief supersedes the older task-board D05 wording.
This is Damir's scenario log, not Sabyrzhan's shared evaluation report.

## Run and acceptance meaning

The actual live run sent **30 core requests plus 4 mixed/alias variants** to
`http://127.0.0.1:8000` on 2026-10-19, starting 13:13:51 Asia/Qyzylorda.
Health was HTTP 200/API 1.3.0. Read-only coverage was 985 real OSM POIs,
985 located, 985 embedded, zero test POIs, and city coverage **unknown**.
The endpoint existed before D05 and was not restarted or reconfigured. Its
reported version is observed; no claim is made about its process working tree.

Core semantic acceptance: **3 passed, 0 failed, 27 not_run**. Aliases:
**1 passed, 0 failed, 3 not_run**. There is no 30/30 product acceptance claim.
All 34 HTTP calls completed with matching request IDs and `Cache-Control: no-store`.
Four explicit outlet requests returned grounded uncertainty without fabricated
places/sources. The other 30 returned HTTP 503/provider unavailable; their
semantic acceptance is **not_run**, despite failure handling being observable.
Event provider diagnostics were `network_unavailable_or_timeout` and
`live_web_search=not_run`. The unavailable POI envelope intentionally hides
the underlying cause; network, key and account causes were not guessed.

A passed result needs the meaning, hard filters, uncertainty and source behavior
in the expectation below. HTTP 200, a nonempty result or an identical venue
across languages is not an oracle. Semantically valid different alternatives
are allowed. A provider failure cannot establish no_match. Controlled UI and
backend checks are reported separately and do not replace these live statuses.

## Exact reproducible input

From `frontend/`, run `node scripts/d05-scenarios.mjs`. The tracked runner
contains every query below, coordinates and constraints; it uses a fresh UUID
per request and at most two concurrent requests. It records sanitized codes,
counts, timings and public QA input to ignored `artifacts/d05/api-results.json`.
It never saves transient event source content, provider bodies or credentials.

Default POST path is `/api/recommendations`; case 08 uses `/api/events/search`.
All six controls are explicitly supplied in `explicit_fields`:

`origin, available_minutes, budget_kzt_per_person, date_time, return_to_start, indoor_only`.

For cases 01–09 use the point below, their stated minutes, a null budget except
06=3000 and 09=0, false return except 04=true, false indoor except 05=true.
Default date/time is `2026-10-24T14:00:00+05:00`; case 07 uses
`2026-10-24T23:30:00+05:00`, case 08 `2026-10-24T18:00:00+05:00`.
Case 10 sends origin, minutes, budget and date/time **null**, both booleans false.

Example shape (replace query/locale/controls according to the rows; request_id
is a fresh UUID, with the actual historical UUID retained in each result row):

```json
{
  "request_id": "e6e52cc2-1f13-4fea-bf78-751154f96b99",
  "query": "30 минутқа серуендейтін орын ұсын.",
  "locale": "kk",
  "origin": {
    "latitude": 51.1282882,
    "longitude": 71.4304546
  },
  "available_minutes": 30,
  "budget_kzt_per_person": null,
  "date_time": "2026-10-24T14:00:00+05:00",
  "return_to_start": false,
  "indoor_only": false,
  "explicit_fields": [
    "origin",
    "available_minutes",
    "budget_kzt_per_person",
    "date_time",
    "return_to_start",
    "indoor_only"
  ]
}
```

## Public starting-point fixtures

These are source-reported real public POIs in different parts of Astana, not
a person's GPS. Way centers are approximate and not verified entrances. The
point for 10 is a reference fixture only and is deliberately **not sent**.
Source consistency is assessed in [the 20-POI audit](handoffs/D05-data-audit.md).

| Case        | Public source point                                                                            | Latitude   | Longitude  | Minutes |
| ----------- | ---------------------------------------------------------------------------------------------- | ---------- | ---------- | ------- |
| 01-walk     | [Baiterek](https://www.openstreetmap.org/way/230401645)                                        | 51.1282882 | 71.4304546 | 30      |
| 02-outlet   | [Khan Shatyr](https://www.openstreetmap.org/way/460703779)                                     | 51.1325089 | 71.4038726 | 90      |
| 03-child    | [Chaplin Cinema EXPO](https://www.openstreetmap.org/node/5880883097)                           | 51.0883192 | 71.40973   | 90      |
| 04-return   | [National Museum](https://www.openstreetmap.org/node/4894937300)                               | 51.1182297 | 71.4693823 | 120     |
| 05-indoor   | [Saken Seifullin Museum](https://www.openstreetmap.org/way/240376692)                          | 51.1714825 | 71.4235922 | 90      |
| 06-budget   | [Koktal 2](https://www.openstreetmap.org/node/4933998230)                                      | 51.1942364 | 71.3361409 | 90      |
| 07-late     | [Baqytbek Arena](https://www.openstreetmap.org/way/1102228687)                                 | 51.1289349 | 71.2564542 | 90      |
| 08-event    | [Railway History Museum](https://www.openstreetmap.org/node/13948916190)                       | 51.1122858 | 71.5316883 | 360     |
| 09-conflict | [Airport-area Starbucks](https://www.openstreetmap.org/node/10976892637)                       | 51.0268214 | 71.4613139 | 30      |
| 10-missing  | [Shanghai public POI reference (not supplied)](https://www.openstreetmap.org/node/10581496518) | 51.205116  | 71.4785643 | null    |

## Semantic expectations

| Case        | Acceptance oracle                                                                                                                                                                       |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 01-walk     | One walk destination within 30 total minutes, or an explicit honest conflict/unknown; no relaxed time, invented walking route or city-wide absence claim.                               |
| 02-outlet   | Power-outlet evidence is unsupported: unknown/clarification, no claimed outlet and no invented source. A cafe alone does not satisfy this request.                                      |
| 03-child    | A museum can be conditional only; child age/admission suitability must remain explicitly unverified. Never claim child suitability from category alone.                                 |
| 04-return   | One destination, independent outbound/return, total within 120 minutes only when both are known; unavailable routing leaves travel and fit unknown.                                     |
| 05-indoor   | No confirmed outdoor venue. Unknown indoor facts remain unknown/conditional and cannot establish fit.                                                                                   |
| 06-budget   | 3000 KZT per person is a hard upper cap. Unknown price is not free; a lower-bound price cannot prove affordability.                                                                     |
| 07-late     | Use 24 October 2026 23:30 Astana time, including any overnight interval. Proven closed venues excluded; unknown dated hours/route remain unknown.                                       |
| 08-event    | Use separate event endpoint and the selected local date/earliest start. Listing is not a session; end, tickets, price-from, source verification and travel remain independent unknowns. |
| 09-conflict | Do not relax explicit 30-minute total or zero budget to satisfy a two-hour museum visit. Clarify/reject the contradiction; no fits card.                                                |
| 10-missing  | Origin/time/budget remain null, never substituted with the reference point or zero. Missing data and provider unavailability must remain distinct from no_match.                        |

## Thirty core queries — actual statuses

`U` below is the actual safe summary `{status:unavailable,items:[],sources:[],warnings:[{code:provider_unavailable,fields:[]}]}` with HTTP 503.
For events it additionally has contract_version=1.3.0, provider_status=unavailable, provider_code=network_unavailable_or_timeout, live_web_search=not_run, listings=[] and zero rejection counters.
`O` is `{status:unknown,items:[],sources:[],warnings:[{code:missing_input,fields:[]}]}` with HTTP 200. The actual localized prose is intentionally omitted; local UI uses stable codes.
These are safe summaries, not fabricated full wire bodies. No query/GPS payload was written to server logs.

| Case / locale  | Exact query                                                                                               | Actual | Semantic status | Seconds | Request ID                             |
| -------------- | --------------------------------------------------------------------------------------------------------- | ------ | --------------- | ------- | -------------------------------------- |
| 01-walk-kk     | 30 минутқа серуендейтін орын ұсын.                                                                        | 503 U  | not_run         | 5.56    | `e6e52cc2-1f13-4fea-bf78-751154f96b99` |
| 01-walk-ru     | Предложи место для прогулки на 30 минут.                                                                  | 503 U  | not_run         | 8.02    | `c5900907-e7b5-46fb-9890-dabbb414815e` |
| 01-walk-en     | Suggest a place for a 30-minute walk.                                                                     | 503 U  | not_run         | 2.52    | `f2b8b50b-d805-4ec8-9238-79a518b3f5c8` |
| 02-outlet-kk   | Розеткасы бар кофехана керек, ноутбукты қуаттағым келеді.                                                 | 200 O  | passed          | 0.37    | `47483afb-ca16-491b-9369-185cf6e8d944` |
| 02-outlet-ru   | Нужна кофейня с розеткой, хочу зарядить ноутбук.                                                          | 200 O  | passed          | 0.18    | `90d99960-51b6-4968-8da1-646f949fc696` |
| 02-outlet-en   | I need a coffee shop with a power outlet to charge my laptop.                                             | 200 O  | passed          | 0.37    | `ca256c90-f7b4-4e68-88f6-0d50868dd547` |
| 03-child-kk    | Алты жастағы баламен баруға болатын мұражай ұсын. Жас шектеуі белгісіз болса, айт.                        | 503 U  | not_run         | 2.92    | `92729a8b-743c-40d3-bd65-8df260ef0a2f` |
| 03-child-ru    | Предложи музей для посещения с шестилетним ребенком. Скажи, если возрастные ограничения неизвестны.       | 503 U  | not_run         | 2.31    | `8f46129a-5edc-42e0-9fa6-eb84ffabe73f` |
| 03-child-en    | Suggest a museum to visit with a six-year-old child. Say if age restrictions are unknown.                 | 503 U  | not_run         | 4.01    | `cc6528e7-0c56-438d-bfb7-4e26cc2e71d2` |
| 04-return-kk   | Мен туристпін. Бір көрікті жерге барып, 120 минут ішінде бастапқы нүктеге қайтқым келеді.                 | 503 U  | not_run         | 2.21    | `4aeb7bf0-89e5-4791-b0a1-fdaf183582e2` |
| 04-return-ru   | Я турист. Хочу посетить одну достопримечательность и вернуться в исходную точку за 120 минут.             | 503 U  | not_run         | 4.08    | `365fa851-45f6-4fe6-88a4-e8fcc422cd0c` |
| 04-return-en   | I am a tourist. I want to visit one landmark and return to the starting point within 120 minutes.         | 503 U  | not_run         | 2.1     | `9b0f6e59-0b25-4a2f-9ea3-a2da41cd44e8` |
| 05-indoor-kk   | Тек ғимарат ішінде болатын көрме немесе мұражай керек.                                                    | 503 U  | not_run         | 2.23    | `f684245a-951a-4e45-ab4b-f4f8e9674095` |
| 05-indoor-ru   | Нужна выставка или музей только внутри помещения.                                                         | 503 U  | not_run         | 3.25    | `5e9d4f5c-3190-400c-a2d0-99989cdfcdab` |
| 05-indoor-en   | I need an exhibition or museum strictly indoors.                                                          | 503 U  | not_run         | 5.25    | `07658490-72ae-4084-9b6c-01a5bd19038b` |
| 06-budget-kk   | Түскі асқа бір адамға 3000 теңгеден аспайтын орын керек.                                                  | 503 U  | not_run         | 2.5     | `575a9047-dc35-4bd7-8b18-69abb65482a7` |
| 06-budget-ru   | Нужно место для обеда с бюджетом не более 3000 тенге на человека.                                         | 503 U  | not_run         | 3.41    | `a8b83e01-e020-4f49-9797-d5918e44790a` |
| 06-budget-en   | I need a lunch place costing no more than 3000 tenge per person.                                          | 503 U  | not_run         | 1.98    | `d461655d-33f5-4171-bdaf-ded89f998b33` |
| 07-late-kk     | 2026 жылғы 24 қазанда сағат 23:30-да кофе ішетін орын керек. Ашық екенін тексер.                          | 503 U  | not_run         | 3.5     | `0babf273-135d-48ce-a7c8-b264f7f0fe21` |
| 07-late-ru     | Нужно место выпить кофе 24 октября 2026 года в 23:30. Проверь часы работы.                                | 503 U  | not_run         | 2.26    | `a56d4d1a-8de4-4586-9cdc-4a596815b33b` |
| 07-late-en     | I need a place for coffee at 23:30 on 24 October 2026. Check opening hours.                               | 503 U  | not_run         | 5.74    | `ef4717be-d715-46f2-83a0-662f274262e9` |
| 08-event-kk    | 2026 жылғы 24 қазанда сағат 18:00-ден кейін Астана Операдағы концертті тап.                               | 503 U  | not_run         | 4.09    | `457d09cd-b993-475e-8355-951e6dcd89de` |
| 08-event-ru    | Найди концерт в Астана Опера 24 октября 2026 года после 18:00.                                            | 503 U  | not_run         | 0.58    | `11a07129-6f9e-4b52-9cb8-ccd630f75040` |
| 08-event-en    | Find a concert at Astana Opera after 18:00 on 24 October 2026.                                            | 503 U  | not_run         | 0.58    | `9f012b02-5344-4c71-8c30-a153b13099f8` |
| 09-conflict-kk | Мұражайда кемінде екі сағат болғым келеді, бірақ жалпы уақытым 30 минут, бюджетім 0 теңге.                | 503 U  | not_run         | 2.94    | `92d3d098-c7d0-4b29-9acc-349403d875a3` |
| 09-conflict-ru | Хочу провести в музее не менее двух часов, но всего есть 30 минут и бюджет 0 тенге.                       | 503 U  | not_run         | 2.25    | `341b089e-01a6-4b7e-b581-563f905f9599` |
| 09-conflict-en | I want to spend at least two hours in a museum, but I have only 30 minutes total and a budget of 0 tenge. | 503 U  | not_run         | 2.17    | `8247aba7-1b7c-4d1b-badd-33b8bd541038` |
| 10-missing-kk  | Мұражай ұсын. Бастапқы нүкте, уақыт және бюджет әзірге белгісіз. Белгісіз деректерді ойдан шығарма.       | 503 U  | not_run         | 5.05    | `9873afc1-be46-4f9a-992b-6bcaeb8e6914` |
| 10-missing-ru  | Предложи музей. Исходная точка, время и бюджет пока неизвестны. Не выдумывай отсутствующие данные.        | 503 U  | not_run         | 2.23    | `426dd9b3-2559-497b-a437-3cd8f7344ee5` |
| 10-missing-en  | Suggest a museum. Starting point, time and budget are unknown for now. Do not invent missing data.        | 503 U  | not_run         | 6.03    | `f3404396-cd92-4192-ae31-91ffe10953ac` |

## Mixed language and aliases

These reuse the named case controls and point. Unknown outlet semantics can
pass without a model call; aliases requiring retrieval remain unverified while
the provider is unavailable. No same-venue matching criterion is imposed.

| Variant / base / locale        | Exact query                                                                     | Actual | Status  | Seconds | Request ID                             |
| ------------------------------ | ------------------------------------------------------------------------------- | ------ | ------- | ------- | -------------------------------------- |
| A1-mixed / 02-outlet / kk      | Кофе керек, нужна розетка, power outlet for laptop.                             | 200 O  | passed  | 0.21    | `2941eeb9-734c-42e3-bfad-1987fe89a5a4` |
| A2-nursultan / 10-missing / en | Suggest a museum in Nur-Sultan (Astana); time, origin and budget are unknown.   | 503 U  | not_run | 2.35    | `a2eef56d-6122-428f-885e-f52690858e1f` |
| A3-baiterek / 04-return / ru   | Я турист, хочу увидеть Бәйтерек / Baiterek / Байтерек и вернуться за 120 минут. | 503 U  | not_run | 4.04    | `36aa7e75-a2ce-41b6-8eda-45ffeec28443` |
| A4-mixed-event / 08-event / ru | Astana Opera / Астана Опера, концерт 24 October 2026 после 18:00.               | 503 U  | not_run | 0.54    | `2070d90c-a83f-4270-b8fa-de5188913843` |

## Separate UI and source evidence

The frontend automated/browser matrix, fixes, exact commands, freeze and
remaining language/source limitations are in [D05 handoff](handoffs/D05.md).
The [data audit](handoffs/D05-data-audit.md) records 20 real POIs, seven
categories, branch identity, coordinates, provenance, a Khan Shatyr hours
conflict, three Ballet productions and four calendar hints. It establishes
source consistency, not complete city coverage or confirmed sessions.
The [backend defect notes](handoffs/D05-backend-defects.md) separate live
provider blockers from controlled, reproducible semantic failures.

Positive live POI selection, 30-minute walk policy, child suitability, indoor,
budget, late hours, return routing, missing-input behavior and a positive event
session need repeat acceptance after the external provider blocker is resolved.
Do not replace not_run rows with fixture passes. D06 was not started.

The event UI compatibility defect found during D05 was corrected and repeated
in ru/kk/en: the current unavailable envelope now renders as unavailable.
Those extra browser transport/display checks are separate from the exact
canonical batch and do not promote blocked semantic cases to passed.
