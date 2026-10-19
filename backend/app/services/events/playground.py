"""Opt-in local D03 harness mounted on the existing application, never on startup.

Run the same backend with this factory to enable synthetic input inspection:
python -m uvicorn backend.app.services.events.playground:create_playground_app \
    --factory --host 127.0.0.1 --port 8003 --no-access-log
"""

import asyncio
import secrets
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import AwareDatetime, Field, HttpUrl, StrictBool, ValidationError

from backend.app.main import create_app
from backend.app.schemas import ContractModel, POIRecord
from backend.app.services.events.models import (
    CandidateEvent,
    Citation,
    EvidenceSource,
    FieldCheck,
    SearchEvidence,
)
from backend.app.services.events.normalize import normalize_events, verify_session
from backend.app.services.events.playground_cases import playground_cases

PREFIX = "/api/dev/events"
ENGINE = "backend.app.services.events.normalize.normalize_events"
MAX_BODY_BYTES = 128 * 1024


class PlaygroundSource(ContractModel):
    url: HttpUrl
    text: Annotated[str, Field(min_length=1, max_length=3000)]


class PlaygroundInput(ContractModel):
    now: AwareDatetime
    selected_at: AwareDatetime
    events: Annotated[list[CandidateEvent], Field(max_length=10)]
    sources: Annotated[list[PlaygroundSource], Field(min_length=1, max_length=10)]
    pois: Annotated[list[POIRecord], Field(max_length=20)] = Field(default_factory=list)
    simulate_start_check: StrictBool = False


def _error(status: int, code: str, fields: list[str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "fields": fields or []}}, status_code=status)


def _local_request(request: Request) -> bool:
    try:
        local_client = bool(request.client and ip_address(request.client.host).is_loopback)
        host = urlsplit("http://" + request.headers.get("host", "")).hostname
    except ValueError:
        return False
    origin = request.headers.get("origin")
    return (
        local_client
        and host in {"127.0.0.1", "localhost", "::1"}
        and (origin is None or origin == str(request.base_url).rstrip("/"))
    )


def run_playground(payload: PlaygroundInput) -> dict:
    """Execute real D03 functions on synthetic declared source contexts, without I/O."""
    citations = []
    offset = 0
    for source in payload.sources:
        citations.append(
            Citation(
                url=source.url,
                title="Synthetic playground input, not an API citation",
                start_index=offset,
                end_index=offset + len(source.text),
                text=source.text,
                context=source.text,
            )
        )
        offset += len(source.text) + 1
    evidence = SearchEvidence(
        text="\n".join(source.text for source in payload.sources),
        citations=citations,
        sources=[
            EvidenceSource(url=source.url, fetched_at=payload.now) for source in payload.sources
        ],
    )
    result = normalize_events(
        payload.events,
        evidence,
        now=payload.now,
        selected_at=payload.selected_at,
        pois=payload.pois,
    )
    simulated = False
    if payload.simulate_start_check:
        for event in result.events:
            for index, session in enumerate(event.sessions):
                if session.starts_at is not None:
                    check = FieldCheck(
                        session_id=session.session_id,
                        field="starts_at",
                        value=session.starts_at.isoformat(),
                        source_url=session.source_url,
                        checked_at=payload.now,
                        method="manual_source",
                    )
                    event.sessions[index] = verify_session(session, checks=[check])
                    simulated = True
    return {
        "is_test": True,
        "engine": ENGINE,
        "network_access": False,
        "simulated_verification": simulated,
        "result": result.model_dump(mode="json"),
    }


def create_playground_app() -> FastAPI:
    """Extend the existing app only for this explicitly chosen local entry point."""
    application = create_app()

    @application.middleware("http")
    async def local_only(request: Request, call_next):
        if request.url.path == PREFIX or request.url.path.startswith(PREFIX + "/"):
            if not _local_request(request):
                return _error(403, "local_playground_only")
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        return await call_next(request)

    @application.get(PREFIX + "/playground", include_in_schema=False)
    async def playground():
        nonce = secrets.token_urlsafe(24)
        html = Path(__file__).with_name("playground.html").read_text(encoding="utf-8")
        return HTMLResponse(
            html.replace("__D03_NONCE__", nonce),
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; "
                    f"script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
                    "connect-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'none'"
                ),
            },
        )

    @application.get(PREFIX + "/examples", include_in_schema=False)
    async def examples():
        return {
            "is_test": True,
            "engine": ENGINE,
            "network_access": False,
            "cases": playground_cases(),
        }

    @application.post(PREFIX + "/normalize", include_in_schema=False)
    async def normalize(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return _error(415, "json_required")
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        return _error(413, "playground_input_too_large")
                    body.extend(chunk)
            payload = PlaygroundInput.model_validate_json(bytes(body))
        except TimeoutError:
            return _error(408, "playground_input_timeout")
        except ValidationError as exc:
            fields = sorted(
                {
                    str(error["loc"][0])
                    for error in exc.errors()
                    if error["loc"] and error["loc"][0] in PlaygroundInput.model_fields
                }
            )
            return _error(422, "invalid_playground_input", fields)
        try:
            return run_playground(payload)
        except (ValueError, OverflowError):
            return _error(422, "invalid_playground_input")

    return application
