"""D03 acceptance checks with inline synthetic evidence; no provider or corpus writes."""

import asyncio
import copy
import json
from datetime import datetime

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from backend.app.openai_client import ProviderError
from backend.app.schemas import EventSearchRequest, POIRecord
from backend.app.services.events.discover import (
    ALLOWED_DOMAINS,
    build_search_prompt,
    discover_events,
    parse_search_evidence,
)
from backend.app.services.events.models import (
    CandidateBatch,
    CandidateEvent,
    Citation,
    DiscoveryResult,
    EvidenceSource,
    FieldCheck,
    SearchEvidence,
)
from backend.app.services.events.normalize import normalize_events, verify_session
from backend.app.services.events.venue import match_venue

SYNTHETIC_URL = "https://ticketon.kz/synthetic-d03-fixture"
OTHER_SYNTHETIC_URL = "https://astanaopera.kz/synthetic-d03-unconsulted"
NOW = datetime.fromisoformat("2026-10-19T09:00:00+05:00")
SELECTED = datetime.fromisoformat("2026-10-19T10:00:00+05:00")
START = "2026-10-19T19:00:00+05:00"
END = "2026-10-19T21:00:00+05:00"
SYNTHETIC_TEXT = (
    "Synthetic D03 event: Astana; Synthetic venue; Synthetic street 1, Astana. "
    "The session is scheduled, starts 19 October 2026, 19:00; "
    "ends 19 October 2026, 21:00; from 3000 KZT. "
    "Starting price; category-dependent. "
    "Synthetic past session: 18 October 2026, 19:00."
)


def raw_search():
    return {
        "status": "completed",
        "output": [
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"type": "search", "sources": [{"url": SYNTHETIC_URL}]},
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": SYNTHETIC_TEXT,
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": SYNTHETIC_URL,
                                "title": "Synthetic D03 test fixture",
                                "start_index": 0,
                                "end_index": len(SYNTHETIC_TEXT),
                            }
                        ],
                    }
                ],
            },
        ],
    }


def evidence(text=SYNTHETIC_TEXT):
    raw = raw_search()
    part = raw["output"][1]["content"][0]
    part["text"] = text
    part["annotations"][0]["end_index"] = len(text)
    return parse_search_evidence(raw, fetched_at=NOW)


def multisource_evidence(source_texts):
    raw = raw_search()
    raw["output"][0]["action"]["sources"] = [{"url": url} for url in source_texts]
    raw["output"][1]["content"] = [
        {
            "type": "output_text",
            "text": text,
            "annotations": [
                {
                    "type": "url_citation",
                    "url": url,
                    "title": "Synthetic source reference",
                    "start_index": 0,
                    "end_index": len(text),
                }
            ],
        }
        for url, text in source_texts.items()
    ]
    return parse_search_evidence(raw, fetched_at=NOW)


def cancellation_evidence():
    return evidence(SYNTHETIC_TEXT + " This Synthetic D03 event session is cancelled.")


def candidate(**changes):
    data = {
        "title": "Synthetic D03 event",
        "source_url": SYNTHETIC_URL,
        "page_kind": "event",
        "city": "Astana",
        "venue_name": "Synthetic venue",
        "venue_address": "Synthetic street 1, Astana",
        "sessions": [
            {
                "source_url": SYNTHETIC_URL,
                "date_text": "19 October 2026, 19:00",
                "date_basis": "session",
                "starts_at": START,
                "ends_at": END,
                "end_text": "19 October 2026, 21:00",
                "price_from": 3000,
                "currency": "KZT",
                "price_conditions": "Starting price; category-dependent",
                "price_kind": "starting",
                "status": "scheduled",
            }
        ],
    }
    data.update(changes)
    return CandidateEvent.model_validate(data)


def with_session(**changes):
    row = candidate().model_dump(mode="json")
    row["sessions"][0].update(changes)
    return CandidateEvent.model_validate(row)


def normalize(row, *, proof=None, pois=()):
    return normalize_events([row], proof or evidence(), now=NOW, selected_at=SELECTED, pois=pois)


def session_for(row=None, *, proof=None):
    return normalize(row or candidate(), proof=proof).events[0].sessions[0]


def poi(**changes):
    # All values simulate a permitted production POI in memory. They are synthetic,
    # never passed to ingestion or a database; the flags exercise the rights gate.
    data = {
        "id": "synthetic:poi:1",
        "primary_source_id": "synthetic:source:1",
        "external_id": "synthetic-d03-fixture",
        "name": "Synthetic venue",
        "address": "Synthetic street 1, Astana",
        "activity_code": "culture",
        "location": {"latitude": 51.12, "longitude": 71.45},
        "sources": [
            {
                "source_id": "synthetic:source:1",
                "provider": "osm",
                "url": "https://www.openstreetmap.org/synthetic-d03-fixture",
                "retrieved_at": NOW,
                "license": "Synthetic rights assertion for tests only",
                "rights_basis_url": "https://www.openstreetmap.org/synthetic-d03-rights",
                "storage_allowed": True,
                "indexing_allowed": True,
                "is_test": False,
            }
        ],
        "provenance": [
            {
                "source_id": "synthetic:source:1",
                "external_id": "synthetic-d03-fixture",
                "fields": ["name", "address", "location"],
            }
        ],
        "is_test": False,
    }
    data.update(changes)
    return POIRecord.model_validate(data)


def test_other_city_is_rejected_without_claiming_no_match():
    result = normalize(
        candidate(city="Almaty"), proof=evidence(SYNTHETIC_TEXT.replace("Astana", "Almaty"))
    )
    assert result.events == []
    assert result.rejected_events == 1
    assert result.provider_status == "unknown"
    assert result.evidence is not None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        (
            {
                "starts_at": "2026-10-18T19:00:00+05:00",
                "date_text": "18 October 2026, 19:00",
                "ends_at": None,
            },
            "past_session",
        ),
        ({"status": "cancelled"}, "cancelled"),
        ({"status": "unknown"}, "status_unknown"),
    ],
)
def test_ineligible_sessions_remain_evidence_but_are_never_recommendations(changes, reason):
    proof = cancellation_evidence() if changes.get("status") == "cancelled" else evidence()
    result = normalize(with_session(**changes), proof=proof)
    session = result.events[0].sessions[0]
    assert session.recommendation_candidate is False
    assert reason in session.exclusion_reasons
    assert result.excluded_sessions == 1


@pytest.mark.parametrize("basis", ["publication", "index", "unknown"])
def test_non_session_date_never_creates_a_start(basis):
    session = session_for(with_session(date_basis=basis))
    assert session.starts_at is None
    assert session.ends_at is None
    assert "starts_at" in session.missing_fields
    assert session.recommendation_candidate is False


def test_missing_year_is_not_completed_from_selected_date():
    session = session_for(with_session(date_text="19 October, 19:00"))
    assert session.starts_at is None
    assert "schedule_unknown" in session.exclusion_reasons


def test_extraction_cannot_invent_a_year_not_present_in_the_cited_source_text():
    session = session_for(
        with_session(starts_at="2030-10-19T19:00:00+05:00", date_text="19 October 2030, 19:00")
    )
    assert session.starts_at is None
    assert session.recommendation_candidate is False


@pytest.mark.parametrize("start", ["2026-10-20T19:00:00+05:00", "2026-10-19T20:00:00+05:00"])
def test_parsed_start_must_match_the_cited_date_and_clock(start):
    session = session_for(with_session(starts_at=start))
    assert session.starts_at is None
    assert "schedule_unknown" in session.exclusion_reasons


def test_day_and_time_cannot_be_recombined_from_different_sessions_in_one_context():
    combined = "19 October 2026, 18:00; ends 20 October 2026, 19:00"
    text = SYNTHETIC_TEXT.replace("19 October 2026, 19:00; ends 19 October 2026, 21:00", combined)
    session = session_for(with_session(date_text=combined), proof=evidence(text))
    assert session.starts_at is None
    assert session.recommendation_candidate is False


@pytest.mark.parametrize("start", ["2026-10-19T19:00:30+05:00", "2026-10-19T19:00:00.123456+05:00"])
def test_unquoted_seconds_or_microseconds_do_not_become_session_times(start):
    session = session_for(with_session(starts_at=start))
    assert session.starts_at is None
    assert session.recommendation_candidate is False


@pytest.mark.parametrize(
    "changes",
    [
        {"ends_at": None, "end_text": None},
        {"end_text": "19 October, 21:00"},
        {"ends_at": "2026-10-19T18:00:00+05:00"},
    ],
)
def test_unknown_or_invalid_end_stays_null_and_explicitly_missing(changes):
    session = session_for(with_session(**changes))
    assert session.starts_at is not None
    assert session.ends_at is None
    assert "ends_at" in session.missing_fields
    assert not hasattr(session, "fit_status")


@pytest.mark.parametrize("amount", [0, 3000])
def test_price_from_preserves_zero_and_is_not_relabelled_as_regular(amount):
    proof = evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", f"from {amount} KZT"))
    session = session_for(with_session(price_from=amount), proof=proof)
    assert session.price_from == amount
    assert session.currency == "KZT"
    assert session.price_kind == "starting"
    assert "price_from" not in session.missing_fields


def test_promotional_price_keeps_its_conditions():
    proof = evidence(
        SYNTHETIC_TEXT.replace("from 3000 KZT", "promotion: 1500 KZT. Synthetic early bird")
    )
    session = session_for(
        with_session(
            price_from=1500, price_kind="promotion", price_conditions="Synthetic early bird"
        ),
        proof=proof,
    )
    assert session.price_from == 1500
    assert session.price_kind == "promotion"
    assert session.price_conditions == "Synthetic early bird"
    assert session.ticket_availability == "unknown"


def test_price_without_currency_is_unknown():
    session = session_for(
        with_session(currency=None),
        proof=evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", "from 3000")),
    )
    assert session.price_from is None
    assert "price_from" in session.missing_fields
    assert "currency" in session.missing_fields


def test_explicit_free_admission_preserves_zero_without_inventing_currency():
    proof = evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", "Free admission"))
    session = session_for(with_session(price_from=0, currency=None), proof=proof)
    assert session.price_from == 0
    assert session.currency is None
    assert "price_from" not in session.missing_fields
    assert "currency" in session.missing_fields


def test_zero_price_cannot_be_taken_from_the_digits_in_3000():
    session = session_for(with_session(price_from=0))
    assert session.price_from is None
    assert "price_from" in session.missing_fields


@pytest.mark.parametrize(
    "phrase",
    [
        "3000 KZT discount on tickets costing 15000",
        "A discount in the amount of 3000 KZT",
        "Скидка в размере 3000 тенге",
        "3000 теңге жеңілдік",
    ],
)
def test_discount_amount_is_never_normalized_as_the_admission_price(phrase):
    proof = evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", phrase))
    session = session_for(proof=proof)
    assert session.price_from is None
    assert "price_from" in session.missing_fields


@pytest.mark.parametrize(
    "phrase",
    [
        "Free cancellation",
        "Free delivery",
        "Free drinks",
        "Free parking for ticket holders",
        "Free cancellation on tickets from 3000 KZT",
    ],
)
def test_unrelated_free_services_do_not_make_event_admission_free(phrase):
    proof = evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", phrase))
    session = session_for(with_session(price_from=0), proof=proof)
    assert session.price_from is None


def test_discounted_ticket_price_is_kept_when_the_amount_prices_admission():
    proof = evidence(SYNTHETIC_TEXT.replace("from 3000 KZT", "Discounted tickets from 3000 KZT"))
    session = session_for(proof=proof)
    assert session.price_from == 3000
    assert session.price_kind == "promotion"


def test_unquoted_price_conditions_and_regular_price_kind_stay_unknown():
    session = session_for(
        with_session(price_kind="regular", price_conditions="Synthetic invented discount")
    )
    assert session.price_from == 3000
    assert session.price_kind != "regular"
    assert session.price_conditions is None


def test_unsupported_astana_city_from_an_almaty_context_stays_unknown():
    proof = evidence(SYNTHETIC_TEXT.replace("Astana", "Almaty"))
    session = session_for(proof=proof)
    assert session.city is None
    assert session.venue_address is None
    assert session.recommendation_candidate is False


def test_session_with_its_own_almaty_source_cannot_inherit_event_astana_city():
    proof = multisource_evidence(
        {
            SYNTHETIC_URL: SYNTHETIC_TEXT,
            OTHER_SYNTHETIC_URL: SYNTHETIC_TEXT.replace("Astana", "Almaty"),
        }
    )
    session = session_for(with_session(source_url=OTHER_SYNTHETIC_URL), proof=proof)
    assert session.city is None
    assert session.recommendation_candidate is False


def test_unsupported_event_title_rejects_the_event_instead_of_reusing_a_source_url():
    result = normalize(candidate(title="Synthetic invented event"))
    assert result.events == []
    assert result.rejected_events == 1


def test_listing_with_dates_remains_a_listing_without_sessions():
    event = normalize(candidate(page_kind="listing")).events[0]
    assert event.status == "listing"
    assert event.sessions == []
    assert event.schedule_hints == ["19 October 2026, 19:00"]
    assert "sessions" in event.missing_fields
    assert str(event.source_url) == SYNTHETIC_URL


@pytest.mark.parametrize(
    "url",
    [
        "https://astanaopera.kz/ru/posters?synthetic=d03-fixture",
        "https://visitastana.kz/afisha?synthetic=d03-fixture",
        "https://astanaballet.com/en?synthetic=d03-fixture",
    ],
)
def test_known_listing_urls_cannot_be_promoted_by_model_session_classification(url):
    raw = raw_search()
    raw["output"][0]["action"]["sources"][0]["url"] = url
    raw["output"][1]["content"][0]["annotations"][0]["url"] = url
    proof = parse_search_evidence(raw, fetched_at=NOW)
    data = candidate(page_kind="session", source_url=url).model_dump(mode="json")
    data["sessions"][0]["source_url"] = url
    event = normalize(CandidateEvent.model_validate(data), proof=proof).events[0]
    assert event.status == "listing"
    assert event.sessions == []


@pytest.mark.parametrize("reverse", [False, True])
def test_cancelled_duplicate_session_dominates_regardless_of_source_order(reverse):
    data = candidate().model_dump(mode="json")
    cancelled = copy.deepcopy(data["sessions"][0])
    cancelled["status"] = "cancelled"
    data["sessions"].append(cancelled)
    if reverse:
        data["sessions"].reverse()
    sessions = (
        normalize(CandidateEvent.model_validate(data), proof=cancellation_evidence())
        .events[0]
        .sessions
    )
    assert len(sessions) == 1
    assert sessions[0].status == "cancelled"
    assert sessions[0].recommendation_candidate is False


def test_conflicting_duplicate_session_facts_cannot_remain_recommendation_candidates():
    data = candidate().model_dump(mode="json")
    conflict = copy.deepcopy(data["sessions"][0])
    conflict["price_from"] = 4000
    data["sessions"].append(conflict)
    sessions = normalize(CandidateEvent.model_validate(data)).events[0].sessions
    assert len(sessions) == 1
    assert sessions[0].recommendation_candidate is False
    assert sessions[0].exclusion_reasons


@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_event_rows_cannot_hide_cancellation(reverse):
    rows = [candidate(), with_session(status="cancelled")]
    if reverse:
        rows.reverse()
    result = normalize_events(rows, cancellation_evidence(), now=NOW, selected_at=SELECTED)
    assert len(result.events) == 1
    assert all(not session.recommendation_candidate for session in result.events[0].sessions)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("city", ["Астана", "ASTANA", "Astana qalasy"])
def test_city_alias_and_venue_formatting_cannot_hide_cancellation(city, reverse):
    data = with_session(status="cancelled").model_dump(mode="json")
    data.update(
        city=city,
        title="SYNTHETIC   D03 event",
        venue_name="SYNTHETIC   venue",
        venue_address="SYNTHETIC  street 1, ASTANA",
    )
    rows = [candidate(), CandidateEvent.model_validate(data)]
    if reverse:
        rows.reverse()
    result = normalize_events(rows, cancellation_evidence(), now=NOW, selected_at=SELECTED)
    assert len(result.events) == 1
    assert len(result.events[0].sessions) == 1
    session = result.events[0].sessions[0]
    assert session.status == "cancelled"
    assert session.recommendation_candidate is False


def test_equivalent_utc_start_has_one_stable_session_identity_without_conflict():
    local = normalize(candidate()).events[0]
    utc_row = with_session(starts_at="2026-10-19T14:00:00+00:00")
    utc = normalize(utc_row).events[0]
    assert utc.event_id == local.event_id
    assert utc.sessions[0].session_id == local.sessions[0].session_id
    result = normalize_events([candidate(), utc_row], evidence(), now=NOW, selected_at=SELECTED)
    assert len(result.events) == 1
    assert len(result.events[0].sessions) == 1
    assert result.events[0].sessions[0].recommendation_candidate is True
    assert "source_conflict" not in result.events[0].sessions[0].exclusion_reasons


def test_utc_new_year_uses_the_cited_local_year_and_retains_the_same_session_identity():
    text = SYNTHETIC_TEXT.replace("19 October 2026, 19:00", "1 January 2027, 00:30").replace(
        "19 October 2026, 21:00", "1 January 2027, 02:00"
    )
    proof = evidence(text)
    local = with_session(
        starts_at="2027-01-01T00:30:00+05:00",
        date_text="1 January 2027, 00:30",
        ends_at=None,
        end_text=None,
    )
    utc = with_session(
        starts_at="2026-12-31T19:30:00+00:00",
        date_text="1 January 2027, 00:30",
        ends_at=None,
        end_text=None,
    )
    result = normalize_events(
        [local, utc],
        proof,
        now=datetime.fromisoformat("2026-12-31T18:00:00+00:00"),
        selected_at=datetime.fromisoformat("2027-01-01T00:00:00+05:00"),
    )
    assert len(result.events) == 1
    assert len(result.events[0].sessions) == 1
    session = result.events[0].sessions[0]
    assert session.starts_at == datetime.fromisoformat("2027-01-01T00:30:00+05:00")
    assert session.recommendation_candidate is True


@pytest.mark.parametrize("field", ["venue_name", "venue_address"])
def test_blank_optional_venue_facts_are_null_and_explicitly_missing(field):
    event = normalize(candidate(**{field: "   "})).events[0]
    assert getattr(event, field) is None
    assert field in event.missing_fields
    assert getattr(event.sessions[0], field) is None
    assert field in event.sessions[0].missing_fields


def test_same_event_title_and_source_do_not_merge_distinct_venue_branches():
    rows = [candidate(), candidate(venue_address="Synthetic street 2, Astana")]
    proof = evidence(SYNTHETIC_TEXT + " Other branch: Synthetic street 2, Astana.")
    result = normalize_events(rows, proof, now=NOW, selected_at=SELECTED)
    assert len(result.events) == 2
    assert result.events[0].event_id != result.events[1].event_id
    assert result.events[0].sessions[0].session_id != result.events[1].sessions[0].session_id


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("missing", ["venue_name", "venue_address"])
def test_partial_venue_cancellation_blocks_compatible_scheduled_sibling(missing, reverse):
    data = with_session(status="cancelled").model_dump(mode="json")
    data[missing] = None
    rows = [candidate(), CandidateEvent.model_validate(data)]
    if reverse:
        rows.reverse()
    result = normalize_events(rows, cancellation_evidence(), now=NOW, selected_at=SELECTED)
    assert result.events
    assert all(
        not session.recommendation_candidate
        for event in result.events
        for session in event.sessions
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_known_other_branch_cancellation_does_not_block_a_different_branch(reverse):
    data = with_session(status="cancelled").model_dump(mode="json")
    data["venue_address"] = "Synthetic street 2, Astana"
    rows = [candidate(), CandidateEvent.model_validate(data)]
    if reverse:
        rows.reverse()
    proof = evidence(
        SYNTHETIC_TEXT + " Other branch: Synthetic street 2, Astana; this branch is cancelled."
    )
    result = normalize_events(rows, proof, now=NOW, selected_at=SELECTED)
    assert len(result.events) == 2
    first_branch = next(
        event for event in result.events if event.venue_address == "Synthetic street 1, Astana"
    )
    assert first_branch.sessions[0].recommendation_candidate is True
    second_branch = next(
        event for event in result.events if event.venue_address == "Synthetic street 2, Astana"
    )
    assert second_branch.sessions[0].recommendation_candidate is False


@pytest.mark.parametrize("reverse", [False, True])
def test_same_session_cancellation_on_an_alternate_source_url_blocks_scheduled_source(reverse):
    data = with_session(status="cancelled", source_url=OTHER_SYNTHETIC_URL).model_dump(mode="json")
    data["source_url"] = OTHER_SYNTHETIC_URL
    rows = [candidate(), CandidateEvent.model_validate(data)]
    if reverse:
        rows.reverse()
    proof = multisource_evidence(
        {
            SYNTHETIC_URL: SYNTHETIC_TEXT,
            OTHER_SYNTHETIC_URL: SYNTHETIC_TEXT.replace("scheduled", "cancelled"),
        }
    )
    result = normalize_events(rows, proof, now=NOW, selected_at=SELECTED)
    assert all(
        not session.recommendation_candidate
        for event in result.events
        for session in event.sessions
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_cancellation_with_unknown_time_blocks_compatible_event_pending_review(reverse):
    rows = [candidate(), with_session(status="cancelled", starts_at=None, date_text=None)]
    if reverse:
        rows.reverse()
    result = normalize_events(rows, cancellation_evidence(), now=NOW, selected_at=SELECTED)
    assert all(
        not session.recommendation_candidate
        for event in result.events
        for session in event.sessions
    )


@pytest.mark.parametrize("location", ["event", "session"])
def test_extracted_urls_must_appear_in_both_source_list_and_citations(location):
    row = (
        candidate(source_url=OTHER_SYNTHETIC_URL)
        if location == "event"
        else with_session(source_url=OTHER_SYNTHETIC_URL)
    )
    result = normalize(row)
    if location == "event":
        assert result.events == []
        assert result.rejected_events == 1
    else:
        assert result.events[0].sessions == []
        assert result.excluded_sessions == 1


@pytest.mark.parametrize("missing", ["sources", "citations"])
def test_a_url_in_only_one_evidence_collection_cannot_ground_an_event(missing):
    proof = evidence().model_copy(update={missing: []})
    assert normalize(candidate(), proof=proof).events == []


def test_discovery_does_not_verify_fields_or_ticket_availability():
    result = normalize(candidate())
    assert result.live_web_search == "not_run"
    session = result.events[0].sessions[0]
    assert session.verification_status == "discovered"
    assert session.verified_fields == []
    assert session.ticket_availability == "unknown"


def test_verification_checks_only_the_explicit_matching_field():
    session = session_for()
    check = FieldCheck(
        session_id=session.session_id,
        field="starts_at",
        value=START,
        source_url=SYNTHETIC_URL,
        checked_at=NOW,
        method="manual_source",
    )
    verified = verify_session(session, checks=[check])
    assert verified.verification_status == "verified"
    assert [item.field for item in verified.verified_fields] == ["starts_at"]
    assert verified.ticket_availability == "unknown"
    assert session.verification_status == "discovered"


def test_event_and_session_identities_stay_stable_when_price_or_status_changes():
    initial = normalize(candidate()).events[0]
    proof = evidence(
        SYNTHETIC_TEXT.replace("from 3000 KZT", "from 4000 KZT").replace("scheduled", "cancelled")
    )
    updated = normalize(with_session(price_from=4000, status="cancelled"), proof=proof).events[0]
    assert updated.event_id == initial.event_id
    assert updated.sessions[0].session_id == initial.sessions[0].session_id
    assert updated.sessions[0].event_id == updated.event_id
    assert updated.sessions[0].price_from == 4000
    assert updated.sessions[0].recommendation_candidate is False


@pytest.mark.parametrize(
    "changes",
    [
        {"value": "2026-10-20T19:00:00+05:00"},
        {"source_url": OTHER_SYNTHETIC_URL},
        {"checked_at": "2026-10-18T09:00:00+05:00"},
    ],
)
def test_verification_cannot_accept_mismatched_or_stale_checks(changes):
    data = {
        "session_id": session_for().session_id,
        "field": "starts_at",
        "value": START,
        "source_url": SYNTHETIC_URL,
        "checked_at": NOW,
        "method": "licensed_feed",
    }
    data.update(changes)
    with pytest.raises(ValueError, match="Check must match"):
        verify_session(session_for(), checks=[FieldCheck.model_validate(data)])


def test_field_verification_cannot_be_transferred_to_another_session_with_the_same_price():
    first = session_for()
    second = session_for(
        with_session(
            starts_at="2026-10-19T20:00:00+05:00",
            date_text="19 October 2026, 20:00",
            ends_at=None,
            end_text=None,
        ),
        proof=evidence(SYNTHETIC_TEXT + " Another scheduled session: 19 October 2026, 20:00."),
    )
    assert first.session_id != second.session_id
    assert first.price_from == second.price_from == 3000
    check = FieldCheck(
        session_id=first.session_id,
        field="price_from",
        value=3000,
        source_url=SYNTHETIC_URL,
        checked_at=NOW,
        method="manual_source",
    )
    with pytest.raises(ValueError, match="Check must match"):
        verify_session(second, checks=[check])


def test_ticket_availability_is_not_a_verifiable_field():
    with pytest.raises(ValidationError):
        FieldCheck(
            session_id=session_for().session_id,
            field="ticket_availability",
            value="available",
            source_url=SYNTHETIC_URL,
            checked_at=NOW,
            method="manual_source",
        )


@pytest.mark.parametrize("changes", [{"price_from": 4000}, {"session_id": "synthetic:other"}])
def test_existing_verification_cannot_survive_a_changed_session_without_rechecking(changes):
    session = session_for()
    check = FieldCheck(
        session_id=session.session_id,
        field="price_from",
        value=3000,
        source_url=SYNTHETIC_URL,
        checked_at=NOW,
        method="manual_source",
    )
    verified = verify_session(session, checks=[check])
    changed = verified.model_copy(update=changes)
    with pytest.raises(ValueError, match="Check must match"):
        verify_session(changed, checks=[])


def test_venue_requires_name_address_and_permitted_geography():
    expected = poi()
    match = match_venue("  SYNTHETIC venue ", "Synthetic street 1, Astana", [expected])
    assert match.poi_id == expected.id
    assert match.location == expected.location
    assert match.basis == "name_address_astana_permitted_poi"
    assert match.source_ids == ["synthetic:source:1"]
    assert match_venue("Synthetic venue", None, [expected]).location is None
    assert match_venue("Synthetic venue", "Different branch address", [expected]).location is None


def test_same_name_branches_are_not_merged_and_duplicate_matches_are_ambiguous():
    first = poi()
    branch = poi(id="synthetic:poi:2", address="Synthetic street 2, Astana")
    assert match_venue(first.name, first.address, [first, branch]).poi_id == first.id
    duplicate = poi(id="synthetic:poi:3")
    unresolved = match_venue(first.name, first.address, [first, duplicate])
    assert unresolved.basis == "ambiguous"
    assert unresolved.location is None
    assert unresolved.poi_id is None


@pytest.mark.parametrize("kind", ["outside_city", "unknown_location", "unindexed", "test", "other"])
def test_venue_coordinates_are_never_taken_from_uncertain_or_unpermitted_pois(kind):
    data = poi().model_dump(mode="json")
    if kind == "outside_city":
        data["location"] = {"latitude": 43.23, "longitude": 76.89}
    elif kind == "unknown_location":
        data["location"] = None
    elif kind == "unindexed":
        data["sources"][0]["indexing_allowed"] = False
    elif kind == "test":
        data["is_test"] = True
        data["sources"][0]["is_test"] = True
    else:
        data["sources"][0]["provider"] = "other"
    source = POIRecord.model_validate(data)
    match = match_venue(source.name, source.address, [source])
    assert match.location is None
    assert match.source_ids == []


def test_completed_web_search_retains_exact_sources_and_citation_text():
    proof = evidence()
    assert str(proof.sources[0].url) == SYNTHETIC_URL
    assert proof.sources[0].fetched_at == NOW
    assert proof.sources[0].storage_allowed is False
    assert proof.sources[0].indexing_allowed is False
    assert str(proof.citations[0].url) == SYNTHETIC_URL
    assert proof.citations[0].text == SYNTHETIC_TEXT


def test_marker_only_citation_retains_discovered_facts_without_claiming_verification():
    raw = raw_search()
    part = raw["output"][1]["content"][0]
    marker = "[1]"
    part["text"] = SYNTHETIC_TEXT + " " + marker
    part["annotations"][0].update(
        start_index=len(SYNTHETIC_TEXT) + 1,
        end_index=len(part["text"]),
    )
    proof = parse_search_evidence(raw, fetched_at=NOW)
    assert proof.citations[0].text == marker
    assert "19 October 2026, 19:00" in proof.citations[0].context
    session = normalize(candidate(), proof=proof).events[0].sessions[0]
    assert session.starts_at == datetime.fromisoformat(START)
    assert session.verification_status == "discovered"
    assert session.verified_fields == []
    assert session.ticket_availability == "unknown"


def test_adjacent_markers_separated_by_a_blank_paragraph_do_not_reuse_context():
    raw = raw_search()
    raw["output"][0]["action"]["sources"].append({"url": OTHER_SYNTHETIC_URL})
    part = raw["output"][1]["content"][0]
    part["text"] = SYNTHETIC_TEXT + " [1]\n\n[2]"
    first_start = len(SYNTHETIC_TEXT) + 1
    part["annotations"][0].update(start_index=first_start, end_index=first_start + 3)
    part["annotations"].append(
        {
            "type": "url_citation",
            "url": OTHER_SYNTHETIC_URL,
            "title": "Synthetic second citation without associated facts",
            "start_index": len(part["text"]) - 3,
            "end_index": len(part["text"]),
        }
    )
    proof = parse_search_evidence(raw, fetched_at=NOW)
    second_context = proof.citations[1].context
    assert "Synthetic D03 event" not in second_context
    assert "19 October 2026" not in second_context


def test_exact_same_marker_with_two_source_annotations_retains_the_same_context():
    raw = raw_search()
    raw["output"][0]["action"]["sources"].append({"url": OTHER_SYNTHETIC_URL})
    part = raw["output"][1]["content"][0]
    part["text"] = SYNTHETIC_TEXT + " [1]"
    part["annotations"][0].update(start_index=len(SYNTHETIC_TEXT) + 1, end_index=len(part["text"]))
    other = copy.deepcopy(part["annotations"][0])
    other["url"] = OTHER_SYNTHETIC_URL
    part["annotations"].append(other)
    proof = parse_search_evidence(raw, fetched_at=NOW)
    assert len(proof.citations) == 2
    assert proof.citations[0].context == proof.citations[1].context
    assert "19 October 2026, 19:00" in proof.citations[1].context


def test_union_of_sources_from_multiple_search_calls_has_one_safe_bound():
    raw = raw_search()
    first = raw["output"][0]
    first["action"]["sources"].extend(
        {"url": f"https://ticketon.kz/synthetic-source-{index}"} for index in range(59)
    )
    second = copy.deepcopy(first)
    second["action"]["sources"] = [
        {"url": f"https://ticketon.kz/synthetic-source-{index}"} for index in range(59, 119)
    ]
    raw["output"].insert(1, second)
    with pytest.raises(ProviderError) as error:
        parse_search_evidence(raw, fetched_at=NOW)
    assert error.value.code == "web_search_sources_invalid"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("no_tool", "web_search_tool_not_used"),
        ("incomplete_tool", "web_search_tool_not_used"),
        ("no_sources", "web_search_sources_missing"),
        ("no_citations", "web_search_citations_missing"),
        ("unconsulted_citation", "web_search_citations_missing"),
        ("invalid_span", "web_search_citations_missing"),
        ("incomplete_response", "web_search_response_incomplete"),
    ],
)
def test_discovery_requires_tool_sources_and_matching_valid_citations(mutation, code):
    raw = raw_search()
    search, message = raw["output"]
    citation = message["content"][0]["annotations"][0]
    if mutation == "no_tool":
        raw["output"].remove(search)
    elif mutation == "incomplete_tool":
        search["status"] = "in_progress"
    elif mutation == "no_sources":
        search["action"]["sources"] = []
    elif mutation == "no_citations":
        message["content"][0]["annotations"] = []
    elif mutation == "unconsulted_citation":
        citation["url"] = OTHER_SYNTHETIC_URL
    elif mutation == "invalid_span":
        citation["end_index"] = len(SYNTHETIC_TEXT) + 1
    else:
        raw["status"] = "incomplete"
    with pytest.raises(ProviderError) as error:
        parse_search_evidence(raw, fetched_at=NOW)
    assert error.value.code == code


@pytest.mark.parametrize(
    "url",
    [
        "https://ticketon.kz.evil.invalid/synthetic-fixture",
        "https://evil.invalid/synthetic-fixture",
        "http://ticketon.kz/synthetic-fixture",
        "https://synthetic-user:synthetic-pass@ticketon.kz/synthetic-fixture",
    ],
)
def test_search_sources_outside_the_https_domain_allowlist_are_rejected(url):
    raw = raw_search()
    raw["output"][0]["action"]["sources"][0]["url"] = url
    raw["output"][1]["content"][0]["annotations"][0]["url"] = url
    with pytest.raises(ProviderError, match="web_search_sources_missing"):
        parse_search_evidence(raw, fetched_at=NOW)


@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
def test_prompt_includes_full_selected_date_and_multilingual_sources_independent_of_ui(locale):
    request = EventSearchRequest(query="Synthetic ballet topic", locale=locale, date_time=SELECTED)
    prompt = build_search_prompt(request, selected_at=SELECTED)
    assert "2026-10-19" in prompt
    assert "Astana / Астана" in prompt
    assert "Synthetic ballet topic" in prompt
    assert "Kazakh, Russian and English" in prompt
    assert "independently of the UI language" in prompt


class BasicClient:
    def __init__(self):
        self.normalization_calls = []

    async def create_response(self, text, *, instructions=""):
        self.normalization_calls.append((text, instructions))
        return json.dumps({"events": [candidate().model_dump(mode="json")]})

    async def embed(self, text):
        raise AssertionError("Event discovery must not create embeddings")


class SyntheticSearchClient(BasicClient):
    def __init__(self, *, search_error=None, response=None, normalization=None, delay=0):
        super().__init__()
        self.search_calls = []
        self.search_error = search_error
        self.response = raw_search() if response is None else response
        self.normalization = normalization
        self.delay = delay

    async def search_web(self, text, *, instructions="", allowed_domains):
        self.search_calls.append((text, instructions, allowed_domains))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.search_error:
            raise self.search_error
        return copy.deepcopy(self.response)

    async def create_response(self, text, *, instructions=""):
        if self.normalization is not None:
            self.normalization_calls.append((text, instructions))
            return self.normalization
        return await super().create_response(text, instructions=instructions)


def discover(client, *, timeout_seconds=25):
    request = EventSearchRequest(query="Synthetic ballet", locale="kk", date_time=SELECTED)
    return asyncio.run(discover_events(client, request, now=NOW, timeout_seconds=timeout_seconds))


def test_missing_shared_search_method_is_unavailable_and_not_run():
    client = BasicClient()
    result = discover(client)
    assert result.provider_status == "unavailable"
    assert result.provider_code == "shared_web_search_method_missing"
    assert result.live_web_search == "not_run"
    assert client.normalization_calls == []


def test_service_uses_shared_client_with_domain_filter_and_separate_normalization():
    client = SyntheticSearchClient()
    result = discover(client)
    assert result.provider_status == "partial"
    assert result.live_web_search == "passed"
    assert result.events[0].sessions[0].verification_status == "discovered"
    assert client.search_calls[0][2] == ALLOWED_DOMAINS
    extraction = json.loads(client.normalization_calls[0][0])
    assert extraction["evidence"]["citations"][0]["url"] == SYNTHETIC_URL
    assert "schema" in extraction


@pytest.mark.parametrize(
    "error_code",
    ["permission_denied", "network_unavailable_or_timeout", "synthetic-secret-do-not-log"],
)
def test_provider_failures_are_safe_and_never_become_no_match(error_code):
    client = SyntheticSearchClient(search_error=ProviderError(error_code))
    result = discover(client)
    assert result.provider_status == "unavailable"
    assert result.live_web_search == "failed"
    assert result.events == []
    assert result.provider_code == (
        "provider_failed" if error_code == "synthetic-secret-do-not-log" else error_code
    )
    assert "synthetic-secret" not in result.model_dump_json()
    assert client.normalization_calls == []


def test_timeout_is_reported_without_no_match_or_raw_exception():
    result = discover(SyntheticSearchClient(delay=1), timeout_seconds=0.001)
    assert result.provider_status == "unavailable"
    assert result.provider_code == "event_search_timeout"
    assert result.live_web_search == "failed"
    assert result.events == []


def test_tool_not_used_stops_before_normalization():
    raw = raw_search()
    raw["output"] = raw["output"][1:]
    client = SyntheticSearchClient(response=raw)
    result = discover(client)
    assert result.provider_status == "unavailable"
    assert result.provider_code == "web_search_tool_not_used"
    assert client.normalization_calls == []


@pytest.mark.parametrize("payload", ["not JSON", '{"events": [{"invented": true}]}'])
def test_malformed_normalization_preserves_successful_search_evidence(payload):
    result = discover(SyntheticSearchClient(normalization=payload))
    assert result.provider_status == "unknown"
    assert result.provider_code == "event_normalization_invalid"
    assert result.live_web_search == "passed"
    assert result.evidence is not None
    assert str(result.evidence.citations[0].url) == SYNTHETIC_URL
    assert result.events == []


def test_inline_synthetic_dtos_validate_against_pydantic_and_json_schema():
    fixtures = [
        (CandidateBatch, {"events": [candidate().model_dump(mode="json")]}),
        (SearchEvidence, evidence().model_dump(mode="json")),
        (DiscoveryResult, normalize(candidate()).model_dump(mode="json")),
    ]
    for model, payload in fixtures:
        assert model.model_validate(payload)
        Draft202012Validator(model.model_json_schema(), format_checker=FormatChecker()).validate(
            payload
        )


def test_runtime_evidence_cannot_claim_storage_or_indexing_rights():
    with pytest.raises(ValidationError):
        EvidenceSource(url=SYNTHETIC_URL, fetched_at=NOW, storage_allowed=True)
    with pytest.raises(ValidationError):
        EvidenceSource(url=SYNTHETIC_URL, fetched_at=NOW, indexing_allowed=True)


def test_citation_fixture_retains_source_text_without_treating_it_as_generated_explanation():
    citation = Citation.model_validate(evidence().citations[0].model_dump(mode="json"))
    assert citation.text == SYNTHETIC_TEXT
    assert "explanation" not in normalize(candidate()).events[0].model_dump()


PLAYGROUND_ENGINE = "backend.app.services.events.normalize.normalize_events"


def playground_payload():
    return {
        "now": NOW.isoformat(),
        "selected_at": SELECTED.isoformat(),
        "events": [candidate().model_dump(mode="json")],
        "sources": [{"url": SYNTHETIC_URL, "text": SYNTHETIC_TEXT}],
        "pois": [],
        "simulate_start_check": False,
    }


def playground_request(method, path, *, app=None, client_address=("127.0.0.1", 123), **kwargs):
    import httpx

    from backend.app.services.events.playground import create_playground_app

    async def run():
        transport = httpx.ASGITransport(
            app=app if app is not None else create_playground_app(), client=client_address
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8003"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_playground_examples_supply_editable_synthetic_inputs_for_the_actual_engine():
    response = playground_request("GET", "/api/dev/events/examples")
    assert response.status_code == 200
    catalog = response.json()
    assert catalog["is_test"] is True
    assert catalog["network_access"] is False
    assert catalog["engine"] == PLAYGROUND_ENGINE
    assert len(catalog["cases"]) >= 8
    baseline = next(case for case in catalog["cases"] if case["id"] == "baseline")
    normalized = playground_request("POST", "/api/dev/events/normalize", json=baseline["input"])
    assert normalized.status_code == 200
    assert normalized.json()["result"]["events"][0]["sessions"][0]["recommendation_candidate"]


def test_playground_status_edits_change_actual_normalization_output():
    payload = playground_payload()
    initial = playground_request("POST", "/api/dev/events/normalize", json=payload)
    assert initial.status_code == 200
    body = initial.json()
    assert body["is_test"] is True
    assert body["network_access"] is False
    assert body["engine"] == PLAYGROUND_ENGINE
    assert body["simulated_verification"] is False
    assert body["result"]["live_web_search"] == "not_run"
    assert body["result"]["events"][0]["sessions"][0]["recommendation_candidate"] is True
    payload["events"][0]["sessions"][0]["status"] = "cancelled"
    edited = playground_request("POST", "/api/dev/events/normalize", json=payload)
    assert edited.status_code == 200
    session = edited.json()["result"]["events"][0]["sessions"][0]
    assert session["status"] == "cancelled"
    assert session["recommendation_candidate"] is False
    assert "cancelled" in session["exclusion_reasons"]


@pytest.mark.parametrize("edited_field", ["year", "end"])
def test_playground_removed_year_or_end_is_visible_as_missing(edited_field):
    payload = playground_payload()
    facts = payload["events"][0]["sessions"][0]
    if edited_field == "year":
        facts["date_text"] = "19 October, 19:00"
    else:
        facts["ends_at"] = None
        facts["end_text"] = None
    response = playground_request("POST", "/api/dev/events/normalize", json=payload)
    assert response.status_code == 200
    session = response.json()["result"]["events"][0]["sessions"][0]
    assert session["ends_at"] is None
    assert "ends_at" in session["missing_fields"]
    if edited_field == "year":
        assert session["starts_at"] is None
        assert session["recommendation_candidate"] is False
        assert "starts_at" in session["missing_fields"]
    else:
        assert session["starts_at"] is not None


def test_playground_unquoted_price_edit_cannot_create_a_source_fact():
    payload = playground_payload()
    payload["events"][0]["sessions"][0]["price_from"] = 987654321
    response = playground_request("POST", "/api/dev/events/normalize", json=payload)
    assert response.status_code == 200
    session = response.json()["result"]["events"][0]["sessions"][0]
    assert session["price_from"] is None
    assert session["currency"] is None
    assert "price_from" in session["missing_fields"]


def test_playground_checkbox_simulates_only_a_session_bound_start_check():
    payload = playground_payload()
    payload["simulate_start_check"] = True
    response = playground_request("POST", "/api/dev/events/normalize", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["is_test"] is True
    assert body["simulated_verification"] is True
    assert body["network_access"] is False
    session = body["result"]["events"][0]["sessions"][0]
    assert session["verification_status"] == "verified"
    assert session["ticket_availability"] == "unknown"
    assert [check["field"] for check in session["verified_fields"]] == ["starts_at"]
    assert session["verified_fields"][0]["session_id"] == session["session_id"]
    assert session["verified_fields"][0]["source_url"] == session["source_url"]


def test_default_app_does_not_expose_the_opt_in_playground():
    from backend.app.main import create_app

    production_app = create_app()
    for path in ("/api/dev/events/playground", "/api/dev/events/examples"):
        response = playground_request("GET", path, app=production_app)
        assert response.status_code == 404
    response = playground_request(
        "POST", "/api/dev/events/normalize", app=production_app, json=playground_payload()
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "request_options",
    [
        {"headers": {"Origin": "https://synthetic-evil.invalid"}},
        {"headers": {"Host": "synthetic-evil.invalid:8003"}},
        {"client_address": ("203.0.113.42", 123)},
    ],
)
def test_playground_rejects_cross_origin_host_and_non_loopback_clients(request_options):
    response = playground_request(
        "POST", "/api/dev/events/normalize", json=playground_payload(), **request_options
    )
    assert response.status_code == 403


@pytest.mark.parametrize("streamed", [False, True])
def test_playground_body_limit_applies_to_declared_and_streamed_bodies(streamed):
    async def chunks():
        for _ in range(3):
            yield b" " * 65536

    content = chunks() if streamed else b" " * (128 * 1024 + 1)
    response = playground_request(
        "POST",
        "/api/dev/events/normalize",
        content=content,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("kind", ["syntax", "schema"])
def test_playground_invalid_inputs_have_sanitized_json_errors(kind):
    marker = "synthetic-private-marker-do-not-echo"
    if kind == "syntax":
        options = {
            "content": ('{"events": "' + marker).encode(),
            "headers": {"Content-Type": "application/json"},
        }
    else:
        payload = playground_payload()
        payload["now"] = marker
        options = {"json": payload}
    response = playground_request("POST", "/api/dev/events/normalize", **options)
    assert response.status_code == 422
    assert "application/json" in response.headers["content-type"]
    assert marker not in response.text
    assert "traceback" not in response.text.casefold()


def test_playground_html_uses_matching_csp_nonces_and_no_external_assets():
    import re
    from html.parser import HTMLParser

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.nonces = []
            self.external_assets = []

        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag in {"script", "style"}:
                self.nonces.append(values.get("nonce"))
            asset = values.get("src") or (values.get("href") if tag == "link" else None)
            if asset and (asset.startswith("//") or not asset.startswith(("/", "data:"))):
                self.external_assets.append(asset)

    response = playground_request("GET", "/api/dev/events/playground")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    policy = response.headers["content-security-policy"]
    nonces = set(re.findall(r"'nonce-([^']+)'", policy))
    assert nonces
    assert "'unsafe-inline'" not in policy
    parser = Assets()
    parser.feed(response.text)
    assert parser.nonces
    assert all(nonce in nonces for nonce in parser.nonces)
    assert parser.external_assets == []
    assert "@import" not in response.text
