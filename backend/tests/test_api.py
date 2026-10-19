"""Observable HTTP status, sanitization, SPA boundary and explicit fixture access."""

import asyncio
from uuid import UUID

import httpx
import pytest

from backend.app import main
from backend.app.database import DatabaseUnavailable
from backend.app.main import create_app, get_repository
from backend.app.settings import Settings


def request(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/events/search",
    ],
)
@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
def test_scaffolds_return_real_503_and_correlation_without_providers(path, locale, monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: (_ for _ in ()).throw(AssertionError()))
    payload = {
        "query": "synthetic",
        "locale": locale,
        "request_id": "00000000-0000-4000-8000-000000000001",
    }
    response = request(create_app(), "POST", path, json=payload)
    assert response.status_code == 503
    assert response.json() == {
        "request_id": payload["request_id"],
        "status": "unavailable",
        "items": [],
        "sources": [],
        "warnings": [
            {
                "code": "provider_unavailable",
                "message": main.UNAVAILABLE_MESSAGES[locale],
                "fields": [],
            }
        ],
    }


def test_route_scaffold_never_fabricates_travel_time():
    response = request(
        create_app(),
        "POST",
        "/api/route",
        json={"destination": {"latitude": 51, "longitude": 71}, "locale": "ru"},
    )
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["travel_minutes_estimate"] is None


def test_wrong_method_is_json_405_with_allow_header():
    response = request(create_app(), "POST", "/api/health")
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert response.json()["error"]["code"] == "http_error"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "OPTIONS"])
def test_unknown_api_path_is_json_404_for_every_method(tmp_path, method):
    (tmp_path / "index.html").write_text("<html>Synthetic SPA</html>", encoding="utf-8")
    response = request(create_app(spa_dir=tmp_path), method, "/api/not-real")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "synthetic-private-query", "origin": {"latitude": 100, "longitude": 71}},
        {"query": "synthetic-private-query", "request_id": "synthetic-private-id"},
        {"query": "synthetic-private-query", "date_time": "2030-01-01T00:00:00"},
    ],
)
def test_validation_hides_raw_input_and_errors(payload):
    response = request(create_app(), "POST", "/api/recommendations", json=payload)
    assert response.status_code == 422
    assert "synthetic-private" not in response.text
    assert "input" not in response.text
    assert response.json()["error"]["code"] == "invalid_request"
    UUID(response.json()["request_id"])


def test_malformed_json_is_422_without_echo():
    response = request(
        create_app(),
        "POST",
        "/api/recommendations",
        content='{"query":"synthetic-private',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "synthetic-private" not in response.text


def test_coverage_database_failure_is_503_and_internal_failure_is_500():
    app = create_app()

    class Repo:
        async def coverage(self):
            raise DatabaseUnavailable("synthetic-private-driver-body")

    app.dependency_overrides[get_repository] = lambda: Repo()
    response = request(app, "GET", "/api/coverage")
    assert response.status_code == 503
    assert "synthetic-private" not in response.text

    class BrokenRepo:
        async def coverage(self):
            raise RuntimeError("synthetic-private-driver-body")

    app.dependency_overrides[get_repository] = lambda: BrokenRepo()
    response = request(app, "GET", "/api/coverage")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_unexpected_error_does_not_escape_to_server_exception_logging(caplog):
    app = create_app()

    class BrokenRepo:
        async def coverage(self):
            raise RuntimeError("synthetic-private-provider-body")

    app.dependency_overrides[get_repository] = lambda: BrokenRepo()

    async def run():
        # Default transport re-raises anything escaping the ASGI application,
        # just as Uvicorn would receive it for exception/traceback logging.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/api/coverage")

    response = asyncio.run(run())
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "synthetic-private-provider-body" not in response.text
    assert "synthetic-private-provider-body" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert response.json()["request_id"] in caplog.text


def test_pool_is_closed_when_lifespan_exits_with_an_exception():
    app = create_app()

    class Pool:
        closed = False

        def close(self):
            self.closed = True

    pool = Pool()
    app.state.pool = pool

    async def run():
        async with app.router.lifespan_context(app):
            raise RuntimeError("synthetic lifecycle failure")

    with pytest.raises(RuntimeError, match="synthetic lifecycle failure"):
        asyncio.run(run())
    assert pool.closed


def test_spa_never_intercepts_api_or_missing_assets(tmp_path):
    (tmp_path / "index.html").write_text("<html>Synthetic SPA</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("// synthetic", encoding="utf-8")
    app = create_app(spa_dir=tmp_path)
    for path in ["/", "/places/one"]:
        assert request(app, "GET", path).status_code == 200
    for path in [
        "/api",
        "/api/not-real",
        "/api/health/other",
        "/assets/missing.js",
        "/%2e%2e/private",
    ]:
        response = request(app, "GET", path)
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"
    assert request(app, "GET", "/assets/app.js").status_code == 200
    assert request(app, "GET", "/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("env", "flag", "status"),
    [
        ("production", False, 404),
        ("production", True, 404),
        ("development", False, 404),
        ("development", True, 200),
    ],
)
def test_fixtures_require_both_explicit_dev_mode_and_flag(monkeypatch, env, flag, status):
    monkeypatch.setattr(
        main, "get_settings", lambda: Settings(_env_file=None, app_env=env, dev_fixture_mode=flag)
    )
    response = request(create_app(), "GET", "/api/dev/pois")
    assert response.status_code == status
    if status == 200:
        assert response.json()["is_production_dataset"] is False
        assert response.json()["items"][0]["is_test"] is True
