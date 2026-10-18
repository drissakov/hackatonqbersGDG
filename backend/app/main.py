"""Same-origin API and optional built SPA. Health never initializes providers."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.database import DatabasePool, DatabaseUnavailable
from backend.app.repository import POIRepository, PostgresPOIRepository
from backend.app.schemas import (
    CoverageResponse,
    EventSearchRequest,
    EventSearchResponse,
    POIRecord,
    RecommendationRequest,
    RecommendationResponse,
    RouteRequest,
    RouteResponse,
    Warning,
)
from backend.app.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)
UNAVAILABLE_MESSAGES = {
    "kk": "Қызмет әлі қолжетімсіз. Кейінірек қайталап көріңіз.",
    "ru": "Сервис пока недоступен. Повторите попытку позже.",
    "en": "This service is not available yet. Please try again later.",
}


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def get_repository(request: Request) -> POIRepository:
    with request.app.state.repository_lock:
        if request.app.state.repository is None:
            try:
                settings = get_settings()
            except ValidationError:
                raise DatabaseUnavailable("invalid_settings") from None
            pool = DatabasePool(
                settings.database_url.get_secret_value(), settings.database_pool_size
            )
            request.app.state.pool = pool
            request.app.state.repository = PostgresPOIRepository(
                pool, allow_test=settings.fixtures_enabled
            )
    return request.app.state.repository


def error_response(status_code, code, fields=(), request_id=None, headers=None):
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {"code": code, "fields": list(fields)},
            "request_id": str(request_id or uuid4()),
        },
    )


class SafeErrorMiddleware:
    """Log correlation only; raw unexpected exceptions must not reach Uvicorn."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        response_started = False

        async def tracked_send(message: Message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            request_id = uuid4()
            logger.error("internal_error request_id=%s", request_id)
            if response_started:
                # Headers cannot be replaced, but the server still gets a safe error.
                raise RuntimeError("Response failed after headers were sent") from None
            await error_response(500, "internal_error", request_id=request_id)(scope, receive, send)


class SPARoute(APIRoute):
    """Exclude API paths before matching methods, preserving genuine 404/405."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        path = scope.get("path", "")
        if path == "/api" or path.startswith("/api/"):
            return Match.NONE, {}
        return super().matches(scope)


def create_app(*, spa_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        try:
            yield
        finally:
            if application.state.pool:
                await asyncio.to_thread(application.state.pool.close)

    application = FastAPI(title="Qadam Astana API", version="1.1.0", lifespan=lifespan)
    application.add_middleware(SafeErrorMiddleware)
    application.state.pool = None
    application.state.repository = None
    application.state.repository_lock = Lock()

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        allowed = set(RecommendationRequest.model_fields) | set(RouteRequest.model_fields)
        fields = sorted(
            {str(e["loc"][1]) for e in exc.errors() if len(e["loc"]) > 1 and e["loc"][1] in allowed}
        )
        request_id = None
        if isinstance(exc.body, dict):
            try:
                request_id = UUID(str(exc.body.get("request_id")))
            except ValueError:
                pass
        return error_response(422, "invalid_request", fields, request_id)

    @application.exception_handler(DatabaseUnavailable)
    async def database_unavailable(request, exc):
        return error_response(503, "database_unavailable")

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(
            exc.status_code,
            "not_found" if exc.status_code == 404 else "http_error",
            headers=exc.headers,
        )

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/api/coverage",
        response_model=CoverageResponse,
        responses={503: {"description": "Database unavailable or not migrated"}},
    )
    async def coverage(repository: Annotated[POIRepository, Depends(get_repository)]):
        return await repository.coverage()

    @application.post("/api/v1/recommendations", include_in_schema=False, status_code=503)
    @application.post(
        "/api/recommendations", response_model=RecommendationResponse, status_code=503
    )
    async def recommendations(body: RecommendationRequest):
        return RecommendationResponse(
            request_id=body.request_id,
            status="unavailable",
            items=[],
            sources=[],
            warnings=[
                Warning(code="provider_unavailable", message=UNAVAILABLE_MESSAGES[body.locale])
            ],
        )

    @application.post("/api/v1/events/search", include_in_schema=False, status_code=503)
    @application.post("/api/events/search", response_model=EventSearchResponse, status_code=503)
    async def events(body: EventSearchRequest):
        return EventSearchResponse(
            request_id=body.request_id,
            status="unavailable",
            items=[],
            sources=[],
            warnings=[
                Warning(code="provider_unavailable", message=UNAVAILABLE_MESSAGES[body.locale])
            ],
        )

    @application.post("/api/v1/route", include_in_schema=False, status_code=503)
    @application.post("/api/route", response_model=RouteResponse, status_code=503)
    async def route(body: RouteRequest):
        return RouteResponse(
            request_id=body.request_id,
            warnings=[Warning(code="route_unavailable", message=UNAVAILABLE_MESSAGES[body.locale])],
        )

    @application.get("/api/dev/pois", include_in_schema=False)
    def fixture_pois():
        try:
            enabled = get_settings().fixtures_enabled
        except ValidationError:
            enabled = False
        path = ROOT / "contracts" / "examples" / "poi.test.json"
        if not enabled or not path.is_file():
            raise HTTPException(404)
        record = POIRecord.model_validate_json(path.read_text(encoding="utf-8"))
        return {"is_test": True, "is_production_dataset": False, "items": [record]}

    distribution = (spa_dir or ROOT / "frontend" / "dist").resolve()

    async def spa(path: str):
        candidate = (distribution / path).resolve()
        if not candidate.is_relative_to(distribution):
            raise HTTPException(404)
        if candidate.is_file():
            return FileResponse(candidate)
        if Path(path).suffix or not (distribution / "index.html").is_file():
            raise HTTPException(404)
        return FileResponse(distribution / "index.html", headers={"Cache-Control": "no-cache"})

    application.router.routes.append(
        SPARoute("/{path:path}", endpoint=spa, methods=["GET"], include_in_schema=False)
    )
    return application


app = create_app()
