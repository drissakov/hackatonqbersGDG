"""The first frontend handoff must run independently of all providers."""

import asyncio

import httpx

from backend.app.main import app


def test_health_does_not_read_provider_settings(monkeypatch):
    from backend.app import settings

    def forbidden_settings():
        raise AssertionError("Health must not initialize providers or settings")

    monkeypatch.setattr(settings, "get_settings", forbidden_settings)
    for name in ("DATABASE_URL", "OPENAI_API_KEY", "TWOGIS_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    async def request_health():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(request_health())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_documented():
    document = app.openapi()
    assert "/api/health" in document["paths"]
