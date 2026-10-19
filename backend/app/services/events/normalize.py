"""Conservative normalization. Extraction is discovery, never verification."""

import hashlib
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from backend.app.schemas import POIRecord
from backend.app.services.events.grounding import (
    ground_metadata,
    ground_price,
    source_spans,
    source_titles,
)
from backend.app.services.events.models import (
    CandidateEvent,
    DiscoveryResult,
    FieldCheck,
    NormalizedEvent,
    NormalizedSession,
    SearchEvidence,
    SessionFacts,
)
from backend.app.services.events.venue import match_venue, normalize_venue_text

logger = logging.getLogger(__name__)
ASTANA_TIMEZONE = ZoneInfo("Asia/Almaty")
ASTANA_NAMES = {"astana", "астана", "astana qalasy", "астана қаласы", "астана қ.", "г. астана"}
MONTH_NAMES = (
    ("january", "января", "қаңтар"),
    ("february", "февраля", "ақпан"),
    ("march", "марта", "наурыз"),
    ("april", "апреля", "сәуір"),
    ("may", "мая", "мамыр"),
    ("june", "июня", "маусым"),
    ("july", "июля", "шілде"),
    ("august", "августа", "тамыз"),
    ("september", "сентября", "қыркүйек"),
    ("october", "октября", "қазан"),
    ("november", "ноября", "қараша"),
    ("december", "декабря", "желтоқсан"),
)
UNSUPPORTED_CLOCK_SUFFIX = re.compile(
    r"[ \t\u00a0\u202f*_`\"'»”’]*(?:,[ \t]*)?(?:[\[(][ \t]*)?(?:по[ \t]+)?"
    r"(?:(?:[ap]\.?[ \t]*m\.?|utc|gmt|msk|мск|z)(?!\w)"
    r"|[+−-](?:[01]?\d|2[0-3])(?::?[0-5]\d)?(?!\w)(?![:.]\d))",
    re.IGNORECASE,
)


def _identity(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:24]


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware timestamp is required")


def _listing_url(url: str) -> bool:
    path = urlsplit(url).path.rstrip("/").casefold()
    return path.split("/")[-1] in {
        "",
        "ru",
        "en",
        "kk",
        "kz",
        "afisha",
        "posters",
        "schedule",
        "events",
    }


def _merge_sessions(sessions: Sequence[NormalizedSession]) -> list[NormalizedSession]:
    merged: dict[str, NormalizedSession] = {}
    for session in sessions:
        previous = merged.get(session.session_id)
        if previous is None:
            merged[session.session_id] = session
        elif any(
            getattr(previous, field) != getattr(session, field)
            for field in (
                "starts_at",
                "ends_at",
                "price_from",
                "currency",
                "price_conditions",
                "price_kind",
                "status",
                "city",
                "venue_name",
                "venue_address",
            )
        ):
            # A cancellation dominates; every other conflict blocks recommendations.
            chosen = session if session.status == "cancelled" else previous
            merged[session.session_id] = chosen.model_copy(
                update={
                    "recommendation_candidate": False,
                    "exclusion_reasons": sorted(
                        set(chosen.exclusion_reasons + ["source_conflict"])
                    ),
                }
            )
    return list(merged.values())


def _timestamp(
    value: str | None, source_text: str | None, supporting_spans: Sequence[str]
) -> datetime | None:
    # Never invent a year from the query, publication date or retrieval time.
    if not value:
        if source_text:
            return _unknown_timestamp("extracted_datetime_missing")
        return None
    if not source_text:
        return _unknown_timestamp("source_quote_missing")
    if not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return _unknown_timestamp("datetime_format_invalid")
    try:
        parsed = datetime.fromisoformat(value)
        require_aware(parsed)
        local = parsed.astimezone(ASTANA_TIMEZONE)
    except (ValueError, OverflowError):
        return _unknown_timestamp("datetime_invalid_or_naive")
    # Seconds/microseconds need explicit precision support before they can be facts.
    if local.second or local.microsecond:
        return _unknown_timestamp("datetime_precision_unsupported")
    supported = [span for span in supporting_spans if source_text in span]
    if not supported:
        return _unknown_timestamp("source_quote_not_literal")
    text = source_text.casefold()
    day, month, year = local.day, local.month, local.year
    names = "|".join(MONTH_NAMES[month - 1])
    numeric_day = rf"0?{day}" if day < 10 else str(day)
    numeric_month = rf"0?{month}" if month < 10 else str(month)
    dates = (
        rf"(?<!\d){year}-{month:02d}-{day:02d}(?!\d)",
        rf"(?<!\d){numeric_day}\.{numeric_month}\.{year}(?!\d)",
        rf"(?<!\d)0?{day}[ \t]+(?:{names})[ \t]+{year}(?!\d)",
        rf"\b(?:{names})[ \t]+0?{day},?[ \t]+{year}(?!\d)",
        rf"(?<!\d){year}[ \t]+жылғы[ \t]+0?{day}[ \t]+(?:{names})\b",
    )
    if not any(re.search(pattern, text) for pattern in dates):
        return _unknown_timestamp(
            "source_date_mismatch_or_unsupported"
            if re.search(r"(?<!\d)\d{4}(?!\d)", text)
            else "source_year_missing"
        )
    clock = rf"0?{local.hour}[:.]{local.minute:02d}(?::00(?:\.0+)?)?(?!\d)(?![:.]\d)"
    # Bind one date to its following clock, rather than combining tokens from
    # different sessions or jumping across prose inside a cited paragraph.
    date_ending = r"[*_`]{0,3}[ \t]*(?:(?:года|г\.?|жыл(?:ы|ғы)?)(?!\w)[ \t]*)?"
    inline_separator = r"(?:[,;:|—–t-][ \t]*)?(?:(?:at|в|сағат)(?!\w)[ \t]+)?[*_`]{0,3}"
    time_label = (
        r"(?:время(?:[ \t]+начала)?|начало(?:[ \t]+сеанса)?|start[ \t]+time|starts?|time"
        r"|басталу[ \t]+уақыты|уақыты|басталуы)"
    )
    labeled_separator = (
        r"(?:[.,;:|—–-][ \t]*)?(?:\r?\n[ \t]*)?[*_`]{0,3}"
        + time_label
        + r"(?!\w)[ \t]*(?::[ \t]*)?[*_`]{0,3}[ \t]*"
        r"(?:(?:at|в|сағат)(?!\w)[ \t]+)?[*_`]{0,3}"
    )
    separator = date_ending + "(?:" + inline_separator + "|" + labeled_separator + ")"
    anchors = [re.compile(pattern + separator + clock) for pattern in dates]
    # Extraction may quote just the explicit date. Extend only that exact quoted
    # occurrence to an immediately following clock in the same source span.
    # A quote with its own clock cannot be replaced by another session's time.
    quoted_clock = (
        r"(?<!\d)(?:[01]?\d|2[0-3])[:.][0-5]\d"
        r"(?::[0-5]\d(?:\.\d+)?)?(?!\d)(?![:.]\d)"
    )
    quote_has_clock = re.search(quoted_clock, text) is not None
    unsupported_suffix = False
    for span in supported:
        folded_span = span.casefold()
        for occurrence in re.finditer(re.escape(text), folded_span):
            for pattern in anchors:
                for match in pattern.finditer(folded_span, occurrence.start()):
                    if match.start() >= occurrence.end():
                        break
                    if quote_has_clock:
                        if match.end() > occurrence.end():
                            continue
                    elif match.end() < occurrence.end():
                        continue
                    # Only bare local 24-hour clocks are supported. Inspect the
                    # actual span too: extraction may omit the timezone suffix.
                    if not UNSUPPORTED_CLOCK_SUFFIX.match(folded_span, match.end()):
                        return parsed
                    unsupported_suffix = True
    return _unknown_timestamp(
        "clock_suffix_unsupported" if unsupported_suffix else "clock_not_bound"
    )


def _unknown_timestamp(code: str) -> None:
    """Log only a caller-selected static reason, never source or request data."""
    logger.warning("event_timestamp_unknown code=%s", code)
    return None


def _session(
    facts: SessionFacts,
    row: CandidateEvent,
    event_id: str,
    evidence: SearchEvidence,
    now: datetime,
    selected_at: datetime,
    pois: Sequence[POIRecord],
    selected_date_only: bool,
) -> NormalizedSession | None:
    url = facts.source_url or row.source_url
    sources = {str(source.url): source for source in evidence.sources}
    cited = {str(citation.url) for citation in evidence.citations}
    if str(url) not in sources or str(url) not in cited:
        return None
    spans = source_spans(evidence, url)
    metadata = ground_metadata(row, spans, titles=source_titles(evidence, url))
    if metadata is None:
        return None
    start = (
        _timestamp(facts.starts_at, facts.date_text, spans)
        if facts.date_basis == "session" and not _listing_url(str(url))
        else None
    )
    end = _timestamp(facts.ends_at, facts.end_text, spans) if start else None
    if end is not None and end <= start:
        end = None
    reasons = []
    if _listing_url(str(url)):
        reasons.append("listing_only")
    if metadata.city is None:
        reasons.append("city_unknown")
    elif normalize_venue_text(metadata.city) not in ASTANA_NAMES:
        reasons.append("other_city")
    if start is None:
        reasons.append("schedule_unknown")
    else:
        if start < now:
            reasons.append("past_session")
        if start < selected_at:
            reasons.append("before_requested_start")
        if (
            selected_date_only
            and start.astimezone(ASTANA_TIMEZONE).date()
            != selected_at.astimezone(ASTANA_TIMEZONE).date()
        ):
            reasons.append("outside_selected_date")
    if facts.status == "cancelled":
        reasons.append("cancelled")
    elif facts.status == "unknown":
        reasons.append("status_unknown")
    venue = (
        match_venue(metadata.venue_name, metadata.venue_address, pois)
        if metadata.city and normalize_venue_text(metadata.city) in ASTANA_NAMES
        else match_venue(None, None, ())
    )
    price, currency, conditions, price_kind = ground_price(facts, spans)
    values = {
        "city": metadata.city,
        "venue_name": metadata.venue_name,
        "venue_address": metadata.venue_address,
        "location": venue.location,
        "starts_at": start,
        "ends_at": end,
        "price_from": price,
        "currency": currency,
        "price_conditions": conditions,
    }
    missing = [key for key, value in values.items() if value is None]
    if facts.status == "unknown":
        missing.append("status")
    return NormalizedSession(
        session_id=_identity(
            event_id,
            start.astimezone(UTC).isoformat()
            if start
            else f"{url}\x00{facts.date_text or 'unknown'}",
        ),
        event_id=event_id,
        source_url=url,
        source_fetched_at=sources[str(url)].fetched_at,
        city=metadata.city,
        venue_name=metadata.venue_name,
        venue_address=metadata.venue_address,
        venue=venue,
        starts_at=start,
        ends_at=end,
        price_from=price,
        currency=currency,
        price_conditions=conditions,
        price_kind=price_kind,
        status=facts.status,
        missing_fields=missing,
        recommendation_candidate=not reasons,
        exclusion_reasons=reasons,
    )


def _exclude_ambiguous_cancellations(events: Sequence[NormalizedEvent]) -> None:
    """Block compatible partial identities without merging distinct venue branches."""
    cancellations = [
        (event, session)
        for event in events
        for session in event.sessions
        if session.status == "cancelled"
    ]
    for event in events:
        for index, session in enumerate(event.sessions):
            if not session.recommendation_candidate:
                continue
            for cancelled_event, cancelled in cancellations:
                same_title = normalize_venue_text(event.title) == normalize_venue_text(
                    cancelled_event.title
                )
                venue_pairs = (
                    (session.venue_name, cancelled.venue_name),
                    (session.venue_address, cancelled.venue_address),
                )
                incompatible_branch = any(
                    left and right and normalize_venue_text(left) != normalize_venue_text(right)
                    for left, right in venue_pairs
                )
                # Keep source-scoped identities separate, but a matching title,
                # complete venue and instant on another source still makes
                # cancellation a reason to withhold a recommendation.
                same_event = same_title and (
                    event.source_url == cancelled_event.source_url
                    or (
                        all(left and right for left, right in venue_pairs)
                        and cancelled.starts_at is not None
                        and cancelled.starts_at == session.starts_at
                    )
                )
                same_or_unknown_start = (
                    cancelled.starts_at is None or cancelled.starts_at == session.starts_at
                )
                if same_event and not incompatible_branch and same_or_unknown_start:
                    event.sessions[index] = session.model_copy(
                        update={
                            "recommendation_candidate": False,
                            "exclusion_reasons": sorted(
                                set(session.exclusion_reasons + ["unresolved_cancellation"])
                            ),
                        }
                    )
                    break


def normalize_events(
    rows: Sequence[CandidateEvent],
    evidence: SearchEvidence,
    *,
    now: datetime,
    selected_at: datetime,
    pois: Sequence[POIRecord] = (),
    selected_date_only: bool = True,
) -> DiscoveryResult:
    require_aware(now)
    require_aware(selected_at)
    sources = {str(source.url): source for source in evidence.sources}
    cited = {str(citation.url) for citation in evidence.citations}
    events: dict[str, NormalizedEvent] = {}
    rejected = excluded = 0
    for row in rows:
        if str(row.source_url) not in sources or str(row.source_url) not in cited:
            rejected += 1
            continue
        row = ground_metadata(
            row,
            source_spans(evidence, row.source_url),
            titles=source_titles(evidence, row.source_url),
        )
        if row is None:
            rejected += 1
            continue
        if row.city is not None and normalize_venue_text(row.city) not in ASTANA_NAMES:
            rejected += 1
            continue
        event_id = _identity(
            str(row.source_url),
            normalize_venue_text(row.title),
            normalize_venue_text(row.venue_name),
            normalize_venue_text(row.venue_address),
        )
        sessions = []
        # A calendar listing is useful evidence, but cannot confirm a particular session.
        is_listing = row.page_kind == "listing" or _listing_url(str(row.source_url))
        if not is_listing:
            for facts in row.sessions:
                session = _session(
                    facts, row, event_id, evidence, now, selected_at, pois, selected_date_only
                )
                if session is None:
                    excluded += 1
                else:
                    sessions.append(session)
        previous_event = events.get(event_id)
        if previous_event:
            is_listing = is_listing or previous_event.status == "listing"
            sessions = previous_event.sessions + sessions
        sessions = [] if is_listing else _merge_sessions(sessions)
        venue = (
            match_venue(row.venue_name, row.venue_address, pois)
            if row.city
            else match_venue(None, None, ())
        )
        missing = [
            field
            for field in ("city", "venue_name", "venue_address")
            if getattr(row, field) is None
        ]
        if not venue.location:
            missing.append("location")
        if not sessions:
            missing.append("sessions")
        events[event_id] = NormalizedEvent(
            event_id=event_id,
            title=row.title,
            source_url=row.source_url,
            source_fetched_at=sources[str(row.source_url)].fetched_at,
            city=row.city,
            venue_name=row.venue_name,
            venue_address=row.venue_address,
            venue=venue,
            status="listing" if is_listing or not sessions else "discovered",
            schedule_hints=list(
                dict.fromkeys(
                    (previous_event.schedule_hints if previous_event else [])
                    + [facts.date_text for facts in row.sessions if facts.date_text]
                )
            ),
            missing_fields=missing,
            sessions=sessions,
        )
    _exclude_ambiguous_cancellations(list(events.values()))
    return DiscoveryResult(
        provider_status="partial" if events else "unknown",
        provider_code="unverified_source_facts" if events else "no_grounded_events",
        live_web_search="not_run",
        evidence=evidence,
        events=list(events.values()),
        excluded_sessions=excluded
        + sum(
            not session.recommendation_candidate
            for event in events.values()
            for session in event.sessions
        ),
        rejected_events=rejected,
    )


def verify_session(
    session: NormalizedSession, *, checks: Sequence[FieldCheck]
) -> NormalizedSession:
    """Mark only matching, explicitly checked fields. This does not confirm tickets or fit."""
    accepted: dict[str, FieldCheck] = {}
    # Existing checks must still match after any caller-side model copy/update.
    for check in [*session.verified_fields, *checks]:
        value = getattr(session, check.field)
        expected = value.isoformat() if isinstance(value, datetime) else value
        if (
            check.session_id != session.session_id
            or value is None
            or check.value != expected
            or check.source_url != session.source_url
            or check.checked_at < session.source_fetched_at
        ):
            raise ValueError("Check must match the session field, source and retrieval time")
        accepted[check.field] = check
    return session.model_copy(
        update={
            "verified_fields": list(accepted.values()),
            "verification_status": "verified" if accepted else "discovered",
        }
    )
