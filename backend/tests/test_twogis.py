"""Synthetic provider responses only; no real 2GIS payloads or credentials."""

import asyncio
import io
import json
from datetime import UTC, datetime
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from backend.app.main import create_app, get_twogis
from backend.app.schemas import Coordinates, RouteLeg, RouteProvenance, RouteResponse
from backend.app.services.twogis import MAX_RESPONSE_BYTES, TwoGISAdapter, _NoRedirect
from backend.app.settings import Settings
from scripts.export_contracts import artifacts

ORIGIN = {"latitude": 51.1, "longitude": 71.4}
DESTINATION = {"latitude": 51.2, "longitude": 71.5}
SECRET = "synthetic-server-key-not-real"
REGION_SECRET = "synthetic-region-key-not-real"


def settings(**changes):
    values = {
        "twogis_enabled": True,
        "twogis_api_key": SECRET,
        "twogis_region_api_key": REGION_SECRET,
        "twogis_places_allowed": True,
        "twogis_routing_allowed": True,
        "twogis_discovery_allowed": True,
        "twogis_rights_basis": "Synthetic test permission; not real authorization",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def success(distance=1234, duration=601):
    return {
        "status": "OK",
        "type": "result",
        "result": [{"length": distance, "duration": duration}],
    }


class SyntheticResponse(io.BytesIO):
    status = 200


class Opener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.responses = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        assert timeout == 5
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        response = SyntheticResponse(
            outcome if isinstance(outcome, bytes) else json.dumps(outcome).encode()
        )
        self.responses.append(response)
        return response


def leg(adapter, locale="ru"):
    return asyncio.run(
        adapter.walking_leg(Coordinates(**ORIGIN), Coordinates(**DESTINATION), locale)
    )


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"twogis_enabled": False}, "disabled"),
        ({"twogis_routing_allowed": False}, "rights_unconfirmed"),
        ({"twogis_rights_basis": "  "}, "rights_unconfirmed"),
        ({"twogis_api_key": ""}, "key_missing"),
    ],
)
def test_routing_requires_all_gates_and_never_calls_network(changes, reason):
    opener = Opener()
    result = leg(TwoGISAdapter(settings(**changes), opener=opener))
    assert result.status == "unavailable"
    assert result.reason == reason
    assert result.duration_seconds is None
    assert not opener.requests


@pytest.mark.parametrize(("locale", "expected"), [("ru", "ru"), ("en", "en"), ("kk", "ru")])
def test_walking_coordinates_units_locale_and_resource_cleanup(locale, expected):
    opener = Opener(success(1234.2, 601.2))
    result = leg(TwoGISAdapter(settings(), opener=opener), locale)
    request = opener.requests[0][0]
    body = json.loads(request.data)
    assert request.get_method() == "POST"
    assert request.full_url.startswith("https://routing.api.2gis.com/routing/7.0.0/global?")
    assert body == {
        "points": [
            {"lon": 71.4, "lat": 51.1, "type": "walking"},
            {"lon": 71.5, "lat": 51.2, "type": "walking"},
        ],
        "transport": "walking",
        "output": "summary",
        "locale": expected,
        "alternative": 0,
        "save_route": False,
    }
    assert not {"origin", "referer"} & {key.lower() for key in request.headers}
    assert result.distance_meters == 1235
    assert result.duration_seconds == 602
    assert result.provenance.provider_locale == expected
    assert not result.provenance.storage_allowed
    assert not result.provenance.indexing_allowed
    assert not result.provenance.ai_allowed
    assert SECRET not in result.model_dump_json()
    assert "?" not in result.provenance.endpoint
    assert all(response.closed for response in opener.responses)


def test_walking_reads_summary_length_and_duration_without_detailed_geometry():
    payload = {
        "status": "OK",
        "type": "result",
        "result": [{"length": 1234.2, "duration": 601.2}],
    }
    result = leg(TwoGISAdapter(settings(), opener=Opener(payload)))
    assert result.status == "known"
    assert result.distance_meters == 1235
    assert result.duration_seconds == 602


def test_walking_retains_compatibility_with_detailed_metric_names():
    payload = {
        "status": "OK",
        "type": "result",
        "result": [{"total_distance": 1234.2, "total_duration": 601.2}],
    }
    result = leg(TwoGISAdapter(settings(), opener=Opener(payload)))
    assert result.status == "known"
    assert result.distance_meters == 1235
    assert result.duration_seconds == 602


@pytest.mark.parametrize(
    ("status", "expected_status", "reason"),
    [
        ("FAIL", "unavailable", "provider_fail"),
        ("POINT_EXCLUDED", "unavailable", "provider_fail"),
        ("ATTRACT_FAIL", "unavailable", "provider_fail"),
        ("ROUTE_NOT_FOUND", "unknown", "route_not_found"),
        ("ROUTE_DOES_NOT_EXISTS", "unknown", "route_not_found"),
        ({"invalid": True}, "unavailable", "invalid_response"),
    ],
)
def test_http_200_does_not_override_provider_failure(status, expected_status, reason):
    payload = {**success(), "status": status, "message": "synthetic-private-body"}
    result = leg(TwoGISAdapter(settings(), opener=Opener(payload)))
    assert result.status == expected_status
    assert result.reason == reason
    assert result.distance_meters is result.duration_seconds is result.provenance is None
    assert "synthetic-private" not in result.model_dump_json()


@pytest.mark.parametrize(
    "payload",
    [
        {**success(), "result": []},
        {**success(), "result": None},
        {**success(), "result": [None]},
        {**success(), "type": "error"},
        {**success(), "result": [{"length": 100, "total_duration": 60}]},
        {**success(), "result": [{"total_distance": 100, "duration": 60}]},
        {
            **success(),
            "result": [
                {"length": None, "duration": 60, "total_distance": 100, "total_duration": 60}
            ],
        },
        success(True, 60),
        success(100, "60"),
        success(-1, 60),
        success(100, None),
        success(100, float("nan")),
        success(100, float("inf")),
        success(100, 604801),
        success(10**1000, 60),
        b"not JSON synthetic-private-body",
        b"[1,2]",
        pytest.param(b"x" * (MAX_RESPONSE_BYTES + 1), id="oversized-body"),
    ],
)
def test_empty_malformed_or_invalid_metrics_never_become_routes(payload):
    result = leg(TwoGISAdapter(settings(), opener=Opener(payload)))
    assert result.status == "unavailable"
    assert result.reason == "invalid_response"
    assert result.duration_seconds is None


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TimeoutError("synthetic-private-body"), "timeout"),
        (URLError(TimeoutError("synthetic-private-body")), "timeout"),
        (URLError("synthetic-private-body"), "network_error"),
        (OSError("synthetic-private-body"), "network_error"),
        (IncompleteRead(b"synthetic-private-body"), "network_error"),
    ],
)
def test_transport_failures_are_sanitized(error, reason, caplog):
    result = leg(TwoGISAdapter(settings(), opener=Opener(error)))
    assert result.reason == reason
    assert result.duration_seconds is None
    assert "synthetic-private" not in result.model_dump_json() + caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (401, "access_denied"),
        (403, "access_denied"),
        (429, "rate_limited"),
        (500, "http_error"),
        (302, "http_error"),
        (404, "http_error"),
    ],
)
def test_http_errors_are_closed_sanitized_and_not_retried(code, reason):
    body = io.BytesIO(b"synthetic-private-provider-body")
    error = HTTPError("https://example.invalid/?key=" + SECRET, code, "private", {}, body)
    opener = Opener(error)
    result = leg(TwoGISAdapter(settings(), opener=opener))
    assert result.reason == reason
    assert body.closed
    assert len(opener.requests) == 1
    assert SECRET not in result.model_dump_json()


def test_redirects_are_not_followed():
    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid") is None


def test_request_deadline_and_cancellation(monkeypatch):
    from backend.app.services import twogis

    monkeypatch.setattr(twogis, "REQUEST_TIMEOUT", 0.01)
    adapter = TwoGISAdapter(settings(), opener=Opener())

    async def delayed(*args):
        await asyncio.sleep(0.1)
        raise AssertionError("Deadline must cancel the awaited work")

    monkeypatch.setattr(twogis.asyncio, "to_thread", delayed)
    assert leg(adapter).reason == "timeout"

    async def cancelled(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(twogis.asyncio, "to_thread", cancelled)
    with pytest.raises(asyncio.CancelledError):
        leg(adapter)


def catalog_items(items, code=200):
    return {"meta": {"code": code}, "result": {"items": items}}


def region():
    return catalog_items([{"id": "99000001", "name": "Astana", "type": "region"}])


def test_places_discovery_fields_coordinates_and_ephemeral_provenance():
    opener = Opener(
        region(),
        catalog_items(
            [
                {
                    "id": "99000003",
                    "region_id": "99000001",
                    "name": "Synthetic place, not a real city record",
                    "point": {"lon": 71.5, "lat": 51.2},
                    "rubrics": [{"id": "99000002"}],
                    "contact_groups": ["must not be retained"],
                }
            ]
        ),
    )
    result = asyncio.run(TwoGISAdapter(settings(), opener=opener).search_places("synthetic", "en"))
    from urllib.parse import parse_qs, urlparse

    queries = [parse_qs(urlparse(req.full_url).query) for req, _ in opener.requests]
    assert queries[0]["key"] == [REGION_SECRET]
    assert queries[0]["q"] == ["Astana"]
    assert queries[1]["key"] == [SECRET]
    assert queries[1]["region_id"] == ["99000001"]
    assert queries[1]["fields"] == ["items.point,items.region_id,items.rubrics"]
    assert queries[1]["locale"] == ["en_RU"]
    assert queries[1]["page_size"] == ["3"]
    assert result.status == "ok"
    place = result.places[0]
    assert place.location == Coordinates(**DESTINATION)
    assert place.location_precision == "approximate"
    assert place.rubric_ids == ("99000002",)
    assert not hasattr(place, "contact_groups")
    assert not any(
        (
            place.provenance.storage_allowed,
            place.provenance.indexing_allowed,
            place.provenance.ranking_allowed,
            place.provenance.ai_allowed,
        )
    )
    assert not any(secret in repr(result) + repr(place) for secret in (SECRET, "Synthetic place"))
    assert "?" not in place.provenance.endpoint


def test_rubric_discovery_uses_the_resolved_astana_region():
    opener = Opener(region(), catalog_items([{"id": "99000002"}]))
    result = asyncio.run(TwoGISAdapter(settings(), opener=opener).discover_astana("museum"))
    assert result.region_id == "99000001"
    assert result.rubric_ids == ("99000002",)
    assert "region_id=99000001" in opener.requests[1][0].full_url


@pytest.mark.parametrize(
    "payload",
    [
        catalog_items([{"id": "32", "name": "Moscow", "type": "region"}]),
        catalog_items([]),
        catalog_items([{"id": "99000001", "name": "Astana", "type": "adm_div"}]),
        catalog_items([], code=403),
        catalog_items([], code=[]),
        {"meta": {"code": 200}, "result": None},
    ],
)
def test_unverified_region_or_catalog_failure_blocks_places(payload):
    opener = Opener(payload)
    result = asyncio.run(TwoGISAdapter(settings(), opener=opener).search_places("synthetic"))
    assert result.status == "unavailable"
    assert result.region_id is None
    assert len(opener.requests) == 1


@pytest.mark.parametrize("field", ["twogis_places_allowed", "twogis_discovery_allowed"])
def test_places_cannot_bypass_separate_capabilities(field):
    opener = Opener()
    result = asyncio.run(
        TwoGISAdapter(settings(**{field: False}), opener=opener).search_places("synthetic")
    )
    assert result.status == "unavailable"
    assert result.reason == "rights_unconfirmed"
    assert not opener.requests


@pytest.mark.parametrize("locale", ["ru", "en", "kk"])
def test_only_a_successful_empty_catalog_search_is_no_match(locale):
    opener = Opener(region(), catalog_items([]))
    result = asyncio.run(
        TwoGISAdapter(settings(), opener=opener).search_places("synthetic", locale)
    )
    assert result.status == "no_match"
    assert result.places == ()
    assert "locale=" + {"ru": "ru_KZ", "en": "en_RU", "kk": "kk_KZ"}[locale] in (
        opener.requests[1][0].full_url
    )


def api(adapter, **changes):
    app = create_app()
    app.dependency_overrides[get_twogis] = lambda: adapter
    payload = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "locale": "ru",
        "request_id": "00000000-0000-4000-8000-000000000001",
        **changes,
    }

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post("/api/route", json=payload)

    response = asyncio.run(run())
    RouteResponse.model_validate(response.json())
    Draft202012Validator(
        artifacts()["route-response.schema.json"], format_checker=FormatChecker()
    ).validate(response.json())
    assert response.json()["request_id"] == payload["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert SECRET not in response.text
    return response


def test_return_is_a_separate_reversed_request_and_total_is_not_doubled():
    opener = Opener(success(500, 61), success(600, 120))
    response = api(TwoGISAdapter(settings(), opener=opener), return_to_start=True)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "known"
    assert data["travel_minutes_estimate"] == 4
    assert data["outbound"]["duration_seconds"] == 61
    assert data["return_route"]["duration_seconds"] == 120
    forward, backward = [json.loads(req.data)["points"] for req, _ in opener.requests]
    assert backward == list(reversed(forward))
    assert data["destination_precision"] == "approximate"
    assert data["warnings"][0]["code"] == "data_unknown"


def test_one_way_never_requests_return_and_zero_route_is_valid():
    opener = Opener(success(0, 0))
    response = api(TwoGISAdapter(settings(), opener=opener))
    assert response.status_code == 200
    assert response.json()["travel_minutes_estimate"] == 0
    assert response.json()["return_route"]["status"] == "not_requested"
    assert len(opener.requests) == 1


@pytest.mark.parametrize(
    ("failure", "code", "status"),
    [
        (TimeoutError(), 503, "unavailable"),
        ({"status": "ROUTE_NOT_FOUND", "type": "error"}, 200, "unknown"),
    ],
)
def test_return_failure_keeps_outbound_but_never_invents_a_total(failure, code, status):
    opener = Opener(success(), failure)
    response = api(TwoGISAdapter(settings(), opener=opener), return_to_start=True)
    assert response.status_code == code
    assert response.json()["status"] == status
    assert response.json()["outbound"]["status"] == "known"
    assert response.json()["return_route"]["duration_seconds"] is None
    assert response.json()["travel_minutes_estimate"] is None


def test_missing_origin_never_becomes_a_city_center_or_a_straight_line():
    opener = Opener()
    response = api(TwoGISAdapter(settings(), opener=opener), origin=None, return_to_start=True)
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
    assert response.json()["outbound"]["reason"] == "missing_origin"
    assert response.json()["return_route"]["reason"] == "missing_origin"
    assert response.json()["travel_minutes_estimate"] is None
    assert not opener.requests


def test_invalid_provider_settings_return_unavailable():
    response = api(None, return_to_start=True)
    assert response.status_code == 503
    assert response.json()["outbound"]["reason"] == "invalid_settings"


def test_contract_rejects_partial_totals_and_metrics_without_a_route():
    known = RouteLeg(
        status="known",
        distance_meters=1,
        duration_seconds=61,
        provenance=RouteProvenance(retrieved_at=datetime.now(UTC), provider_locale="ru"),
    )
    with pytest.raises(ValidationError):
        RouteResponse(
            request_id="00000000-0000-4000-8000-000000000001",
            status="known",
            travel_minutes_estimate=2,
            outbound=known,
            return_route=RouteLeg(status="unavailable", reason="timeout"),
            warnings=[],
        )
    with pytest.raises(ValidationError):
        RouteLeg(status="unknown", reason="route_not_found", duration_seconds=61)


def test_disabled_smoke_reports_not_run_without_network_or_payloads(monkeypatch):
    from backend.app.services import twogis
    from scripts.twogis_smoke import run_checks

    opener = Opener()
    monkeypatch.setattr(twogis, "build_opener", lambda *args: opener)
    results = asyncio.run(run_checks(settings(twogis_enabled=False)))
    assert len(results) == 4
    assert all(result["status"] == "not_run" for result in results.values())
    report = json.dumps(results)
    assert all(
        value not in report for value in (SECRET, REGION_SECRET, "latitude", "longitude", "https")
    )
    assert not opener.requests


def test_body_read_timeout_closes_the_response(monkeypatch):
    from backend.app.services import twogis

    opener = Opener(success())
    times = iter([0, 0, 9])
    monkeypatch.setattr(twogis.time, "monotonic", lambda: next(times))
    with pytest.raises(twogis._ProviderFailure, match="timeout"):
        TwoGISAdapter(settings(), opener=opener)._read_json(twogis.ROUTING, {}, {}, False)
    assert all(response.closed for response in opener.responses)


def test_smoke_configuration_error_does_not_print_raw_input(monkeypatch, capsys):
    from scripts import twogis_smoke

    def invalid_settings():
        return settings(twogis_enabled="synthetic-private-setting")

    monkeypatch.setattr(twogis_smoke, "Settings", invalid_settings)
    assert twogis_smoke.main() == 1
    output = capsys.readouterr().out
    assert "invalid_settings" in output
    assert "synthetic-private" not in output
