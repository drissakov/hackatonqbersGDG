"""Synthetic feature replay/HTTP cases and read-only production bundle integrity."""

import copy
import io
import json
import urllib.error

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app.schemas import POIRecord
from ingestion import curated

CHECKED_AT = "2026-10-20T00:00:00Z"


def node(**extra):
    return {
        "type": "node",
        "id": 1,
        "version": 2,
        "timestamp": "2026-10-01T00:00:00Z",
        "lat": 51.1,
        "lon": 71.4,
        "tags": {"leisure": "playground", "access": "yes"},
        **extra,
    }


def way(**extra):
    return {
        **node(),
        "type": "way",
        "nodes": [11, 12, 13, 14, 11],
        "geometry": [
            {"lat": 51.0, "lon": 71.0},
            {"lat": 51.0, "lon": 71.2},
            {"lat": 51.2, "lon": 71.2},
            {"lat": 51.2, "lon": 71.0},
            {"lat": 51.0, "lon": 71.0},
        ],
        **extra,
    }


def bundle(elements=None):
    elements = [node()] if elements is None else elements
    catalog = curated.build_catalog(elements, CHECKED_AT)
    audit = {
        "format_version": curated.AUDIT_FORMAT,
        "checked_at": CHECKED_AT,
        "rights": {
            "attribution": "© OpenStreetMap contributors",
            "license": "ODbL-1.0",
            "license_url": curated.LICENSE_URL,
            "rights_basis_url": curated.COPYRIGHT_URL,
            "storage_allowed": True,
            "indexing_allowed": True,
        },
        "elements": elements,
        "elements_sha256": curated.digest_elements(elements),
    }
    return catalog, audit


def save(directory, catalog, audit):
    directory.mkdir(exist_ok=True)
    (directory / "poi-features.json").write_bytes(curated.json_bytes(catalog))
    (directory / "source-audit.json").write_bytes(curated.json_bytes(audit))


def test_production_catalog_matches_sources_and_both_poi_validators():
    catalog = json.loads((curated.DATA_DIR / "poi-features.json").read_text("utf-8"))
    audit = json.loads((curated.DATA_DIR / "source-audit.json").read_text("utf-8"))
    assert curated.validate_bundle(catalog, audit) == {
        "status": "ok",
        "records": 22,
        "public_access_known": 11,
        "physical_verification": "not_run",
        "database_write": "not_run",
    }
    schema = json.loads((curated.ROOT / "contracts/poi.schema.json").read_text("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for record in catalog["records"]:
        poi = record["poi"]
        POIRecord.model_validate(poi)
        validator.validate(poi)
        assert not poi["is_test"] and record["name_is_derived"]
        assert poi["name"].startswith("Unnamed playground (OSM ")
        assert "name" not in poi["provenance"][0]["fields"]
        assert poi["description"] is None
        assert all(e["observed_at"] is None for e in record["evidence"])
        assert {e["field"] for e in record["evidence"]} <= {"family_playground", "public_access"}
    assert all("user" not in element and "uid" not in element for element in audit["elements"])


def test_unknown_access_and_age_are_never_derived():
    catalog, audit = bundle([node(tags={"leisure": "playground", "min_age": "6"})])
    assert curated.validate_bundle(catalog, audit)["public_access_known"] == 0
    assert [e["field"] for e in catalog["records"][0]["evidence"]] == ["family_playground"]
    assert catalog["records"][0]["poi"]["indoor"] is None


def test_charging_audit_records_zero_qualified_cafes_without_negative_outlet_facts():
    audit = json.loads((curated.DATA_DIR / "source-audit.json").read_text("utf-8"))
    review = audit["charging_evidence_review"]
    assert review["qualified_cafe_count"] == 0
    assert review["complete_osm_query"]["count"]["total"] == "0"
    assert review["complete_osm_query"]["remark"] is None
    assert review["rights_basis_url"] == curated.COPYRIGHT_URL
    assert "not proof" in " ".join(review["limitations"])
    assert not any(
        "power_supply" in element["tags"] or "service:electricity" in element["tags"]
        for element in audit["elements"]
    )


@pytest.mark.parametrize(
    "value,expected", [("yes", True), ("public", True), ("no", False), ("private", False)]
)
def test_exact_access_values(value, expected):
    catalog, _ = bundle([node(tags={"leisure": "playground", "access": value})])
    assert catalog["records"][0]["evidence"][1]["value"] is expected


def test_source_names_and_only_explicit_indoor_hours_are_preserved():
    catalog, audit = bundle(
        [
            node(
                tags={
                    "leisure": "playground",
                    "name": "SYNTHETIC playground",
                    "opening_hours": "24/7",
                    "indoor": "yes",
                    "addr:full": "SYNTHETIC address",
                }
            )
        ]
    )
    record = catalog["records"][0]
    assert record["name_is_derived"] is False
    assert record["poi"]["name"] == "SYNTHETIC playground"
    assert record["poi"]["indoor"] is True
    assert record["poi"]["provenance"][0]["fields"] == [
        "location",
        "activity_code",
        "name",
        "address",
        "opening_hours_text",
        "indoor",
    ]
    curated.validate_bundle(catalog, audit)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["records"][0]["evidence"][0].update(value=1),
        lambda c: c["records"][0]["evidence"][0].update(source_value="park"),
        lambda c: c["records"][0]["evidence"][0].update(source_version=3),
        lambda c: c["records"][0]["evidence"][0].update(observed_at=CHECKED_AT),
        lambda c: c["records"][0]["evidence"][0].update(checked_at="2026-10-21T00:00:00Z"),
        lambda c: c["records"][0]["poi"].update(price_kzt_per_person=0),
        lambda c: c["records"][0]["poi"]["provenance"][0]["fields"].append("name"),
        lambda c: c["records"][0]["poi"]["location"].update(latitude=51.2),
        lambda c: c["records"][0].update(name_is_derived=False),
        lambda c: c["records"][0]["poi"]["sources"][0].update(storage_allowed=False),
    ],
)
def test_fabricated_feature_metadata_and_canonical_facts_are_rejected(mutation):
    catalog, audit = bundle()
    mutation(catalog)
    with pytest.raises(curated.CuratedError, match="source_catalog_mismatch"):
        curated.validate_bundle(catalog, audit)


def test_modified_source_requires_matching_checksum_and_rebuilt_catalog():
    catalog, audit = bundle()
    audit["elements"][0]["tags"]["access"] = "private"
    with pytest.raises(curated.CuratedError, match="source_checksum_mismatch"):
        curated.validate_bundle(catalog, audit)
    audit["elements_sha256"] = curated.digest_elements(audit["elements"])
    with pytest.raises(curated.CuratedError, match="source_catalog_mismatch"):
        curated.validate_bundle(catalog, audit)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a["rights"].update(storage_allowed=False),
        lambda a: a["rights"].update(storage_allowed=1),
        lambda a: a["rights"].update(license="unknown"),
        lambda a: a["rights"].update(rights_basis_url="https://example.invalid"),
    ],
)
def test_rights_cannot_be_weakened(mutation):
    catalog, audit = bundle()
    mutation(audit)
    with pytest.raises(curated.CuratedError, match="invalid_source_rights"):
        curated.validate_bundle(catalog, audit)


@pytest.mark.parametrize(
    "element,code",
    [
        (node(version=True), "invalid_source_version"),
        (node(timestamp="2026-10-21T00:00:00Z"), "invalid_source_version"),
        (node(timestamp="2026-10-01T00:00:00"), "invalid_timestamp"),
        (node(tags={"leisure": "park"}), "source_is_not_playground"),
        (node(tags={"leisure": "playground", "amenity": "childcare"}), "institutional_playground"),
        (node(tags={"leisure": "playground", "disused:leisure": "playground"}), "inactive_source"),
        (node(lat=True), "invalid_geometry"),
        (way(nodes=[11]), "incomplete_geometry"),
    ],
)
def test_invalid_or_institutional_source_is_not_silently_promoted(element, code):
    with pytest.raises(curated.CuratedError, match=code):
        curated.build_catalog([element], CHECKED_AT)


def test_duplicate_ids_and_excessive_counts_are_rejected():
    with pytest.raises(curated.CuratedError, match="duplicate_source_identity"):
        curated.build_catalog([node(), node()], CHECKED_AT)
    with pytest.raises(curated.CuratedError, match="invalid_record_count"):
        curated.build_catalog([], CHECKED_AT)


def test_concave_polygon_gets_an_interior_point_not_the_bounding_box_centre():
    geometry = [
        {"lat": y, "lon": x}
        for y, x in [
            (51.0, 71.0),
            (51.0, 71.4),
            (51.1, 71.4),
            (51.1, 71.1),
            (51.4, 71.1),
            (51.4, 71.0),
            (51.0, 71.0),
        ]
    ]
    element = way(nodes=[1, 2, 3, 4, 5, 6, 1], geometry=geometry)
    lat, lon = curated.representative_point(element)
    ring = [(p["lat"], p["lon"]) for p in geometry]
    assert not curated._inside(51.2, 71.2, ring)
    assert curated._inside(lat, lon, ring)
    catalog, audit = bundle([element])
    assert catalog["records"][0]["coordinate_precision"] == "area_representative"
    curated.validate_bundle(catalog, audit)


def test_boundary_clipping_prevents_outside_city_candidates():
    catalog, audit = bundle()
    audit["selection"] = {
        "candidate_boundary": {
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [[[[70, 50], [70.1, 50], [70.1, 50.1], [70, 50.1], [70, 50]]]],
            }
        }
    }
    with pytest.raises(curated.CuratedError, match="outside_astana_boundary"):
        curated.validate_bundle(catalog, audit)


def test_refresh_joins_complete_source_nodes_and_omits_contributor_metadata(monkeypatch):
    source_way = way()
    source_way.pop("geometry")
    source_way.update(user="SYNTHETIC contributor", uid=1)
    source_nodes = [
        node(id=identifier, lat=point["lat"], lon=point["lon"], user="SYNTHETIC contributor", uid=1)
        for identifier, point in zip(way()["nodes"][:-1], way()["geometry"][:-1], strict=True)
    ]
    calls = []

    def fetch(path):
        calls.append(path)
        return {
            "elements": copy.deepcopy([source_way] if path.startswith("ways") else source_nodes)
        }

    monkeypatch.setattr(curated, "_fetch", fetch)
    elements, urls = curated.refresh_elements([way()])
    assert len(calls) == 2 and all(url.startswith(curated.API_ROOT) for url in urls)
    assert elements[0]["geometry"] == way()["geometry"]
    assert "user" not in elements[0] and "uid" not in elements[0]
    curated.build_catalog(elements, CHECKED_AT)


def test_missing_geometry_node_fails_closed(monkeypatch):
    monkeypatch.setattr(
        curated, "_fetch", lambda path: {"elements": [way()] if path.startswith("ways") else []}
    )
    with pytest.raises(curated.CuratedError, match="incomplete_source_response"):
        curated.refresh_elements([way()])


def test_duplicate_api_records_are_not_accepted_as_complete(monkeypatch):
    monkeypatch.setattr(curated, "_fetch", lambda _: {"elements": [node(), node()]})
    with pytest.raises(curated.CuratedError, match="incomplete_source_response"):
        curated.refresh_elements([node()])


def test_fetch_uses_timeout_and_limit_and_closes_response(monkeypatch):
    class Response:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.closed = True

        def read(self, limit):
            assert limit == curated.MAX_BYTES + 1
            return b'{"elements": []}'

    response = Response()

    def urlopen(request, timeout):
        assert request.full_url.startswith(curated.API_ROOT)
        assert timeout == 25
        return response

    monkeypatch.setattr(curated.urllib.request, "urlopen", urlopen)
    assert curated._fetch("nodes.json?nodes=1") == {"elements": []}
    assert response.closed


def test_refresh_failure_does_not_change_saved_bundle(tmp_path, monkeypatch, capsys):
    catalog, audit = bundle()
    save(tmp_path, catalog, audit)
    before = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}

    def fail(_, **kwargs):
        raise urllib.error.URLError("SYNTHETIC PRIVATE PROVIDER ERROR")

    monkeypatch.setattr(curated.urllib.request, "urlopen", fail)
    assert curated.main(["refresh", "--data-dir", str(tmp_path)]) == 1
    assert {p.name: p.read_bytes() for p in tmp_path.glob("*.json")} == before
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "error_code": "source_unavailable",
    }


def test_provider_http_error_is_closed_without_disclosing_body(monkeypatch):
    body = io.BytesIO(b"SYNTHETIC PRIVATE PROVIDER ERROR")
    error = urllib.error.HTTPError(curated.API_ROOT, 503, "unavailable", {}, body)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(curated.urllib.request, "urlopen", fail)
    with pytest.raises(curated.CuratedError, match="^source_unavailable$"):
        curated._fetch("nodes.json?nodes=1")
    assert body.closed


def test_concurrent_refresh_fails_before_acquisition(tmp_path, monkeypatch, capsys):
    save(tmp_path, *bundle())
    monkeypatch.setattr(curated, "_fetch", lambda _: pytest.fail("locked refresh must not fetch"))
    with curated.data_lock(tmp_path):
        assert curated.main(["refresh", "--data-dir", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "error_code": "refresh_already_running",
    }


def test_validate_cli_has_no_network_or_database_dependency(monkeypatch, capsys):
    monkeypatch.setattr(curated, "_fetch", lambda _: pytest.fail("validate must be offline"))
    assert curated.main(["validate"]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 22


def test_corrupt_bundle_cli_has_safe_error(tmp_path, capsys):
    (tmp_path / "poi-features.json").write_text("SYNTHETIC malformed JSON", "utf-8")
    assert curated.main(["validate", "--data-dir", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "failed",
        "error_code": "invalid_bundle",
    }
