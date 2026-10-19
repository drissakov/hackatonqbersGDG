"""Shallow corpus QA: python -m ingestion.validate --data-dir data.

JSON Schema validation uses the existing backend development dependencies.
Passing these checks does not verify a place's facts or city completeness.
"""

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from backend.app.schemas import POIRecord
from ingestion.cli import ROOT, atomic_write, data_lock, digest, json_bytes
from ingestion.osm import OSMError, _validate_ring, contains

IDENTITY = re.compile(r"(node|way|relation)/([1-9][0-9]*)")
SCOPE = "structural_and_coordinate_checks_only"


class QualityError(Exception):
    """A safe aggregate code; never include source values in a diagnostic."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _schema_validator():
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        raise QualityError("json_schema_dependency_missing") from None
    schema = json.loads((ROOT / "contracts/poi.schema.json").read_text("utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_boundary(boundary):
    try:
        if (
            not isinstance(boundary, dict)
            or boundary.get("type") != "Feature"
            or boundary["geometry"]["type"] != "MultiPolygon"
        ):
            raise QualityError("invalid_boundary")
        polygons = boundary["geometry"]["coordinates"]
        if not isinstance(polygons, list) or not polygons:
            raise QualityError("invalid_boundary")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise QualityError("invalid_boundary")
            for ring in polygon:
                _validate_ring(ring)
    except (KeyError, TypeError, OSMError, OverflowError):
        raise QualityError("invalid_boundary") from None


def _nfc(value):
    if not isinstance(value, str) or not unicodedata.is_normalized("NFC", value):
        raise QualityError("non_nfc_name")


def _null_verification(value):
    if isinstance(value, dict):
        if "verified_at" in value and value["verified_at"] is not None:
            raise QualityError("unexpected_verified_fact")
        for child in value.values():
            _null_verification(child)
    elif isinstance(value, list):
        for child in value:
            _null_verification(child)


def _validate_sidecar(details, row, osm_type):
    if not isinstance(details, dict) or details.get("source_id") != row.id:
        raise QualityError("invalid_record_sidecar")
    if "verified_at" not in details:
        raise QualityError("invalid_record_sidecar")
    _null_verification(details)
    coordinates = details.get("coordinates")
    if (
        not isinstance(coordinates, dict)
        or coordinates.get("approximate") is not (osm_type != "node")
        or coordinates.get("source")
        != ("node_coordinates" if osm_type == "node" else "overpass_center")
        or "verified_at" not in coordinates
    ):
        raise QualityError("invalid_coordinate_accuracy")
    names, name_fields, aliases = (
        details.get("names"),
        details.get("name_fields"),
        details.get("aliases"),
    )
    aliases_by_tag, facts = details.get("aliases_by_tag"), details.get("facts")
    if (
        not isinstance(names, dict)
        or not {"kk", "ru", "en"}.issubset(names)
        or not isinstance(name_fields, dict)
        or not isinstance(aliases, list)
        or not isinstance(aliases_by_tag, dict)
        or not isinstance(facts, dict)
    ):
        raise QualityError("invalid_record_sidecar")
    for value in names.values():
        if value is not None:
            _nfc(value)
    for key, value in name_fields.items():
        if not isinstance(key, str) or not key.startswith("name:"):
            raise QualityError("invalid_record_sidecar")
        _nfc(value)
    for values in aliases_by_tag.values():
        if not isinstance(values, list):
            raise QualityError("invalid_record_sidecar")
        for value in values:
            _nfc(value)
    for value in aliases:
        _nfc(value)
    for fact in facts.values():
        if not isinstance(fact, dict) or "verified_at" not in fact or "observed_at" not in fact:
            raise QualityError("invalid_record_sidecar")
        if fact["observed_at"] is not None:
            raise QualityError("unexpected_fact_observation")
    if row.description is not None:
        derived_fields = details.get("derived_fields")
        description = (
            derived_fields.get("description") if isinstance(derived_fields, dict) else None
        )
        if not isinstance(description, dict) or description.get("derived") is not True:
            raise QualityError("missing_derived_marker")


def validate_corpus(data_dir: Path) -> dict:
    """Validate an already exported pair, returning counts without source text.

    Callers should hold data_lock while reading and publishing a quality report.
    Repeated names/points across distinct OSM IDs are counted, never merged.
    """
    schema_validator = _schema_validator()
    manifest = json.loads((data_dir / "normalized/manifest.json").read_text("utf-8"))
    payload = (data_dir / "normalized/pois.jsonl").read_bytes()
    if not isinstance(manifest, dict) or manifest.get("format") != "qadam-poi-export-v1":
        raise QualityError("invalid_export_manifest")
    contract = json.loads((ROOT / "contracts/codes.json").read_text("utf-8"))["contract_version"]
    if (
        manifest.get("contract_version") != contract
        or manifest.get("provider") != "osm"
        or manifest.get("city") != "astana"
        or manifest.get("sidecar_required") is not True
        or type(manifest.get("complete")) is not bool
    ):
        raise QualityError("invalid_export_manifest")
    sha256 = digest(payload)
    if manifest.get("sha256") != sha256:
        raise QualityError("jsonl_checksum_mismatch")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    if (
        not rows
        or type(manifest.get("records_count")) is not int
        or manifest["records_count"] != len(rows)
    ):
        raise QualityError("record_count_mismatch")
    boundary = manifest.get("boundary")
    _validate_boundary(boundary)
    normalization = manifest.get("normalization")
    sidecar = normalization.get("records") if isinstance(normalization, dict) else None
    if not isinstance(sidecar, dict):
        raise QualityError("missing_metadata_sidecar")
    seen, by_category, by_type, names_points, samples = set(), Counter(), Counter(), Counter(), {}
    latitudes, longitudes = [], []
    approximate_centers = 0
    for raw in rows:
        try:
            row = POIRecord.model_validate(raw)
        except (ValidationError, ValueError):
            raise QualityError("invalid_canonical_record") from None
        if next(schema_validator.iter_errors(raw), None) is not None:
            raise QualityError("invalid_json_schema_record")
        identity = IDENTITY.fullmatch(row.external_id)
        if identity is None:
            raise QualityError("invalid_osm_identity")
        osm_type, osm_id = identity.groups()
        expected_id = f"osm:{osm_type}:{osm_id}"
        if row.id != expected_id or row.primary_source_id != expected_id:
            raise QualityError("invalid_osm_identity")
        if row.external_id in seen:
            raise QualityError("duplicate_osm_identity")
        seen.add(row.external_id)
        if (
            row.is_test
            or len(row.sources) != 1
            or str(row.sources[0].url) != f"https://www.openstreetmap.org/{row.external_id}"
            or any(source.provider != "osm" or source.is_test for source in row.sources)
            or any(fact.observed_at is not None for fact in row.provenance)
        ):
            raise QualityError("invalid_osm_provenance")
        if row.location is None:
            raise QualityError("missing_coordinates")
        lat, lon = row.location.latitude, row.location.longitude
        if not contains(boundary, lon, lat):
            raise QualityError("representative_point_outside_boundary")
        _nfc(row.name)
        _validate_sidecar(sidecar.get(row.id), row, osm_type)
        by_category[row.activity_code.value] += 1
        by_type[osm_type] += 1
        samples.setdefault(row.activity_code.value, row.id)
        names_points[(row.name.casefold(), round(lat, 6), round(lon, 6))] += 1
        latitudes.append(lat)
        longitudes.append(lon)
        approximate_centers += osm_type != "node"
    if set(sidecar) != {f"osm:{identity.replace('/', ':')}" for identity in seen}:
        raise QualityError("sidecar_identity_mismatch")
    return {
        "format": "qadam-poi-quality-v1",
        "status": "passed",
        "scope": SCOPE,
        "checked_at": datetime.now(UTC).isoformat(),
        "import_id": manifest.get("import_id"),
        "sha256": sha256,
        "records_count": len(rows),
        "source_queries_complete": manifest["complete"],
        "by_category": dict(sorted(by_category.items())),
        "by_osm_type": dict(sorted(by_type.items())),
        "coordinates": {
            "located_records": len(rows),
            "outside_boundary": 0,
            "approximate_centers": approximate_centers,
            "extent": {
                "west": min(longitudes),
                "south": min(latitudes),
                "east": max(longitudes),
                "north": max(latitudes),
            },
        },
        "duplicate_identities": 0,
        "potential_cross_id_duplicate_groups": sum(count > 1 for count in names_points.values()),
        "potential_cross_id_duplicate_records": sum(
            count for count in names_points.values() if count > 1
        ),
        "potential_duplicate_rule": (
            "NFC casefold name and representative coordinates rounded to 6 decimals; never merged"
        ),
        "category_sample_ids": dict(sorted(samples.items())[:7]),
        "validation": {
            "pydantic": "passed",
            "json_schema": "passed",
            "sha256": "passed",
            "sidecar": "passed",
            "nfc": "passed",
        },
        "city_coverage": "unknown",
        "human_verification": {
            "status": "not_run",
            "planned_stages": ["D05", "D06"],
            "sample_size": 0,
        },
    }


def _failure_report(code):
    return {
        "status": "failed",
        "scope": SCOPE,
        "error_code": code,
        "city_coverage": "unknown",
        "human_verification": {"status": "not_run", "sample_size": 0},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    try:
        with data_lock(args.data_dir):
            try:
                report = validate_corpus(args.data_dir)
            except QualityError as error:
                report = _failure_report(error.code)
            except (OSError, ValueError, TypeError, KeyError, IndexError, UnicodeError):
                report = _failure_report("invalid_export_artifacts")
            atomic_write(args.data_dir / "quality-report.json", json_bytes(report))
    except (OSMError, OSError) as error:
        report = _failure_report(
            error.code if isinstance(error, OSMError) else "artifact_write_failed"
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
