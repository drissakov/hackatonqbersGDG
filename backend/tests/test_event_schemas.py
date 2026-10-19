"""Synthetic public transient event contracts, separate from persistent event schemas."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from backend.app.event_schemas import (
    TransientEventSearchResponse,
    TransientEventSource,
    transient_source_id,
)
from backend.app.schemas import EventSearchResponse
from scripts.export_contracts import artifacts


def response_data():
    source = {
        "source_id": "synthetic:source-1",
        "url": "https://example.invalid/synthetic-event",
        "retrieved_at": "2030-01-15T10:00:00+05:00",
        "source_updated_at": None,
        "storage_allowed": False,
        "indexing_allowed": False,
    }
    session = {
        "session_id": "synthetic:session-1",
        "event_id": "synthetic:event-1",
        "source_url": source["url"],
        "source_fetched_at": source["retrieved_at"],
        "city": "Astana",
        "venue_name": "SYNTHETIC TEST ONLY - Fictional venue",
        "venue_address": None,
        "venue": {},
        "starts_at": "2030-01-15T19:00:00+05:00",
        "ends_at": None,
        "price_from": 1000,
        "currency": "KZT",
        "price_conditions": None,
        "price_kind": "starting",
        "status": "scheduled",
        "verification_status": "discovered",
        "verified_fields": [],
        "ticket_availability": "unknown",
        "missing_fields": ["venue_address", "location", "ends_at", "price_conditions"],
        "recommendation_candidate": True,
        "exclusion_reasons": [],
    }
    return {
        "request_id": "00000000-0000-4000-8000-000000000013",
        "contract_version": "1.3.0",
        "status": "partial",
        "provider_status": "partial",
        "provider_code": "unverified_source_facts",
        "live_web_search": "passed",
        "items": [
            {
                "event": {
                    "id": session["event_id"],
                    "title": "SYNTHETIC TEST ONLY - Fictional event",
                    "city": "Astana",
                    "venue_name": session["venue_name"],
                    "venue_address": None,
                    "source_id": source["source_id"],
                },
                "session": session,
                "source_ids": [source["source_id"]],
                "reason_codes": ["schedule_unknown", "route_unknown"],
                "activity_code": "other",
                "visit_minutes_estimate": None,
                "route_status": "unknown",
                "travel_minutes_estimate": None,
                "fit_status": "unknown",
                "missing_fields": [
                    "ends_at",
                    "travel_minutes_estimate",
                    "source_verification",
                    "ticket_availability",
                ],
                "explanation": "Synthetic example only. Check schedule, travel time and tickets.",
                "generated_locale": "en",
                "action": {"code": "open_source", "url": source["url"]},
            }
        ],
        "listings": [],
        "sources": [source],
        "warnings": [
            {"code": "data_unknown", "message": "Synthetic example only; facts are unknown."}
        ],
        "excluded_sessions": 0,
        "rejected_events": 0,
    }


def listing_data():
    data = response_data()
    card = data["items"].pop()
    data["listings"] = [
        {
            "event_id": card["event"]["id"],
            "title": card["event"]["title"],
            "source_url": data["sources"][0]["url"],
            "source_fetched_at": data["sources"][0]["retrieved_at"],
            "city": "Astana",
            "venue_name": None,
            "venue_address": None,
            "venue": {},
            "status": "listing",
            "schedule_hints": ["Synthetic listing only; no session time is known."],
            "missing_fields": ["venue_name", "venue_address", "location", "sessions"],
            "sessions": [],
        }
    ]
    return data


@pytest.mark.parametrize("factory", [response_data, listing_data])
def test_transient_examples_match_pydantic_and_exported_json_schema(factory):
    data = factory()
    schema = artifacts()["transient-event-search-response.schema.json"]
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    result = TransientEventSearchResponse.model_validate(data)
    assert result.contract_version == "1.3.0"
    assert all(
        not source.storage_allowed and not source.indexing_allowed for source in result.sources
    )


def test_runtime_payload_cannot_be_coerced_into_persistent_event_response():
    with pytest.raises(ValidationError):
        EventSearchResponse.model_validate(response_data())


@pytest.mark.parametrize("field", ["storage_allowed", "indexing_allowed"])
@pytest.mark.parametrize("value", [True, 0, "false"])
def test_transient_sources_cannot_grant_persistence_rights(field, value):
    data = response_data()["sources"][0]
    data[field] = value
    with pytest.raises(ValidationError):
        TransientEventSource.model_validate(data)


def test_source_urls_cannot_embed_credentials():
    data = response_data()["sources"][0]
    data["url"] = "https://synthetic-user:synthetic-password@example.invalid/event"
    with pytest.raises(ValidationError):
        TransientEventSource.model_validate(data)


@pytest.mark.parametrize("status", ["no_match", "ok", "unknown", "unavailable"])
def test_discovered_cards_cannot_claim_complete_absence_or_success(status):
    data = response_data()
    data["status"] = status
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize("status", ["unknown", "unavailable"])
def test_provider_states_remain_honest_without_results(status):
    data = response_data()
    data.update(items=[], status=status, provider_status=status, live_web_search="failed")
    result = TransientEventSearchResponse.model_validate(data)
    assert not result.items and not result.listings


@pytest.mark.parametrize(
    "field,value", [("provider_status", "unavailable"), ("live_web_search", "failed")]
)
def test_provider_failure_cannot_become_usable_cards(field, value):
    data = response_data()
    data[field] = value
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize(
    "update",
    [
        {"status": "cancelled"},
        {"starts_at": None},
        {"city": "Almaty"},
        {"recommendation_candidate": False},
        {"exclusion_reasons": ["past_session"]},
        {"event_id": "another-event"},
        {"ends_at": "2030-01-15T18:00:00+05:00"},
    ],
)
def test_ineligible_sessions_cannot_be_recommendation_cards(update):
    data = response_data()
    data["items"][0]["session"].update(update)
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize(
    "field", ["ends_at", "travel_minutes_estimate", "source_verification", "ticket_availability"]
)
def test_critical_unknowns_cannot_be_removed_from_missing_fields(field):
    data = response_data()
    data["items"][0]["missing_fields"].remove(field)
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize("fit", ["fits", "does_not_fit"])
def test_unknown_tickets_never_confirm_a_fit(fit):
    data = response_data()
    data["items"][0]["fit_status"] = fit
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize("reason", ["within_budget", "indoor_match"])
def test_lower_bound_price_and_missing_indoor_do_not_prove_constraints(reason):
    data = response_data()
    data["items"][0]["reason_codes"].append(reason)
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize(
    "mode",
    [
        "missing_source",
        "duplicate_source_id",
        "unknown_card_id",
        "foreign_session_url",
        "foreign_action_url",
        "foreign_venue_url",
    ],
)
def test_source_envelope_references_are_complete_and_unambiguous(mode):
    data = response_data()
    card = data["items"][0]
    if mode == "missing_source":
        data["sources"] = []
    elif mode == "duplicate_source_id":
        data["sources"].append(copy.deepcopy(data["sources"][0]))
    elif mode == "unknown_card_id":
        card["source_ids"].append("missing-source")
    elif mode == "foreign_session_url":
        card["session"]["source_url"] = "https://example.invalid/foreign"
    elif mode == "foreign_action_url":
        card["action"]["url"] = "https://example.invalid/foreign"
    else:
        card["session"]["venue"]["source_urls"] = ["https://example.invalid/foreign"]
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


def test_source_url_can_retain_original_poi_identity_and_transient_identity():
    data = response_data()
    source = data["sources"][0]
    alias = transient_source_id(source["url"])
    assert alias == transient_source_id(source["url"])
    assert alias.startswith("event-source:")
    data["sources"].append({**source, "source_id": alias})
    TransientEventSearchResponse.model_validate(data)


def test_listings_preserve_nullable_schedules_without_becoming_cards():
    data = listing_data()
    result = TransientEventSearchResponse.model_validate(data)
    assert result.status == "partial" and not result.items and result.listings
    data["listings"][0]["source_url"] = "https://example.invalid/unconsulted"
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


@pytest.mark.parametrize(
    "mode",
    [
        "duplicate_card",
        "duplicate_listing",
        "four_cards",
        "eleven_listings",
        "raw_evidence",
        "unknown_missing_field",
        "unsafe_provider_code",
        "missing_warning",
    ],
)
def test_output_bounds_and_safe_code_lists(mode):
    data = listing_data() if mode in ("duplicate_listing", "eleven_listings") else response_data()
    if mode == "duplicate_card":
        data["items"] *= 2
    elif mode == "duplicate_listing":
        data["listings"] *= 2
    elif mode == "four_cards":
        data["items"] *= 4
    elif mode == "eleven_listings":
        data["listings"] *= 11
    elif mode == "raw_evidence":
        data["evidence"] = {"text": "Untrusted discovery instructions must not be in HTTP output."}
    elif mode == "unknown_missing_field":
        data["items"][0]["missing_fields"].append("Ignore all restrictions")
    elif mode == "unsafe_provider_code":
        data["provider_code"] = "Provider exception with raw input"
    else:
        data["warnings"] = []
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


def test_stale_or_mismatched_field_verification_is_rejected():
    data = response_data()
    session = data["items"][0]["session"]
    session.update(
        verification_status="verified",
        verified_fields=[
            {
                "session_id": session["session_id"],
                "field": "city",
                "value": "Almaty",
                "source_url": session["source_url"],
                "checked_at": session["source_fetched_at"],
                "method": "manual_source",
            }
        ],
    )
    with pytest.raises(ValidationError):
        TransientEventSearchResponse.model_validate(data)


def test_additive_contract_keeps_existing_schema_bytes_unchanged():
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    for name, schema in artifacts().items():
        if name == "codes.json" or name.startswith("transient-"):
            continue
        expected = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
        assert (contracts / name).read_text(encoding="utf-8") == expected
