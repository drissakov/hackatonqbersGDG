"""Replay and refresh a small source-checked OSM feature supplement.

This is a licensed source-record check, never an on-site inspection. It neither
imports records into Postgres nor calls embeddings or commercial providers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import urllib.error
import urllib.request
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

from backend.app.poi_features import FeatureCatalog
from backend.app.schemas import POIRecord
from ingestion.cli import atomic_write, data_lock, json_bytes
from ingestion.osm import OSMError, contains

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "curated"
API_ROOT = "https://api.openstreetmap.org/api/0.6/"
COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
CATALOG_FORMAT = "qadam-poi-features-v1"
AUDIT_FORMAT = "qadam-poi-feature-source-audit-v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 30
SUPPORTED_TAGS = {
    "family_playground": ("leisure", {"playground": True}),
    "public_access": ("access", {"yes": True, "public": True, "no": False, "private": False}),
}


class CuratedError(ValueError):
    """Safe diagnostic codes exclude source content and provider errors."""


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise CuratedError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CuratedError("invalid_timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CuratedError("invalid_timestamp")
    return parsed.astimezone(UTC)


def digest_elements(elements: list[dict]) -> str:
    return hashlib.sha256(json_bytes(elements)).hexdigest()


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _point(value: object) -> tuple[float, float]:
    if not isinstance(value, dict):
        raise CuratedError("invalid_geometry")
    lat, lon = value.get("lat"), value.get("lon")
    if not _number(lat) or not _number(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise CuratedError("invalid_geometry")
    return float(lat), float(lon)


def _inside(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for (y1, x1), (y2, x2) in zip(ring, ring[1:], strict=False):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def representative_point(element: dict) -> tuple[float, float]:
    """Use source node coordinates or a point strictly inside a closed way.

    A scan line avoids placing the representative point outside concave areas.
    The resulting area point is approximate and is not an entrance.
    """
    if element.get("type") == "node":
        return _point(element)
    if element.get("type") != "way":
        raise CuratedError("unsupported_source_type")
    geometry, nodes = element.get("geometry"), element.get("nodes")
    if not isinstance(geometry, list) or not isinstance(nodes, list) or len(geometry) != len(nodes):
        raise CuratedError("incomplete_geometry")
    ring = [_point(point) for point in geometry]
    if len(ring) < 4 or nodes[0] != nodes[-1] or ring[0] != ring[-1]:
        raise CuratedError("unclosed_geometry")
    if any(type(node) is not int or node <= 0 for node in nodes):
        raise CuratedError("invalid_geometry")
    levels = sorted({lat for lat, _ in ring})
    # Midpoints between vertex latitudes never coincide with a polygon vertex.
    for lat in sorted(
        ((a + b) / 2 for a, b in zip(levels, levels[1:], strict=False)),
        key=lambda value: abs(value - (levels[0] + levels[-1]) / 2),
    ):
        intersections = sorted(
            x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            for (y1, x1), (y2, x2) in zip(ring, ring[1:], strict=False)
            if (y1 > lat) != (y2 > lat)
        )
        if len(intersections) % 2:
            raise CuratedError("invalid_geometry")
        spans = list(zip(intersections[::2], intersections[1::2], strict=True))
        for left, right in sorted(spans, key=lambda span: span[1] - span[0], reverse=True):
            lon = (left + right) / 2
            if left < right and _inside(lat, lon, ring):
                return lat, lon
    raise CuratedError("invalid_geometry")


def _source_identity(element: dict) -> tuple[str, str]:
    kind, identifier = element.get("type"), element.get("id")
    if kind not in ("node", "way") or type(identifier) is not int or identifier <= 0:
        raise CuratedError("invalid_source_identity")
    return f"osm:{kind}:{identifier}", f"{kind}/{identifier}"


def _record(element: dict, checked_at: str) -> dict:
    identifier, external_id = _source_identity(element)
    tags = element.get("tags")
    if not isinstance(tags, dict) or tags.get("leisure") != "playground":
        raise CuratedError("source_is_not_playground")
    if any(key.startswith(("disused:", "abandoned:", "construction:")) for key in tags):
        raise CuratedError("inactive_source")
    if tags.get("amenity") in ("school", "kindergarten", "childcare"):
        raise CuratedError("institutional_playground")
    source_updated_at, version = element.get("timestamp"), element.get("version")
    if (
        type(version) is not int
        or version < 1
        or timestamp(source_updated_at) > timestamp(checked_at)
    ):
        raise CuratedError("invalid_source_version")
    lat, lon = representative_point(element)
    name = tags.get("name")
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise CuratedError("invalid_source_name")
    name_is_derived = name is None
    source_fields = ["location", "activity_code"]
    if not name_is_derived:
        source_fields.append("name")
    address = tags.get("addr:full")
    if address is not None:
        source_fields.append("address")
    hours = tags.get("opening_hours")
    if hours is not None:
        source_fields.append("opening_hours_text")
    indoor = {"yes": True, "no": False}.get(tags.get("indoor"))
    if indoor is not None:
        source_fields.append("indoor")
    poi = {
        "id": identifier,
        "primary_source_id": identifier,
        "external_id": external_id,
        "name": name if name is not None else f"Unnamed playground (OSM {external_id})",
        "description": None,
        "location": {"latitude": lat, "longitude": lon},
        "address": address,
        "activity_code": "entertainment",
        "indoor": indoor,
        "price_kzt_per_person": None,
        "visit_minutes_estimate": None,
        "opening_hours_text": hours,
        "sources": [
            {
                "source_id": identifier,
                "provider": "osm",
                "url": f"https://www.openstreetmap.org/{external_id}",
                "retrieved_at": checked_at,
                "license": "Open Database License (ODbL) 1.0",
                "rights_basis_url": COPYRIGHT_URL,
                "storage_allowed": True,
                "indexing_allowed": True,
                "is_test": False,
            }
        ],
        "provenance": [
            {
                "source_id": identifier,
                "external_id": external_id,
                "fields": source_fields,
                "observed_at": None,
            }
        ],
        "is_test": False,
    }
    POIRecord.model_validate(poi)
    evidence = []
    for field, (source_field, values) in SUPPORTED_TAGS.items():
        source_value = tags.get(source_field)
        if not isinstance(source_value, str) or source_value not in values:
            continue
        evidence.append(
            {
                "field": field,
                "value": values[source_value],
                "source_id": identifier,
                "source_field": source_field,
                "source_value": source_value,
                "source_version": version,
                "source_updated_at": source_updated_at,
                "checked_at": checked_at,
                "observed_at": None,
            }
        )
    return {
        "poi": poi,
        "name_is_derived": name_is_derived,
        "coordinate_precision": "node" if element["type"] == "node" else "area_representative",
        "evidence": evidence,
    }


def build_catalog(elements: list[dict], checked_at: str) -> dict:
    timestamp(checked_at)
    if not isinstance(elements, list) or not 1 <= len(elements) <= MAX_RECORDS:
        raise CuratedError("invalid_record_count")
    identities = [_source_identity(element)[0] for element in elements]
    if len(set(identities)) != len(identities):
        raise CuratedError("duplicate_source_identity")
    catalog = {
        "format_version": CATALOG_FORMAT,
        "checked_at": checked_at,
        "records": [_record(element, checked_at) for element in elements],
    }
    FeatureCatalog.model_validate(catalog)
    return catalog


def validate_bundle(catalog: dict, audit: dict) -> dict:
    """Compare every runtime fact with the preserved licensed source snapshot."""
    if (
        audit.get("format_version") != AUDIT_FORMAT
        or catalog.get("format_version") != CATALOG_FORMAT
    ):
        raise CuratedError("invalid_bundle_format")
    elements = audit.get("elements")
    if not isinstance(elements, list) or digest_elements(elements) != audit.get("elements_sha256"):
        raise CuratedError("source_checksum_mismatch")
    rights = audit.get("rights", {})
    expected_rights = {
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
        "license_url": LICENSE_URL,
        "rights_basis_url": COPYRIGHT_URL,
        "storage_allowed": True,
        "indexing_allowed": True,
    }
    if json_bytes(rights) != json_bytes(expected_rights):
        raise CuratedError("invalid_source_rights")
    checked_at = audit.get("checked_at")
    expected = build_catalog(elements, checked_at)
    if json_bytes(catalog) != json_bytes(expected):
        raise CuratedError("source_catalog_mismatch")
    boundary = audit.get("selection", {}).get("candidate_boundary", {})
    if "geometry" in boundary:
        for element in elements:
            lat, lon = representative_point(element)
            if not contains({"geometry": boundary["geometry"]}, lon, lat):
                raise CuratedError("outside_astana_boundary")
    return {
        "status": "ok",
        "records": len(catalog["records"]),
        "public_access_known": sum(
            any(e["field"] == "public_access" and e["value"] for e in record["evidence"])
            for record in catalog["records"]
        ),
        "physical_verification": "not_run",
        "database_write": "not_run",
    }


def _fetch(path: str) -> dict:
    request = urllib.request.Request(
        API_ROOT + path,
        headers={"User-Agent": "QadamAstana-SourceAudit/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise CuratedError("response_too_large")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise CuratedError("invalid_source_response") from None
    except urllib.error.HTTPError as exc:
        exc.close()
        raise CuratedError("source_unavailable") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CuratedError("source_unavailable") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise CuratedError("invalid_source_response")
    return payload


def refresh_elements(existing: list[dict]) -> tuple[list[dict], list[str]]:
    """Refresh only reviewed OSM IDs, with complete node geometry and bounded calls."""
    if not isinstance(existing, list) or not 1 <= len(existing) <= MAX_RECORDS:
        raise CuratedError("invalid_record_count")
    identities = [_source_identity(element) for element in existing]
    way_ids = sorted({str(e["id"]) for e in existing if e["type"] == "way"})
    node_ids = {e["id"] for e in existing if e["type"] == "node"}
    paths, ways = [], []
    if way_ids:
        path = "ways.json?ways=" + ",".join(way_ids)
        paths.append(path)
        ways = _fetch(path)["elements"]
        if (
            len(ways) != len(way_ids)
            or any(e.get("type") != "way" for e in ways)
            or {str(e.get("id")) for e in ways} != set(way_ids)
        ):
            raise CuratedError("incomplete_source_response")
        for way in ways:
            if not isinstance(way.get("nodes"), list) or len(way["nodes"]) > 1000:
                raise CuratedError("invalid_geometry")
            node_ids.update(way["nodes"])
    if any(type(node) is not int or node <= 0 for node in node_ids):
        raise CuratedError("invalid_geometry")
    if len(node_ids) > 2000:
        raise CuratedError("geometry_too_large")
    points = {}
    ordered_nodes = sorted(node_ids)
    for offset in range(0, len(ordered_nodes), 150):
        batch = ordered_nodes[offset : offset + 150]
        path = "nodes.json?nodes=" + ",".join(str(node) for node in batch)
        paths.append(path)
        nodes = _fetch(path)["elements"]
        if (
            len(nodes) != len(batch)
            or any(e.get("type") != "node" for e in nodes)
            or {e.get("id") for e in nodes} != set(batch)
        ):
            raise CuratedError("incomplete_source_response")
        points.update({node["id"]: node for node in nodes})
    by_identity = {}
    for way in ways:
        way["geometry"] = [{"lat": points[n]["lat"], "lon": points[n]["lon"]} for n in way["nodes"]]
        by_identity[_source_identity(way)[0]] = way
    for element in existing:
        if element["type"] == "node":
            node = points[element["id"]]
            by_identity[_source_identity(node)[0]] = node
    # Contributor usernames/UIDs are unrelated to venue facts and are not retained.
    allowed = {
        "type",
        "id",
        "timestamp",
        "version",
        "changeset",
        "tags",
        "nodes",
        "lat",
        "lon",
        "geometry",
    }
    return [
        {key: value for key, value in by_identity[identity].items() if key in allowed}
        for identity, _ in identities
    ], [API_ROOT + path for path in paths]


def _run(args: argparse.Namespace) -> dict:
    lock = data_lock(args.data_dir) if args.command == "refresh" else nullcontext()
    with lock:
        catalog_path = args.data_dir / "poi-features.json"
        audit_path = args.data_dir / "source-audit.json"
        catalog = json.loads(catalog_path.read_text("utf-8"))
        audit = json.loads(audit_path.read_text("utf-8"))
        result = validate_bundle(catalog, audit)
        if args.command == "refresh":
            elements, urls = refresh_elements(audit["elements"])
            checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            refreshed_audit = {
                **audit,
                "checked_at": checked_at,
                "elements": elements,
                "elements_sha256": digest_elements(elements),
                "acquisition_urls": urls,
            }
            refreshed_catalog = build_catalog(elements, checked_at)
            selection = refreshed_audit.get("selection")
            if isinstance(selection, dict) and isinstance(selection.get("counts"), dict):
                public_count = sum(
                    any(e["field"] == "public_access" and e["value"] for e in row["evidence"])
                    for row in refreshed_catalog["records"]
                )
                selection = {
                    **selection,
                    "counts": {
                        **selection["counts"],
                        "selected": len(elements),
                        "selected_public_access_yes": public_count,
                        "selected_public_access_unknown": sum(
                            not any(e["field"] == "public_access" for e in row["evidence"])
                            for row in refreshed_catalog["records"]
                        ),
                    },
                }
                refreshed_audit["selection"] = selection
            result = validate_bundle(refreshed_catalog, refreshed_audit)
            atomic_write(audit_path, json_bytes(refreshed_audit))
            atomic_write(catalog_path, json_bytes(refreshed_catalog))
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "refresh"))
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(_run(args), sort_keys=True))
        return 0
    except OSMError:
        print(json.dumps({"status": "failed", "error_code": "refresh_already_running"}))
        return 1
    except (CuratedError, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        code = str(exc) if type(exc) is CuratedError else "invalid_bundle"
        print(json.dumps({"status": "failed", "error_code": code}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
