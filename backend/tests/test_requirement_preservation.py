"""Unsupported requirements must survive selection without inventing venue facts."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.constraints import unsupported_requirements
from backend.app.explain import ExplanationBatch
from backend.app.intent import TextIntent
from backend.app.schemas import (
    RecommendationRequest,
    RecommendationResponse,
    RouteLeg,
    RouteProvenance,
)
from backend.tests.test_api import request
from backend.tests.test_event_recommend import search as search_events
from backend.tests.test_event_recommend import service as event_service
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record, service

REQUIREMENTS = [
    ("child_suitability", "kk", "Алты жастағы баламен баруға болатын мұражай ұсын."),
    ("child_suitability", "ru", "Предложи музей для посещения с шестилетним ребенком."),
    ("child_suitability", "en", "A museum suitable for my six-year-old child."),
    ("child_suitability", "kk", "Балалар үшін қолайлы мұражай ұсын."),
    ("child_suitability", "kk", "Бала үшін қолайлы мұражай ұсын."),
    ("child_suitability", "kk", "Отбасымен баратын мұражай ұсын."),
    ("child_suitability", "ru", "Предложи музей для всей семьи."),
    ("child_suitability", "en", "Suggest a museum for the whole family."),
    ("child_suitability", "en", "Suggest a museum where children are welcome."),
    ("child_suitability", "kk", "6 жасқа лайық мұражай ұсын."),
    ("child_suitability", "kk", "Алты жасқа сай мұражай."),
    ("power_outlets", "kk", "Телефонды зарядтауға болатын кафе керек."),
    ("power_outlets", "ru", "Кофе с зарядкой для телефона."),
    ("power_outlets", "en", "Coffee with a charging point for my laptop."),
    ("power_outlets", "ru", "Кафе, где можно зарядить смартфон."),
    ("power_outlets", "en", "A cafe to charge my smartphone."),
    ("power_outlets", "ru", "Кафе с зарядкой."),
    ("power_outlets", "ru", "Нужно кафе, где есть подзарядка."),
    ("power_outlets", "ru", "Есть ли зарядка в кафе?"),
    ("power_outlets", "en", "Find a cafe, charging required."),
]
MESSAGE_TERMS = {
    "child_suitability": {
        "kk": ("бала", "жас"),
        "ru": ("дет", "реб", "возраст"),
        "en": ("child", "age"),
    },
    "power_outlets": {
        "kk": ("қуат", "заряд", "розет"),
        "ru": ("заряд", "розет", "питан"),
        "en": ("charg", "power", "outlet"),
    },
}
ORDINARY_QUERIES = [
    "Show ballet at Astana Ballet.",
    "Покажи балет в Астана Балет.",
    "Show the museum named «Балалар».",
    "Find the Children's Museum.",
    "Visit Family Park.",
    "Посети Детский мир.",
    "Найди музей детства.",
    "What is the museum admission charge?",
    "Find a museum free of charge.",
    "Музей после утренней зарядки.",
    "Кафе «Зарядка» рядом с парком.",
    "Хочу зарядиться энергией в парке.",
    "Museum after morning exercise.",
    "Кәдімгі кафе ұсын.",
    "Предложи обычное кафе.",
    "Suggest an ordinary cafe.",
]


def known_fact_service(*, locale="en", requirement=None):
    """All supported facts fit, so only an omitted requirement could prevent a match."""
    activity = "food" if requirement == "power_outlets" else "museum"
    poi = record(
        activity_code=activity,
        price_kzt_per_person=500,
        opening_hours_text="24/7",
        indoor=True,
    )
    router = AsyncMock()
    leg = RouteLeg(
        status="known",
        distance_meters=300,
        duration_seconds=120,
        provenance=RouteProvenance(retrieved_at="2030-01-15T10:00:00+05:00", provider_locale="ru"),
    )
    router.route.return_value = (leg, leg)
    search, repository, client = service([poi], router=router)

    async def parse(text, schema, **kwargs):
        if schema is TextIntent:
            return text_intent(
                language=locale,
                categories=[activity],
                interests=[requirement] if requirement else [],
            )
        packet = json.loads(text)
        return ExplanationBatch(
            locale=packet["locale"],
            items=[
                {
                    "item_id": item["item_id"],
                    "source_ids": item["source_ids"],
                    "reason_codes": item["allowed_reason_codes"],
                    "activity_code": item["activity_code"],
                    "idea": item["allowed_ideas"][0],
                }
                for item in packet["alternatives"]
            ],
        )

    client.parse_response.side_effect = parse
    return search, repository, client, router


def known_fact_request(query, locale="en"):
    return RecommendationRequest(
        query=query,
        locale=locale,
        origin={"latitude": 51.12, "longitude": 71.43},
        available_minutes=120,
        budget_kzt_per_person=1000,
        date_time="2030-01-15T10:00:00+05:00",
        return_to_start=True,
        indoor_only=True,
        explicit_fields=[
            "origin",
            "available_minutes",
            "budget_kzt_per_person",
            "date_time",
            "return_to_start",
            "indoor_only",
        ],
    )


def assert_requirement_unknown(result, requirement, locale):
    assert result.status == "unknown"
    assert result.items == result.sources == []
    assert result.warnings and result.warnings[0].code == "missing_input"
    message = result.warnings[0].message.casefold()
    assert any(term in message for term in MESSAGE_TERMS[requirement][locale])
    assert requirement not in message


@pytest.mark.parametrize("requirement,locale,query", REQUIREMENTS)
def test_requirement_cannot_be_lost_when_every_supported_fact_fits(requirement, locale, query):
    assert unsupported_requirements(query) == [requirement]
    search, repository, client, router = known_fact_service(locale=locale, requirement=requirement)
    result = asyncio.run(search.recommend(known_fact_request(query, locale)))
    assert_requirement_unknown(result, requirement, locale)
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
@pytest.mark.parametrize("requirement,locale,query", REQUIREMENTS)
def test_http_preserves_unknown_requirement_without_provider_work(
    path, requirement, locale, query, monkeypatch
):
    _, repository, client, router = known_fact_service(locale=locale, requirement=requirement)

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    # This regression exercises the no-evidence path, independently of packaged real data.
    monkeypatch.setattr(api, "load_feature_catalog", lambda: None)
    payload = known_fact_request(query, locale).model_dump(mode="json")
    response = request(main.create_app(), "POST", path, json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = RecommendationResponse.model_validate(response.json())
    assert str(result.request_id) == payload["request_id"]
    assert_requirement_unknown(result, requirement, locale)
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []


@pytest.mark.parametrize("requirement,locale,query", REQUIREMENTS)
def test_shared_event_guard_preserves_requirement_before_discovery(requirement, locale, query):
    router = AsyncMock()
    search, repository, client = event_service(router=router)
    result = search_events(search, query=query, locale=locale)
    assert_requirement_unknown(result, requirement, locale)
    assert result.listings == [] and result.live_web_search == "not_run"
    assert result.provider_code == "unsupported_fact_requirement"
    assert client.parse_calls == client.search_calls == []
    assert repository.mock_calls == router.mock_calls == []


@pytest.mark.parametrize("query", ORDINARY_QUERIES)
def test_unrelated_words_and_named_venues_are_not_unsupported_requirements(query):
    assert unsupported_requirements(query) == []
    search, repository, client, router = known_fact_service()
    result = asyncio.run(search.recommend(known_fact_request(query)))
    assert result.status == "ok"
    assert len(result.items) == 1 and result.sources
    assert result.items[0].fit_status == "fits" and result.items[0].missing_fields == []
    repository.retrieve_candidates.assert_awaited_once()
    assert client.parse_response.await_count == 2
    router.route.assert_awaited_once()
