"""Deterministic single-destination constraints; no provider calls or inferred facts."""

import re
from collections.abc import Iterable
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
MIN_WALK_MINUTES = 10
MIN_PLAYGROUND_MINUTES = 10
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


def _detected_requirement_codes(query: str, *, interests: Iterable[str] = ()) -> list[str]:
    """Identify unsupported conditions, keeping age separate from child suitability.

    Audit both the original query and explicit requirements retained by extraction.
    This is a bounded presence check, not a general language or negation parser.
    """
    devices = (
        r"(?:телефон\w*|смартфон\w*|ноутбу[кг]\w*|планшет\w*|гаджет\w*|аккумулятор\w*|"
        r"(?:smart)?phones?|laptops?|tablets?|devices?|batter(?:y|ies)|cars?)"
    )
    charging = r"(?:(?:под)?заряд\w*|(?:под)?заряж\w*|(?:re)?charg(?:e|ing))"
    nearby_words = r"(?:\s+[\w-]+){0,3}\s+"
    russian_age = (
        r"(?:\d{1,2}|одного|двух|тр[её]х|четыр[её]х|пяти|шести|семи|восьми|девяти|"
        r"десяти|одиннадцати|двенадцати|тринадцати|четырнадцати|пятнадцати|"
        r"шестнадцати|семнадцати|восемнадцати|один|два|три|четыре|пять|шесть|семь|"
        r"восемь|девять|десять|одиннадцать|двенадцать|тринадцать|четырнадцать|"
        r"пятнадцать|шестнадцать|семнадцать|восемнадцать)"
    )
    english_age = (
        r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen)"
    )
    patterns = {
        "quiet": (
            r"\bтих\w*|\bтишин\w*|\bспокойн\w*|\bүнсіз\w*|\bтыныш\w*|\bшусыз\w*|"
            r"\bquiet\w*|\bsilent\w*|\bpeaceful\b"
        ),
        "power_outlets": (
            r"розет\w*|қуатта\w*|зарядта\w*|(?:тоқ|ток|қуат)\s+көзі|"
            r"\boutlets?\b|\bsockets?\b|\b(?:re)?chargers?\b|"
            r"\bcharging[ -]+(?:points?|stations?|ports?|facilities)\b|"
            r"\b(?:wireless|usb(?:[ -]c)?)[ -]+charg(?:ing|ers?)\b|"
            r"\b(?:with|has|offers?)\s+(?:(?:free|wireless)\s+)?charging\b|"
            r"\b(?:re)?charging\s+(?:is\s+)?(?:required|needed|available)\b|"
            r"\b(?:с|со)\s+(?:под)?зарядк\w*\b|"
            r"\b(?:есть|нужна|доступна)\s+(?:ли\s+)?(?:под)?зарядк\w*\b|"
            r"\bзарядн\w*\s+(?:станц\w*|устройств\w*|точк\w*)\b|"
            rf"\b{charging}{nearby_words}{devices}\b|"
            rf"\b{devices}{nearby_words}{charging}\b"
        ),
        "accessibility": (
            r"доступн\w*\s+(?:сред\w*|для\s+(?:коляс\w*|инвалид\w*))|"
            r"доступность|безбарьер\w*|пандус\w*|коляс\w*|арбамен|арбаға|кедергісіз\w*|"
            r"\bwheelchair\w*|\baccessible\b|\baccessibility\b|\bstep[ -]free\b"
        ),
        "child_suitability": (
            r"\bреб[её]н\w*|\bдет(?:и|ей|ям|ьми|ок)\b|\bмалыш\w*|"
            r"\bмладен\w*|\bподрост\w*|"
            r"\bдля\s+(?:всей|моей|нашей)\s+семьи\b|\bс\s+семь[её]й\b|"
            r"\bсемейн\w*\s+(?:досуг|прогулк\w*|отдых)\b|"
            r"\bбала(?:мен|м\w*|ға|ны|ның|сы\w*|лар(?:мен|ға|ды|дың))\b|"
            r"\bбала(?:лар)?\s+үшін\b|\bотбасымен\b|"
            r"\bжастағы\s+бала(?:лар)?\b|\bнәрест\w*|\bбүлдіршін\w*|"
            r"\b(?:with|for|my|our)\s+(?:[\w-]+\s+){0,4}"
            r"(?:child(?:ren)?|kids?|bab(?:y|ies)|toddlers?|infants?|teen(?:ager)?s?)\b|"
            r"\b(?:children|kids)\s+(?:are\s+)?(?:welcome|allowed)\b|"
            r"\b(?:child(?:ren)?|kids?|family)[ -](?:friendly|free)\b|"
            r"\bfor\s+(?:the\s+whole|my|our)\s+family\b|\bno\s+(?:children|kids)\b"
        ),
        "age_restrictions": (
            r"\bвозрастн\w*\s+(?:огранич\w*|допуск\w*)|"
            r"\b(?:\d{1,2}[ -]|одно|двух|тр[её]х|четыр[её]х|пяти|шести|семи|восьми|"
            r"девяти|десяти|одиннадцати|двенадцати|тринадцати|четырнадцати|пятнадцати|"
            r"шестнадцати|семнадцати|восемнадцати)летн\w*|"
            r"\b(?:реб[её]н\w*|дет(?:и|ей|ям|ьми)|малыш\w*|подрост\w*)\s+"
            r"(?:в\s+возрасте\s+)?(?:(?:от|до|старше|младше)\s+)?"
            rf"{russian_age}\s+(?:лет|года?|месяц\w*)\b|"
            r"\b(?:реб[её]н\w*|дет(?:и|ей|ям|ьми))\b[^.!?;]{0,40}"
            rf"{russian_age}\s+(?:лет|года?|месяц\w*)\b|"
            rf"\b{russian_age}\s+(?:лет|года?|месяц\w*)\b[^.!?;]{{0,40}}"
            r"\b(?:реб[её]н\w*|дет(?:и|ей|ям|ьми))\b|"
            r"\bжас\s+шекте\w*|\bжасқа\s+(?:лайық|сай|сәйкес|арналған)\w*|"
            r"\b(?:жастағы|жасар)\s+бала\w*|"
            r"\b(?:\d{1,2}|бір|екі|үш|төрт|бес|алты|жеті|сегіз|тоғыз|он)\s+"
            r"(?:жаста(?:ғы)?|жасар|айлық)\b|"
            r"\b\w+[ -](?:years?|months?)[ -]olds?\b|"
            rf"\bage[sd]?\s+{english_age}\b|"
            r"\b(?:child(?:ren)?|kids?|sons?|daughters?)\b[^.!?;]{0,40}"
            rf"{english_age}\s+(?:years?|months?)\b|"
            r"\bage[ -]+(?:restrictions?|limits?|appropriate|suitab\w*)\b|"
            r"\ball\s+ages\b|\badults?[ -]only\b"
        ),
    }
    interests = tuple(interests)
    texts = (query, *interests)
    detected = {
        name
        for name, pattern in patterns.items()
        if any(re.search(pattern, text, re.I) for text in texts)
    }
    aliases = {
        "child suitability": "child_suitability",
        "age restrictions": "age_restrictions",
        "age limits": "age_restrictions",
        "child friendly": "child_suitability",
        "family friendly": "child_suitability",
        "power outlets": "power_outlets",
        "charging": "power_outlets",
        "charging point": "power_outlets",
    }
    for interest in interests:
        normalized = re.sub(r"[\s_-]+", " ", interest.casefold()).strip()
        if normalized in aliases:
            detected.add(aliases[normalized])
    return [name for name in patterns if name in detected]


def unsupported_requirements(query: str, *, interests: Iterable[str] = ()) -> list[str]:
    """Preserve the existing coarse guard groups used for uncertainty messages."""
    detected = set(_detected_requirement_codes(query, interests=interests))
    if "age_restrictions" in detected:
        detected.add("child_suitability")
    return [
        code
        for code in ("quiet", "power_outlets", "accessibility", "child_suitability")
        if code in detected
    ]


def unsupported_requirement_fields(
    query: str, *, interests: Iterable[str] = ()
) -> list[MissingField]:
    """Return stable display reasons without sending or parsing provider prose."""
    detected = set(_detected_requirement_codes(query, interests=interests))
    return [
        field
        for field in (
            MissingField.CHILD_SUITABILITY,
            MissingField.AGE_RESTRICTIONS,
            MissingField.POWER_OUTLETS,
        )
        if field.value in detected
    ]


def suggested_visit_minutes(
    poi: POIRecord,
    intent: ResolvedIntent,
    *,
    known_travel_seconds: int = 0,
    playground: bool = False,
) -> int:
    """Shorten suggested walks or proved playground visits within the time budget.

    Unknown legs are not zero estimates: this budget is only an upper bound on
    possible visit time. Fit evaluation still requires every requested leg.
    The caller must derive playground from source evidence, never a category guess.
    """
    default = VISIT_MINUTES[poi.activity_code]
    if (
        poi.activity_code != ActivityCode.WALK and not playground
    ) or intent.available_minutes is None:
        return default
    remaining = (
        intent.available_minutes
        - ENTRY_MINUTES
        - BUFFER_MINUTES
        - (known_travel_seconds + 59) // 60
    )
    minimum = MIN_PLAYGROUND_MINUTES if playground else MIN_WALK_MINUTES
    return max(minimum, min(default, remaining))


def hard_reject(poi: POIRecord, intent: ResolvedIntent, *, playground: bool = False) -> bool:
    """Reject proven conflicts before spending route requests on a short list."""
    if (
        intent.available_minutes is not None
        and ENTRY_MINUTES
        + suggested_visit_minutes(poi, intent, playground=playground)
        + BUFFER_MINUTES
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
    playground: bool = False,
) -> FitEvaluation:
    """Evaluate one independent alternative; visit duration is our recommendation."""
    missing: list[MissingField] = []
    reasons = [ReasonCode.VISIT_DURATION_ESTIMATE]
    rejected = hard_reject(poi, intent, playground=playground)
    known_seconds = 0
    if intent.origin is not None and sourced_field(poi, "location"):
        legs = [outbound, return_route] if intent.return_to_start else [outbound]
        known_seconds = sum(
            leg.duration_seconds for leg in legs if leg is not None and leg.status == "known"
        )
    visit = suggested_visit_minutes(
        poi, intent, known_travel_seconds=known_seconds, playground=playground
    )
    # Unknown legs cannot hide a conflict already proved by the known travel.
    if intent.available_minutes is not None:
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
