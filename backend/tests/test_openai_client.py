"""Exercise actual SDK serialization with synthetic HTTP responses; no network."""

import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI

from backend.app.openai_client import OpenAIClient, ProviderError
from backend.app.settings import Settings


def run_with_transport(handler, operation):
    async def run():
        settings = Settings(_env_file=None, openai_api_key="synthetic-test-key")
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        sdk = AsyncOpenAI(api_key="synthetic-test-key", http_client=http, max_retries=0)
        async with OpenAIClient(settings, sdk=sdk) as client:
            return await operation(client)

    return asyncio.run(run())


def test_responses_uses_configured_model_and_does_not_store():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert body["model"] == "gpt-6-luna"
        assert body["store"] is False
        assert body["input"] == "Synthetic probe"
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "model": body["model"],
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "OK", "annotations": []}],
                    }
                ],
            },
        )

    assert run_with_transport(handler, lambda c: c.create_response("Synthetic probe")) == "OK"


@pytest.mark.parametrize("dimensions", [1536, 1535])
def test_embedding_requests_and_checks_1536_dimensions(dimensions):
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/embeddings"
        assert body["model"] == "text-embedding-3-large"
        assert body["dimensions"] == 1536
        assert body["encoding_format"] == "float"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1] * dimensions}],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    if dimensions == 1536:
        assert len(run_with_transport(handler, lambda c: c.embed("Synthetic"))) == 1536
    else:
        with pytest.raises(ProviderError, match="invalid_embedding_dimensions_or_values"):
            run_with_transport(handler, lambda c: c.embed("Synthetic"))


def test_model_access_is_checked_by_real_sdk_method():
    def handler(request):
        assert request.url.path == "/v1/models/gpt-6-luna"
        return httpx.Response(
            200, json={"id": "gpt-6-luna", "object": "model", "created": 0, "owned_by": "test"}
        )

    assert run_with_transport(handler, lambda c: c.check_model_access("gpt-6-luna")) == "gpt-6-luna"


def test_provider_error_body_is_not_exposed():
    def handler(request):
        return httpx.Response(401, json={"error": {"message": "synthetic-secret-do-not-log"}})

    with pytest.raises(ProviderError) as error:
        run_with_transport(handler, lambda c: c.create_response("Synthetic"))
    assert str(error.value) == "authentication_failed"
    assert "synthetic-secret" not in str(error.value)
