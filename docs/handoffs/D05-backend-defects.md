# D05 backend evidence for Sabyrzhan

Owner: Sabyrzhan. Review baseline: `181e012`, contract 1.3.0. This document
records handoff evidence; it does not claim teammate delivery or acknowledgement.
No backend, contract, dependency or database changes were made during this review.

## Live execution blocker: provider unavailable

The saved run in `frontend/artifacts/d05/api-results.json` contains 34 actual HTTP
requests, including 30 canonical kk/ru/en requests and four mixed/alias requests.
Requests started on 2026-10-19 between 13:13:51 and 13:14:51 Astana time
(UTC+05:00). The runner was `node frontend/scripts/d05-scenarios.mjs` against
`http://127.0.0.1:8000`.

| Population         | HTTP 200 / unknown | HTTP 503 / unavailable | Total |
| ------------------ | -----------------: | ---------------------: | ----: |
| Canonical kk/ru/en |                  3 |                     27 |    30 |
| Mixed/aliases      |                  1 |                      3 |     4 |
| All                |                  4 |                     30 |    34 |

All 34 responses preserved the request ID and `Cache-Control: no-store`.
The four unknown results are the three outlet scenarios and `A1-mixed`.
All four event requests returned `provider_code=network_unavailable_or_timeout`
and `live_web_search=not_run`. No response contained a POI card, event card,
listing or source. A semantic child, indoor, route, date or alias success cannot
be inferred from these unavailable responses. Those live acceptance checks are
not_run; the observed 503 handling is separately verified.

Copyable recorded request for the POI blocker (`10-missing-en`):

```http
POST /api/recommendations
Content-Type: application/json

{
  "request_id": "f3404396-cd92-4192-ae31-91ffe10953ac",
  "query": "Suggest a museum. Starting point, time and budget are unknown for now. Do not invent missing data.",
  "locale": "en",
  "origin": null,
  "available_minutes": null,
  "budget_kzt_per_person": null,
  "date_time": null,
  "return_to_start": false,
  "indoor_only": false,
  "explicit_fields": ["origin", "available_minutes", "budget_kzt_per_person", "date_time", "return_to_start", "indoor_only"]
}
```

Expected with working dependencies: sourced conditional alternatives or an honest
unknown result; absent inputs must remain unknown. Expected during a provider
failure: 503/unavailable, never no_match. Actual sanitized projection:

```json
{
  "http": 503,
  "status": "unavailable",
  "warnings": [{ "code": "provider_unavailable", "fields": [] }],
  "item_count": 0,
  "source_count": 0,
  "correlated": true,
  "cache_control": "no-store"
}
```

The saved English event request (`08-event-en`) is also copyable:

```http
POST /api/events/search
Content-Type: application/json

{
  "request_id": "9f012b02-5344-4c71-8c30-a153b13099f8",
  "query": "Find a concert at Astana Opera after 18:00 on 24 October 2026.",
  "locale": "en",
  "origin": {"latitude":51.1122858,"longitude":71.5316883},
  "available_minutes": 360,
  "budget_kzt_per_person": null,
  "date_time": "2026-10-24T18:00:00+05:00",
  "return_to_start": false,
  "indoor_only": false,
  "explicit_fields": ["origin", "available_minutes", "budget_kzt_per_person", "date_time", "return_to_start", "indoor_only"]
}
```

Actual sanitized projection:

```json
{
  "http": 503,
  "status": "unavailable",
  "contract_version": "1.3.0",
  "provider_status": "unavailable",
  "provider_code": "network_unavailable_or_timeout",
  "live_web_search": "not_run",
  "item_count": 0,
  "listing_count": 0,
  "source_count": 0
}
```

The precise provider root cause is unknown. Do not infer an invalid key, model
permission, exhausted quota or empty corpus from this code. Sabyrzhan should
restore provider access and rerun the same inputs; no provider exception bodies
or credentials are needed in the handoff.

## BQ-01: child suitability can disappear before fit evaluation

Priority: high. Status: controlled failure reproduced; live child acceptance
not_run because all three live child requests returned unavailable.

Minimal query: `A museum suitable for my six-year-old child; say if age restrictions are unknown.`
The complete synthetic request and provider/repository/route stubs are below.
The extraction retains `interests=["child-friendly"]`. All supported source facts
and route legs are deliberately known, isolating the missing requirement.

Expected: do not assert `fits` until child/age suitability is supported. Preserve
that requirement as unknown or request clarification. A conservative unknown
response is sufficient; no new amenity database is required by this handoff.

Actual controlled output:

```json
{
  "case": "family",
  "status": "ok",
  "fit": "fits",
  "missing_fields": [],
  "explanation": "Consider planning a museum visit. Suggested visit allowance: 45 min; advice, not a source fact."
}
```

Evidence: `backend/app/constraints.py:59` guards quietness, power outlets and
accessibility only. `TextIntent`/`ResolvedIntent` in `backend/app/intent.py:17`
have no child/age constraint; `merge_intent` retains interests at line 153, but
the deterministic evaluator does not inspect them. `MissingField` in
`backend/app/schemas.py:92` cannot describe child/age uncertainty. Provider-free
checks also returned an empty unsupported-requirement list for `Museum with my
child`, `Музей с ребенком` and `Баламен мұражайға бару`.

## BQ-02: charging synonyms bypass the unsupported-fact guard

Priority: high. Status: controlled failure reproduced; no new live provider calls
were made for these variants.

Minimal query: `Coffee with a charging point for my laptop.` The stub retains
`interests=["charging point"]` and category `food`.

Expected: preserve uncertainty about power/charging, as for `power outlets`.
Actual controlled output:

```json
{
  "case": "charging",
  "status": "ok",
  "fit": "fits",
  "missing_fields": [],
  "explanation": "Consider planning a food break. Suggested visit allowance: 30 min; advice, not a source fact."
}
```

`unsupported_requirements("Coffee with power outlets")` returns
`["power_outlets"]`; `Coffee with a charging point` and `Кофе с зарядкой для
телефона` return `[]`. The regex is at `backend/app/constraints.py:70`; there is
no subsequent structured amenity field to catch the omitted requirement.
The observed live `power outlet` variants correctly returned 200/unknown and
zero cards; this controlled synonym failure must not invalidate those results.

## BQ-03: clarification messages expose internal field keys

Priority: low. Status: controlled failure reproduced. A Russian request with
`TextIntent.conflicts=["indoor_only"]` produces:

```json
{
  "status": "unknown",
  "warnings": [
    {
      "code": "missing_input",
      "message": "Уточните ограничения: indoor_only.",
      "fields": []
    }
  ]
}
```

Expected: a localized label for the conflicting constraint, with its stable key
available separately for the client. `backend/app/recommend.py:96` joins raw
clarification keys into localized prose. The analogous composition is in
`backend/app/event_recommend.py:168`. Frontend generic warning translations can
hide this string, but the API localization gap remains. Do not change the shared
contract from Damir's branch.

## Policy limitation: every 30-minute request is rejected

Status: controlled policy behavior verified; this is distinct from a provider
failure or a proven data error. All eight activity codes are hard rejected for
`available_minutes=30`, even with no travel time. The minimum visit policy is
30 minutes, plus a five-minute entry allowance and a five-minute buffer
(`backend/app/constraints.py:20`, `:25`, `:80`). Walks therefore require at least
40 minutes under the current policy. A 30-minute walk cannot produce a card.

For D05 this is an acceptance limitation to discuss with Sabyrzhan, not authority
to change duration policy. If a later change allows a shorter suggested walk,
it must still preserve travel, return and buffer constraints. The current live
walk requests all returned unavailable, so no live no_match is claimed here.

Unknown indoor values are correctly retained as conditional missing data by
`backend/app/constraints.py:298`. Unknown indoor alone is not evidence of a bug.
Retrieval is bounded to 12 rows and a default five-kilometer radius; the separate
three-card shortlist is also bounded. No live response in this run was no_match,
so the run provides no evidence of a city-wide absence claim or a false no_match.

## Complete controlled reproduction

Run from the repository root with the existing dependency runtime. This script
reads only the explicitly synthetic `contracts/examples/poi.test.json`; it makes
no network/database/provider calls and writes no files. The fixed coordinates
are the public Baiterek QA reference, not user GPS. All routes and source facts
in this reproduction are synthetic. The command completed with exit 0.

```powershell
$d05Python = 'C:/Users/Ilytsm/.codex/worktrees/current-project-run/hackatonqbersGDG/.venv/Scripts/python.exe'
@'
import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

from backend.app.constraints import hard_reject, unsupported_requirements
from backend.app.explain import ExplanationBatch
from backend.app.intent import ResolvedIntent, TextIntent
from backend.app.recommend import RecommendationService
from backend.app.schemas import POIRecord, RecommendationRequest, RouteLeg, RouteProvenance

BASE = json.loads(Path('contracts/examples/poi.test.json').read_text(encoding='utf-8'))

def record(**updates):
    row = {**BASE, **updates}
    row['provenance'] = [{
        **BASE['provenance'][0],
        'fields': sorted(set(BASE['provenance'][0]['fields']) | set(updates)),
    }]
    return POIRecord.model_validate(row)

def extraction(**updates):
    values = dict(
        language='en', interests=[], categories=['museum'], name_queries=[],
        available_minutes=None, budget_kzt_per_person=None, indoor=[],
        return_to_start=[], date_time=None, conflicts=[],
    )
    return TextIntent.model_validate({**values, **updates})

def service(poi, text):
    repository, client, router = AsyncMock(), AsyncMock(), AsyncMock()
    repository.retrieve_candidates.return_value = [dict(
        document=poi.model_dump(mode='json'), lexical_score=1.0,
        semantic_score=0.9, category_match=True, score=2.0,
        distance_m=500, metadata=None,
    )]
    repository.coverage.return_value = dict(production_pois=985, embedded_pois=985)
    client.embed.return_value = [0.5] * 1536

    async def parse(payload, schema, **kwargs):
        if schema is TextIntent:
            return text
        packet = json.loads(payload)
        return ExplanationBatch(locale=packet['locale'], items=[dict(
            item_id=item['item_id'], source_ids=item['source_ids'],
            reason_codes=item['allowed_reason_codes'],
            activity_code=item['activity_code'], idea=item['allowed_ideas'][0],
        ) for item in packet['alternatives']])

    client.parse_response.side_effect = parse
    leg = RouteLeg(
        status='known', distance_meters=300, duration_seconds=120,
        provenance=RouteProvenance(
            retrieved_at=datetime.fromisoformat('2030-01-15T10:00:00+05:00'),
            provider_locale='ru',
        ),
    )
    router.route.return_value = (leg, leg)
    return RecommendationService(repository, client, router)

async def main():
    cases = [
        ('family', 'A museum suitable for my six-year-old child; say if age restrictions are unknown.',
         'museum', ['child-friendly']),
        ('charging', 'Coffee with a charging point for my laptop.',
         'food', ['charging point']),
    ]
    for label, query, activity, interests in cases:
        app = service(
            record(activity_code=activity, price_kzt_per_person=500, opening_hours_text='24/7'),
            extraction(categories=[activity], interests=interests),
        )
        request = RecommendationRequest(
            query=query, locale='en',
            origin={'latitude': 51.1282882, 'longitude': 71.4304546},
            available_minutes=100, budget_kzt_per_person=1000,
            date_time='2030-01-15T10:00:00+05:00',
        )
        response = await app.recommend(request)
        card = response.items[0]
        print(json.dumps(dict(
            case=label, status=response.status, fit=card.fit_status,
            missing_fields=card.missing_fields, explanation=card.explanation,
        )))
        assert response.status == 'ok' and card.fit_status == 'fits'
        assert card.missing_fields == []

    app = service(record(), extraction(conflicts=['indoor_only']))
    response = await app.recommend(RecommendationRequest(
        query='Public QA conflicting indoor requirements', locale='ru',
    ))
    print(json.dumps(dict(
        case='conflict', status=response.status,
        warnings=[warning.model_dump() for warning in response.warnings],
    )))
    assert response.warnings[0].message.endswith('indoor_only.')

    activities = ['walk', 'museum', 'food', 'culture', 'sport', 'shopping', 'entertainment', 'other']
    rejected = {activity: hard_reject(
        record(activity_code=activity), ResolvedIntent(query='Public QA', available_minutes=30),
    ) for activity in activities}
    print(json.dumps(dict(case='thirty_minute_policy', rejected=rejected)))
    assert all(rejected.values())
    guards = {query: unsupported_requirements(query) for query in [
        'Museum with my child', 'Coffee with power outlets', 'Coffee with a charging point',
    ]}
    print(json.dumps(dict(case='guards', results=guards)))
    assert guards['Coffee with power outlets'] == ['power_outlets']
    assert guards['Coffee with a charging point'] == []

asyncio.run(main())
'@ | & $d05Python -B -
```

The assertions intentionally verify the current faulty outputs; they are a
reproduction, not desired regression-test expectations. Reverse those semantic
expectations when implementing the owner-approved fix.

Initial local probes failed before exercising product behavior: system Python
lacked Pydantic; the existing application runtime lacked pytest, so importing
test helpers failed. A first standalone attempt also had a duplicate Python
keyword in its temporary test harness. The final reproduction above avoids
pytest/test-helper imports and passed. No dependency was installed to make it
pass, and none of these harness failures is reported as a product defect.

## Evidence/privacy audit

The live artifact retains the fixed public QA inputs, generated request IDs,
timestamps, HTTP/status codes, correlation/no-store flags and stable summaries.
It does not retain raw response bodies, provider exception text, headers, keys,
transient event titles, session payloads, citation contexts or generated prose.
All saved card arrays are empty in this run. Public scenario coordinates and
queries are test inputs, never real user location/history.

The controlled reproduction is separate from the 30 live acceptance statuses;
its synthetic successes/failures do not count as a live city-corpus result.
Next consumer: Sabyrzhan for provider recovery and BQ-01/BQ-02/BQ-03 assessment;
Damir/D06 for rerunning the blocked acceptance cases after that work. No D06
implementation is included.
