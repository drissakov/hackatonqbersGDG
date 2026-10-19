"""One fail-closed REST adapter. Provider payloads stay in request memory only."""

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from http.client import HTTPException
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import ValidationError

from backend.app.schemas import (
    Coordinates,
    Locale,
    RouteFailureReason,
    RouteLeg,
    RouteProvenance,
    RouteRequest,
)
from backend.app.settings import Settings

CATALOG = "https://catalog.api.2gis.com"
ROUTING = "https://routing.api.2gis.com/routing/7.0.0/global"
SOCKET_TIMEOUT = 5
REQUEST_TIMEOUT = 8
MAX_RESPONSE_BYTES = 256 * 1024
ROUTE_LOCALES = {"kk": "ru", "ru": "ru", "en": "en"}
PLACE_LOCALES = {"kk": "kk_KZ", "ru": "ru_KZ", "en": "en_RU"}
PLACE_FIELDS = "items.point,items.region_id,items.rubrics"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Keys and coordinates must never be forwarded to a redirect target.
        return None


class _ProviderFailure(Exception):
    def __init__(self, reason: RouteFailureReason):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, repr=False)
class CatalogProvenance:
    endpoint: str
    retrieved_at: datetime
    provider_locale: str
    observed_at: None = None
    provider: Literal["twogis"] = "twogis"
    storage_allowed: Literal[False] = False
    indexing_allowed: Literal[False] = False
    ranking_allowed: Literal[False] = False
    ai_allowed: Literal[False] = False


@dataclass(frozen=True, repr=False)
class LivePlace:
    external_id: str
    name: str
    location: Coordinates | None
    rubric_ids: tuple[str, ...]
    provenance: CatalogProvenance
    location_precision: Literal["approximate"] = "approximate"


@dataclass(frozen=True, repr=False)
class CatalogResult:
    status: Literal["ok", "no_match", "unavailable"]
    reason: RouteFailureReason | None = None
    region_id: str | None = None
    rubric_ids: tuple[str, ...] = ()
    places: tuple[LivePlace, ...] = ()
    provenance: CatalogProvenance | None = None


def _identifier(value) -> str:
    if not isinstance(value, str) or not value.isascii() or not value.isdigit():
        raise _ProviderFailure("invalid_response")
    if not 1 <= len(value) <= 100:
        raise _ProviderFailure("invalid_response")
    return value


def _units(value, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= maximum:
        raise _ProviderFailure("invalid_response")
    return math.ceil(value)


class TwoGISAdapter:
    """No DB, AI, retries, response logging, browser headers or payload cache."""

    def __init__(self, settings: Settings, *, opener=None):
        self._settings = settings
        self._opener = opener if opener is not None else build_opener(_NoRedirect())

    def _blocked(self, capability: str, *, region_key: bool = False) -> RouteFailureReason | None:
        if not self._settings.twogis_enabled:
            return "disabled"
        if not getattr(self._settings, f"twogis_{capability}_allowed") or not (
            self._settings.twogis_rights_basis.strip()
        ):
            return "rights_unconfirmed"
        key = self._settings.twogis_region_api_key if region_key else self._settings.twogis_api_key
        if not key.get_secret_value().strip():
            return "key_missing"
        return None

    def _read_json(self, endpoint: str, params: dict, body: dict | None, region_key: bool):
        key = self._settings.twogis_region_api_key if region_key else self._settings.twogis_api_key
        url = endpoint + "?" + urlencode({**params, "key": key.get_secret_value()})
        request = Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST" if body is not None else "GET",
        )
        try:
            deadline = time.monotonic() + REQUEST_TIMEOUT
            with self._opener.open(request, timeout=SOCKET_TIMEOUT) as response:
                if response.status != 200:
                    raise _ProviderFailure("http_error")
                chunks = []
                size = 0
                while True:
                    if time.monotonic() >= deadline:
                        raise _ProviderFailure("timeout")
                    chunk = response.read1(min(16 * 1024, MAX_RESPONSE_BYTES + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise _ProviderFailure("invalid_response")
                payload = b"".join(chunks)
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise _ProviderFailure("invalid_response")
            return data
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code == 429:
                raise _ProviderFailure("rate_limited") from None
            if code in {401, 403}:
                raise _ProviderFailure("access_denied") from None
            raise _ProviderFailure("http_error") from None
        except TimeoutError:
            raise _ProviderFailure("timeout") from None
        except URLError as exc:
            reason = "timeout" if isinstance(exc.reason, TimeoutError) else "network_error"
            raise _ProviderFailure(reason) from None
        except (OSError, HTTPException):
            raise _ProviderFailure("network_error") from None
        except (ValueError, UnicodeError, RecursionError):
            raise _ProviderFailure("invalid_response") from None

    async def _request(self, endpoint, params=None, body=None, *, region_key=False):
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await asyncio.to_thread(
                    self._read_json, endpoint, params or {}, body, region_key
                )
        except TimeoutError:
            raise _ProviderFailure("timeout") from None

    async def walking_leg(self, origin: Coordinates, destination: Coordinates, locale: Locale):
        blocked = self._blocked("routing")
        if blocked:
            return RouteLeg(status="unavailable", reason=blocked)
        provider_locale = ROUTE_LOCALES[locale]
        body = {
            "points": [
                {"lon": point.longitude, "lat": point.latitude, "type": "walking"}
                for point in (origin, destination)
            ],
            "transport": "walking",
            "output": "summary",
            "locale": provider_locale,
            "alternative": 0,
            "save_route": False,
        }
        try:
            data = await self._request(ROUTING, body=body)
            status = data.get("status")
            if not isinstance(status, str):
                raise _ProviderFailure("invalid_response")
            if status in {"ROUTE_NOT_FOUND", "ROUTE_DOES_NOT_EXISTS"}:
                return RouteLeg(status="unknown", reason="route_not_found")
            if status != "OK":
                raise _ProviderFailure("provider_fail")
            if data.get("type") != "result":
                raise _ProviderFailure("invalid_response")
            results = data.get("result")
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                raise _ProviderFailure("invalid_response")
            result = results[0]
            return RouteLeg(
                status="known",
                distance_meters=_units(result.get("total_distance"), 1_000_000),
                duration_seconds=_units(result.get("total_duration"), 604_800),
                provenance=RouteProvenance(
                    retrieved_at=datetime.now(UTC), provider_locale=provider_locale
                ),
            )
        except _ProviderFailure as exc:
            return RouteLeg(status="unavailable", reason=exc.reason)

    async def route(self, request: RouteRequest) -> tuple[RouteLeg, RouteLeg]:
        back = RouteLeg(status="not_requested", reason="not_requested")
        if request.origin is None:
            # Keep the existing disabled-provider 503 behavior even without an origin.
            blocked = self._blocked("routing")
            leg = RouteLeg(
                status="unavailable" if blocked else "unknown", reason=blocked or "missing_origin"
            )
            return leg, leg if request.return_to_start else back
        outbound = await self.walking_leg(request.origin, request.destination, request.locale)
        if request.return_to_start:
            back = await self.walking_leg(request.destination, request.origin, request.locale)
        return outbound, back

    @staticmethod
    def _items(data: dict, *, allow_no_match: bool = False) -> list[dict]:
        meta = data.get("meta")
        if not isinstance(meta, dict):
            raise _ProviderFailure("invalid_response")
        code = meta.get("code")
        if type(code) is not int:
            raise _ProviderFailure("invalid_response")
        error = meta.get("error")
        if (
            allow_no_match
            and code == 404
            and isinstance(error, dict)
            and error.get("type") == "itemNotFound"
            and data.get("result") is None
        ):
            # Recognize documented Places misses without weakening region discovery.
            return []
        if code == 429:
            raise _ProviderFailure("rate_limited")
        if code in {401, 403}:
            raise _ProviderFailure("access_denied")
        if code != 200:
            raise _ProviderFailure("provider_fail")
        result = data.get("result")
        if not isinstance(result, dict):
            raise _ProviderFailure("invalid_response")
        items = result.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise _ProviderFailure("invalid_response")
        return items

    async def discover_astana(self, rubric_query: str | None = None) -> CatalogResult:
        """Resolve IDs live; never borrow IDs from examples or another city."""
        blocked = self._blocked("discovery", region_key=True) or self._blocked("discovery")
        if blocked:
            return CatalogResult("unavailable", reason=blocked)
        if rubric_query is not None and not 1 <= len(rubric_query.strip()) <= 100:
            raise ValueError("Rubric query must contain 1..100 characters")
        try:
            endpoint = CATALOG + "/2.0/region/search"
            data = await self._request(
                endpoint, {"q": "Astana", "locale": "en_RU"}, region_key=True
            )
            regions = [
                item
                for item in self._items(data)
                if item.get("type") == "region"
                and isinstance(item.get("name"), str)
                and item["name"].strip().casefold() in {"astana", "астана"}
            ]
            if len(regions) != 1:
                raise _ProviderFailure("invalid_response")
            region_id = _identifier(regions[0].get("id"))
            rubrics = ()
            if rubric_query is not None:
                endpoint = CATALOG + "/2.0/catalog/rubric/search"
                data = await self._request(
                    endpoint,
                    {
                        "q": rubric_query.strip(),
                        "region_id": region_id,
                        "locale": "en_RU",
                        "page_size": 5,
                    },
                )
                rubrics = tuple(_identifier(item.get("id")) for item in self._items(data))
            return CatalogResult(
                "ok" if rubric_query is None or rubrics else "no_match",
                region_id=region_id,
                rubric_ids=rubrics,
                provenance=CatalogProvenance(endpoint, datetime.now(UTC), "en_RU"),
            )
        except _ProviderFailure as exc:
            return CatalogResult("unavailable", reason=exc.reason)

    async def search_places(self, query: str, locale: Locale = "ru") -> CatalogResult:
        """Ephemeral bounded Places query, deliberately separate from POIRecord/AI."""
        blocked = self._blocked("places")
        if blocked:
            return CatalogResult("unavailable", reason=blocked)
        if not 1 <= len(query.strip()) <= 500:
            raise ValueError("Places query must contain 1..500 characters")
        region = await self.discover_astana()
        if region.status != "ok":
            return region
        endpoint = CATALOG + "/3.0/items"
        provider_locale = PLACE_LOCALES[locale]
        try:
            data = await self._request(
                endpoint,
                {
                    "q": query.strip(),
                    "region_id": region.region_id,
                    "fields": PLACE_FIELDS,
                    "page_size": 3,
                    "locale": provider_locale,
                },
            )
            provenance = CatalogProvenance(endpoint, datetime.now(UTC), provider_locale)
            places = []
            items = self._items(data, allow_no_match=True)
            if len(items) > 3:
                raise _ProviderFailure("invalid_response")
            for item in items:
                if item.get("region_id") != region.region_id:
                    raise _ProviderFailure("invalid_response")
                name = item.get("name")
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 4000:
                    raise _ProviderFailure("invalid_response")
                point = item.get("point")
                location = None
                if point is not None:
                    if not isinstance(point, dict):
                        raise _ProviderFailure("invalid_response")
                    location = Coordinates(latitude=point.get("lat"), longitude=point.get("lon"))
                rubrics = item.get("rubrics", [])
                if not isinstance(rubrics, list) or any(not isinstance(r, dict) for r in rubrics):
                    raise _ProviderFailure("invalid_response")
                places.append(
                    LivePlace(
                        external_id=_identifier(item.get("id")),
                        name=name.strip(),
                        location=location,
                        rubric_ids=tuple(_identifier(r.get("id")) for r in rubrics),
                        provenance=provenance,
                    )
                )
            return CatalogResult(
                "ok" if places else "no_match",
                region_id=region.region_id,
                places=tuple(places),
                provenance=provenance,
            )
        except (_ProviderFailure, ValidationError) as exc:
            reason = exc.reason if isinstance(exc, _ProviderFailure) else "invalid_response"
            return CatalogResult("unavailable", reason=reason)
