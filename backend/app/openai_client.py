"""Shared, bounded Responses/embeddings adapter; never log provider payloads."""

from collections.abc import Awaitable
from typing import Protocol, Self

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from backend.app.indexing import DIMENSIONS, EMBEDDING_MODEL, valid_vector
from backend.app.settings import Settings


class AIClient(Protocol):
    async def create_response(self, text: str, *, instructions: str = "") -> str: ...

    async def embed(self, text: str) -> list[float]: ...

    async def parse_response[T: BaseModel](
        self, text: str, schema: type[T], *, instructions: str = ""
    ) -> T: ...


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
        return (await self.embed_many([text]))[0]

    async def parse_response[T: BaseModel](
        self, text: str, schema: type[T], *, instructions: str = ""
    ) -> T:
        try:
            response = await _safe_call(
                self._sdk.responses.parse(
                    model=self._settings.openai_model,
                    input=text,
                    instructions=instructions,
                    text_format=schema,
                    store=False,
                    max_output_tokens=2000,
                )
            )
        except (ValidationError, ValueError):
            raise ProviderError("invalid_structured_response") from None
        if response.status != "completed" or not isinstance(response.output_parsed, schema):
            raise ProviderError("response_incomplete_or_refused")
        return response.output_parsed

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts or len(texts) > 32 or any(not text.strip() for text in texts):
            raise ValueError("Embedding batches require 1..32 nonempty texts")
        if (
            self._settings.openai_embedding_model != EMBEDDING_MODEL
            or self._settings.openai_embedding_dimensions != DIMENSIONS
        ):
            raise ProviderError("incompatible_embedding_space")
        response = await _safe_call(
            self._sdk.embeddings.create(
                model=self._settings.openai_embedding_model,
                input=texts[0] if len(texts) == 1 else texts,
                dimensions=self._settings.openai_embedding_dimensions,
                encoding_format="float",
            )
        )
        if len(response.data) != len(texts):
            raise ProviderError("unexpected_embedding_count")
        if response.model != EMBEDDING_MODEL:
            raise ProviderError("incompatible_embedding_space")
        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(texts))):
            raise ProviderError("unexpected_embedding_indices")
        if any(not valid_vector(item.embedding) for item in ordered):
            raise ProviderError("invalid_embedding_dimensions_or_values")
        return [item.embedding for item in ordered]
