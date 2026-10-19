"""Entirely synthetic OSM-shaped cases; none is a production city corpus."""

import copy
import json
import unicodedata
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.app.schemas import POIRecord
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


def element(osm_type="node", osm_id=1001, *, tags=None, **extra):
    row = {
        "type": osm_type,
        "id": osm_id,
        "version": 1,
        "timestamp": "2026-01-01T00:00:00Z",
        "tags": {"name": "SYNTHETIC TEST CAFE", "amenity": "cafe"},
    }
    if osm_type == "node":
        row.update(lat=51.0, lon=71.0)
    else:
        row["center"] = {"lat": 51.0, "lon": 71.0}
    if tags:
        row["tags"].update(tags)
    row.update(extra)
    return row


def normalize(rows):
    return normalize_elements(rows, fetched_at=FETCHED_AT, boundary=BOUNDARY)


@pytest.mark.parametrize("osm_type", ["node", "way", "relation"])
def test_stable_typed_ids_and_source_provenance(osm_type):
    rows, metadata = normalize([element(osm_type)])
    row = rows[0]
    identifier = f"osm:{osm_type}:1001"
    assert row["id"] == row["primary_source_id"] == identifier
    assert row["external_id"] == f"{osm_type}/1001"
    assert row["location"] == {"latitude": 51.0, "longitude": 71.0}
    assert row["sources"][0] == {
        "source_id": identifier,
        "provider": "osm",
        "url": f"https://www.openstreetmap.org/{osm_type}/1001",
        "retrieved_at": FETCHED_AT,
        "license": "Open Database License (ODbL) 1.0",
        "rights_basis_url": "https://www.openstreetmap.org/copyright",
        "storage_allowed": True,
        "indexing_allowed": True,
        "is_test": False,
    }
    assert row["provenance"][0]["observed_at"] is None
    details = metadata["records"][identifier]
    assert details["coordinates"]["approximate"] is (osm_type != "node")
    assert details["source_updated_at"] == "2026-01-01T00:00:00Z"
    assert details["verified_at"] is None


def test_kazakh_nfc_names_and_aliases_do_not_imply_translations():
    kazakh_name = "SYNTHETIC Өңірлік Ә Ғ Қ Ң Ө Ұ Ү Һ І"
    rows, metadata = normalize(
        [
            element(
                tags={
                    "name": unicodedata.normalize("NFD", kazakh_name),
                    "name:kk": kazakh_name,
                    "name:ru": "SYNTHETIC Русское имя",
                    "name:de": "SYNTHETIC Deutscher Name",
                    "alt_name": "SYNTHETIC Alias; SYNTHETIC Alias; SYNTHETIC Other",
                    "int_name": "SYNTHETIC Qazaqsha Latin",
                }
            )
        ]
    )
    assert rows[0]["name"] == kazakh_name
    details = metadata["records"][rows[0]["id"]]
    assert details["names"] == {"kk": kazakh_name, "ru": "SYNTHETIC Русское имя", "en": None}
    assert details["name_fields"]["name:de"] == "SYNTHETIC Deutscher Name"
    assert details["aliases_by_tag"]["alt_name"] == ["SYNTHETIC Alias", "SYNTHETIC Other"]
    assert details["aliases_by_tag"]["int_name"] == ["SYNTHETIC Qazaqsha Latin"]
    assert details["alias_language_inferred"] is False
    assert unicodedata.is_normalized("NFC", json.dumps([rows, metadata], ensure_ascii=False))


def test_explicit_localized_name_can_fill_missing_default_name():
    raw = element(tags={"name:kk": "SYNTHETIC Қазақша атау", "int_name": "SYNTHETIC Latin"})
    del raw["tags"]["name"]
    rows, metadata = normalize([raw])
    assert rows[0]["name"] == "SYNTHETIC Қазақша атау"
    assert metadata["records"][rows[0]["id"]]["name_source_tag"] == "name:kk"


def test_alias_or_name_annotation_alone_is_not_an_object_name():
    raw = element()
    raw["tags"] = {"amenity": "cafe", "int_name": "SYNTHETIC Latin", "name:etymology": "SYNTHETIC"}
    rows, metadata = normalize([raw])
    assert rows == []
    assert metadata["stats"]["rejected_by_reason"] == {"missing_name": 1}


def test_repeated_objects_collapse_and_latest_valid_version_wins():
    old = element(version=1)
    new = element(version=2, tags={"name": "SYNTHETIC NEW NAME"})
    invalid_newest = element(version=3, lat=None)
    forward, meta = normalize([old, new, copy.deepcopy(new), invalid_newest])
    reverse, _ = normalize([invalid_newest, new, old, copy.deepcopy(new)])
    assert forward == reverse
    assert len(forward) == 1
    assert forward[0]["name"] == "SYNTHETIC NEW NAME"
    assert meta["stats"]["duplicate_elements_collapsed"] == 2
    assert meta["stats"]["rejected_by_reason"] == {"missing_or_invalid_coordinates": 1}
    assert meta["records"][forward[0]["id"]]["source_version"] == 2


def test_latest_timestamp_and_content_tie_break_are_deterministic():
    first = element(timestamp="2026-01-01T00:00:00Z")
    later = element(timestamp="2026-02-01T05:00:00+05:00", tags={"name": "SYNTHETIC LATER"})
    rows, _ = normalize([later, first])
    assert rows[0]["name"] == "SYNTHETIC LATER"
    conflicting = element(timestamp=later["timestamp"], tags={"name": "SYNTHETIC CONFLICT"})
    assert normalize([later, conflicting]) == normalize([conflicting, later])


def test_fractional_source_edit_time_is_compared_chronologically():
    earlier = element(timestamp="2026-02-01T00:00:00Z")
    later = element(timestamp="2026-02-01T00:00:00.100Z", tags={"name": "SYNTHETIC LATER"})
    rows, _ = normalize([later, earlier])
    assert rows[0]["name"] == "SYNTHETIC LATER"


def test_brand_and_shared_coordinates_do_not_merge_distinct_osm_objects():
    rows, metadata = normalize(
        [
            element("node", 1001, tags={"brand": "SYNTHETIC CHAIN"}),
            element("node", 1002, tags={"brand": "SYNTHETIC CHAIN"}),
            element("way", 1001, tags={"brand": "SYNTHETIC CHAIN"}),
        ]
    )
    assert len(rows) == 3
    assert len({row["external_id"] for row in rows}) == 3
    assert metadata["stats"]["duplicate_elements_collapsed"] == 0


def test_unknowns_stay_unknown_despite_wifi_photo_and_category():
    rows, metadata = normalize(
        [
            element(
                tags={
                    "internet_access": "wlan",
                    "image": "https://example.invalid/synthetic.jpg",
                }
            )
        ]
    )
    row = rows[0]
    assert row["indoor"] is None
    assert row["opening_hours_text"] is None
    assert row["price_kzt_per_person"] is None
    assert row["visit_minutes_estimate"] is None
    details = metadata["records"][row["id"]]
    assert all(value is None for value in details["unknown"].values())
    assert details["facts"]["internet_access"]["value"] == "wlan"
    assert "image" not in details["facts"]
    assert details["derived_fields"]["description"] == {
        "derived": True,
        "source_tags": ["amenity"],
    }
    assert row["description"] == "Derived summary from OSM tags: amenity=cafe"
    assert "description" not in row["provenance"][0]["fields"]


def test_explicit_source_facts_are_preserved_without_claiming_verification():
    rows, metadata = normalize(
        [
            element(
                tags={
                    "opening_hours": "Mo-Fr 10:00-19:00",
                    "indoor": "no",
                    "wheelchair": "yes",
                    "fee": "no",
                    "charge": "1000 KZT",
                    "addr:street": "SYNTHETIC STREET",
                    "addr:housenumber": "10",
                    "addr:city": "SYNTHETIC CITY",
                    "cuisine": "coffee_shop",
                }
            )
        ]
    )
    row = rows[0]
    assert row["opening_hours_text"] == "Mo-Fr 10:00-19:00"
    assert row["indoor"] is False
    assert row["address"] == "SYNTHETIC STREET 10, SYNTHETIC CITY"
    assert row["price_kzt_per_person"] is None
    details = metadata["records"][row["id"]]
    assert details["facts"]["wheelchair"]["value"] == "yes"
    assert all(fact["verified_at"] is None for fact in details["facts"].values())
    assert details["derived_fields"]["address"]["derived"] is True


@pytest.mark.parametrize(
    "raw,reason",
    [
        (None, "invalid_element"),
        ({"type": "node", "id": True}, "invalid_identity"),
        ({"type": "node", "id": "1"}, "invalid_identity"),
        (element(tags=None, center=None, lat=float("nan")), "missing_or_invalid_coordinates"),
        (element(lat=True), "missing_or_invalid_coordinates"),
        (element(lat=100), "missing_or_invalid_coordinates"),
        (element("way", center={"lat": 51}), "missing_or_invalid_coordinates"),
        (element("relation", center=None), "missing_or_invalid_coordinates"),
        (element(tags={"name": "\x00SYNTHETIC"}), "missing_name"),
        (element(lat=49), "outside_boundary"),
    ],
)
def test_invalid_or_missing_fields_have_safe_reasons(raw, reason):
    rows, metadata = normalize([raw])
    assert rows == []
    assert metadata["stats"]["rejected_by_reason"] == {reason: 1}
    assert "SYNTHETIC" not in json.dumps(metadata)


def test_unsupported_category_and_malformed_tags_are_counted():
    bad_tags = element()
    bad_tags["tags"] = []
    unsupported = element()
    unsupported["tags"] = {"name": "SYNTHETIC PRIVATE HOUSE", "building": "house"}
    rows, metadata = normalize([bad_tags, unsupported])
    assert rows == []
    assert metadata["stats"]["rejected_by_reason"] == {
        "invalid_tags": 1,
        "unsupported_category": 1,
    }


def test_invalid_optional_tag_keys_and_values_do_not_escape_to_metadata():
    raw = element()
    raw["tags"].update({None: "SYNTHETIC", "name:\x00": "SYNTHETIC", "name:en": {"bad": "value"}})
    rows, metadata = normalize([raw])
    assert len(rows) == 1
    details = metadata["records"][rows[0]["id"]]
    assert details["name_fields"] == {}
    assert details["names"]["en"] is None


def test_boundary_holes_are_excluded():
    boundary = copy.deepcopy(BOUNDARY)
    boundary["geometry"]["coordinates"][0].append(
        [
            [70.5, 50.5],
            [71.5, 50.5],
            [71.5, 51.5],
            [70.5, 51.5],
            [70.5, 50.5],
        ]
    )
    rows, metadata = normalize_elements([element()], fetched_at=FETCHED_AT, boundary=boundary)
    assert rows == []
    assert metadata["stats"]["rejected_by_reason"] == {"outside_boundary": 1}


@pytest.mark.parametrize("value", ["2026-10-19", "bad", "2026-10-19T00:00:00", None])
def test_fetch_timestamp_must_be_aware(value):
    with pytest.raises(ValueError, match="aware ISO 8601"):
        normalize_elements([], fetched_at=value, boundary=BOUNDARY)


def test_bad_osm_edit_time_stays_unknown():
    rows, metadata = normalize([element(timestamp="2026-01-01")])
    assert metadata["records"][rows[0]["id"]]["source_updated_at"] is None
    assert rows[0]["provenance"][0]["observed_at"] is None


def test_multiple_categories_and_every_row_match_shared_models_and_json_schema():
    museum = element("relation", 1002)
    museum["tags"] = {"name": "SYNTHETIC TEST MUSEUM", "tourism": "museum"}
    park = element("way", 1003)
    park["tags"] = {"name": "SYNTHETIC TEST PARK", "leisure": "park"}
    rows, metadata = normalize([element(), museum, park])
    assert {row["activity_code"] for row in rows} == {"food", "museum", "walk"}
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/poi.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for row in rows:
        assert POIRecord.model_validate(row).id == row["id"]
        validator.validate(row)
        assert set(metadata["records"][row["id"]]["names"]) == {"kk", "ru", "en"}
    assert metadata["stats"]["by_activity"] == {"food": 1, "museum": 1, "walk": 1}
    assert metadata["stats"]["approximate_centers"] == 2
