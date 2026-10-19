"""Transient event HTTP wiring, lifecycle, aliases and safe degradation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.database import DatabaseUnavailable
from backend.app.event_schemas import (
    TransientEventSearchResponse,
    TransientEventSource,
    transient_source_id,
)
from backend.app.openai_client import ProviderError
from backend.app.schemas import Warning
from backend.app.settings import Settings
from backend.tests.test_api import request
from backend.tests.test_event_recommend import service as event_service

REQUEST_ID = "00000000-0000-4000-8000-000000000001"


def empty_discovery(request_id, *, status="unknown"):
    url = "https://ticketon.kz/synthetic-s04-api"
    return TransientEventSearchResponse(
        request_id=request_id,
        status=status,
        provider_status=status,
        provider_code="no_grounded_events" if status == "unknown" else "provider_failed",
        live_web_search="passed" if status == "unknown" else "failed",
        items=[],
        listings=[],
        sources=[
            TransientEventSource(
                source_id=transient_source_id(url),
                url=url,
                retrieved_at=datetime(2030, 1, 15, tzinfo=UTC),
            )
        ]
        if status == "unknown"
        else [],
        warnings=[Warning(code="data_unknown", message="Synthetic unavailable facts")],
    )


@pytest.mark.parametrize("path", ["/api/events/search", "/api/v2/events/search"])
@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
def test_missing_key_is_typed_503_without_external_calls(path, locale, monkeypatch):
    monkeypatch.setattr(
        api, "get_settings", lambda: Settings(_env_file=None, openai_api_key="", database_url="")
    )
    monkeypatch.setattr(main, "get_repository", lambda _: None)
    service = AsyncMock()
    monkeypatch.setattr(api, "EventRecommendationService", service)
    result = request(
        main.create_app(),
        "POST",
        path,
        json={"query": "Synthetic", "locale": locale, "request_id": REQUEST_ID},
    )
    parsed = TransientEventSearchResponse.model_validate(result.json())
    assert result.status_code == 503 and parsed.status == "unavailable"
    assert parsed.contract_version == "1.3.0" and str(parsed.request_id) == REQUEST_ID
    assert result.headers["cache-control"] == "no-store"
    service.assert_not_called()


@pytest.mark.parametrize("path", ["/api/events/search", "/api/v2/events/search"])
@pytest.mark.parametrize("failure", [False, True])
def test_shared_client_closes_and_optional_corpus_outage_does_not_prevent_discovery(
    path, failure, monkeypatch
):
    borrowed = object()
    state = {"closed": False}

    class Context:
        async def __aenter__(self):
            return borrowed

        async def __aexit__(self, *_):
            state["closed"] = True

    class Service:
        def __init__(self, repository, client, router):
            assert repository is None and client is borrowed and router is None

        async def search(self, body):
            if failure:
                raise ProviderError("synthetic-private-provider-body")
            return empty_discovery(body.request_id)

    def database_outage(_):
        raise DatabaseUnavailable("synthetic-private-database-body")

    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(api, "OpenAIClient", lambda _: Context())
    monkeypatch.setattr(api, "EventRecommendationService", Service)
    monkeypatch.setattr(main, "get_repository", database_outage)
    monkeypatch.setattr(main, "get_twogis", lambda: None)
    response = request(
        main.create_app(), "POST", path, json={"query": "Synthetic", "request_id": REQUEST_ID}
    )
    assert response.status_code == (503 if failure else 200)
    parsed = TransientEventSearchResponse.model_validate(response.json())
    assert parsed.status == ("unavailable" if failure else "unknown")
    assert str(parsed.request_id) == REQUEST_ID and state["closed"]
    assert "synthetic-private" not in response.text


def test_legacy_v1_response_shape_is_unchanged_and_does_not_initialize_search(monkeypatch):
    monkeypatch.setattr(api, "get_settings", lambda: (_ for _ in ()).throw(AssertionError()))
    response = request(
        main.create_app(), "POST", "/api/v1/events/search", json={"query": "Synthetic"}
    )
    assert response.status_code == 503
    assert set(response.json()) == {"request_id", "status", "items", "sources", "warnings"}
    assert response.headers["cache-control"] == "no-store"


def test_event_validation_is_sanitized_and_openapi_advertises_new_contract():
    app = main.create_app()
    response = request(
        app,
        "POST",
        "/api/v2/events/search",
        json={"query": "synthetic-private-query", "date_time": "2030-01-15"},
    )
    assert response.status_code == 422 and "synthetic-private" not in response.text
    schema = app.openapi()
    for path in ("/api/events/search", "/api/v2/events/search"):
        success = schema["paths"][path]["post"]["responses"]["200"]
        assert success["content"]["application/json"]["schema"]["$ref"].endswith(
            "TransientEventSearchResponse"
        )
        unavailable = schema["paths"][path]["post"]["responses"]["503"]
        assert unavailable["content"]["application/json"]["schema"]["$ref"].endswith(
            "TransientEventSearchResponse"
        )
    assert schema["info"]["version"] == "1.3.0"


@pytest.mark.parametrize("path", ["/api/events/search", "/api/v2/events/search"])
def test_http_pipeline_executes_d03_and_returns_conditional_runtime_card(path, monkeypatch):
    _, repository, client = event_service()

    class Context:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(api, "OpenAIClient", lambda _: Context())
    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: None)
    response = request(
        main.create_app(),
        "POST",
        path,
        json={
            "query": "Synthetic event",
            "locale": "ru",
            "date_time": "2030-01-15T18:00:00+05:00",
            "available_minutes": 240,
            "budget_kzt_per_person": 5000,
        },
    )
    assert response.status_code == 200
    parsed = TransientEventSearchResponse.model_validate(response.json())
    assert parsed.status == "partial" and parsed.live_web_search == "passed"
    assert len(parsed.items) == 1 and parsed.items[0].fit_status == "unknown"
    assert parsed.items[0].session.price_from == 3000
    assert "within_budget" not in parsed.items[0].reason_codes
    assert "raw_search" not in response.text and '"evidence"' not in response.text
    assert all(not s.storage_allowed and not s.indexing_allowed for s in parsed.sources)
    assert len(client.search_calls) == 1
