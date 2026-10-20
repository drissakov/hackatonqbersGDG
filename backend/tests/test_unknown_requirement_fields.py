"""Unknown facts expose distinct language-independent reasons to result consumers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.constraints import unsupported_requirement_fields
from backend.app.event_schemas import TransientEventSearchResponse
from backend.app.intent import TextIntent
from backend.app.schemas import MissingField, RecommendationResponse
from backend.tests.test_api import request
from backend.tests.test_event_recommend import search as search_events
from backend.tests.test_event_recommend import service as event_service
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record, service
from backend.tests.test_requirement_preservation import known_fact_request, known_fact_service

CHILD = "child_suitability"
AGE = "age_restrictions"
POWER = "power_outlets"
EXPLICIT_CASES = [
    ("kk", "Балалар үшін қолайлы мұражай ұсын.", {CHILD}),
    ("ru", "Музей для ребёнка.", {CHILD}),
    ("en", "A museum for children.", {CHILD}),
    ("kk", "6 жасқа лайық мұражай ұсын.", {AGE}),
    ("ru", "Музей без возрастных ограничений.", {AGE}),
    ("en", "An event suitable for all ages.", {AGE}),
    ("kk", "Алты жастағы баламен баратын мұражай ұсын.", {CHILD, AGE}),
    ("kk", "6 жасар баламен баратын мұражай ұсын.", {CHILD, AGE}),
    ("ru", "Музей для посещения с шестилетним ребёнком.", {CHILD, AGE}),
    ("ru", "Музей для детей 6 лет.", {CHILD, AGE}),
    ("ru", "Музей с ребёнком шести лет.", {CHILD, AGE}),
    ("en", "A museum suitable for my six-year-old child.", {CHILD, AGE}),
    ("en", "A museum for a child aged six.", {CHILD, AGE}),
    ("kk", "Телефонды зарядтауға болатын кафе керек.", {POWER}),
    ("ru", "Кафе с зарядкой для телефона.", {POWER}),
    ("en", "A cafe with a charging point for my laptop.", {POWER}),
    (
        "kk",
        "Алты жастағы баламен баруға және телефонды зарядтауға болатын кафе.",
        {CHILD, AGE, POWER},
    ),
    ("ru", "Кафе для шестилетнего ребёнка с зарядкой для телефона.", {CHILD, AGE, POWER}),
    ("en", "A cafe for my six-year-old child with a charging point.", {CHILD, AGE, POWER}),
]


def assert_unknown_fields(result, expected):
    assert result.status == "unknown"
    assert result.items == result.sources == []
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == "missing_input"
    assert set(warning.fields) == expected
    assert len(warning.fields) == len(expected)
    assert all(isinstance(field, MissingField) for field in warning.fields)


@pytest.mark.parametrize("locale,query,expected", EXPLICIT_CASES)
def test_raw_requirements_expose_specific_fields_to_poi_and_event_consumers(
    locale, query, expected
):
    fields = unsupported_requirement_fields(query)
    assert set(fields) == expected and len(fields) == len(expected)

    search, repository, client, router = known_fact_service(locale=locale)
    result = asyncio.run(search.recommend(known_fact_request(query, locale)))
    assert_unknown_fields(result, expected)
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []

    event_router = AsyncMock()
    events, event_repository, event_client = event_service(router=event_router)
    event_result = search_events(events, query=query, locale=locale)
    assert_unknown_fields(event_result, expected)
    assert event_result.listings == [] and event_result.live_web_search == "not_run"
    assert event_result.provider_code == "unsupported_fact_requirement"
    assert event_client.parse_calls == event_client.search_calls == []
    assert event_repository.mock_calls == event_router.mock_calls == []


@pytest.mark.parametrize(
    "path,event_mode",
    [
        ("/api/recommendations", False),
        ("/api/v1/recommendations", False),
        ("/api/events/search", True),
        ("/api/v2/events/search", True),
    ],
)
@pytest.mark.parametrize("locale,query,expected", EXPLICIT_CASES)
def test_http_aliases_preserve_exact_reason_fields_without_provider_work(
    path, event_mode, locale, query, expected, monkeypatch
):
    if event_mode:
        router = AsyncMock()
        _, repository, client = event_service(router=router)
    else:
        _, repository, client, router = known_fact_service(locale=locale)
    lifecycle = {"entered": False, "closed": False}

    class ClientContext:
        async def __aenter__(self):
            lifecycle["entered"] = True
            return client

        async def __aexit__(self, *_):
            lifecycle["closed"] = True

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    # Keep missing-evidence behavior isolated from the real packaged supplement.
    monkeypatch.setattr(api, "load_feature_catalog", lambda: None)
    payload = known_fact_request(query, locale).model_dump(mode="json")

    response = request(main.create_app(), "POST", path, json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    response_type = TransientEventSearchResponse if event_mode else RecommendationResponse
    result = response_type.model_validate(response.json())
    assert str(result.request_id) == payload["request_id"]
    assert_unknown_fields(result, expected)
    assert lifecycle == {"entered": True, "closed": True}
    assert repository.mock_calls == router.mock_calls == []
    if event_mode:
        assert result.listings == [] and result.live_web_search == "not_run"
        assert result.provider_code == "unsupported_fact_requirement"
        assert client.parse_calls == client.search_calls == []
    else:
        assert client.mock_calls == []


@pytest.mark.parametrize(
    "interests,expected",
    [
        (["child_suitability"], {CHILD}),
        (["child suitability"], {CHILD}),
        (["age_restrictions"], {AGE}),
        (["AGE-RESTRICTIONS"], {AGE}),
        (["age limits"], {AGE}),
        (["power_outlets"], {POWER}),
        (["child_suitability", "age_restrictions"], {CHILD, AGE}),
        (["child_suitability", "age_restrictions", "power_outlets"], {CHILD, AGE, POWER}),
        (["age_restrictions", "AGE-RESTRICTIONS", "age limits"], {AGE}),
    ],
)
def test_extracted_reasons_survive_distinctly_before_poi_routes_or_event_discovery(
    interests, expected
):
    query = "Suggest a museum."
    assert unsupported_requirement_fields(query) == []
    fields = unsupported_requirement_fields(query, interests=interests)
    assert set(fields) == expected and len(fields) == len(expected)
    router = AsyncMock()
    poi = record(price_kzt_per_person=500, opening_hours_text="24/7", indoor=True)
    provider, repository, client = service(
        [poi], extracted=text_intent(categories=["museum"], interests=interests), router=router
    )

    result = asyncio.run(provider.recommend(known_fact_request(query)))

    assert_unknown_fields(result, expected)
    repository.retrieve_candidates.assert_awaited_once()
    router.route.assert_not_called()
    assert client.parse_response.await_count == 1
    assert client.parse_response.await_args.args[1] is TextIntent

    event_router = AsyncMock()
    events, event_repository, event_client = event_service(
        extracted=text_intent(categories=[], interests=interests), router=event_router
    )
    event_result = search_events(events, query=query, locale="en")
    assert_unknown_fields(event_result, expected)
    assert event_result.listings == [] and event_result.live_web_search == "not_run"
    assert event_result.provider_code == "unsupported_fact_requirement"
    assert [call[1] for call in event_client.parse_calls] == [TextIntent]
    assert event_client.search_calls == []
    assert event_repository.mock_calls == event_router.mock_calls == []


@pytest.mark.parametrize(
    "query,interests",
    [
        ("Find the Children's Museum.", ["Children's Museum"]),
        ("Visit Children’s Museum.", ["Children’s Museum"]),
        ("Visit Family Park.", ["Family Park"]),
        ("Show the museum named «Балалар».", ["Балалар"]),
        ("Посети Детский мир.", ["Детский мир"]),
        ("I have 30 minutes; leave at 6 PM.", []),
        ("Find a museum free of charge.", []),
        ("Музей после утренней зарядки.", []),
        ("Кафе «Зарядка» рядом с парком.", ["Зарядка"]),
    ],
)
def test_names_times_and_other_charges_do_not_invent_specific_requirements(query, interests):
    assert unsupported_requirement_fields(query, interests=interests) == []
