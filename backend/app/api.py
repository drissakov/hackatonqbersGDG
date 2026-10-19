"""HTTP composition for S04; shared contracts and event ownership stay intact."""

from collections.abc import Callable

from fastapi import Request, Response
from pydantic import ValidationError

from backend.app.database import DatabaseUnavailable
from backend.app.event_recommend import EventRecommendationService
from backend.app.event_schemas import TransientEventSearchResponse
from backend.app.openai_client import OpenAIClient, ProviderError
from backend.app.recommend import MESSAGES, RecommendationService, empty_response
from backend.app.repository import POIRepository
from backend.app.schemas import (
    EventSearchRequest,
    RecommendationRequest,
    RecommendationResponse,
    Warning,
)
from backend.app.services.twogis import TwoGISAdapter
from backend.app.settings import get_settings


async def recommendations(
    body: RecommendationRequest,
    response: Response,
    request: Request,
    *,
    repository_factory: Callable[[Request], POIRepository],
    router_factory: Callable[[], TwoGISAdapter | None],
) -> RecommendationResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        repository = repository_factory(request)
        settings = get_settings()
        async with OpenAIClient(settings) as client:
            result = await RecommendationService(
                repository, client, router_factory(), timezone=settings.app_timezone
            ).recommend(body)
    except (DatabaseUnavailable, ValidationError, ProviderError):
        result = empty_response(
            body, "unavailable", "provider_unavailable", MESSAGES[body.locale]["unavailable"]
        )
    response.status_code = 503 if result.status == "unavailable" else 200
    return result


async def events(
    body: EventSearchRequest,
    response: Response,
    request: Request,
    *,
    repository_factory: Callable[[Request], POIRepository],
    router_factory: Callable[[], TwoGISAdapter | None],
) -> TransientEventSearchResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        settings = get_settings()
        # The corpus enriches exact venue matches; it is optional for live discovery.
        try:
            repository = repository_factory(request)
        except (DatabaseUnavailable, ValidationError):
            repository = None
        async with OpenAIClient(settings) as client:
            result = await EventRecommendationService(repository, client, router_factory()).search(
                body
            )
    except (ValidationError, ProviderError):
        result = TransientEventSearchResponse(
            request_id=body.request_id,
            status="unavailable",
            provider_status="unavailable",
            provider_code="event_service_unavailable",
            live_web_search="not_run",
            items=[],
            listings=[],
            sources=[],
            warnings=[
                Warning(code="provider_unavailable", message=MESSAGES[body.locale]["unavailable"])
            ],
        )
    response.status_code = 503 if result.status == "unavailable" else 200
    return result
