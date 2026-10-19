"""Evaluate D03 runtime sessions without inventing persistent event records or rights."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil

from backend.app.constraints import BUFFER_MINUTES, ENTRY_MINUTES
from backend.app.intent import ResolvedIntent
from backend.app.schemas import FitStatus, ReasonCode, RouteLeg
from backend.app.services.events.models import NormalizedSession
from backend.app.services.events.normalize import ASTANA_NAMES, ASTANA_TIMEZONE, require_aware
from backend.app.services.events.venue import normalize_venue_text


@dataclass(frozen=True)
class EventEvaluation:
    """A withheld uncertain session is rejected for display, not proven to be absent."""

    rejected: bool
    fit_status: FitStatus
    missing_fields: tuple[str, ...]
    reason_codes: tuple[ReasonCode, ...]
    exclusion_reasons: tuple[str, ...]
    total_minutes: int | None
    arrival_at: datetime | None


def _field_verified(session: NormalizedSession, field: str) -> bool:
    """Do not let a one-field check or a stale copied check verify the whole session."""
    value = getattr(session, field)
    expected = value.isoformat() if isinstance(value, datetime) else value
    return value is not None and any(
        check.field == field
        and check.session_id == session.session_id
        and check.value == expected
        and check.source_url == session.source_url
        and check.checked_at >= session.source_fetched_at
        for check in session.verified_fields
    )


def _after(value: datetime, *, minutes: int = 0, seconds: int = 0) -> datetime | None:
    try:
        return value + timedelta(minutes=minutes, seconds=seconds)
    except OverflowError:
        return None


def evaluate_event_session(
    session: NormalizedSession,
    intent: ResolvedIntent,
    outbound: RouteLeg | None = None,
    return_route: RouteLeg | None = None,
    *,
    now: datetime,
    window_start: datetime | None = None,
) -> EventEvaluation:
    """Check one session and one independent trip; this performs no I/O.

    ``date_time`` anchors the user's availability window. Missing input is explicit;
    ``now`` is only the conservative current-date/past-session comparison anchor.
    D03 prices remain lower bounds, source checks remain field-specific, and its
    unknown ticket inventory never becomes confirmed availability. ``rejected``
    with unknown fit means withhold, not a proven hard-constraint conflict.
    """
    require_aware(now)
    if window_start is not None:
        require_aware(window_start)
    selected = intent.date_time or window_start or now
    require_aware(selected)
    departure = max(selected, now)
    missing: list[str] = []
    reasons: list[ReasonCode] = []
    exclusions = list(session.exclusion_reasons)
    hard_conflict = False
    withheld = not session.recommendation_candidate or bool(exclusions)

    def conflict(reason: str) -> None:
        nonlocal hard_conflict
        hard_conflict = True
        exclusions.append(reason)

    def unknown(field: str, *, withhold_reason: str | None = None) -> None:
        nonlocal withheld
        missing.append(field)
        if withhold_reason:
            withheld = True
            exclusions.append(withhold_reason)

    if not session.recommendation_candidate and not exclusions:
        exclusions.append("normalizer_withheld")
    if session.city is None:
        unknown("city", withhold_reason="city_unknown")
    elif normalize_venue_text(session.city) not in ASTANA_NAMES:
        conflict("other_city")
    if session.status == "cancelled":
        conflict("cancelled")
    elif session.status != "scheduled":
        unknown("status", withhold_reason="status_unknown")
    if intent.date_time is None:
        unknown("date_time")
    start, end = session.starts_at, session.ends_at
    if start is None:
        unknown("starts_at", withhold_reason="schedule_unknown")
        reasons.append(ReasonCode.SCHEDULE_UNKNOWN)
    else:
        require_aware(start)
        if start < now:
            conflict("past_session")
        if start < selected:
            conflict("before_requested_start")
        try:
            if (
                start.astimezone(ASTANA_TIMEZONE).date()
                != selected.astimezone(ASTANA_TIMEZONE).date()
            ):
                conflict("outside_selected_date")
        except (OverflowError, ValueError):
            unknown("date_time", withhold_reason="date_out_of_range")
        minimum_arrival = _after(departure, minutes=ENTRY_MINUTES)
        if minimum_arrival is None:
            unknown("date_time", withhold_reason="date_out_of_range")
        elif minimum_arrival > start:
            conflict("insufficient_arrival_time")
    if end is None:
        unknown("ends_at")
        reasons.append(ReasonCode.SCHEDULE_UNKNOWN)
    else:
        require_aware(end)
        if start is not None and end <= start:
            conflict("invalid_time_order")

    if intent.origin is None:
        unknown("origin")
    location_known = (
        session.venue.location is not None
        and session.venue.basis == "name_address_astana_permitted_poi"
        and bool(session.venue.source_ids)
        and bool(session.venue.source_urls)
    )
    if not location_known:
        unknown("location")
    outbound_known = (
        intent.origin is not None
        and location_known
        and outbound is not None
        and outbound.status == "known"
    )
    return_known = not intent.return_to_start or (
        return_route is not None and return_route.status == "known"
    )
    if not outbound_known or not return_known:
        unknown("travel_minutes_estimate")
        reasons.append(ReasonCode.ROUTE_UNKNOWN)
    if intent.return_to_start and not return_known:
        unknown("return_travel_minutes_estimate")
    arrival = None
    entry_ready = None
    if outbound_known:
        arrival = _after(departure, seconds=outbound.duration_seconds)
        entry_ready = _after(arrival, minutes=ENTRY_MINUTES) if arrival else None
        if entry_ready is None:
            unknown("date_time", withhold_reason="date_out_of_range")
        elif start is not None and entry_ready > start:
            conflict("insufficient_arrival_time")

    total = None
    if (
        start is not None
        and end is not None
        and end > start
        and outbound_known
        and return_known
        and entry_ready is not None
        and entry_ready <= start
    ):
        # Scheduled waiting and entry are inside departure-to-session-end time.
        seconds = (end - selected).total_seconds() + BUFFER_MINUTES * 60
        if intent.return_to_start:
            seconds += return_route.duration_seconds
        total = ceil(seconds / 60)
    if intent.available_minutes is None:
        unknown("available_minutes")
    else:
        deadline = _after(selected, minutes=intent.available_minutes)
        # A known start/end can already prove a conflict even when other times are unknown.
        known_return_seconds = (
            return_route.duration_seconds
            if intent.return_to_start
            and return_route is not None
            and return_route.status == "known"
            else 0
        )
        after_visit_seconds = BUFFER_MINUTES * 60 + known_return_seconds
        if deadline is None:
            unknown("date_time", withhold_reason="date_out_of_range")
        elif end is not None and (deadline - end).total_seconds() < after_visit_seconds:
            conflict("insufficient_time")
        elif start is not None and (deadline - start).total_seconds() <= after_visit_seconds:
            # A visit needs some time after its start; unknown duration is not zero.
            # Subtraction also preserves this lower bound at datetime.max.
            conflict("insufficient_time")
        if total is not None and total > intent.available_minutes:
            conflict("insufficient_time")
    if intent.minimum_minutes is not None and total is not None and total < intent.minimum_minutes:
        conflict("below_minimum_time")
    if total is not None and intent.available_minutes is not None and not hard_conflict:
        reasons.append(ReasonCode.WITHIN_TIME)
    else:
        reasons.append(ReasonCode.TIME_UNKNOWN)

    if intent.budget_kzt_per_person is not None or intent.minimum_budget_kzt is not None:
        # price_from is not an exact admission price, even when labelled regular.
        unknown("price_kzt_per_person")
        reasons.append(ReasonCode.BUDGET_UNKNOWN)
        if (
            session.currency == "KZT"
            and session.price_from is not None
            and intent.budget_kzt_per_person is not None
            and session.price_from > intent.budget_kzt_per_person
        ):
            conflict("price_above_budget")
    if intent.indoor is not None:
        unknown("indoor")
    # A verified city alone never verifies the schedule, venue or cancellation.
    if not all(
        _field_verified(session, field)
        for field in ("city", "venue_name", "venue_address", "starts_at", "ends_at", "status")
    ):
        unknown("source_verification")
    unknown("ticket_availability")
    fit = FitStatus.DOES_NOT_FIT if hard_conflict else FitStatus.UNKNOWN
    return EventEvaluation(
        rejected=hard_conflict or withheld,
        fit_status=fit,
        missing_fields=tuple(dict.fromkeys(missing)),
        reason_codes=tuple(dict.fromkeys(reasons)),
        exclusion_reasons=tuple(dict.fromkeys(exclusions)),
        total_minutes=total,
        arrival_at=arrival,
    )
