"""Event HTTP aliases preserve unsupported requirements before provider work."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app import api, main
from backend.app.event_schemas import TransientEventSearchResponse
from backend.tests.test_api import request
from backend.tests.test_event_recommend import service as event_service
from backend.tests.test_requirement_preservation import assert_requirement_unknown

REQUEST_ID = "00000000-0000-4000-8000-000000000042"
EVENT_REQUIREMENTS = [
    ("child_suitability", "kk", "Алты жастағы баламен баратын іс-шара ұсын."),
    ("child_suitability", "ru", "Предложи мероприятие для шестилетнего ребенка."),
    ("child_suitability", "en", "An event suitable for my six-year-old child."),
    ("power_outlets", "kk", "Телефонды зарядтауға болатын іс-шара керек."),
    ("power_outlets", "ru", "Мероприятие с зарядкой для телефона."),
    ("power_outlets", "en", "An event with a charging point for my laptop."),
]


@pytest.mark.parametrize("path", ["/api/events/search", "/api/v2/events/search"])
@pytest.mark.parametrize("requirement,locale,query", EVENT_REQUIREMENTS)
def test_event_http_alias_preserves_requirement_before_provider_work(
    path, requirement, locale, query, monkeypatch
):
    router = AsyncMock()
    _, repository, client = event_service(router=router)
    lifecycle = {"entered": False, "closed": False}

    class ClientContext:
        async def __aenter__(self):
            lifecycle["entered"] = True
            return client

        async def __aexit__(self, *_):
            lifecycle["closed"] = True

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    response = request(
        main.create_app(),
        "POST",
        path,
        json={"query": query, "locale": locale, "request_id": REQUEST_ID},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    result = TransientEventSearchResponse.model_validate(response.json())
    assert str(result.request_id) == REQUEST_ID
    assert result.contract_version == "1.3.0"
    assert_requirement_unknown(result, requirement, locale)
    assert result.provider_status == "unknown"
    assert result.provider_code == "unsupported_fact_requirement"
    assert result.listings == [] and result.live_web_search == "not_run"
    assert client.parse_calls == client.search_calls == []
    assert repository.mock_calls == router.mock_calls == []
    assert lifecycle == {"entered": True, "closed": True}
