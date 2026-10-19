"""Shared, bounded Responses/embeddings adapter; never log provider payloads."""

import re
from collections.abc import Awaitable, Mapping
from typing import Protocol, Self

from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    OpenAIError,
    pydantic_function_tool,
)
from pydantic import BaseModel, ValidationError

from backend.app.indexing import DIMENSIONS, EMBEDDING_MODEL, valid_vector
from backend.app.settings import Settings

WEB_SEARCH_MAX_OUTPUT_TOKENS = 4096
WEB_SEARCH_MAX_TOOL_CALLS = 3
WEB_SEARCH_TIMEOUT_SECONDS = 40.0
MAX_STRUCTURED_OUTPUT_TOKENS = 8192
WEB_SEARCH_BUDGET_INSTRUCTIONS = (
    "Hard tool budget: use at most three hosted web_search actions in total, including "
    "search, open_page and find_in_page. Prefer one search and one page inspection; reserve "
    "the third action for missing session date/year evidence. After the third action, stop "
    "using tools and produce the final factual answer with citations from consulted sources. "
    "Never attempt a fourth action. If the budget leaves "
    "coverage or facts uncertain, say they are unknown instead of performing another action. "
    "Languages are alternatives within this shared budget, not separate search quotas."
)
_DOMAIN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)


class AIClient(Protocol):
    async def create_response(self, text: str, *, instructions: str = "") -> str: ...

    async def embed(self, text: str) -> list[float]: ...

    async def parse_response[T: BaseModel](
        self,
        text: str,
        schema: type[T],
        *,
        instructions: str = "",
        max_output_tokens: int = 2000,
    ) -> T: ...

    async def search_web(
        self, text: str, *, instructions: str = "", allowed_domains: tuple[str, ...]
    ) -> Mapping[str, object]: ...


def _web_search_input(text: str, instructions: str, domains: tuple[str, ...]) -> list[str]:
    """Require bounded text and explicit DNS hosts, never URLs or an open search."""
    for value, limit, required in ((text, 16000, True), (instructions, 8000, False)):
        if (
            not isinstance(value, str)
            or len(value) > limit
            or (required and not value.strip())
            or any(ord(char) < 32 and char not in "\n\r\t" for char in value)
        ):
            raise ValueError("Web search requires bounded text and instructions")
    if not isinstance(domains, tuple) or not 1 <= len(domains) <= 100:
        raise ValueError("Web search requires 1..100 explicit allowed domains")
    normalized = []
    for domain in domains:
        if not isinstance(domain, str) or not _DOMAIN.fullmatch(domain.lower()):
            raise ValueError("Allowed domains must be DNS hostnames without schemes or paths")
        host = domain.lower()
        if host.endswith((".local", ".localhost", ".internal")) or host in normalized:
            raise ValueError("Allowed domains must be unique public DNS hostnames")
        normalized.append(host)
    return normalized


def _validate_web_search_output(raw: Mapping[str, object]) -> None:
    """Text alone cannot establish that the requested search actually succeeded.

    Domain-specific sources, citation offsets and factual grounding are checked
    by the consumer against the preserved action/annotation payload.
    """
    if (
        raw.get("status") != "completed"
        or raw.get("error") is not None
        or raw.get("incomplete_details") is not None
    ):
        raise ProviderError("web_search_response_incomplete")
    output = raw.get("output")
    if not isinstance(output, list) or len(output) > 100:
        raise ProviderError("web_search_output_invalid")
    calls, searched, text = 0, False, ""
    for item in output:
        if not isinstance(item, Mapping):
            raise ProviderError("web_search_output_invalid")
        if item.get("type") == "web_search_call":
            calls += 1
            action = item.get("action")
            if item.get("status") != "completed":
                raise ProviderError("web_search_response_incomplete")
            if not isinstance(action, Mapping) or action.get("type") not in (
                "search",
                "open_page",
                "find_in_page",
            ):
                raise ProviderError("web_search_output_invalid")
            searched = searched or action["type"] == "search"
        elif item.get("type") == "message":
            if item.get("status") != "completed" or not isinstance(item.get("content"), list):
                raise ProviderError("web_search_response_incomplete")
            for content in item["content"]:
                if not isinstance(content, Mapping):
                    raise ProviderError("web_search_output_invalid")
                if content.get("type") == "refusal":
                    raise ProviderError("response_incomplete_or_empty")
                if content.get("type") == "output_text":
                    value = content.get("text")
                    if not isinstance(value, str) or len(text) + len(value) > 40000:
                        raise ProviderError("web_search_text_invalid")
                    text += value
        elif item.get("type") != "reasoning":
            raise ProviderError("web_search_output_invalid")
    if not searched:
        raise ProviderError("web_search_tool_not_used")
    if calls > WEB_SEARCH_MAX_TOOL_CALLS:
        raise ProviderError("web_search_output_invalid")
    if not text.strip():
        raise ProviderError("response_incomplete_or_empty")


def _structured_output_text(raw: Mapping[str, object]) -> str:
    """Require one complete structured answer, never a partial/refused tool result."""
    if (
        not isinstance(raw, Mapping)
        or raw.get("status") != "completed"
        or raw.get("error") is not None
        or raw.get("incomplete_details") is not None
    ):
        raise ProviderError("response_incomplete_or_refused")
    output = raw.get("output")
    if not isinstance(output, list) or not 1 <= len(output) <= 100:
        raise ProviderError("invalid_structured_response")
    texts = []
    for item in output:
        if not isinstance(item, Mapping):
            raise ProviderError("invalid_structured_response")
        if item.get("type") == "reasoning":
            if item.get("status") not in (None, "completed"):
                raise ProviderError("response_incomplete_or_refused")
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            raise ProviderError("invalid_structured_response")
        if item.get("status") != "completed":
            raise ProviderError("response_incomplete_or_refused")
        content = item.get("content")
        if not isinstance(content, list):
            raise ProviderError("invalid_structured_response")
        if any(isinstance(part, Mapping) and part.get("type") == "refusal" for part in content):
            raise ProviderError("response_incomplete_or_refused")
        if (
            len(content) != 1
            or not isinstance(content[0], Mapping)
            or content[0].get("type") != "output_text"
            or not isinstance(content[0].get("text"), str)
            or not content[0]["text"].strip()
        ):
            raise ProviderError("invalid_structured_response")
        texts.append(content[0]["text"])
    if len(texts) != 1:
        raise ProviderError("invalid_structured_response")
    return texts[0]


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
        self,
        text: str,
        schema: type[T],
        *,
        instructions: str = "",
        max_output_tokens: int = 2000,
    ) -> T:
        if (
            type(max_output_tokens) is not int
            or not 0 < max_output_tokens <= MAX_STRUCTURED_OUTPUT_TOKENS
        ):
            raise ValueError("Structured output budget must be an integer in 1..8192")
        try:
            # The public SDK helper supplies its canonical strict Pydantic schema.
            # Only the schema is used; no function tool is sent or executed.
            function = pydantic_function_tool(schema)["function"]
            response = await _safe_call(
                self._sdk.responses.create(
                    model=self._settings.openai_model,
                    input=text,
                    instructions=instructions,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": function["name"],
                            "schema": function["parameters"],
                            "strict": True,
                        }
                    },
                    store=False,
                    max_output_tokens=max_output_tokens,
                )
            )
            # SDK parsing serializes with warnings that may contain raw provider
            # values. Validate a quiet wire dump before parsing trusted model fields.
            raw = response.model_dump(mode="json", warnings=False)
            return schema.model_validate_json(_structured_output_text(raw))
        except (ValidationError, ValueError, TypeError, AttributeError):
            raise ProviderError("invalid_structured_response") from None

    async def search_web(
        self, text: str, *, instructions: str = "", allowed_domains: tuple[str, ...]
    ) -> Mapping[str, object]:
        domains = _web_search_input(text, instructions, allowed_domains)
        response = await _safe_call(
            self._sdk.responses.create(
                model=self._settings.openai_model,
                input=text,
                instructions=(instructions + "\n" + WEB_SEARCH_BUDGET_INSTRUCTIONS).strip(),
                tools=[{"type": "web_search", "filters": {"allowed_domains": domains}}],
                tool_choice="required",
                include=["web_search_call.action.sources"],
                max_tool_calls=WEB_SEARCH_MAX_TOOL_CALLS,
                max_output_tokens=WEB_SEARCH_MAX_OUTPUT_TOKENS,
                timeout=WEB_SEARCH_TIMEOUT_SECONDS,
                store=False,
            )
        )
        # The SDK deliberately accepts forward-compatible wire fields. Its
        # serializer warnings can include those raw values; validate explicitly
        # below instead of allowing provider data to reach stderr/logs.
        raw = response.model_dump(mode="json", warnings=False)
        _validate_web_search_output(raw)
        return raw

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
