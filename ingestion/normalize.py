"""Normalize permitted OSM objects without inventing facts or merging branches.

The shared POI contract deliberately has no multilingual or derived-fact fields.
Those details are returned in a mandatory metadata sidecar, keyed by canonical ID.
OSM edit timestamps describe the source version, never fact verification.
"""

import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from pydantic import ValidationError

from backend.app.schemas import POIRecord
from ingestion.categories import category_for
from ingestion.osm import contains

OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
NAME_LOCALE = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")
ALIAS_TAGS = ("alt_name", "int_name", "official_name", "short_name", "loc_name", "old_name")
FACT_TAGS = (
    "amenity",
    "tourism",
    "leisure",
    "shop",
    "sport",
    "historic",
    "cuisine",
    "opening_hours",
    "indoor",
    "wheelchair",
    "internet_access",
    "fee",
    "charge",
    "brand",
    "operator",
    "addr:full",
    "addr:street",
    "addr:housenumber",
    "addr:place",
    "addr:city",
    "addr:postcode",
)
SUMMARY_TAGS = ("amenity", "tourism", "leisure", "shop", "sport", "historic", "cuisine")


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > 4000 or "\x00" in value:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _coordinates(element: Mapping) -> tuple[float, float] | None:
    source = element if element.get("type") == "node" else element.get("center")
    if not isinstance(source, Mapping):
        return None
    lat, lon = source.get("lat"), source.get("lon")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) for v in (lat, lon)):
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def _names(tags: dict[str, str]) -> tuple[str | None, str | None, dict, dict, list]:
    fields = {key: value for key, value in tags.items() if key.startswith("name:")}
    localized = {
        key.removeprefix("name:"): value
        for key, value in sorted(fields.items())
        if NAME_LOCALE.fullmatch(key.removeprefix("name:"))
    }
    chosen_tag = next(
        (key for key in ("name", "name:kk", "name:ru", "name:en") if key in tags), None
    )
    if chosen_tag is None and localized:
        chosen_tag = f"name:{next(iter(localized))}"
    name = tags.get(chosen_tag) if chosen_tag else None
    aliases_by_tag = {
        key: list(dict.fromkeys(value for part in tags[key].split(";") if (value := _text(part))))
        for key in ALIAS_TAGS
        if key in tags
    }
    aliases = list(
        dict.fromkeys(
            value
            for value in [*localized.values(), *(v for vs in aliases_by_tag.values() for v in vs)]
            if value != name
        )
    )
    return name, chosen_tag, fields, aliases_by_tag, aliases


def _address(tags: dict[str, str]) -> tuple[str | None, list[str]]:
    if "addr:full" in tags:
        return tags["addr:full"], ["addr:full"]
    street_tag = "addr:street" if "addr:street" in tags else "addr:place"
    if street_tag not in tags:
        return None, []
    keys = [key for key in (street_tag, "addr:housenumber", "addr:city") if key in tags]
    street = " ".join(tags[key] for key in keys if key != "addr:city")
    value = f"{street}, {tags['addr:city']}" if "addr:city" in tags else street
    return _text(value), keys


def _description(tags: dict[str, str]) -> tuple[str | None, list[str]]:
    parts, keys = [], []
    for key in SUMMARY_TAGS:
        if key in tags and len("; ".join([*parts, f"{key}={tags[key]}"])) <= 1000:
            parts.append(f"{key}={tags[key]}")
            keys.append(key)
    return ("Derived summary from OSM tags: " + "; ".join(parts), keys) if parts else (None, [])


def _normalize_one(element: object, fetched_at: str, boundary: dict) -> tuple:
    if not isinstance(element, Mapping):
        return None, None, "invalid_element"
    osm_type, osm_id = element.get("type"), element.get("id")
    if osm_type not in ("node", "way", "relation") or type(osm_id) is not int or osm_id <= 0:
        return None, None, "invalid_identity"
    raw_tags = element.get("tags", {})
    if not isinstance(raw_tags, Mapping):
        return None, None, "invalid_tags"
    tags = {
        key: value
        for key, raw_value in raw_tags.items()
        if isinstance(key, str) and _text(key) == key and (value := _text(raw_value)) is not None
    }
    category = category_for(tags)
    if category is None:
        return None, None, "unsupported_category"
    name, name_tag, name_fields, aliases_by_tag, aliases = _names(tags)
    if name is None:
        return None, None, "missing_name"
    coordinates = _coordinates(element)
    if coordinates is None:
        return None, None, "missing_or_invalid_coordinates"
    lat, lon = coordinates
    if not contains(boundary, lon, lat):
        return None, None, "outside_boundary"
    identifier, external_id = f"osm:{osm_type}:{osm_id}", f"{osm_type}/{osm_id}"
    address, address_tags = _address(tags)
    description, description_tags = _description(tags)
    indoor = {"yes": True, "no": False}.get(tags.get("indoor"))
    fields = ["name", "location", "activity_code"]
    fields.extend(
        field
        for field, value in (
            ("address", address),
            ("indoor", indoor),
            ("opening_hours_text", tags.get("opening_hours")),
        )
        if value is not None
    )
    row = {
        "id": identifier,
        "primary_source_id": identifier,
        "external_id": external_id,
        "name": name,
        "description": description,
        "location": {"latitude": lat, "longitude": lon},
        "address": address,
        "activity_code": category,
        "indoor": indoor,
        "price_kzt_per_person": None,
        "visit_minutes_estimate": None,
        "opening_hours_text": tags.get("opening_hours"),
        "sources": [
            {
                "source_id": identifier,
                "provider": "osm",
                "url": f"https://www.openstreetmap.org/{external_id}",
                "retrieved_at": fetched_at,
                "license": "Open Database License (ODbL) 1.0",
                "rights_basis_url": OSM_COPYRIGHT_URL,
                "storage_allowed": True,
                "indexing_allowed": True,
                "is_test": False,
            }
        ],
        "provenance": [
            {
                "source_id": identifier,
                "external_id": external_id,
                "fields": fields,
                "observed_at": None,
            }
        ],
        "is_test": False,
    }
    try:
        row = POIRecord.model_validate(row).model_dump(mode="json")
    except (ValidationError, ValueError):
        return None, None, "invalid_canonical_record"
    version = element.get("version")
    metadata = {
        "source_id": identifier,
        "url": row["sources"][0]["url"],
        "fetched_at": fetched_at,
        "verified_at": None,
        "source_updated_at": _timestamp(element.get("timestamp")),
        "source_version": version if type(version) is int and version > 0 else None,
        "name_source_tag": name_tag,
        "names": {locale: tags.get(f"name:{locale}") for locale in ("kk", "ru", "en")},
        "name_fields": dict(sorted(name_fields.items())),
        "aliases": aliases,
        "aliases_by_tag": aliases_by_tag,
        "alias_language_inferred": False,
        "coordinates": {
            "source": "node_coordinates" if osm_type == "node" else "overpass_center",
            "approximate": osm_type != "node",
            "verified_at": None,
        },
        "facts": {
            key: {
                "value": tags[key],
                "source_id": identifier,
                "source_tag": key,
                "observed_at": None,
                "verified_at": None,
            }
            for key in FACT_TAGS
            if key in tags
        },
        "derived_fields": {
            "description": {"derived": True, "source_tags": description_tags},
            "address": {
                "derived": bool(address and address_tags != ["addr:full"]),
                "source_tags": address_tags,
            },
        },
        "unknown": {
            "hours_at_visit": None,
            "price_kzt_per_person": None,
            "quiet": None,
            "sockets": None,
            "accessibility": None,
            "visit_minutes": None,
        },
    }
    return row, metadata, None


def normalize_elements(
    elements: Iterable[object], *, fetched_at: str, boundary: dict
) -> tuple[list[dict], dict]:
    """Return canonical records and metadata; invalid objects yield safe counters.

    Repeated type/ID objects collapse deterministically to their newest valid
    version, then source edit time, then normalized content. Different OSM IDs
    always remain separate, including same-name branches at the same point.
    """
    fetched_at = _timestamp(fetched_at)
    if fetched_at is None:
        raise ValueError("fetched_at must be an aware ISO 8601 timestamp")
    selected, ranks, rejections = {}, {}, Counter()
    seen = duplicate_count = 0
    for element in elements:
        seen += 1
        row, details, error = _normalize_one(element, fetched_at, boundary)
        if error:
            rejections[error] += 1
            continue
        identifier = row["id"]
        rank = (
            details["source_version"] or 0,
            datetime.fromisoformat(details["source_updated_at"])
            if details["source_updated_at"]
            else datetime.min.replace(tzinfo=UTC),
            json.dumps([row, details], ensure_ascii=False, sort_keys=True),
        )
        if identifier in selected:
            duplicate_count += 1
        if identifier not in selected or rank > ranks[identifier]:
            selected[identifier], ranks[identifier] = (row, details), rank
    ordered = [selected[key] for key in sorted(selected)]
    return [row for row, _ in ordered], {
        "records": {row["id"]: details for row, details in ordered},
        "stats": {
            "input_elements": seen,
            "normalized_records": len(ordered),
            "duplicate_elements_collapsed": duplicate_count,
            "rejected_elements": sum(rejections.values()),
            "rejected_by_reason": dict(sorted(rejections.items())),
            "by_activity": dict(
                sorted(Counter(row["activity_code"] for row, _ in ordered).items())
            ),
            "approximate_centers": sum(
                details["coordinates"]["approximate"] for _, details in ordered
            ),
        },
    }
