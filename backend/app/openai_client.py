"""Shared, bounded Responses/embeddings adapter; never log provider payloads."""

import math
from collections.abc import Awaitable
from typing import Protocol, Self

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAIError

from backend.app.settings import Settings


class AIClient(Protocol):
    async def create_response(self, text: str, *, instructions: str = "") -> str: ...

    async def embed(self, text: str) -> list[float]: ...


class ProviderError(RuntimeError):
    """Safe error code only: no API body, headers, credentials, or input text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def _safe_call[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except APIConnectionError:
        raise ProviderError("network_unavailable_or_timeout") from None
    except APIStatusError as exc:
        code = {
            401: "authentication_failed",
            403: "permission_denied",
            404: "model_or_endpoint_not_found",
            429: "rate_limit_or_quota",
        }.get(exc.status_code, "provider_http_error")
        raise ProviderError(code) from None
    except OpenAIError:
        raise ProviderError("invalid_provider_response") from None


class OpenAIClient:
    def __init__(self, settings: Settings, *, sdk: AsyncOpenAI | None = None):
        if not settings.openai_api_key.get_secret_value():
            raise ProviderError("missing_openai_api_key")
        self._settings = settings
        self._sdk = sdk or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=20.0,
            max_retries=0,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._sdk.close()

    async def check_model_access(self, model_id: str) -> str:
        """Check project access, not merely the existence of public documentation."""
        model = await _safe_call(self._sdk.models.retrieve(model_id))
        return model.id

    async def create_response(self, text: str, *, instructions: str = "") -> str:
        response = await _safe_call(
            self._sdk.responses.create(
                model=self._settings.openai_model,
                input=text,
                instructions=instructions,
                max_output_tokens=512,
                store=False,
            )
        )
        if response.status != "completed" or not response.output_text.strip():
            raise ProviderError("response_incomplete_or_empty")
        return response.output_text

    async def embed(self, text: str) -> list[float]:
        response = await _safe_call(
            self._sdk.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=text,
                dimensions=self._settings.openai_embedding_dimensions,
                encoding_format="float",
            )
        )
        if len(response.data) != 1:
            raise ProviderError("unexpected_embedding_count")
        vector = response.data[0].embedding
        if len(vector) != 1536 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            for value in vector
        ):
            raise ProviderError("invalid_embedding_dimensions_or_values")
        return vector
