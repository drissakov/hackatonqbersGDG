"""Synthetic OSM transport and boundary cases; never a real city corpus."""

import copy
import io
import json
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest

from ingestion.categories import CATEGORY_FILTERS, category_for
from ingestion.osm import (
    OSMError,
    OverpassClient,
    _boundary_feature,
    _response_elements,
    contains,
    fetch_astana,
    validate_snapshot,
)

FETCHED_AT = "2026-10-19T00:00:00+00:00"


def counted(elements):
    return {
        "osm3s": {"timestamp_osm_base": FETCHED_AT},
        "elements": elements
        + [
            {
                "type": "count",
                "id": 0,
                "tags": {
                    "nodes": str(sum(element["type"] == "node" for element in elements)),
                    "ways": str(sum(element["type"] == "way" for element in elements)),
                    "relations": str(sum(element["type"] == "relation" for element in elements)),
                    "total": str(len(elements)),
                },
            }
        ],
    }


def member(points, role="outer"):
    return {"type": "way", "role": role, "geometry": [{"lon": x, "lat": y} for x, y in points]}


def relation():
    return {
        "type": "relation",
        "id": 999999001,
        "tags": {
            "boundary": "administrative",
            "admin_level": "4",
            "ISO3166-2": "KZ-71",
            "wikidata": "Q1520",
            "name": "SYNTHETIC TEST BOUNDARY",
        },
        "members": [
            member([[71, 51], [72, 51], [72, 52]]),
            member([[71, 51], [71, 52], [72, 52]]),
            member([[71.4, 51.4], [71.6, 51.4], [71.6, 51.6], [71.4, 51.6], [71.4, 51.4]], "inner"),
            member([[73, 51], [74, 51], [74, 52], [73, 52], [73, 51]]),
            {"type": "node", "role": "admin_centre", "ref": 999999002},
        ],
    }


def node(identifier=999999003):
    return {
        "type": "node",
        "id": identifier,
        "lat": 51.2,
        "lon": 71.2,
        "tags": {"tourism": "museum", "name": "SYNTHETIC TEST ONLY"},
        "timestamp": FETCHED_AT,
    }


class FakeClient:
    query_timeout = 15
    concurrency = 2

    def __init__(self, failed_category=None):
        self.failed_category = failed_category

    def query(self, query):
        assert "out count;" in query
        if "out meta geom" in query:
            assert '"ISO3166-2"="KZ-71"' in query
            return counted([relation()])
        if self.failed_category and any(
            f'["{key}"="{value}"]' in query for key, value in CATEGORY_FILTERS[self.failed_category]
        ):
            raise OSMError("http_rate_limited")
        assert "nwr" in query and "out meta center" in query
        return counted([node()])


def test_stitches_reversed_members_preserves_holes_and_multiple_polygons():
    feature = _boundary_feature(relation(), FETCHED_AT)
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert len(feature["geometry"]["coordinates"]) == 2
    assert contains(feature, 71.2, 51.2)
    assert contains(feature, 73.5, 51.5)
    assert contains(feature, 71, 51.5)
    assert not contains(feature, 71.5, 51.5)
    assert not contains(feature, 71.4, 51.5)
    assert not contains(feature, 72.5, 51.5)
    assert not contains(feature, float("nan"), 51)


@pytest.mark.parametrize("change", ["missing", "unclosed", "nested_relation", "orphan_hole"])
def test_refuses_incomplete_boundary_geometry(change):
    value = relation()
    if change == "missing":
        value["members"][0]["geometry"] = None
    elif change == "unclosed":
        value["members"].pop(1)
    elif change == "nested_relation":
        value["members"][0]["type"] = "relation"
    else:
        value["members"][2] = member([[80, 50], [81, 50], [81, 51], [80, 51], [80, 50]], "inner")
    with pytest.raises(OSMError):
        _boundary_feature(value, FETCHED_AT)


@pytest.mark.parametrize(
    "change", ["no_count", "wrong_count", "remark", "duplicate", "extra_after"]
)
def test_response_requires_matching_final_count_sentinel(change):
    value = counted([node()])
    if change == "no_count":
        value["elements"].pop()
    elif change == "wrong_count":
        value["elements"][-1]["tags"]["total"] = "2"
    elif change == "remark":
        value["remark"] = "SYNTHETIC PRIVATE PROVIDER ERROR"
    elif change == "duplicate":
        value = counted([node(), node()])
    else:
        value["elements"].append(node(999999004))
    with pytest.raises(OSMError, match="incomplete_response"):
        _response_elements(value)


def test_response_accepts_valid_empty_category_but_not_fake_empty_city():
    assert _response_elements(counted([])) == []
    snapshot = fetch_astana(FakeClient())
    snapshot["elements"] = []
    for query in snapshot["queries"]:
        query["count"] = 0
        query["element_ids"] = []
    with pytest.raises(OSMError, match="empty_corpus"):
        validate_snapshot(snapshot)


def test_fetch_discovers_boundary_and_deduplicates_osm_identity():
    snapshot = fetch_astana(FakeClient())
    validate_snapshot(snapshot)
    assert snapshot["complete"] is True
    assert len(snapshot["elements"]) == 1
    assert len(snapshot["queries"]) == len(CATEGORY_FILTERS)
    assert snapshot["boundary"]["properties"]["osm_id"] == 999999001
    assert snapshot["boundary"]["properties"]["source_timestamp"] == FETCHED_AT


def test_partial_query_failure_remains_visible_and_cannot_claim_complete():
    snapshot = fetch_astana(FakeClient(failed_category="food"))
    assert not snapshot["complete"]
    failed = next(query for query in snapshot["queries"] if query["category"] == "food")
    assert failed == {
        "category": "food",
        "status": "failed",
        "count": 0,
        "error_code": "http_rate_limited",
        "element_ids": [],
    }
    validate_snapshot(snapshot)
    snapshot["complete"] = True
    with pytest.raises(OSMError, match="invalid_snapshot_completeness"):
        validate_snapshot(snapshot)


def test_full_outage_preserves_safe_query_outcomes_without_success():
    class UnavailableClient(FakeClient):
        def query(self, query):
            if "out meta geom" in query:
                return counted([relation()])
            raise OSMError("http_rate_limited")

    with pytest.raises(OSMError, match="empty_corpus") as caught:
        fetch_astana(UnavailableClient())
    assert len(caught.value.queries) == len(CATEGORY_FILTERS)
    assert all(query["error_code"] == "http_rate_limited" for query in caught.value.queries)


@pytest.mark.parametrize(
    "change", ["twogis", "license", "rights", "timestamp", "queries", "duplicate"]
)
def test_snapshot_rejects_other_sources_bad_rights_and_invalid_metadata(change):
    snapshot = fetch_astana(FakeClient())
    if change == "twogis":
        snapshot["provider"] = "twogis"
    elif change == "license":
        snapshot["license"] = "unknown"
    elif change == "rights":
        snapshot["rights_basis_url"] = "https://example.invalid"
    elif change == "timestamp":
        snapshot["fetched_at"] = "2026-10-19"
    elif change == "queries":
        snapshot["queries"].pop()
    else:
        snapshot["elements"].append(copy.deepcopy(snapshot["elements"][0]))
    with pytest.raises(OSMError):
        validate_snapshot(snapshot)


def test_category_is_explicit_and_finite():
    assert category_for({"tourism": "museum"}) == "museum"
    assert category_for({"name": "museum cafe", "brand": "Example"}) is None
    assert category_for({"amenity": "cafe", "internet_access": "wlan"}) == "food"
    assert "other" not in CATEGORY_FILTERS


def test_truncated_snapshot_is_rejected_even_with_other_records_remaining():
    snapshot = fetch_astana(FakeClient())
    extra_node = node(999999004)
    snapshot["elements"].append(extra_node)
    snapshot["queries"][0]["count"] += 1
    snapshot["queries"][0]["element_ids"].append("node/999999004")
    validate_snapshot(snapshot)
    snapshot["elements"].pop()
    with pytest.raises(OSMError, match="invalid_snapshot_counts"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize("field", ["category", "element_ids", "count", "status"])
def test_malformed_query_snapshot_raises_safe_diagnostic(field):
    snapshot = fetch_astana(FakeClient())
    snapshot["queries"][0][field] = [["SYNTHETIC INVALID TYPE"]]
    with pytest.raises(OSMError, match="invalid_snapshot_queries"):
        validate_snapshot(snapshot)


def test_provider_timestamp_is_required_to_measure_source_freshness():
    payload = counted([node()])
    payload["osm3s"] = None
    with pytest.raises(OSMError, match="invalid_response_timestamp"):
        _response_elements(payload)


class Response(io.BytesIO):
    pass


def test_client_sends_post_and_obeys_retry_after(monkeypatch):
    calls = []
    sleeps = []

    def urlopen(request, timeout):
        calls.append(request)
        assert request.method == "POST"
        assert timeout == 15
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 429, "private", {"Retry-After": "30"}, None
            )
        return Response(json.dumps(counted([node()])).encode())

    monkeypatch.setattr("ingestion.osm.urllib.request.urlopen", urlopen)
    monkeypatch.setattr("ingestion.osm.time.sleep", sleeps.append)
    payload = OverpassClient(timeout=15, retries=1).query("SYNTHETIC QUERY")
    assert len(payload["elements"]) == 2
    assert len(calls) == 2
    assert sleeps == [30]


def test_forbidden_response_is_never_empty_success_or_raw_error(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "SYNTHETIC SECRET BODY", {}, None)

    monkeypatch.setattr("ingestion.osm.urllib.request.urlopen", urlopen)
    with pytest.raises(OSMError, match="^http_forbidden$"):
        OverpassClient(timeout=15).query("SYNTHETIC QUERY")


def test_retries_have_a_finite_attempt_limit(monkeypatch):
    attempts = []

    def urlopen(request, timeout):
        attempts.append(1)
        raise TimeoutError("SYNTHETIC PRIVATE NETWORK BODY")

    monkeypatch.setattr("ingestion.osm.urllib.request.urlopen", urlopen)
    monkeypatch.setattr("ingestion.osm.time.sleep", lambda delay: None)
    with pytest.raises(OSMError, match="^network_unavailable$"):
        OverpassClient(timeout=15, retries=2).query("SYNTHETIC QUERY")
    assert len(attempts) == 3


def test_concurrency_limit_cannot_be_expanded():
    assert OverpassClient().concurrency == 1
    assert OverpassClient(concurrency=2).concurrency == 2
    with pytest.raises(ValueError):
        OverpassClient(concurrency=3)
    # Both validated clients are safe for the category executor's maximum.
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: OverpassClient().concurrency, range(2))) == [1, 1]
