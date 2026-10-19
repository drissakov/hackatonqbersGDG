"""Bounded Overpass acquisition and boundary validation, using only stdlib.

The raw snapshot is licensed OSM input, not an assertion that the city is fully
mapped. Queries cover the boundary's bounding box; normalization must clip each
representative point against the saved administrative boundary.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from ingestion.categories import CATEGORY_FILTERS, category_for

ENDPOINT = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
RIGHTS_URL = "https://www.openstreetmap.org/copyright"
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
SNAPSHOT_FORMAT = "qadam-osm-snapshot-v1"
__all__ = [
    "OSMError",
    "OverpassClient",
    "category_for",
    "contains",
    "fetch_astana",
    "validate_snapshot",
]


class OSMError(Exception):
    """A stable diagnostic code that never includes a provider response body."""

    def __init__(self, code: str, *, queries: list[dict[str, Any]] | None = None):
        self.code = code
        self.queries = queries
        self.snapshot: dict[str, Any] | None = None
        super().__init__(code)


class OverpassClient:
    """A public read-only client with bounded HTTP/query timeouts and retries."""

    def __init__(self, timeout: float = 60, retries: int = 2, concurrency: int = 1):
        if not 5 <= timeout <= 120 or not 0 <= retries <= 3 or not 1 <= concurrency <= 2:
            raise ValueError("timeout=5..120, retries=0..3, concurrency=1..2 required")
        self.timeout = timeout
        self.retries = retries
        self.concurrency = concurrency

    @property
    def query_timeout(self) -> int:
        return max(1, int(self.timeout) - 5)

    def query(self, query: str) -> dict[str, Any]:
        """Return verified JSON; every query must end with an out-count sentinel."""
        request = urllib.request.Request(
            ENDPOINT,
            data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
            headers={
                "User-Agent": "QadamAstana-D02/1.0 (OSM corpus importer)",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            },
            method="POST",
        )
        for attempt in range(self.retries + 1):
            retry_after = 0.0
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise OSMError("response_too_large")
                try:
                    payload = json.loads(raw)
                except (UnicodeDecodeError, ValueError):
                    raise OSMError("invalid_response") from None
                _response_elements(payload)
                return payload
            except urllib.error.HTTPError as exc:
                status = exc.code
                try:
                    retry_after = _retry_delay(exc.headers.get("Retry-After", "0"))
                except (TypeError, ValueError):
                    retry_after = 0
                finally:
                    exc.close()
                code = {
                    403: "http_forbidden",
                    429: "http_rate_limited",
                    504: "provider_timeout",
                }.get(status, "http_unavailable")
                if status not in (408, 429, 500, 502, 503, 504) or retry_after > 120:
                    raise OSMError(code) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                code = "network_unavailable"
            except OSMError as exc:
                code = exc.code
                if code not in ("incomplete_response", "invalid_response"):
                    raise
            if attempt == self.retries:
                raise OSMError(code) from None
            time.sleep(max(retry_after, min(2**attempt, 4)))
        raise OSMError("network_unavailable")  # pragma: no cover


def _retry_delay(value: str) -> float:
    try:
        return max(0.0, float(value))
    except ValueError:
        return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())


def _response_elements(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise OSMError("invalid_response")
    if payload.get("remark"):
        raise OSMError("incomplete_response")
    metadata = payload.get("osm3s")
    if not isinstance(metadata, dict) or not _aware_timestamp(metadata.get("timestamp_osm_base")):
        raise OSMError("invalid_response_timestamp")
    elements = payload["elements"]
    if any(not isinstance(element, dict) for element in elements):
        raise OSMError("invalid_response")
    counts = [element for element in elements if element.get("type") == "count"]
    records = [element for element in elements if element.get("type") != "count"]
    if len(counts) != 1 or elements[-1] is not counts[0]:
        raise OSMError("incomplete_response")
    if any(
        element.get("type") not in ("node", "way", "relation")
        or type(element.get("id")) is not int
        or element["id"] <= 0
        for element in records
    ):
        raise OSMError("invalid_response")
    identities = [(element.get("type"), element.get("id")) for element in records]
    if len(set(identities)) != len(identities):
        raise OSMError("incomplete_response")
    totals = Counter(element["type"] for element in records)
    tags = counts[0].get("tags", {})
    if not isinstance(tags, dict):
        raise OSMError("incomplete_response")
    for tag, actual in (
        ("total", len(records)),
        ("nodes", totals["node"]),
        ("ways", totals["way"]),
        ("relations", totals["relation"]),
    ):
        reported = tags.get(tag)
        if not isinstance(reported, str) or not reported.isdecimal() or int(reported) != actual:
            raise OSMError("incomplete_response")
    return records


def _point(value: object) -> list[float]:
    if not isinstance(value, dict):
        raise OSMError("invalid_boundary_geometry")
    lon, lat = value.get("lon"), value.get("lat")
    if not _coordinate(lon, lat):
        raise OSMError("invalid_boundary_geometry")
    return [lon, lat]


def _coordinate(lon: object, lat: object) -> bool:
    return (
        type(lon) in (int, float)
        and type(lat) in (int, float)
        and math.isfinite(lon)
        and math.isfinite(lat)
        and -180 <= lon <= 180
        and -90 <= lat <= 90
    )


def _rings(parts: list[list[list[float]]]) -> list[list[list[float]]]:
    """Join reversed/split way members; refuse incomplete or ambiguous chains."""
    remaining = [part[:] for part in parts]
    rings = []
    while remaining:
        ring = remaining.pop(0)
        while ring[0] != ring[-1]:
            matches = [
                (index, part)
                for index, part in enumerate(remaining)
                if ring[-1] in (part[0], part[-1])
            ]
            if len(matches) != 1:
                raise OSMError("unclosed_boundary_geometry")
            index, part = matches[0]
            remaining.pop(index)
            if ring[-1] != part[0]:
                part = list(reversed(part))
            ring.extend(part[1:])
        _validate_ring(ring)
        rings.append(ring)
    return rings


def _area(ring: list[list[float]]) -> float:
    return (
        sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(ring, ring[1:], strict=False)
        )
        / 2
    )


def _validate_ring(ring: object) -> None:
    if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
        raise OSMError("invalid_boundary_geometry")
    if any(
        not isinstance(point, list) or len(point) != 2 or not _coordinate(*point) for point in ring
    ):
        raise OSMError("invalid_boundary_geometry")
    if len({tuple(point) for point in ring[:-1]}) < 3 or abs(_area(ring)) < 1e-12:
        raise OSMError("invalid_boundary_geometry")


def _in_ring(ring: list[list[float]], lon: float, lat: float) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-12
            and min(x1, x2) <= lon <= max(x1, x2)
            and min(y1, y2) <= lat <= max(y1, y2)
        ):
            return True
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(boundary: dict[str, Any], lon: float, lat: float) -> bool:
    """Point-in-MultiPolygon, including outer edges and excluding inner holes."""
    if not _coordinate(lon, lat):
        return False
    return any(
        _in_ring(polygon[0], lon, lat) and not any(_in_ring(hole, lon, lat) for hole in polygon[1:])
        for polygon in boundary["geometry"]["coordinates"]
    )


def _boundary_feature(relation: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    parts: dict[str, list[list[list[float]]]] = {"outer": [], "inner": []}
    members = relation.get("members")
    if not isinstance(members, list) or any(not isinstance(member, dict) for member in members):
        raise OSMError("missing_boundary_geometry")
    for member in members:
        role = member.get("role", "") or "outer"
        if not isinstance(role, str):
            raise OSMError("invalid_boundary_geometry")
        if role not in parts:
            continue  # admin_centre, label and subarea do not form the boundary.
        geometry = member.get("geometry")
        if member.get("type") != "way" or not isinstance(geometry, list) or len(geometry) < 2:
            raise OSMError("missing_boundary_geometry")
        parts[role].append([_point(point) for point in geometry])
    outers = _rings(parts["outer"])
    if not outers:
        raise OSMError("missing_boundary_geometry")
    polygons = [[ring if _area(ring) > 0 else list(reversed(ring))] for ring in outers]
    for hole in _rings(parts["inner"]):
        owners = [
            polygon for polygon in polygons if all(_in_ring(polygon[0], *point) for point in hole)
        ]
        if len(owners) != 1:
            raise OSMError("invalid_boundary_geometry")
        owners[0].append(hole if _area(hole) < 0 else list(reversed(hole)))
    return {
        "type": "Feature",
        "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        "properties": {
            "osm_type": "relation",
            "osm_id": relation["id"],
            "url": f"https://www.openstreetmap.org/relation/{relation['id']}",
            "tags": relation.get("tags", {}),
            "fetched_at": fetched_at,
            "timestamp": relation.get("timestamp"),
            "version": relation.get("version"),
        },
    }


def _boundary_tags(tags: object) -> bool:
    return (
        isinstance(tags, dict)
        and tags.get("boundary") == "administrative"
        and tags.get("admin_level") == "4"
        and (tags.get("ISO3166-2") in ("KZ-71", "KZ-AST") or tags.get("wikidata") == "Q1520")
    )


def fetch_astana(client: OverpassClient) -> dict[str, Any]:
    """Discover the current admin relation, then fetch finite category queries."""
    prefix = f"[out:json][timeout:{client.query_timeout}];"
    discovery = (
        prefix + '(relation["boundary"="administrative"]["admin_level"="4"]'
        '["ISO3166-2"="KZ-71"];'
        'relation["boundary"="administrative"]["admin_level"="4"]'
        '["ISO3166-2"="KZ-AST"];'
        'relation["boundary"="administrative"]["admin_level"="4"]'
        '["wikidata"="Q1520"];);out meta geom;out count;'
    )
    response = client.query(discovery)
    candidates = [
        element
        for element in _response_elements(response)
        if element.get("type") == "relation" and _boundary_tags(element.get("tags"))
    ]
    if not candidates:
        raise OSMError("boundary_not_found")
    if len(candidates) != 1:
        raise OSMError("boundary_ambiguous")
    fetched_at = datetime.now(UTC).isoformat()
    boundary = _boundary_feature(candidates[0], fetched_at)
    boundary["properties"]["source_timestamp"] = response.get("osm3s", {}).get("timestamp_osm_base")
    vertices = [point for polygon in boundary["geometry"]["coordinates"] for point in polygon[0]]
    bbox = ",".join(
        str(value)
        for value in (
            min(point[1] for point in vertices),
            min(point[0] for point in vertices),
            max(point[1] for point in vertices),
            max(point[0] for point in vertices),
        )
    )
    outcomes: dict[str, dict[str, Any]] = {}
    by_identity: dict[tuple[str, int], dict[str, Any]] = {}

    def fetch_category(category: str) -> dict[str, Any]:
        selectors = "".join(
            f'nwr["{key}"="{value}"]({bbox});' for key, value in CATEGORY_FILTERS[category]
        )
        return client.query(prefix + "(" + selectors + ");out meta center;out count;")

    with ThreadPoolExecutor(max_workers=client.concurrency) as executor:
        futures = {
            executor.submit(fetch_category, category): category for category in CATEGORY_FILTERS
        }
        for future in as_completed(futures):
            category = futures[future]
            try:
                payload = future.result()
                records = _response_elements(payload)
            except OSMError as exc:
                outcomes[category] = {
                    "category": category,
                    "status": "failed",
                    "count": 0,
                    "error_code": exc.code,
                    "element_ids": [],
                }
                continue
            outcomes[category] = {
                "category": category,
                "status": "ok",
                "count": len(records),
                "error_code": None,
                "source_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
                "element_ids": sorted(f"{record['type']}/{record['id']}" for record in records),
            }
            for element in records:
                key = element["type"], element["id"]
                previous = by_identity.get(key)
                if previous is None or element.get("timestamp", "") > previous.get("timestamp", ""):
                    by_identity[key] = element
    snapshot = {
        "format": SNAPSHOT_FORMAT,
        "provider": "osm",
        "city": "astana",
        "license": "ODbL-1.0",
        "rights_basis_url": RIGHTS_URL,
        "endpoint": ENDPOINT,
        "attribution": "© OpenStreetMap contributors",
        "fetched_at": fetched_at,
        "source_timestamp": response.get("osm3s", {}).get("timestamp_osm_base"),
        "boundary": boundary,
        "queries": [outcomes[category] for category in CATEGORY_FILTERS],
        "elements": [by_identity[key] for key in sorted(by_identity)],
        "complete": all(outcome["status"] == "ok" for outcome in outcomes.values()),
    }
    try:
        validate_snapshot(snapshot)
    except OSMError as exc:
        exc.snapshot = snapshot
        exc.queries = snapshot["queries"]
        raise
    return snapshot


def _aware_timestamp(value: object) -> bool:
    try:
        return isinstance(value, str) and datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def validate_snapshot(snapshot: object) -> None:
    """Permit only declared OSM snapshots; reject fake empty or complete imports."""
    if not isinstance(snapshot, dict):
        raise OSMError("invalid_snapshot")
    if (
        snapshot.get("format") != SNAPSHOT_FORMAT
        or snapshot.get("provider") != "osm"
        or snapshot.get("city") != "astana"
        or snapshot.get("license") != "ODbL-1.0"
        or snapshot.get("rights_basis_url") != RIGHTS_URL
        or ("is_test" in snapshot and snapshot["is_test"] is not False)
    ):
        raise OSMError("snapshot_rights_not_permitted")
    if not _aware_timestamp(snapshot.get("fetched_at")) or not _aware_timestamp(
        snapshot.get("source_timestamp")
    ):
        raise OSMError("invalid_snapshot_timestamp")
    boundary = snapshot.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("type") != "Feature":
        raise OSMError("invalid_boundary_geometry")
    geometry = boundary.get("geometry", {})
    if not isinstance(geometry, dict) or geometry.get("type") != "MultiPolygon":
        raise OSMError("invalid_boundary_geometry")
    polygons = geometry.get("coordinates")
    if not isinstance(polygons, list) or not polygons:
        raise OSMError("invalid_boundary_geometry")
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise OSMError("invalid_boundary_geometry")
        for ring in polygon:
            _validate_ring(ring)
        if any(not all(_in_ring(polygon[0], *point) for point in hole) for hole in polygon[1:]):
            raise OSMError("invalid_boundary_geometry")
    properties = boundary.get("properties", {})
    if (
        not isinstance(properties, dict)
        or properties.get("osm_type") != "relation"
        or type(properties.get("osm_id")) is not int
        or properties["osm_id"] <= 0
        or properties.get("url")
        != f"https://www.openstreetmap.org/relation/{properties.get('osm_id')}"
        or not _boundary_tags(properties.get("tags"))
        or not _aware_timestamp(properties.get("fetched_at"))
        or not _aware_timestamp(properties.get("source_timestamp"))
    ):
        raise OSMError("invalid_snapshot_boundary")
    queries = snapshot.get("queries")
    if not isinstance(queries, list) or len(queries) != len(CATEGORY_FILTERS):
        raise OSMError("invalid_snapshot_queries")
    found = set()
    referenced_ids = set()
    for query in queries:
        if not isinstance(query, dict):
            raise OSMError("invalid_snapshot_queries")
        category = query.get("category")
        if not isinstance(category, str) or category not in CATEGORY_FILTERS or category in found:
            raise OSMError("invalid_snapshot_queries")
        found.add(category)
        element_ids = query.get("element_ids")
        if (
            query.get("status") not in ("ok", "failed")
            or type(query.get("count")) is not int
            or query["count"] < 0
            or not isinstance(element_ids, list)
            or any(not isinstance(value, str) for value in element_ids)
            or len(set(element_ids)) != len(element_ids)
            or len(element_ids) != query["count"]
            or (query["status"] == "ok" and query.get("error_code") is not None)
            or (query["status"] == "ok" and not _aware_timestamp(query.get("source_timestamp")))
            or (
                query["status"] == "failed"
                and (query["count"] != 0 or not isinstance(query.get("error_code"), str))
            )
        ):
            raise OSMError("invalid_snapshot_queries")
        referenced_ids.update(element_ids)
    if type(snapshot.get("complete")) is not bool or snapshot["complete"] != all(
        query["status"] == "ok" for query in queries
    ):
        raise OSMError("invalid_snapshot_completeness")
    elements = snapshot.get("elements")
    if not isinstance(elements, list):
        raise OSMError("invalid_snapshot_elements")
    identities = set()
    for element in elements:
        if (
            not isinstance(element, dict)
            or element.get("type") not in ("node", "way", "relation")
            or type(element.get("id")) is not int
            or element["id"] <= 0
            or not isinstance(element.get("tags", {}), dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in element.get("tags", {}).items()
            )
        ):
            raise OSMError("invalid_snapshot_elements")
        identity = element["type"], element["id"]
        if identity in identities:
            raise OSMError("duplicate_snapshot_elements")
        identities.add(identity)
    if not elements or not any(query["count"] for query in queries):
        raise OSMError("empty_corpus")
    if referenced_ids != {f"{kind}/{identifier}" for kind, identifier in identities}:
        raise OSMError("invalid_snapshot_counts")
