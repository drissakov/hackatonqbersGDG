"""S04 composition and real HTTP contracts with deterministic provider doubles."""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.database import DatabaseUnavailable
from backend.app.explain import ExplanationBatch
from backend.app.intent import TextIntent
from backend.app.openai_client import ProviderError
from backend.app.recommend import RecommendationService
from backend.app.schemas import (
    POIRecord,
    RecommendationRequest,
    RecommendationResponse,
    RouteLeg,
    RouteProvenance,
)
from backend.tests.test_api import request
from backend.tests.test_intent import text_intent
from backend.tests.test_repository import poi


def record(**updates):
    row = poi()
    row.update(updates)
    fields = set(row["provenance"][0]["fields"]) | set(updates)
    row["provenance"][0]["fields"] = sorted(fields)
    return POIRecord.model_validate(row)


def candidate_row(poi):
    return {
        "document": poi.model_dump(mode="json"),
        "lexical_score": 1.0,
        "semantic_score": 0.9,
        "category_match": True,
        "score": 2.0,
        "distance_m": 500,
        "metadata": None,
    }


def service(records, extracted=None, router=None):
    repository, client = AsyncMock(), AsyncMock()
    repository.retrieve_candidates.return_value = [candidate_row(p) for p in records]
    repository.coverage.return_value = {"production_pois": 985, "embedded_pois": 985}
    client.embed.return_value = [0.5] * 1536

    async def parse(text, schema, **kwargs):
        if schema is TextIntent:
            return extracted or text_intent(categories=["museum"])
        raise ProviderError("response_incomplete_or_refused")

    client.parse_response.side_effect = parse
    return RecommendationService(repository, client, router), repository, client


def test_unknown_route_price_hours_are_conditional_and_facts_are_separate():
    poi = record(price_kzt_per_person=None, opening_hours_text=None)
    search, _, _ = service([poi])
    result = asyncio.run(
        search.recommend(
            RecommendationRequest(query="Synthetic museum", locale="ru", budget_kzt_per_person=1000)
        )
    )
    card = result.items[0]
    assert result.status == "partial" and card.fit_status == "unknown"
    assert card.poi == poi and card.poi.visit_minutes_estimate == 45
    assert card.travel_minutes_estimate is None
    assert {"price_kzt_per_person", "opening_hours", "travel_minutes_estimate"} <= set(
        card.missing_fields
    )
    assert "within_budget" not in card.reason_codes and "within_time" not in card.reason_codes
    assert card.generated_locale == "ru" and card.action.url == poi.sources[0].url
    assert result.sources == poi.sources
    assert "оцен" in card.explanation.lower() or "рекомен" in card.explanation.lower()
    RecommendationResponse.model_validate_json(result.model_dump_json())


def test_hard_conflicts_are_filtered_before_any_routing():
    router = AsyncMock()
    search, _, client = service([record(price_kzt_per_person=5000)], router=router)
    result = asyncio.run(
        search.recommend(
            RecommendationRequest(query="Synthetic museum", budget_kzt_per_person=1000)
        )
    )
    assert result.status == "no_match" and result.items == []
    router.route.assert_not_called()
    assert client.parse_response.await_count == 1


def test_conflicting_intent_and_unsupported_amenities_require_clarification():
    search, repository, client = service([], text_intent(conflicts=["date_time"]))
    result = asyncio.run(search.recommend(RecommendationRequest(query="Synthetic")))
    assert result.status == "unknown" and result.warnings[0].code == "missing_input"
    repository.retrieve_candidates.assert_not_called()
    client.embed.assert_not_called()
    search, repository, client = service([])
    result = asyncio.run(search.recommend(RecommendationRequest(query="Тихое место с розетками")))
    assert result.status == "unknown" and not result.items
    repository.retrieve_candidates.assert_not_called()
    client.parse_response.assert_not_called()


def test_intent_outage_and_database_outage_never_become_no_match():
    search, repository, client = service([])
    client.parse_response.side_effect = ProviderError("network_unavailable_or_timeout")
    result = asyncio.run(search.recommend(RecommendationRequest(query="Synthetic")))
    assert result.status == "unavailable" and not result.items
    search, repository, _ = service([])
    repository.retrieve_candidates.side_effect = DatabaseUnavailable("synthetic-private")
    result = asyncio.run(search.recommend(RecommendationRequest(query="Synthetic")))
    assert result.status == "unavailable"
    assert "synthetic-private" not in result.model_dump_json()


def test_three_distinct_alternatives_and_bounded_routes():
    records = [record(id=f"test:poi-{i}") for i in range(7)]
    router = AsyncMock()
    from backend.app.schemas import RouteLeg

    router.route.return_value = (
        RouteLeg(status="unavailable", reason="disabled"),
        RouteLeg(status="unavailable", reason="disabled"),
    )
    search, _, client = service([records[0], *records], router=router)
    result = asyncio.run(
        search.recommend(
            RecommendationRequest(
                query="Synthetic museum",
                origin={"latitude": 51.12, "longitude": 71.43},
                return_to_start=True,
            )
        )
    )
    assert len(result.items) == 3 and len({item.poi.id for item in result.items}) == 3
    assert router.route.await_count == 3
    assert all(call.args[0].return_to_start for call in router.route.call_args_list)
    assert client.parse_response.await_count == 2  # Intent + one batch explanation.


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
def test_http_unavailable_preserves_envelope_correlation_and_no_store(path, locale, monkeypatch):
    def unavailable(_):
        raise DatabaseUnavailable("synthetic-private")

    monkeypatch.setattr(main, "get_repository", unavailable)
    payload = {
        "query": "Synthetic",
        "locale": locale,
        "request_id": "00000000-0000-4000-8000-000000000001",
    }
    response = request(main.create_app(), "POST", path, json=payload)
    result = RecommendationResponse.model_validate(response.json())
    assert response.status_code == 503 and result.status == "unavailable"
    assert str(result.request_id) == payload["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert "synthetic-private" not in response.text


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
def test_http_pipeline_calls_existing_retriever_and_returns_actual_cards(path, monkeypatch):
    search, repository, client = service([record()])

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: None)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    response = request(main.create_app(), "POST", path, json={"query": "Synthetic museum"})
    assert response.status_code == 200
    result = RecommendationResponse.model_validate(response.json())
    assert result.status == "partial" and result.items[0].poi.id == "test:poi-001"
    repository.retrieve_candidates.assert_awaited_once()


def test_fully_evaluated_pool_of_closed_places_can_be_no_match():
    records = [record(id=f"test:{i}", opening_hours_text="Mo-Su 09:00-10:00") for i in range(5)]
    router = AsyncMock()
    router.route.return_value = (
        RouteLeg(
            status="known",
            duration_seconds=60,
            distance_meters=10,
            provenance=RouteProvenance(
                retrieved_at=datetime.fromisoformat("2030-01-15T19:00:00+05:00"),
                provider_locale="ru",
            ),
        ),
        RouteLeg(status="not_requested", reason="not_requested"),
    )
    search, _, _ = service(records, router=router)
    result = asyncio.run(
        search.recommend(
            RecommendationRequest(
                query="Synthetic museum",
                available_minutes=100,
                date_time="2030-01-15T19:00:00+05:00",
                origin={"latitude": 51.12, "longitude": 71.43},
            )
        )
    )
    assert result.status == "no_match" and not result.items
    assert router.route.await_count == len(records)


def test_zero_candidates_with_embedding_outage_or_empty_corpus_are_not_no_match():
    search, repository, client = service([])
    client.embed.side_effect = ProviderError("network_unavailable_or_timeout")
    result = asyncio.run(search.recommend(RecommendationRequest(query="Synthetic")))
    assert result.status == "unavailable"
    search, repository, _ = service([])
    repository.coverage.return_value = {"production_pois": 0, "embedded_pois": 0}
    result = asyncio.run(search.recommend(RecommendationRequest(query="Synthetic")))
    assert result.status == "unknown" and result.warnings


@pytest.mark.parametrize(
    "production,embedded,expected",
    [(985, 985, "no_match"), (0, 0, "unknown"), (985, 0, "unknown")],
)
def test_http_empty_retrieval_uses_repository_coverage_mapping(
    production, embedded, expected, monkeypatch
):
    _, repository, client = service([])
    # Match PostgresPOIRepository.coverage(), which returns a dict, not an object.
    repository.coverage.return_value = {"production_pois": production, "embedded_pois": embedded}

    class Context:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: None)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: Context())
    response = request(
        main.create_app(), "POST", "/api/recommendations", json={"query": "Synthetic museum"}
    )
    assert response.status_code == 200
    parsed = RecommendationResponse.model_validate(response.json())
    assert parsed.status == expected and not parsed.items
    repository.coverage.assert_awaited_once()


def test_known_fit_can_be_ok_and_duration_remains_recommendation():
    row = record(price_kzt_per_person=500, opening_hours_text="24/7", visit_minutes_estimate=7)
    router = AsyncMock()
    leg = RouteLeg(
        status="known",
        distance_meters=300,
        duration_seconds=120,
        provenance=RouteProvenance(
            retrieved_at=datetime.fromisoformat("2030-01-15T10:00:00+05:00"), provider_locale="ru"
        ),
    )
    router.route.return_value = (leg, leg)
    search, _, client = service([row], router=router)

    async def valid_parse(text, schema, **kwargs):
        if schema is TextIntent:
            return text_intent(categories=["museum"])
        packet = json.loads(text)
        assert "duration_seconds" not in text and "travel_minutes_estimate" not in text
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

    client.parse_response.side_effect = valid_parse
    result = asyncio.run(
        search.recommend(
            RecommendationRequest(
                query="Synthetic museum",
                available_minutes=100,
                budget_kzt_per_person=1000,
                date_time="2030-01-15T10:00:00+05:00",
                return_to_start=True,
                origin={"latitude": 51.12, "longitude": 71.43},
            )
        )
    )
    assert result.status == "ok" and len(result.items) == 1
    card = result.items[0]
    assert card.fit_status == "fits" and card.missing_fields == []
    assert card.travel_minutes_estimate == 4
    assert card.visit_minutes_estimate == 45 and card.poi.visit_minutes_estimate == 7
    assert {"within_time", "within_budget", "visit_duration_estimate"} <= set(card.reason_codes)
