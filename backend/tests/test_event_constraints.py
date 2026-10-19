"""S04 session checks consume the unchanged D03 normalizer on synthetic input only."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.event_constraints import evaluate_event_session
from backend.app.intent import ResolvedIntent
from backend.app.schemas import Coordinates, POIRecord, RouteLeg, RouteProvenance
from backend.app.services.events.models import (
    CandidateEvent,
    Citation,
    EvidenceSource,
    FieldCheck,
    SearchEvidence,
)
from backend.app.services.events.normalize import normalize_events, verify_session
from backend.app.services.events.playground_cases import playground_cases
from backend.app.services.events.venue import VenueMatch

NOW = datetime.fromisoformat("2030-01-15T09:00:00+05:00")
DEPARTURE = datetime.fromisoformat("2030-01-15T18:00:00+05:00")


def session_for(case="matchedvenue"):
    data = deepcopy(next(row["input"] for row in playground_cases() if row["id"] == case))
    source = data["sources"][0]
    evidence = SearchEvidence(
        text=source["text"],
        sources=[EvidenceSource(url=source["url"], fetched_at=NOW)],
        citations=[
            Citation(
                url=source["url"],
                title="Synthetic S04/D03 session acceptance input",
                start_index=0,
                end_index=len(source["text"]),
                text=source["text"],
                context=source["text"],
            )
        ],
    )
    result = normalize_events(
        [CandidateEvent.model_validate(row) for row in data["events"]],
        evidence,
        now=NOW,
        selected_at=datetime.fromisoformat(data["selected_at"]),
        pois=[POIRecord.model_validate(row) for row in data["pois"]],
    )
    return result.events[0].sessions[0]


def intent(**changes):
    values = {
        "query": "Synthetic event request",
        "origin": Coordinates(latitude=51.13, longitude=71.44),
        "date_time": DEPARTURE,
        "available_minutes": 240,
    }
    values.update(changes)
    return ResolvedIntent(**values)


def known_leg(seconds=600):
    return RouteLeg(
        status="known",
        duration_seconds=seconds,
        distance_meters=600,
        provenance=RouteProvenance(retrieved_at=NOW, provider_locale="en"),
    )


@pytest.mark.parametrize("available_minutes", [30, 65])
def test_unknown_end_cannot_hide_start_outside_or_at_buffered_window(available_minutes):
    result = evaluate_event_session(
        session_for("missingend"), intent(available_minutes=available_minutes), now=NOW
    )
    assert result.rejected and result.fit_status == "does_not_fit"
    assert "insufficient_time" in result.exclusion_reasons


def test_known_return_can_prove_deadline_conflict_with_unknown_outbound():
    result = evaluate_event_session(
        session_for(),
        intent(available_minutes=190, return_to_start=True),
        return_route=known_leg(1200),
        now=NOW,
    )
    assert result.rejected and result.fit_status == "does_not_fit"
    assert "insufficient_time" in result.exclusion_reasons


def test_refreshed_clock_does_not_extend_window_when_date_input_is_missing():
    result = evaluate_event_session(
        session_for(),
        intent(date_time=None, available_minutes=170),
        now=DEPARTURE + timedelta(minutes=30),
        window_start=DEPARTURE,
    )
    assert result.rejected and "insufficient_time" in result.exclusion_reasons
    assert "date_time" in result.missing_fields


def test_unknown_end_at_calendar_limit_cannot_hide_a_known_window_conflict():
    departure = datetime.fromisoformat("9999-12-31T23:54:00+05:00")
    session = session_for().model_copy(
        update={
            "starts_at": datetime.fromisoformat("9999-12-31T23:59:00+05:00"),
            "ends_at": None,
        }
    )
    result = evaluate_event_session(
        session,
        intent(date_time=departure, available_minutes=1),
        known_leg(0),
        now=departure,
    )
    assert result.rejected and result.fit_status == "does_not_fit"
    assert "insufficient_time" in result.exclusion_reasons


def assess(session=None, request=None, outbound=None, back=None, *, now=NOW):
    return evaluate_event_session(
        session or session_for(),
        request or intent(),
        outbound or known_leg(),
        back,
        now=now,
    )


def test_real_normalizer_output_remains_conditional_and_source_fields_unchanged():
    session = session_for()
    before = session.model_dump(mode="json")
    result = assess(session)
    assert session.recommendation_candidate
    assert not result.rejected and result.fit_status == "unknown"
    assert result.total_minutes == 185  # Includes waiting, session and final buffer.
    assert result.arrival_at == DEPARTURE + timedelta(minutes=10)
    assert "ticket_availability" in result.missing_fields
    assert "source_verification" in result.missing_fields
    assert "within_time" in result.reason_codes
    assert session.model_dump(mode="json") == before


@pytest.mark.parametrize("case,reason", [("cancelled", "cancelled"), ("past", "past_session")])
def test_normalizer_exclusions_are_preserved(case, reason):
    session = session_for(case)
    result = assess(session)
    assert result.rejected and result.fit_status == "does_not_fit"
    assert reason in result.exclusion_reasons
    assert set(session.exclusion_reasons) <= set(result.exclusion_reasons)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"city": "Almaty"}, "other_city"),
        ({"status": "cancelled"}, "cancelled"),
        ({"starts_at": NOW - timedelta(minutes=1)}, "past_session"),
        ({"starts_at": DEPARTURE - timedelta(minutes=1)}, "before_requested_start"),
        ({"starts_at": DEPARTURE + timedelta(days=1)}, "outside_selected_date"),
    ],
)
def test_independent_checks_do_not_trust_candidate_true(changes, reason):
    # A copied DTO can retain a stale candidate flag; S04 rechecks critical values.
    result = assess(session_for().model_copy(update=changes))
    assert result.rejected and result.fit_status == "does_not_fit"
    assert reason in result.exclusion_reasons


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"city": None}, "city"),
        ({"status": "unknown"}, "status"),
        ({"starts_at": None}, "starts_at"),
    ],
)
def test_unknown_identity_or_schedule_is_withheld_without_claiming_a_conflict(changes, field):
    result = assess(session_for().model_copy(update=changes))
    assert result.rejected and result.fit_status == "unknown"
    assert field in result.missing_fields


def test_source_conflict_cannot_be_revived_by_otherwise_valid_facts():
    session = session_for().model_copy(
        update={"recommendation_candidate": False, "exclusion_reasons": ["source_conflict"]}
    )
    result = assess(session)
    assert result.rejected and result.fit_status == "unknown"
    assert "source_conflict" in result.exclusion_reasons


def test_local_session_date_and_equivalent_utc_instant_are_used():
    session = session_for()
    utc_session = session.model_copy(
        update={
            "starts_at": session.starts_at.astimezone(UTC),
            "ends_at": session.ends_at.astimezone(UTC),
        }
    )
    result = assess(utc_session, intent(date_time=DEPARTURE.astimezone(UTC)))
    assert not result.rejected
    assert "outside_selected_date" not in result.exclusion_reasons


def test_entry_buffer_is_required_before_session_start_with_inclusive_boundary():
    # 18:45 departure + 10 min walking + 5 min entry reaches the 19:00 start.
    boundary = DEPARTURE + timedelta(minutes=45)
    assert not assess(request=intent(date_time=boundary)).rejected
    result = assess(request=intent(date_time=boundary + timedelta(seconds=1)))
    assert result.rejected and "insufficient_arrival_time" in result.exclusion_reasons


def test_known_minimum_entry_time_can_reject_even_when_route_is_unknown():
    result = assess(
        request=intent(date_time=DEPARTURE + timedelta(minutes=56)),
        outbound=RouteLeg(status="unknown", reason="route_not_found"),
    )
    assert result.rejected and "insufficient_arrival_time" in result.exclusion_reasons


def test_elapsed_time_does_not_slide_an_existing_availability_window():
    result = assess(
        request=intent(available_minutes=180),
        now=DEPARTURE + timedelta(minutes=30),
    )
    assert result.rejected and "insufficient_time" in result.exclusion_reasons
    assert result.arrival_at == DEPARTURE + timedelta(minutes=40)
    assert result.total_minutes == 185


def test_return_uses_independent_leg_and_final_buffer():
    request = intent(return_to_start=True, available_minutes=195)
    result = assess(request=request, back=known_leg(600))
    assert not result.rejected and result.total_minutes == 195
    result = assess(request=request, back=known_leg(601))
    assert result.rejected and result.total_minutes == 196


@pytest.mark.parametrize("back", [None, RouteLeg(status="unavailable", reason="timeout")])
def test_missing_return_is_not_replaced_by_outbound(back):
    result = assess(request=intent(return_to_start=True), back=back)
    assert result.fit_status == "unknown" and result.total_minutes is None
    assert "return_travel_minutes_estimate" in result.missing_fields


def test_unrequested_return_does_not_affect_time():
    result = assess(back=RouteLeg(status="unavailable", reason="timeout"))
    assert result.total_minutes == 185
    assert "return_travel_minutes_estimate" not in result.missing_fields


@pytest.mark.parametrize("case", ["baseline", "missingend"])
def test_unknown_location_or_end_cannot_prove_time_fit(case):
    result = assess(session_for(case))
    assert result.fit_status == "unknown" and result.total_minutes is None
    assert "time_unknown" in result.reason_codes
    assert ("location" if case == "baseline" else "ends_at") in result.missing_fields


def test_end_after_deadline_rejects_even_with_unknown_route():
    result = assess(
        request=intent(available_minutes=120),
        outbound=RouteLeg(status="unknown", reason="route_not_found"),
    )
    assert result.rejected and "insufficient_time" in result.exclusion_reasons


@pytest.mark.parametrize("price_kind", ["starting", "regular", "promotion", "unknown"])
def test_lower_bound_price_never_confirms_a_hard_budget(price_kind):
    session = session_for().model_copy(update={"price_kind": price_kind})
    result = assess(session, intent(budget_kzt_per_person=5000))
    assert not result.rejected and result.fit_status == "unknown"
    assert "budget_unknown" in result.reason_codes
    assert "within_budget" not in result.reason_codes
    assert "price_kzt_per_person" in result.missing_fields


def test_price_lower_bound_above_budget_is_a_known_conflict_only_in_known_currency():
    session = session_for()
    result = assess(session, intent(budget_kzt_per_person=2500))
    assert result.rejected and "price_above_budget" in result.exclusion_reasons
    result = assess(
        session.model_copy(update={"currency": None}), intent(budget_kzt_per_person=2500)
    )
    assert not result.rejected and result.fit_status == "unknown"


def test_unknown_price_stays_unknown_and_indoor_is_not_guessed():
    result = assess(
        session_for().model_copy(update={"price_from": None}),
        intent(budget_kzt_per_person=5000, indoor="indoor"),
    )
    assert not result.rejected
    assert {"price_kzt_per_person", "indoor"} <= set(result.missing_fields)


def verified(session, fields):
    return verify_session(
        session,
        checks=[
            FieldCheck(
                session_id=session.session_id,
                field=field,
                value=(
                    getattr(session, field).isoformat()
                    if isinstance(getattr(session, field), datetime)
                    else getattr(session, field)
                ),
                source_url=session.source_url,
                checked_at=NOW,
                method="manual_source",
            )
            for field in fields
        ],
    )


def test_one_verified_field_does_not_verify_schedule_or_ticket_inventory():
    session = verified(session_for(), ["city"])
    assert session.verification_status == "verified"
    result = assess(session)
    assert {"source_verification", "ticket_availability"} <= set(result.missing_fields)
    assert result.fit_status == "unknown"


def test_all_relevant_verified_fields_still_do_not_claim_ticket_inventory():
    fields = ["city", "venue_name", "venue_address", "starts_at", "ends_at", "status"]
    session = verified(session_for(), fields)
    result = assess(session)
    assert "source_verification" not in result.missing_fields
    assert result.missing_fields == ("ticket_availability",)
    assert result.fit_status == "unknown"
    copied = session.model_copy(update={"venue_name": "Different synthetic branch"})
    assert "source_verification" in assess(copied).missing_fields


def test_missing_origin_or_unproven_venue_cannot_reuse_route_metrics():
    assert "origin" in assess(request=intent(origin=None)).missing_fields
    session = session_for().model_copy(
        update={"venue": VenueMatch(location=Coordinates(latitude=51.12, longitude=71.45))}
    )
    result = assess(session)
    assert result.arrival_at is None and result.total_minutes is None
    assert "location" in result.missing_fields


def test_absent_time_inputs_and_naive_now_are_explicit():
    result = assess(request=intent(date_time=None, available_minutes=None))
    assert {"date_time", "available_minutes"} <= set(result.missing_fields)
    with pytest.raises(ValueError, match="aware"):
        assess(now=datetime(2030, 1, 15, 9))


@pytest.mark.parametrize(
    "timestamp",
    ["9999-12-31T23:59:00+05:00", "0001-01-01T00:00:00+14:00"],
)
def test_valid_extreme_timestamps_do_not_raise_overflow(timestamp):
    result = assess(request=intent(date_time=datetime.fromisoformat(timestamp)))
    assert result.rejected and result.fit_status != "fits"
