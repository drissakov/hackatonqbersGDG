"""Playground discovery across HTTP aliases keeps source facts and user constraints."""

from types import SimpleNamespace

import pytest

from backend.app import api, main
from backend.app import recommend as recommendations
from backend.app.poi_features import load_feature_catalog
from backend.app.schemas import ActivityCode, RecommendationResponse
from backend.tests.test_api import request
from backend.tests.test_constraints import route
from backend.tests.test_playground_recommendations import validate_response
from backend.tests.test_poi_features import feature_request, feature_service

PATHS = ["/api/recommendations", "/api/v1/recommendations"]
QUERIES = [
    ("kk", "Балалар ойын алаңын тап."),
    ("ru", "Найди детскую площадку."),
    ("en", "Find a playground."),
    ("kk", "Баламен серуендегім келеді."),
    ("ru", "Предложи прогулку с ребёнком."),
    ("en", "Suggest a walk with my child."),
]


def install_http_providers(monkeypatch, *, categories=("walk",), names=()):
    """Real licensed source records, synthetic intent/explanation/route providers."""
    checked = load_feature_catalog()
    assert checked is not None and len(checked.records) == 22
    _, repository, client, router = feature_service(
        checked, categories=categories, names=names, interests=()
    )

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    monkeypatch.setattr(api, "load_feature_catalog", lambda: checked)
    return checked, repository, client, router


def post_recommendation(path, payload):
    response = request(main.create_app(), "POST", path, json=payload)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = validate_response(RecommendationResponse.model_validate(response.json()))
    assert str(result.request_id) == payload["request_id"]
    return result


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("locale,query", QUERIES)
def test_http_playground_and_family_walk_find_the_real_supplement_without_child_interest(
    path, locale, query, monkeypatch
):
    checked, repository, client, router = install_http_providers(monkeypatch)
    source_before = checked.model_dump(mode="json")
    payload = feature_request(query, locale, available_minutes=30).model_dump(mode="json")

    result = post_recommendation(path, payload)

    assert result.status == "partial" and 1 <= len(result.items) <= 3
    records = {row.poi.id: row for row in checked.records}
    for card in result.items:
        source_record = records[card.poi.id]
        assert card.poi == source_record.poi
        assert card.feature_evidence == source_record.evidence
        assert card.name_is_derived == source_record.name_is_derived
        assert card.poi.activity_code == ActivityCode.ENTERTAINMENT
        assert card.generated_locale == locale
        assert not card.poi.is_test
        assert card.travel_minutes_estimate == 2
        assert card.visit_minutes_estimate == 18
        assert card.route_status == "known"
        assert "within_time" in card.reason_codes
        assert "family_playground_match" in card.reason_codes
        assert "child_suitability" not in card.missing_fields
        assert all(fact.observed_at is None for fact in card.feature_evidence)
    assert all(source.provider == "osm" and not source.is_test for source in result.sources)
    assert checked.model_dump(mode="json") == source_before
    repository.retrieve_candidates.assert_not_called()
    client.embed.assert_not_called()
    assert router.route.await_count == len(result.items)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("locale,query", QUERIES[3:])
def test_http_family_walk_preserves_every_explicit_form_constraint_and_unknown_source_fact(
    path, locale, query, monkeypatch
):
    _, repository, _, router = install_http_providers(monkeypatch)
    router.route.return_value = (route(120), route(180))
    resolved = []
    evaluate = recommendations.evaluate_poi

    def capture_evaluation(poi, intent, *args, **kwargs):
        resolved.append(intent.model_dump(mode="json"))
        return evaluate(poi, intent, *args, **kwargs)

    monkeypatch.setattr(recommendations, "evaluate_poi", capture_evaluation)
    payload = feature_request(
        query,
        locale,
        origin={"latitude": 51.12, "longitude": 71.43},
        available_minutes=30,
        budget_kzt_per_person=900,
        indoor_only=True,
        return_to_start=True,
        date_time="2030-01-16T10:00:00+05:00",
        explicit_fields=[
            "origin",
            "available_minutes",
            "budget_kzt_per_person",
            "indoor_only",
            "return_to_start",
            "date_time",
        ],
    ).model_dump(mode="json")

    result = post_recommendation(path, payload)

    assert result.status == "partial" and result.items and resolved
    for intent in resolved:
        assert intent["origin"] == payload["origin"]
        assert intent["available_minutes"] == payload["available_minutes"]
        assert intent["budget_kzt_per_person"] == payload["budget_kzt_per_person"]
        assert intent["indoor"] == "indoor"
        assert intent["return_to_start"] is True
        assert intent["date_time"] == payload["date_time"]
        assert set(intent["constraint_sources"]) == set(payload["explicit_fields"])
        assert all(value == "form" for value in intent["constraint_sources"].values())
    for call in router.route.await_args_list:
        routed = call.args[0]
        assert routed.origin.model_dump(mode="json") == payload["origin"]
        assert routed.return_to_start is True and routed.locale == locale
        assert str(routed.request_id) == payload["request_id"]
    for card in result.items:
        assert card.visit_minutes_estimate == 15 and card.travel_minutes_estimate == 5
        assert card.fit_status == "unknown"
        assert {"indoor", "price_kzt_per_person"} <= set(card.missing_fields)
        assert "indoor_match" not in card.reason_codes
        assert "within_budget" not in card.reason_codes
    repository.retrieve_candidates.assert_not_called()


NEGATIVE_CASES = [
    ("kk", "museum", "Баламен серуендеу үшін музей керек."),
    ("ru", "museum", "Для прогулки с ребёнком нужен музей."),
    ("en", "museum", "For a walk with my child, find a museum."),
    ("kk", "cafe", "Баламен серуендеу үшін кафе керек."),
    ("ru", "cafe", "Для прогулки с ребёнком нужно кафе."),
    ("en", "cafe", "For a walk with my child, find a cafe."),
    ("kk", "named", "Баламен серуендеу үшін SYNTHETIC TEST ONLY аталған орын керек."),
    ("ru", "named", "Для прогулки с ребёнком нужно место SYNTHETIC TEST ONLY."),
    ("en", "named", "For a walk with my child, find SYNTHETIC TEST ONLY."),
    ("kk", "age", "Алты жасар баламен серуендегім келеді."),
    ("ru", "age", "Предложи прогулку с ребёнком шести лет."),
    ("en", "age", "Suggest a walk with my six-year-old child."),
    ("kk", "geo", "Баламен серуендегім келеді."),
    ("ru", "geo", "Предложи прогулку с ребёнком."),
    ("en", "geo", "Suggest a walk with my child."),
]


@pytest.mark.parametrize("locale,case,query", NEGATIVE_CASES)
def test_http_family_walk_does_not_replace_an_explicit_venue_age_or_origin(
    locale, case, query, monkeypatch
):
    names = ("SYNTHETIC TEST ONLY",) if case == "named" else ()
    # A permissive walk category must not erase an explicit venue type in the raw text.
    _, _, _, router = install_http_providers(monkeypatch, names=names)
    updates = {"origin": {"latitude": 52.0, "longitude": 72.0}} if case == "geo" else {}
    payload = feature_request(query, locale, available_minutes=30, **updates).model_dump(
        mode="json"
    )

    result = post_recommendation("/api/v1/recommendations", payload)

    assert result.status in {"unknown", "no_match"} and not result.items
    if case == "age":
        assert any("age_restrictions" in warning.fields for warning in result.warnings)
    router.route.assert_not_called()
