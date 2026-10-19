"""Deterministic single-destination constraints; no provider calls or inferred facts."""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from backend.app.intent import ResolvedIntent
from backend.app.schemas import (
    ActivityCode,
    FitStatus,
    MissingField,
    POIRecord,
    ReasonCode,
    RouteLeg,
    RouteStatus,
    Warning,
)

ENTRY_MINUTES = 5
BUFFER_MINUTES = 5
MAX_CARD_TRAVEL_MINUTES = 10080
# These are product recommendations, never source facts or admission guarantees.
VISIT_MINUTES = {
    ActivityCode.WALK: 30,
    ActivityCode.MUSEUM: 45,
    ActivityCode.FOOD: 30,
    ActivityCode.CULTURE: 45,
    ActivityCode.SPORT: 45,
    ActivityCode.SHOPPING: 30,
    ActivityCode.ENTERTAINMENT: 45,
    ActivityCode.OTHER: 30,
}


@dataclass(frozen=True)
class FitEvaluation:
    fit_status: FitStatus
    missing_fields: tuple[MissingField, ...]
    reason_codes: tuple[ReasonCode, ...]
    visit_minutes_estimate: int
    route_status: RouteStatus
    travel_minutes_estimate: int | None
    warnings: tuple[Warning, ...]
    rejected: bool
    total_minutes: int | None


def sourced_field(poi: POIRecord, field: str) -> bool:
    """Only structured values with explicit field provenance can prove a constraint."""
    fields = {name for item in poi.provenance for name in item.fields}
    if field == "price_kzt_per_person" and fields.intersection(
        {"price_from", "price_from_kzt", "price_from_kzt_per_person"}
    ):
        return False
    return field in fields and getattr(poi, field, None) is not None


def unsupported_requirements(query: str) -> list[str]:
    """Flag requirements that the current contract has no factual fields to evaluate.

    This presence check intentionally prefers clarification over silently omitting a
    possible requirement; it is not a general language parser or an amenity detector.
    """
    patterns = {
        "quiet": (
            r"\bтих\w*|\bтишин\w*|\bспокойн\w*|\bүнсіз\w*|\bтыныш\w*|\bшусыз\w*|"
            r"\bquiet\w*|\bsilent\w*|\bpeaceful\b"
        ),
        "power_outlets": r"розет\w*|қуатта\w*|тоқ\s+көзі|\boutlets?\b|\bsockets?\b",
        "accessibility": (
            r"доступн\w*\s+(?:сред\w*|для\s+(?:коляс\w*|инвалид\w*))|"
            r"доступность|безбарьер\w*|пандус\w*|коляс\w*|арбамен|арбаға|кедергісіз\w*|"
            r"\bwheelchair\w*|\baccessible\b|\baccessibility\b|\bstep[ -]free\b"
        ),
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, query, re.I)]


def hard_reject(poi: POIRecord, intent: ResolvedIntent) -> bool:
    """Reject proven conflicts before spending route requests on a short list."""
    if (
        intent.available_minutes is not None
        and ENTRY_MINUTES + VISIT_MINUTES[poi.activity_code] + BUFFER_MINUTES
        > intent.available_minutes
    ):
        return True
    if intent.categories and poi.activity_code not in intent.categories:
        return True
    if sourced_field(poi, "indoor") and intent.indoor is not None:
        if poi.indoor != (intent.indoor == "indoor"):
            return True
    price = poi.price_kzt_per_person
    price_is_sourced = price is not None and any(
        "price_kzt_per_person" in item.fields for item in poi.provenance
    )
    if price_is_sourced:
        # Both an exact amount and a sourced lower bound can disprove an upper cap.
        if intent.budget_kzt_per_person is not None and price > intent.budget_kzt_per_person:
            return True
        if (
            sourced_field(poi, "price_kzt_per_person")
            and intent.minimum_budget_kzt is not None
            and price < intent.minimum_budget_kzt
        ):
            return True
    return False


_DAYS = {name: index for index, name in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"))}
_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su)"
_RULE = re.compile(rf"(?:(?P<days>{_DAY}(?:-{_DAY})?(?:,{_DAY}(?:-{_DAY})?)*)\s+)?(?P<times>.+)")
_INTERVAL = re.compile(r"(?P<start>\d{2}:\d{2})-(?P<end>\d{2}:\d{2})")


def _clock(value: str, *, end: bool = False) -> int | None:
    hours, minutes = map(int, value.split(":"))
    if end and hours == 24 and minutes == 0:
        return 1440
    return hours * 60 + minutes if hours < 24 and minutes < 60 else None


def _weekly_intervals(text: str) -> dict[int, list[tuple[int, int]]] | None:
    """Accept a deliberately narrow normalized weekly subset, not all OSM syntax."""
    if text == "24/7":
        return {day: [(0, 1440)] for day in range(7)}
    schedule: dict[int, list[tuple[int, int]]] = {}
    for raw_rule in text.split(";"):
        rule = _RULE.fullmatch(raw_rule.strip())
        if rule is None:
            return None
        days: set[int] = set()
        for part in rule["days"].split(",") if rule["days"] else ["Mo-Su"]:
            bounds = part.split("-")
            first, last = _DAYS[bounds[0]], _DAYS[bounds[-1]]
            days.update((first + offset) % 7 for offset in range((last - first) % 7 + 1))
        if any(day in schedule for day in days):
            # Overlapping rules can encode overrides; do not invent their precedence.
            return None
        intervals = []
        if rule["times"] not in ("off", "closed"):
            for raw_interval in rule["times"].split(","):
                interval = _INTERVAL.fullmatch(raw_interval.strip())
                if interval is None:
                    return None
                start = _clock(interval["start"])
                end = _clock(interval["end"], end=True)
                if start is None or end is None or start == end:
                    return None
                intervals.append((start, end if end > start else end + 1440))
        for day in days:
            schedule[day] = intervals
    return schedule


def opening_window(
    text: str | None, start: datetime, end: datetime, *, timezone: str = "Asia/Almaty"
) -> bool | None:
    """Check continuous opening from arrival through visit end, in the city timezone.

    PH/SH, dates, exceptions, comments, sunrise/sunset and unsupported syntax are
    unknown. Explicit weekly gaps are closed. Adjacent intervals are continuous.
    """
    if text is None or start.tzinfo is None or end.tzinfo is None or end <= start:
        return None
    schedule = _weekly_intervals(text.strip())
    if schedule is None:
        return None
    city_zone = ZoneInfo(timezone)
    try:
        start, end = start.astimezone(city_zone), end.astimezone(city_zone)
        # One previous day is necessary for a cross-midnight interval.
        first_date = start.date() - timedelta(days=1)
        last_date = end.date()
    except (OverflowError, ValueError):
        return None
    intervals = []
    for offset in range((last_date - first_date).days + 1):
        day = first_date + timedelta(days=offset)
        midnight = datetime.combine(day, time(), tzinfo=city_zone)
        for left, right in schedule.get(day.weekday(), []):
            try:
                intervals.append(
                    (midnight + timedelta(minutes=left), midnight + timedelta(minutes=right))
                )
            except (OverflowError, ValueError):
                return None
    covered_until = start
    for left, right in sorted(intervals):
        if left <= covered_until < right:
            covered_until = right
            if covered_until >= end:
                return True
    return False


def _travel(
    intent: ResolvedIntent, outbound: RouteLeg | None, return_route: RouteLeg | None
) -> tuple[RouteStatus, int | None]:
    legs = [outbound, return_route] if intent.return_to_start else [outbound]
    if intent.origin is not None and all(leg and leg.status == "known" for leg in legs):
        return RouteStatus.KNOWN, (sum(leg.duration_seconds for leg in legs) + 59) // 60
    unavailable = any(leg and leg.status == "unavailable" for leg in legs)
    return RouteStatus.UNAVAILABLE if unavailable else RouteStatus.UNKNOWN, None


def evaluate_poi(
    poi: POIRecord,
    intent: ResolvedIntent,
    outbound: RouteLeg | None = None,
    return_route: RouteLeg | None = None,
    *,
    timezone: str = "Asia/Almaty",
) -> FitEvaluation:
    """Evaluate one independent alternative; visit duration is our recommendation."""
    missing: list[MissingField] = []
    reasons = [ReasonCode.VISIT_DURATION_ESTIMATE]
    rejected = hard_reject(poi, intent)
    visit = VISIT_MINUTES[poi.activity_code]
    if (
        intent.origin is not None
        and sourced_field(poi, "location")
        and intent.available_minutes is not None
    ):
        legs = [outbound, return_route] if intent.return_to_start else [outbound]
        known_seconds = sum(
            leg.duration_seconds for leg in legs if leg is not None and leg.status == "known"
        )
        # Unknown legs cannot hide a conflict already proved by the known travel.
        if known_seconds + (ENTRY_MINUTES + visit + BUFFER_MINUTES) * 60 > (
            intent.available_minutes * 60
        ):
            rejected = True
    route_status, travel = _travel(intent, outbound, return_route)
    if travel is not None and travel > MAX_CARD_TRAVEL_MINUTES:
        if (
            intent.available_minutes is not None
            and travel + ENTRY_MINUTES + visit + BUFFER_MINUTES > intent.available_minutes
        ):
            rejected = True
        # S02 permits a week for each leg; CardDetails permits a week in total.
        # Preserve the shared schema instead of publishing an invalid duration.
        route_status, travel = RouteStatus.UNKNOWN, None
    if intent.origin is None:
        missing.append(MissingField.ORIGIN)
    if not sourced_field(poi, "location"):
        missing.append(MissingField.LOCATION)
        route_status, travel = RouteStatus.UNKNOWN, None
    if travel is None:
        missing.append(MissingField.TRAVEL_MINUTES)
        reasons.append(ReasonCode.ROUTE_UNKNOWN)
    total = travel + ENTRY_MINUTES + visit + BUFFER_MINUTES if travel is not None else None
    if intent.available_minutes is None:
        missing.append(MissingField.AVAILABLE_MINUTES)
    elif ENTRY_MINUTES + visit + BUFFER_MINUTES > intent.available_minutes:
        rejected = True
    elif total is not None and total > intent.available_minutes:
        rejected = True
    if intent.minimum_minutes is not None and total is not None and total < intent.minimum_minutes:
        rejected = True
    if total is not None and intent.available_minutes is not None and not rejected:
        reasons.append(ReasonCode.WITHIN_TIME)
    else:
        reasons.append(ReasonCode.TIME_UNKNOWN)
    if intent.date_time is None:
        missing.append(MissingField.DATE_TIME)
    open_during_visit = None
    if (
        sourced_field(poi, "opening_hours_text")
        and intent.date_time is not None
        and intent.origin is not None
        and sourced_field(poi, "location")
        and outbound is not None
        and outbound.status == "known"
    ):
        try:
            arrival = intent.date_time + timedelta(seconds=outbound.duration_seconds)
            open_during_visit = opening_window(
                poi.opening_hours_text,
                arrival,
                arrival + timedelta(minutes=ENTRY_MINUTES + visit),
                timezone=timezone,
            )
        except (OverflowError, ValueError):
            # Valid datetime extremes still need representable arrival/visit instants.
            open_during_visit = None
    if open_during_visit is None:
        missing.append(MissingField.OPENING_HOURS)
        reasons.append(ReasonCode.HOURS_UNKNOWN)
    elif not open_during_visit:
        rejected = True
    if intent.budget_kzt_per_person is not None or intent.minimum_budget_kzt is not None:
        if not sourced_field(poi, "price_kzt_per_person"):
            missing.append(MissingField.PRICE)
            reasons.append(ReasonCode.BUDGET_UNKNOWN)
        elif not rejected:
            reasons.append(ReasonCode.WITHIN_BUDGET)
    if intent.indoor is not None:
        if not sourced_field(poi, "indoor"):
            missing.append(MissingField.INDOOR)
        elif not rejected:
            reasons.append(ReasonCode.INDOOR_MATCH)
    fit = FitStatus.DOES_NOT_FIT if rejected else FitStatus.UNKNOWN if missing else FitStatus.FITS
    return FitEvaluation(
        fit_status=fit,
        missing_fields=tuple(dict.fromkeys(missing)),
        reason_codes=tuple(dict.fromkeys(reasons)),
        visit_minutes_estimate=visit,
        route_status=route_status,
        travel_minutes_estimate=travel,
        warnings=(),
        rejected=rejected,
        total_minutes=total,
    )
