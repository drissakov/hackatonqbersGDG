"""Short walking visits preserve total-time constraints and source facts."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.constraints import evaluate_poi, hard_reject
from backend.app.schemas import RecommendationRequest, RecommendationResponse, RouteLeg
from backend.tests.test_api import request
from backend.tests.test_constraints import intent, poi, route
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record, service


@pytest.mark.parametrize(
    "seconds,visit,travel,rejected",
    [(0, 20, 0, False), (300, 15, 5, False), (600, 10, 10, False), (601, 10, 11, True)],
)
def test_thirty_minute_total_includes_travel_entry_visit_and_buffer(
    seconds, visit, travel, rejected
):
    result = evaluate_poi(poi(activity_code="walk"), intent(available_minutes=30), route(seconds))
    assert result.visit_minutes_estimate == visit
    assert result.travel_minutes_estimate == travel
    assert result.total_minutes == travel + visit + 10
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "fits")
    if not rejected:
        assert result.total_minutes <= 30
        assert "within_time" in result.reason_codes


@pytest.mark.parametrize("minutes,rejected", [(19, True), (20, False), (30, False)])
def test_short_walk_minimum_is_checked_before_routes(minutes, rejected):
    walking = poi(activity_code="walk")
    query = intent(available_minutes=minutes)
    assert hard_reject(walking, query) is rejected
    evaluated = evaluate_poi(walking, query, route(0))
    assert evaluated.rejected is rejected
    assert evaluated.visit_minutes_estimate >= 10


@pytest.mark.parametrize("minutes", [None, 120])
def test_walk_default_stays_thirty_minutes_when_no_reduction_is_needed(minutes):
    result = evaluate_poi(poi(activity_code="walk"), intent(available_minutes=minutes), route(0))
    assert result.visit_minutes_estimate == 30
    assert not result.rejected
    if minutes is None:
        assert result.fit_status == "unknown"
        assert "available_minutes" in result.missing_fields


def test_return_legs_are_combined_before_rounding_and_reducing_visit():
    result = evaluate_poi(
        poi(activity_code="walk"),
        intent(available_minutes=30, return_to_start=True),
        route(61),
        route(61),
    )
    assert result.fit_status == "fits"
    assert result.travel_minutes_estimate == 3
    assert result.visit_minutes_estimate == 17
    assert result.total_minutes == 30


def test_unrequested_return_cannot_reduce_the_visit_or_create_a_conflict():
    result = evaluate_poi(
        poi(activity_code="walk"), intent(available_minutes=30), route(300), route(604800)
    )
    assert result.fit_status == "fits" and not result.rejected
    assert result.travel_minutes_estimate == 5
    assert result.visit_minutes_estimate == 15
    assert result.total_minutes == 30


@pytest.mark.parametrize("known_side", ["outbound", "return"])
@pytest.mark.parametrize("unknown_status", ["unknown", "unavailable"])
@pytest.mark.parametrize("known_seconds,rejected", [(600, False), (601, True)])
def test_partial_return_uses_known_lower_bound_without_inventing_unknown_travel(
    known_side, unknown_status, known_seconds, rejected
):
    unknown = RouteLeg(status=unknown_status, reason="timeout")
    outbound, back = (
        (route(known_seconds), unknown)
        if known_side == "outbound"
        else (unknown, route(known_seconds))
    )
    result = evaluate_poi(
        poi(activity_code="walk"),
        intent(available_minutes=30, return_to_start=True),
        outbound,
        back,
    )
    assert result.visit_minutes_estimate == 10
    assert result.travel_minutes_estimate is None and result.total_minutes is None
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "unknown")
    assert "travel_minutes_estimate" in result.missing_fields
    assert "within_time" not in result.reason_codes


@pytest.mark.parametrize("missing", ["origin", "location_provenance", "location"])
def test_route_metrics_without_matching_geography_cannot_shorten_or_reject_walk(missing):
    walking = poi(activity_code="walk")
    query = intent(available_minutes=30)
    if missing == "origin":
        query.origin = None
    elif missing == "location_provenance":
        walking.provenance[0].fields.remove("location")
    else:
        walking.location = None
    result = evaluate_poi(walking, query, route(3600))
    assert not result.rejected and result.fit_status == "unknown"
    assert result.visit_minutes_estimate == 20
    assert result.travel_minutes_estimate is None and result.total_minutes is None
    assert "within_time" not in result.reason_codes


def test_unknown_outbound_does_not_turn_available_time_into_known_total():
    result = evaluate_poi(
        poi(activity_code="walk"),
        intent(available_minutes=30),
        RouteLeg(status="unknown", reason="timeout"),
    )
    assert result.visit_minutes_estimate == 20
    assert result.fit_status == "unknown" and not result.rejected
    assert result.total_minutes is None and result.travel_minutes_estimate is None
    assert "time_unknown" in result.reason_codes


@pytest.mark.parametrize("minimum,rejected", [(40, False), (41, True)])
def test_walk_reduction_preserves_explicit_minimum_total_time(minimum, rejected):
    result = evaluate_poi(
        poi(activity_code="walk"),
        intent(available_minutes=60, minimum_minutes=minimum),
        route(0),
    )
    assert result.visit_minutes_estimate == 30 and result.total_minutes == 40
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "fits")


def test_opening_window_uses_the_shortened_visit():
    result = evaluate_poi(
        poi(activity_code="walk", opening_hours_text="Mo-Su 12:00-12:25"),
        intent(available_minutes=30),
        route(300),
    )
    assert result.fit_status == "fits"
    assert result.visit_minutes_estimate == 15 and result.total_minutes == 30
    assert "opening_hours" not in result.missing_fields


@pytest.mark.parametrize(
    "activity,visit",
    [
        ("museum", 45),
        ("food", 30),
        ("culture", 45),
        ("sport", 45),
        ("shopping", 30),
        ("entertainment", 45),
        ("other", 30),
    ],
)
def test_nonwalking_visit_policies_are_unchanged(activity, visit):
    current = poi(activity_code=activity)
    query = intent(available_minutes=30)
    assert hard_reject(current, query)
    result = evaluate_poi(current, query, route(0))
    assert result.rejected and result.fit_status == "does_not_fit"
    assert result.visit_minutes_estimate == visit


def short_walk_service():
    walking = record(
        activity_code="walk",
        visit_minutes_estimate=7,
        opening_hours_text="24/7",
        price_kzt_per_person=500,
    )
    router = AsyncMock()
    router.route.return_value = (
        route(300),
        RouteLeg(status="not_requested", reason="not_requested"),
    )
    extracted = text_intent(categories=["walk"])
    search, repository, client = service([walking], extracted=extracted, router=router)
    body = RecommendationRequest(
        query="Synthetic short walk",
        locale="en",
        available_minutes=30,
        date_time="2026-10-19T12:00:00+05:00",
        origin={"latitude": 51.1, "longitude": 71.4},
        budget_kzt_per_person=1000,
    )
    return search, repository, client, router, walking, body


def assert_short_walk_card(result, walking):
    assert result.status == "partial"  # The provider double uses explanation fallback.
    assert len(result.items) == 1
    card = result.items[0]
    assert card.fit_status == "fits" and not card.missing_fields
    assert card.route_status == "known" and card.travel_minutes_estimate == 5
    assert card.visit_minutes_estimate == 15
    assert card.poi == walking and card.poi.visit_minutes_estimate == 7
    assert "15 min" in card.explanation
    assert "within_time" in card.reason_codes


def test_recommendation_service_returns_a_short_walk_without_changing_source_duration():
    search, repository, _, router, walking, body = short_walk_service()
    result = asyncio.run(search.recommend(body))
    assert_short_walk_card(result, walking)
    repository.retrieve_candidates.assert_awaited_once()
    router.route.assert_awaited_once()


def test_http_short_walk_preserves_contract_source_fact_and_total_time(monkeypatch):
    _, repository, client, router, walking, body = short_walk_service()

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    response = request(
        main.create_app(),
        "POST",
        "/api/recommendations",
        json=body.model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = RecommendationResponse.model_validate(response.json())
    assert result.request_id == body.request_id
    assert_short_walk_card(result, walking)
    assert router.route.await_args.args[0].return_to_start is False
