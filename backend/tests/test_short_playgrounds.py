"""Synthetic playground visit policies; feature proof is supplied by the caller."""

import pytest

from backend.app.constraints import evaluate_poi, hard_reject, suggested_visit_minutes
from backend.app.schemas import RouteLeg
from backend.tests.test_constraints import intent, poi, route


@pytest.mark.parametrize(
    "seconds,visit,travel,rejected",
    [(0, 20, 0, False), (300, 15, 5, False), (600, 10, 10, False), (601, 10, 11, True)],
)
def test_thirty_minute_playground_includes_travel_entry_visit_and_buffer(
    seconds, visit, travel, rejected
):
    playground = poi(activity_code="entertainment", visit_minutes_estimate=7)
    original = playground.model_dump()
    result = evaluate_poi(playground, intent(available_minutes=30), route(seconds), playground=True)
    assert result.visit_minutes_estimate == visit
    assert result.travel_minutes_estimate == travel
    assert result.total_minutes == travel + 5 + visit + 5
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "fits")
    assert playground.model_dump() == original
    assert playground.visit_minutes_estimate == 7
    if not rejected:
        assert "within_time" in result.reason_codes
        assert result.total_minutes <= 30


@pytest.mark.parametrize("minutes,rejected", [(0, True), (19, True), (20, False), (30, False)])
def test_irreducible_playground_minimum_is_checked_before_routes(minutes, rejected):
    playground = poi(activity_code="entertainment")
    query = intent(available_minutes=minutes)
    assert hard_reject(playground, query, playground=True) is rejected
    evaluated = evaluate_poi(playground, query, route(0), playground=True)
    assert evaluated.rejected is rejected
    assert evaluated.visit_minutes_estimate >= 10


@pytest.mark.parametrize("minutes", [None, 120])
def test_playground_default_remains_forty_five_minutes_without_a_tight_budget(minutes):
    playground = poi(activity_code="entertainment")
    query = intent(available_minutes=minutes)
    assert suggested_visit_minutes(playground, query, playground=True) == 45
    evaluated = evaluate_poi(playground, query, route(0), playground=True)
    assert evaluated.visit_minutes_estimate == 45
    assert not evaluated.rejected
    if minutes is None:
        assert evaluated.fit_status == "unknown"
        assert "available_minutes" in evaluated.missing_fields


def test_requested_return_seconds_are_combined_before_rounding_and_reducing_visit():
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=30, return_to_start=True),
        route(61),
        route(61),
        playground=True,
    )
    assert result.fit_status == "fits"
    assert result.travel_minutes_estimate == 3
    assert result.visit_minutes_estimate == 17
    assert result.total_minutes == 30


def test_unrequested_return_does_not_reduce_a_playground_visit():
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=30),
        route(300),
        route(604800),
        playground=True,
    )
    assert result.fit_status == "fits"
    assert result.visit_minutes_estimate == 15
    assert result.travel_minutes_estimate == 5
    assert result.total_minutes == 30


@pytest.mark.parametrize("known_side", ["outbound", "return"])
@pytest.mark.parametrize("unknown_status", ["unknown", "unavailable"])
@pytest.mark.parametrize("known_seconds,rejected", [(600, False), (601, True)])
def test_unknown_leg_stays_unknown_but_known_leg_can_disprove_the_total(
    known_side, unknown_status, known_seconds, rejected
):
    unknown = RouteLeg(status=unknown_status, reason="timeout")
    outbound, back = (
        (route(known_seconds), unknown)
        if known_side == "outbound"
        else (unknown, route(known_seconds))
    )
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=30, return_to_start=True),
        outbound,
        back,
        playground=True,
    )
    assert result.visit_minutes_estimate == 10
    assert result.travel_minutes_estimate is None and result.total_minutes is None
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "unknown")
    assert "travel_minutes_estimate" in result.missing_fields
    assert "within_time" not in result.reason_codes


@pytest.mark.parametrize("missing", ["origin", "location_provenance", "location"])
def test_unmatched_route_geography_cannot_reduce_or_disprove_the_visit(missing):
    playground = poi(activity_code="entertainment")
    query = intent(available_minutes=30)
    if missing == "origin":
        query.origin = None
    elif missing == "location_provenance":
        playground.provenance[0].fields.remove("location")
    else:
        playground.location = None
    result = evaluate_poi(playground, query, route(3600), playground=True)
    assert not result.rejected and result.fit_status == "unknown"
    assert result.visit_minutes_estimate == 20
    assert result.travel_minutes_estimate is None and result.total_minutes is None


def test_unknown_outbound_does_not_claim_a_known_total_or_a_confirmed_fit():
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=30),
        RouteLeg(status="unknown", reason="timeout"),
        playground=True,
    )
    assert result.visit_minutes_estimate == 20
    assert result.fit_status == "unknown" and not result.rejected
    assert result.travel_minutes_estimate is None and result.total_minutes is None
    assert "time_unknown" in result.reason_codes


@pytest.mark.parametrize("minimum,rejected", [(30, False), (31, True)])
def test_reduced_playground_visit_preserves_explicit_minimum_total_time(minimum, rejected):
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=30, minimum_minutes=minimum),
        route(300),
        playground=True,
    )
    assert result.visit_minutes_estimate == 15 and result.total_minutes == 30
    assert result.rejected is rejected


@pytest.mark.parametrize("minimum,rejected", [(55, False), (56, True)])
def test_playground_default_is_not_extended_to_silently_satisfy_a_minimum(minimum, rejected):
    result = evaluate_poi(
        poi(activity_code="entertainment"),
        intent(available_minutes=120, minimum_minutes=minimum),
        route(0),
        playground=True,
    )
    assert result.visit_minutes_estimate == 45 and result.total_minutes == 55
    assert result.rejected is rejected


@pytest.mark.parametrize("closing,rejected", [("12:25", False), ("12:24", True)])
def test_opening_window_covers_entry_and_the_shortened_visit(closing, rejected):
    result = evaluate_poi(
        poi(activity_code="entertainment", opening_hours_text=f"Mo-Su 12:00-{closing}"),
        intent(available_minutes=30),
        route(300),
        playground=True,
    )
    assert result.visit_minutes_estimate == 15 and result.total_minutes == 30
    assert result.rejected is rejected
    assert result.fit_status == ("does_not_fit" if rejected else "fits")


@pytest.mark.parametrize("flag", [None, False])
def test_entertainment_category_alone_does_not_allow_short_playground_policy(flag):
    current = poi(activity_code="entertainment")
    query = intent(available_minutes=30)
    options = {} if flag is None else {"playground": flag}
    assert hard_reject(current, query, **options)
    result = evaluate_poi(current, query, route(0), **options)
    assert result.rejected and result.fit_status == "does_not_fit"
    assert result.visit_minutes_estimate == 45
