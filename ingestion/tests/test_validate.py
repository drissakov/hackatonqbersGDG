"""Synthetic temporary export pairs; no fixture is imported into a city corpus."""

import copy
import hashlib
import json
import unicodedata

import pytest

from ingestion import validate
from ingestion.cli import data_lock
from ingestion.normalize import normalize_elements

FETCHED_AT = "2026-10-19T00:00:00Z"
BOUNDARY = {
    "type": "Feature",
    "properties": {"name": "SYNTHETIC TEST BOUNDARY"},
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[70.0, 50.0], [72.0, 50.0], [72.0, 52.0], [70.0, 52.0], [70.0, 50.0]]]],
    },
}


@pytest.fixture
def corpus(tmp_path):
    elements = [
        {
            "type": "node",
            "id": 1,
            "lat": 51.0,
            "lon": 71.0,
            "tags": {"name": "SYNTHETIC Қазақша Ә Ғ Қ Ң Ө Ұ Ү Һ І", "amenity": "cafe"},
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": 51.1, "lon": 71.1},
            "tags": {"name": "SYNTHETIC PARK", "leisure": "park"},
        },
        {
            "type": "relation",
            "id": 3,
            "center": {"lat": 51.2, "lon": 71.2},
            "tags": {"name": "SYNTHETIC MUSEUM", "tourism": "museum"},
        },
    ]
    rows, metadata = normalize_elements(elements, fetched_at=FETCHED_AT, boundary=BOUNDARY)
    manifest = {
        "format": "qadam-poi-export-v1",
        "contract_version": "1.1.0",
        "import_id": "synthetic-test-import",
        "provider": "osm",
        "city": "astana",
        "complete": True,
        "sidecar_required": True,
        "records_count": len(rows),
        "boundary": copy.deepcopy(BOUNDARY),
        "normalization": metadata,
    }
    save_pair(tmp_path, rows, manifest)
    return tmp_path, rows, manifest


def save_pair(directory, rows, manifest, *, update_checksum=True):
    normalized = directory / "normalized"
    normalized.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    if update_checksum:
        manifest["sha256"] = hashlib.sha256(payload).hexdigest()
    (normalized / "pois.jsonl").write_bytes(payload)
    (normalized / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), "utf-8")


def test_valid_pair_reports_shallow_counts_without_claiming_manual_verification(corpus):
    directory, _, manifest = corpus
    report = validate.validate_corpus(directory)
    assert report["status"] == "passed"
    assert report["scope"] == "structural_and_coordinate_checks_only"
    assert report["records_count"] == 3
    assert report["sha256"] == manifest["sha256"]
    assert report["by_category"] == {"food": 1, "museum": 1, "walk": 1}
    assert report["by_osm_type"] == {"node": 1, "relation": 1, "way": 1}
    assert report["coordinates"] == {
        "located_records": 3,
        "outside_boundary": 0,
        "approximate_centers": 2,
        "extent": {"west": 71.0, "south": 51.0, "east": 71.2, "north": 51.2},
    }
    assert report["city_coverage"] == "unknown"
    assert report["human_verification"]["status"] == "not_run"
    assert report["human_verification"]["sample_size"] == 0
    assert len(report["category_sample_ids"]) == 3
    assert "SYNTHETIC" not in json.dumps(report)


def test_partial_source_queries_can_pass_only_structural_checks(corpus):
    directory, rows, manifest = corpus
    manifest["complete"] = False
    save_pair(directory, rows, manifest)
    report = validate.validate_corpus(directory)
    assert report["status"] == "passed"
    assert report["source_queries_complete"] is False
    assert report["city_coverage"] == "unknown"


def test_exact_cross_id_name_and_rounded_point_duplicates_are_counted_never_merged(corpus):
    directory, rows, manifest = corpus
    rows[1]["name"] = rows[0]["name"].lower()
    rows[1]["location"] = {"latitude": 51.0000001, "longitude": 71.0000001}
    save_pair(directory, rows, manifest)
    report = validate.validate_corpus(directory)
    assert report["records_count"] == 3
    assert report["duplicate_identities"] == 0
    assert report["potential_cross_id_duplicate_groups"] == 1
    assert report["potential_cross_id_duplicate_records"] == 2


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda rows, manifest: manifest.update(sha256="0" * 64), "jsonl_checksum_mismatch"),
        (lambda rows, manifest: manifest.update(records_count=4), "record_count_mismatch"),
        (lambda rows, manifest: manifest.update(records_count=True), "record_count_mismatch"),
        (lambda rows, manifest: manifest.update(sidecar_required=False), "invalid_export_manifest"),
        (lambda rows, manifest: manifest.update(normalization={}), "missing_metadata_sidecar"),
        (
            lambda rows, manifest: rows[0].update(extra="SYNTHETIC PRIVATE PAYLOAD"),
            "invalid_canonical_record",
        ),
        (lambda rows, manifest: rows[0].update(external_id="node/01"), "invalid_osm_identity"),
        (lambda rows, manifest: rows[0].update(id="osm:node:999"), "invalid_osm_identity"),
        (lambda rows, manifest: rows[0].update(location=None), "missing_coordinates"),
        (
            lambda rows, manifest: rows[0]["location"].update(latitude=49.0),
            "representative_point_outside_boundary",
        ),
        (
            lambda rows, manifest: rows[0].update(
                name=unicodedata.normalize("NFD", "SYNTHETIC Өңір Й")
            ),
            "non_nfc_name",
        ),
        (
            lambda rows, manifest: manifest["normalization"]["records"][rows[0]["id"]].update(
                verified_at=FETCHED_AT
            ),
            "unexpected_verified_fact",
        ),
        (
            lambda rows, manifest: manifest["normalization"]["records"][rows[1]["id"]][
                "coordinates"
            ].update(approximate=False),
            "invalid_coordinate_accuracy",
        ),
        (
            lambda rows, manifest: manifest["normalization"]["records"][rows[0]["id"]][
                "names"
            ].update(kk=unicodedata.normalize("NFD", "SYNTHETIC Өңір Й")),
            "non_nfc_name",
        ),
        (
            lambda rows, manifest: manifest["normalization"]["records"][rows[0]["id"]].update(
                derived_fields=[]
            ),
            "missing_derived_marker",
        ),
    ],
)
def test_invalid_export_fields_have_safe_codes(corpus, mutation, code):
    directory, rows, manifest = corpus
    mutation(rows, manifest)
    save_pair(directory, rows, manifest, update_checksum=code != "jsonl_checksum_mismatch")
    with pytest.raises(validate.QualityError, match=f"^{code}$"):
        validate.validate_corpus(directory)


def test_same_osm_identity_is_rejected(corpus):
    directory, rows, manifest = corpus
    rows.append(copy.deepcopy(rows[0]))
    manifest["records_count"] = 4
    save_pair(directory, rows, manifest)
    with pytest.raises(validate.QualityError, match="duplicate_osm_identity"):
        validate.validate_corpus(directory)


def test_extra_or_missing_sidecar_id_is_rejected(corpus):
    directory, rows, manifest = corpus
    manifest["normalization"]["records"]["osm:node:999"] = {}
    save_pair(directory, rows, manifest)
    with pytest.raises(validate.QualityError, match="sidecar_identity_mismatch"):
        validate.validate_corpus(directory)


def test_cli_writes_compact_report_and_failure_has_no_source_payload(corpus, capsys):
    directory, rows, manifest = corpus
    assert validate.main(["--data-dir", str(directory)]) == 0
    report = json.loads((directory / "quality-report.json").read_text("utf-8"))
    assert report["status"] == "passed"
    rows[0]["extra"] = "SYNTHETIC PRIVATE PAYLOAD"
    save_pair(directory, rows, manifest)
    assert validate.main(["--data-dir", str(directory)]) == 1
    report = json.loads((directory / "quality-report.json").read_text("utf-8"))
    assert report["error_code"] == "invalid_canonical_record"
    assert "SYNTHETIC PRIVATE PAYLOAD" not in capsys.readouterr().out
    assert "SYNTHETIC PRIVATE PAYLOAD" not in json.dumps(report)


def test_jsonschema_is_really_checked_and_dependency_failure_is_clear(corpus, monkeypatch):
    directory, _, _ = corpus

    class RejectingSchema:
        def iter_errors(self, value):
            yield object()

    monkeypatch.setattr(validate, "_schema_validator", lambda: RejectingSchema())
    with pytest.raises(validate.QualityError, match="invalid_json_schema_record"):
        validate.validate_corpus(directory)

    def missing():
        raise validate.QualityError("json_schema_dependency_missing")

    monkeypatch.setattr(validate, "_schema_validator", missing)
    assert validate.main(["--data-dir", str(directory)]) == 1
    report = json.loads((directory / "quality-report.json").read_text("utf-8"))
    assert report["error_code"] == "json_schema_dependency_missing"


def test_validation_does_not_replace_report_while_import_holds_lock(corpus):
    directory, _, _ = corpus
    previous = b'{"status":"synthetic-old-report"}\n'
    (directory / "quality-report.json").write_bytes(previous)
    with data_lock(directory):
        assert validate.main(["--data-dir", str(directory)]) == 1
    assert (directory / "quality-report.json").read_bytes() == previous


@pytest.mark.parametrize("content", ["{", "[]", '{"normalization":[]}'])
def test_malformed_manifest_does_not_leak_tracebacks(corpus, content, capsys):
    directory, _, _ = corpus
    (directory / "normalized/manifest.json").write_text(content, "utf-8")
    assert validate.main(["--data-dir", str(directory)]) == 1
    assert json.loads((directory / "quality-report.json").read_text("utf-8"))["status"] == "failed"
    assert "Traceback" not in capsys.readouterr().out
