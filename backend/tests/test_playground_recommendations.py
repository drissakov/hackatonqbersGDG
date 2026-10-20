"""Short visits use explicit playground evidence without changing source facts."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app import api, main
from backend.app.poi_features import load_feature_catalog
from backend.app.schemas import ActivityCode, FeatureEvidence, RecommendationResponse, RouteLeg
from backend.tests.test_api import request
from backend.tests.test_constraints import route
from backend.tests.test_intent import text_intent
from backend.tests.test_poi_features import (
    FAMILY_QUERIES,
    catalog,
    curated,
    evidence,
    feature_request,
    feature_service,
    recommend,
)
from backend.tests.test_recommend import record, service

ROOT = Path(__file__).resolve().parents[2]
RESPONSE_SCHEMA = json.loads(
    (ROOT / "contracts/recommendation-response.schema.json").read_text("utf-8")
)


def validate_response(result):
    body = result.model_dump(mode="json")
    Draft202012Validator(RESPONSE_SCHEMA, format_checker=FormatChecker()).validate(body)
    return RecommendationResponse.model_validate(body)


def entertainment_playground(**updates):
    """Synthetic fixture follows the real playground category, not walk defaults."""
    source = record(
        id="test:short-playground",
        name="SYNTHETIC TEST ONLY - Short Visit Playground",
        activity_code="entertainment",
        opening_hours_text="24/7",
        price_kzt_per_person=0,
        indoor=False,
        **updates,
    )
    return curated(poi=source.model_dump(mode="json"))


@pytest.mark.parametrize("locale,query", FAMILY_QUERIES)
def test_checked_in_playgrounds_support_thirty_minute_visits_in_each_language(locale, query):
    checked_catalog = load_feature_catalog()
    assert checked_catalog is not None
    assert len(checked_catalog.records) == 22
    search, repository, _, router = feature_service(checked_catalog, categories=("entertainment",))
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "partial"
    assert 1 <= len(result.items) <= 3
    checked_places = {row.poi.id: row for row in checked_catalog.records}
    for card in result.items:
        source_record = checked_places[card.poi.id]
        assert card.poi.activity_code == ActivityCode.ENTERTAINMENT
        assert not card.poi.is_test and all(not source.is_test for source in card.poi.sources)
        assert card.poi == source_record.poi
        assert card.feature_evidence == source_record.evidence
        assert card.visit_minutes_estimate == 18
        assert card.travel_minutes_estimate == 2 and card.route_status == "known"
        assert card.visit_minutes_estimate + card.travel_minutes_estimate + 10 == 30
        assert "family_playground_match" in card.reason_codes
        assert "child_suitability" not in card.missing_fields
        assert all(fact.observed_at is None for fact in card.feature_evidence)
    repository.retrieve_candidates.assert_not_called()
    assert router.route.await_count == len(result.items)
    validate_response(result)


def test_known_return_route_reduces_the_actual_playground_visit_budget():
    row = entertainment_playground()
    search, _, _, router = feature_service(catalog(row), categories=("entertainment",))
    router.route.return_value = (route(120), route(180))
    result = recommend(
        search, "A playground for children.", available_minutes=30, return_to_start=True
    )
    assert result.status == "ok" and len(result.items) == 1
    card = result.items[0]
    assert card.fit_status == "fits" and not card.missing_fields
    assert card.visit_minutes_estimate == 15 and card.travel_minutes_estimate == 5
    assert card.visit_minutes_estimate + card.travel_minutes_estimate + 10 == 30
    assert router.route.await_args.args[0].return_to_start is True
    validate_response(result)


@pytest.mark.parametrize("unknown_status", ["unknown", "unavailable"])
def test_unknown_requested_return_preserves_uncertainty_and_known_outbound_budget(unknown_status):
    search, _, _, router = feature_service(
        catalog(entertainment_playground()), categories=("entertainment",)
    )
    router.route.return_value = (
        route(120),
        RouteLeg(status=unknown_status, reason="timeout"),
    )
    result = recommend(
        search, "A playground for children.", available_minutes=30, return_to_start=True
    )
    assert result.status == "partial" and len(result.items) == 1
    card = result.items[0]
    assert card.fit_status == "unknown" and card.visit_minutes_estimate == 18
    assert card.travel_minutes_estimate is None and card.route_status == unknown_status
    assert "travel_minutes_estimate" in card.missing_fields
    assert "within_time" not in card.reason_codes
    assert "time_unknown" in card.reason_codes
    validate_response(result)


def test_shortened_playground_recommendation_does_not_rewrite_a_sourced_duration():
    row = entertainment_playground(visit_minutes_estimate=7)
    source_before = row.poi.model_dump(mode="json")
    search, _, _, _ = feature_service(catalog(row), categories=("entertainment",))
    result = recommend(search, "A playground for children.", available_minutes=30)
    assert len(result.items) == 1
    card = result.items[0]
    assert card.visit_minutes_estimate == 18
    assert card.poi.visit_minutes_estimate == 7
    assert card.poi.model_dump(mode="json") == source_before
    assert row.poi.model_dump(mode="json") == source_before
    validate_response(result)


@pytest.mark.parametrize(
    "query,missing_field",
    [
        ("A playground for my six-year-old child.", "age_restrictions"),
        ("A quiet playground for children.", None),
    ],
)
def test_short_visit_never_relaxes_unsupported_age_or_quiet_requirements(query, missing_field):
    search, _, _, router = feature_service(
        catalog(entertainment_playground()), categories=("entertainment",)
    )
    result = recommend(search, query, available_minutes=30)
    assert result.status == "unknown" and not result.items
    assert any(warning.code == "missing_input" for warning in result.warnings)
    if missing_field is not None:
        assert any(missing_field in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


def test_short_visit_does_not_allow_a_source_confirmed_private_playground():
    row = entertainment_playground()
    row.evidence = [
        row.evidence[0],
        FeatureEvidence.model_validate(
            evidence("public_access", value=False, source_value="private")
        ),
    ]
    search, _, _, router = feature_service(catalog(row), categories=("entertainment",))
    result = recommend(search, "A playground for children.", available_minutes=30)
    assert result.status == "unknown" and not result.items
    router.route.assert_not_called()


def test_entertainment_category_alone_cannot_enable_a_short_playground_policy():
    non_playground = record(
        activity_code="entertainment",
        name="SYNTHETIC TEST ONLY - Entertainment Venue",
        opening_hours_text="24/7",
    )
    router = AsyncMock()
    search, _, _ = service(
        [non_playground], extracted=text_intent(categories=["entertainment"]), router=router
    )
    result = asyncio.run(
        search.recommend(feature_request("Synthetic entertainment.", available_minutes=30))
    )
    assert result.status == "no_match" and not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
@pytest.mark.parametrize("locale,query", FAMILY_QUERIES)
def test_http_short_playground_uses_checked_in_sources_and_keeps_the_response_uncached(
    path, locale, query, monkeypatch
):
    checked_catalog = load_feature_catalog()
    assert checked_catalog is not None
    _, repository, client, router = feature_service(checked_catalog, categories=("entertainment",))

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    monkeypatch.setattr(api, "load_feature_catalog", lambda: checked_catalog)
    payload = feature_request(query, locale, available_minutes=30).model_dump(mode="json")
    response = request(main.create_app(), "POST", path, json=payload)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = validate_response(RecommendationResponse.model_validate(response.json()))
    assert str(result.request_id) == payload["request_id"]
    assert result.status == "partial" and 1 <= len(result.items) <= 3
    assert all(card.visit_minutes_estimate == 18 for card in result.items)
    assert all(card.feature_evidence and not card.poi.is_test for card in result.items)
    assert all(source.provider == "osm" and not source.is_test for source in result.sources)
