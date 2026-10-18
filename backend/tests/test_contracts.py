"""Validate wire examples and invariants that JSON Schema cannot express."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from backend.app.schemas import (
    EventCard,
    EventSession,
    POIRecord,
    RecommendationRequest,
    RecommendationResponse,
    Source,
    UpsertResult,
)
from scripts.export_contracts import MODELS, artifacts

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
EXAMPLES = CONTRACTS / "examples"
MANIFEST = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))


def fixture(name):
    return json.loads((EXAMPLES / f"{name}.test.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", MANIFEST, ids=[row["file"] for row in MANIFEST])
def test_examples_validate_against_schema_and_python(entry):
    schema = json.loads((CONTRACTS / entry["schema"]).read_text(encoding="utf-8"))
    data = (EXAMPLES / entry["file"]).read_text(encoding="utf-8")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(json.loads(data))
    MODELS[entry["schema"].removesuffix(".schema.json")].model_validate_json(data)


def test_contract_artifacts_have_no_drift():
    for name, expected in artifacts().items():
        assert json.loads((CONTRACTS / name).read_text(encoding="utf-8")) == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("locale", "fr"),
        ("query", "   "),
        ("available_minutes", 0),
        ("available_minutes", True),
        ("budget_kzt_per_person", -1),
        ("indoor_only", "false"),
        ("origin", {"latitude": 91, "longitude": 71}),
        ("origin", {"latitude": float("nan"), "longitude": 71}),
        ("date_time", "2030-01-15T12:00:00"),
        ("unexpected", "not allowed"),
        ("explicit_fields", ["origin", "origin"]),
    ],
)
def test_invalid_request_values_are_rejected(field, value):
    data = fixture("recommendation-request-en")
    data[field] = value
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(data)


def test_null_budget_is_unknown_and_zero_is_free_only():
    for value in (None, 0):
        data = fixture("recommendation-request-en")
        data["budget_kzt_per_person"] = value
        assert RecommendationRequest.model_validate(data).budget_kzt_per_person == value


def test_explicit_fields_must_actually_be_sent():
    with pytest.raises(ValidationError):
        RecommendationRequest(query="Test only", explicit_fields=["origin"])


def test_missing_request_id_is_generated_and_default_locale_is_kk():
    first = RecommendationRequest(query="Test only")
    second = RecommendationRequest(query="Test only")
    assert first.request_id != second.request_id
    assert first.locale == "kk"


@pytest.mark.parametrize("status", ["unknown", "unavailable", "no_match"])
def test_empty_statuses_cannot_contain_cards(status):
    data = fixture("recommendation-partial")
    data["status"] = status
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_unknown_fit_cannot_be_reported_as_ok():
    data = fixture("recommendation-partial")
    data["status"] = "ok"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_at_most_three_alternatives():
    data = fixture("recommendation-partial")
    data["items"] *= 4
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_unknown_route_cannot_invent_a_duration():
    data = fixture("recommendation-partial")
    data["items"][0]["route_status"] = "unknown"
    with pytest.raises(ValidationError):
        RecommendationResponse.model_validate(data)


def test_zero_travel_is_valid_when_origin_is_at_destination():
    data = fixture("recommendation-ok")
    data["items"][0]["travel_minutes_estimate"] = 0
    assert RecommendationResponse.model_validate(data).items[0].travel_minutes_estimate == 0


def test_duplicate_alternatives_and_known_violations_are_rejected():
    for mode in ("duplicate", "does_not_fit"):
        data = fixture("recommendation-partial")
        if mode == "duplicate":
            data["items"] *= 2
        else:
            data["items"][0]["fit_status"] = "does_not_fit"
        with pytest.raises(ValidationError):
            RecommendationResponse.model_validate(data)


def test_unknown_observation_time_is_not_replaced_by_retrieval_time():
    data = fixture("poi")
    data["provenance"][0]["observed_at"] = None
    assert POIRecord.model_validate(data).provenance[0].observed_at is None


def test_cancelled_session_is_not_a_recommendation():
    from backend.app.schemas import EventSearchResponse

    data = fixture("event-search-response")
    data["items"][0]["session"]["status"] = "cancelled"
    with pytest.raises(ValidationError):
        EventSearchResponse.model_validate(data)


def test_envelope_cannot_drop_or_change_cited_sources():
    for sources in (
        [],
        [{**fixture("poi")["sources"][0], "url": "https://example.invalid/changed"}],
    ):
        data = fixture("recommendation-partial")
        data["sources"] = sources
        with pytest.raises(ValidationError):
            RecommendationResponse.model_validate(data)


def test_unlicensed_and_twogis_persistent_records_are_rejected():
    for change in (
        {"storage_allowed": False, "indexing_allowed": False},
        {"provider": "twogis"},
        {"license": None},
        {"rights_basis_url": None},
    ):
        data = fixture("poi")
        data["sources"][0].update(change)
        with pytest.raises(ValidationError):
            POIRecord.model_validate(data)


def test_ephemeral_twogis_source_is_allowed_without_storage_rights():
    data = fixture("poi")["sources"][0]
    data.update(
        provider="twogis",
        storage_allowed=False,
        indexing_allowed=False,
        license=None,
        rights_basis_url=None,
    )
    assert not Source.model_validate(data).storage_allowed


def test_fixtures_cannot_be_mislabeled_as_real_records():
    data = fixture("poi")
    data["is_test"] = False
    with pytest.raises(ValidationError):
        POIRecord.model_validate(data)


def test_provenance_must_reference_an_included_source():
    data = fixture("poi")
    data["provenance"][0]["source_id"] = "unknown-source"
    with pytest.raises(ValidationError):
        POIRecord.model_validate(data)


def test_event_session_time_and_parent_are_checked():
    data = fixture("event-session")
    data["ends_at"] = data["starts_at"]
    with pytest.raises(ValidationError):
        EventSession.model_validate(data)
    card = fixture("event-search-response")["items"][0]
    card["session"]["event_id"] = "wrong-parent"
    with pytest.raises(ValidationError):
        EventCard.model_validate(card)


def test_upsert_counts_and_indexes_are_consistent():
    valid = fixture("upsert-result")
    for data in (
        {**valid, "rejected": 2},
        {**valid, "rejected": 2, "rejections": copy.deepcopy(valid["rejections"]) * 2},
    ):
        with pytest.raises(ValidationError):
            UpsertResult.model_validate(data)
