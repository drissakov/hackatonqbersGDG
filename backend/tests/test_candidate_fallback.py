"""Progressive destination checks remain bounded and preserve known constraints."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app import api, main
from backend.app import recommend as recommendation_module
from backend.app.explain import ExplanationBatch
from backend.app.intent import TextIntent
from backend.app.schemas import (
    ActivityCode,
    RecommendationRequest,
    RecommendationResponse,
    RouteLeg,
    RouteProvenance,
)
from backend.tests.test_api import request as http_request
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record, service

ROOT = Path(__file__).resolve().parents[2]
CHECKED = "2030-01-15T10:00:00+05:00"
ABSENT = RouteLeg(status="not_requested", reason="not_requested")


def known(minutes=1):
    return RouteLeg(
        status="known",
        duration_seconds=minutes * 60,
        distance_meters=minutes * 50,
        provenance=RouteProvenance(retrieved_at=CHECKED, provider_locale="en"),
    )


def rows(count, **updates):
    return [
        record(
            id=f"test:fallback-{index:03}",
            name=f"SYNTHETIC TEST ONLY - Fictional Museum {index}",
            opening_hours_text="24/7",
            price_kzt_per_person=0,
            indoor=True,
            location={"latitude": 51.12 + index / 10000, "longitude": 71.43},
            **updates,
        )
        for index in range(count)
    ]


def search_request(**updates):
    return RecommendationRequest.model_validate(
        {
            "query": "Synthetic museum",
            "locale": "en",
            "origin": {"latitude": 51.12, "longitude": 71.43},
            "available_minutes": 60,
            "date_time": CHECKED,
            **updates,
        }
    )


def search_service(records, *, route_pairs=None, extracted=None):
    router = AsyncMock()
    router.route.return_value = (known(), ABSENT)
    if route_pairs is not None:
        router.route.side_effect = route_pairs
    search, repository, client = service(records, extracted=extracted, router=router)

    async def valid_parse(text, schema, **_kwargs):
        if schema is TextIntent:
            return extracted or text_intent(categories=["museum"])
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

    client.parse_response.side_effect = valid_parse
    return search, repository, client, router


def assert_wire_contract(result):
    payload = result.model_dump(mode="json")
    schema = json.loads((ROOT / "contracts/recommendation-response.schema.json").read_text("utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    assert RecommendationResponse.model_validate(payload) == result


@pytest.mark.parametrize("reason", ["travel", "closed"])
def test_fourth_candidate_is_checked_after_three_proven_conflicts(reason):
    records = rows(4)
    if reason == "closed":
        records[:3] = [
            row.model_copy(update={"opening_hours_text": "Mo-Su 18:00-19:00"})
            for row in records[:3]
        ]
    routes = [(known(10 if reason == "travel" else 1), ABSENT)] * 3 + [(known(), ABSENT)]
    search, repository, _, router = search_service(records, route_pairs=routes)

    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "ok"
    assert [card.poi.id for card in result.items] == [records[3].id]
    assert result.items[0].fit_status == "fits"
    assert router.route.await_count == 4
    assert repository.retrieve_candidates.await_args.kwargs["limit"] == 12
    assert_wire_contract(result)


def test_progressive_checks_fill_three_alternatives_and_stop_before_later_candidates():
    records = rows(9)
    routes = [(known(10), ABSENT), (known(), ABSENT)] * 3
    search, _, _, router = search_service(records, route_pairs=routes)

    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "ok"
    assert {card.poi.id for card in result.items} == {records[i].id for i in (1, 3, 5)}
    assert router.route.await_count == 6
    assert all(card.fit_status == "fits" for card in result.items)


def test_three_conditional_alternatives_count_toward_the_limit_without_inventing_routes():
    records = rows(6)
    unknown = RouteLeg(status="unknown", reason="missing_origin")
    search, _, _, router = search_service(records, route_pairs=[(unknown, ABSENT)] * 3)

    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "partial"
    assert len(result.items) == 3 and router.route.await_count == 3
    assert all(card.fit_status == "unknown" for card in result.items)
    assert all(card.travel_minutes_estimate is None for card in result.items)
    assert all("within_time" not in card.reason_codes for card in result.items)
    assert all("travel_minutes_estimate" in card.missing_fields for card in result.items)
    assert_wire_contract(result)


def test_duplicate_ids_are_not_rechecked_or_counted_as_distinct_alternatives():
    records = rows(6)
    repeated = [records[0], records[0], records[1], records[1], *records[2:]]
    routes = [(known(10), ABSENT)] * 2 + [(known(), ABSENT)] * 3
    search, _, _, router = search_service(repeated, route_pairs=routes)

    result = asyncio.run(search.recommend(search_request()))

    assert {card.poi.id for card in result.items} == {records[i].id for i in (2, 3, 4)}
    assert len(result.items) == 3 and router.route.await_count == 5
    destinations = [call.args[0].destination for call in router.route.await_args_list]
    assert len({(point.latitude, point.longitude) for point in destinations}) == 5


@pytest.mark.parametrize("count", [4, 12])
def test_fully_evaluated_ordinary_pool_with_only_proven_rejections_is_no_match(count):
    search, _, _, router = search_service(rows(count), route_pairs=[(known(10), ABSENT)] * count)

    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "no_match" and not result.items
    assert router.route.await_count == count
    assert_wire_contract(result)


def test_larger_supplement_remains_unknown_after_the_twelve_candidate_cap():
    # A supplement may provide 30 rows, independently of the ordinary DB LIMIT.
    search, _, _, router = search_service(rows(15), route_pairs=[(known(10), ABSENT)] * 12)
    retrieve = search.retriever.retrieve

    async def limited_scope(*args, **kwargs):
        result = await retrieve(*args, **kwargs)
        result.diagnostics.update(feature_catalog=True, scope_limited=True)
        return result

    search.retriever.retrieve = limited_scope
    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "unknown" and not result.items
    assert router.route.await_count == 12
    assert any(warning.code == "data_unknown" for warning in result.warnings)
    assert_wire_contract(result)


def test_candidate_cap_keeps_fully_evaluated_card_and_marks_search_partial():
    search, _, _, router = search_service(
        rows(15), route_pairs=[(known(), ABSENT)] + [(known(10), ABSENT)] * 11
    )

    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "partial"
    assert len(result.items) == 1 and result.items[0].fit_status == "fits"
    assert router.route.await_count == 12
    assert any(warning.code == "data_unknown" for warning in result.warnings)


def test_exhausted_supplement_does_not_claim_city_wide_no_match():
    search, _, _, router = search_service(rows(4), route_pairs=[(known(10), ABSENT)] * 4)
    retrieve = search.retriever.retrieve

    async def limited_scope(*args, **kwargs):
        result = await retrieve(*args, **kwargs)
        result.diagnostics.update(feature_catalog=True, scope_limited=True)
        return result

    search.retriever.retrieve = limited_scope
    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "unknown" and not result.items
    assert router.route.await_count == 4


def test_return_leg_is_evaluated_independently_for_every_next_candidate():
    records = rows(4)
    routes = [(known(), known(10))] * 3 + [(known(), known())]
    search, _, _, router = search_service(records, route_pairs=routes)

    result = asyncio.run(search.recommend(search_request(return_to_start=True)))

    assert result.status == "ok"
    assert [card.poi.id for card in result.items] == [records[3].id]
    assert result.items[0].travel_minutes_estimate == 2
    assert all(call.args[0].return_to_start for call in router.route.await_args_list)
    assert all(
        call.args[0].origin == search_request().origin for call in router.route.await_args_list
    )


@pytest.mark.parametrize("conflict", ["price", "indoor", "category"])
def test_progressive_fallback_keeps_other_hard_constraints_before_routing(conflict):
    records = rows(5)
    changes = {
        "price": {"price_kzt_per_person": 5000},
        "indoor": {"indoor": False},
        "category": {"activity_code": ActivityCode.FOOD},
    }[conflict]
    records[:4] = [row.model_copy(update=changes) for row in records[:4]]
    search, _, _, router = search_service(records)

    result = asyncio.run(
        search.recommend(search_request(budget_kzt_per_person=1000, indoor_only=True))
    )

    assert result.status == "ok"
    assert [card.poi.id for card in result.items] == [records[4].id]
    assert router.route.await_count == 1
    assert {"within_budget", "indoor_match", "within_time"} <= set(result.items[0].reason_codes)


@pytest.mark.parametrize("completed", [0, 1])
def test_global_route_deadline_cancels_work_without_publishing_unchecked_cards(
    completed, monkeypatch
):
    monkeypatch.setattr(recommendation_module, "ROUTE_SEARCH_DEADLINE_SECONDS", 0.03, raising=False)
    monkeypatch.setattr(recommendation_module, "ROUTE_DEADLINE_SECONDS", 1.0)
    records = rows(5)
    search, _, _, router = search_service(records)
    cancelled = []

    async def route(_request):
        if router.route.await_count <= completed:
            return known(), ABSENT
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    router.route.side_effect = route

    async def run():
        return await asyncio.wait_for(search.recommend(search_request()), timeout=0.5)

    result = asyncio.run(run())

    assert result.status == ("partial" if completed else "unknown")
    assert len(result.items) == completed
    assert router.route.await_count == completed + 1 and cancelled == [True]
    assert all(card.fit_status == "fits" for card in result.items)
    assert any(warning.code == "data_unknown" for warning in result.warnings)
    assert_wire_contract(result)


def test_individual_route_timeout_can_remain_conditional_before_global_deadline(monkeypatch):
    monkeypatch.setattr(recommendation_module, "ROUTE_SEARCH_DEADLINE_SECONDS", 1.0, raising=False)
    monkeypatch.setattr(recommendation_module, "ROUTE_DEADLINE_SECONDS", 0.01)
    search, _, _, router = search_service(rows(5))

    async def route(_request):
        if router.route.await_count == 1:
            await asyncio.Event().wait()
        return known(), ABSENT

    router.route.side_effect = route
    result = asyncio.run(search.recommend(search_request()))

    assert result.status == "partial" and len(result.items) == 3
    assert router.route.await_count == 3
    assert sum(card.fit_status == "unknown" for card in result.items) == 1
    unknown_card = next(card for card in result.items if card.fit_status == "unknown")
    assert (
        unknown_card.route_status == "unavailable" and unknown_card.travel_minutes_estimate is None
    )
    assert any(warning.code == "route_unavailable" for warning in result.warnings)


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
def test_http_aliases_return_the_later_candidate_and_valid_wire_contract(path, monkeypatch):
    records = rows(4)
    _, repository, client, router = search_service(
        records, route_pairs=[(known(10), ABSENT)] * 3 + [(known(), ABSENT)]
    )

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _request: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _settings: ClientContext())
    monkeypatch.setattr(api, "load_feature_catalog", lambda: None)

    response = http_request(
        main.create_app(), "POST", path, json=search_request().model_dump(mode="json")
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = RecommendationResponse.model_validate(response.json())
    assert result.status == "ok" and [card.poi.id for card in result.items] == [records[3].id]
    assert router.route.await_count == 4
    assert_wire_contract(result)
