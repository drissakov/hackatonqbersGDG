"""Small source-bound guards, not a general event-status or schedule parser."""

import re
from datetime import datetime

from backend.app.services.events.grounding import source_spans
from backend.app.services.events.models import NormalizedSession, SearchEvidence
from backend.app.services.events.normalize import ASTANA_TIMEZONE, MONTH_NAMES
from backend.app.services.events.venue import normalize_venue_text

CLAUSE_BREAK = re.compile(r"[;\n]|(?<!\d)[.!?](?:\s|$)")
CANCELLATION = re.compile(
    r"\b(?:cancelled|canceled|отмен[её]н(?:а|о|ы)?|күші\s+жойылды|тоқтатылды)\b",
    re.IGNORECASE,
)
NEGATED_CANCELLATION = re.compile(
    r"\b(?:not(?:\s+(?:been|be|being|yet|officially|currently))*"
    r"|never|не(?:\s+(?:был|была|было|были|будет))?)\s+$",
    re.IGNORECASE,
)
CONDITIONAL = re.compile(
    r"\b(?:if|when|unless|если|при|егер)\b|in\s+case|в\s+случае", re.IGNORECASE
)
CLOCK = re.compile(r"(?<![\d.])\d{1,2}[:.][0-5]\d(?![\d.])")
TEMPORAL_HINT = re.compile(
    r"\d|\b(?:today|tomorrow|yesterday|сегодня|завтра|вчера|бүгін|ертең|кеше"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|понедельник|вторник|сред[ау]|четверг|пятниц[ау]|суббот[ау]|воскресенье)\b|"
    + "|".join(re.escape(name) for names in MONTH_NAMES for name in names),
    re.IGNORECASE,
)
POLICY = re.compile(
    r"\b(?:refund\w*|policy|policies|возврат\w*|правил\w*|қайтар\w*)\b", re.IGNORECASE
)


def _session_anchor(start: datetime) -> re.Pattern[str]:
    local = start.astimezone(ASTANA_TIMEZONE)
    day, month, year = local.day, local.month, local.year
    names = "|".join(re.escape(name) for name in MONTH_NAMES[month - 1])
    date = (
        rf"(?:{year}-{month:02d}-{day:02d}|{day:02d}\.{month:02d}\.{year}"
        rf"|0?{day}\s+(?:{names})\s+{year}|(?:{names})\s+0?{day},?\s+{year}"
        rf"|{year}\s+жылғы\s+0?{day}\s+(?:{names}))"
    )
    return re.compile(
        rf"(?<!\d){date}(?!\d)\s*[,t]?\s*(?:(?:at|в|сағат)\s+)?"
        rf"0?{local.hour}[:.]{local.minute:02d}(?!\d)",
        re.IGNORECASE,
    )


def _distance(left: re.Match[str], right: re.Match[str]) -> int:
    return max(left.start() - right.end(), right.start() - left.end(), 0)


def _direct_title_statement(clause: str, cancellation: re.Match[str], title: str) -> bool:
    before = normalize_venue_text(clause[: cancellation.start()])
    after = normalize_venue_text(clause[cancellation.end() :])
    punctuation = r"[\s\"'«»—–:()\-]*"
    return bool(
        re.search(
            re.escape(title) + punctuation + r"(?:(?:is|was|has been|был|была|было)\s*)?$",
            before,
        )
        or re.match(punctuation + re.escape(title) + r"(?!\w)", after)
    )


def has_source_cancellation(
    session: NormalizedSession, evidence: SearchEvidence | None, *, event_title: str | None = None
) -> bool:
    """Recognize an explicit cancellation next to this exact source/date/start.

    The date includes its year and the nearest clock must be this session's clock.
    Other dates, sessions, conditional refund rules and explicit negations do not
    establish a cancellation. Ambiguous prose remains unverified; this deliberately
    does not infer status from a whole page, another URL, or a model's label.
    """
    if evidence is None or session.starts_at is None:
        return False
    anchor = _session_anchor(session.starts_at)
    title = normalize_venue_text(event_title)
    spans = source_spans(evidence, session.source_url)
    source_has_anchor = any(anchor.search(span) for span in spans)
    for span in spans:
        for clause in CLAUSE_BREAK.split(span):
            anchors = list(anchor.finditer(clause))
            if CONDITIONAL.search(clause):
                continue
            # A source can state "<exact event title> cancelled" separately from
            # its schedule. Accept only a direct title-level statement without
            # other temporal qualifiers or generic ticket/refund policy wording.
            normalized = normalize_venue_text(clause)
            title_statement = bool(
                title
                and title in normalized
                and source_has_anchor
                and not TEMPORAL_HINT.search(normalized.replace(title, "", 1))
                and not POLICY.search(clause)
            )
            if not anchors and not title_statement:
                continue
            clocks = list(CLOCK.finditer(clause))
            target_clocks = {
                clock.span()
                for clock in clocks
                if any(
                    start.start() <= clock.start() and clock.end() <= start.end()
                    for start in anchors
                )
            }
            for cancellation in CANCELLATION.finditer(clause):
                if NEGATED_CANCELLATION.search(clause[: cancellation.start()]):
                    continue
                if title_statement and _direct_title_statement(clause, cancellation, title):
                    return True
                nearest = min((_distance(cancellation, clock) for clock in clocks), default=None)
                matches = [clock for clock in clocks if _distance(cancellation, clock) == nearest]
                if len(matches) == 1 and matches[0].span() in target_clocks:
                    return True
    return False
