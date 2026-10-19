"""Ground extracted runtime facts in cited response text, never in URL guesses."""

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import HttpUrl

from backend.app.services.events.models import CandidateEvent, SearchEvidence, SessionFacts
from backend.app.services.events.venue import normalize_venue_text

ASTANA_NAMES = ("astana", "астана", "astana qalasy", "астана қаласы", "астана қ.", "г. астана")
PriceKind = Literal["starting", "regular", "promotion", "unknown"]
Price = tuple[int | None, Literal["KZT"] | None, str | None, PriceKind]
UNKNOWN_PRICE: Price = (None, None, None, "unknown")
AMOUNT = r"(?:\d{1,3}(?: \d{3})+|\d+)"
CURRENCY = r"(?:kzt|₸|тг\.?|тенге|теңге(?:ден)?)"
PRICE = re.compile(
    rf"(?<![\w.,])(?:(?P<amount>{AMOUNT})\s*(?P<currency>{CURRENCY})(?!\w)"
    rf"|(?P<prefix>{CURRENCY})\s*(?P<prefix_amount>{AMOUNT})(?![\w.,]))"
)
FREE = re.compile(r"(?<!\w)(?:free|бесплатно|тегін|вход свободный)(?!\w)")
ADMISSION = re.compile(
    r"\b(?:admission|entry|entrance|tickets?|вход|билет\w*|посещени\w*|кіру|бағасы|цена)\b"
)
PROMOTION = re.compile(
    r"\b(?:promo\w*|discount\w*|sale|early[ -]bird|акци\w*|скидк\w*|жеңілдік\w*)\b"
)
STARTING = re.compile(r"\b(?:from|starting(?: at)?|от|бастап)\b")
REGULAR = re.compile(r"\b(?:regular|standard|ordinary|обычн\w*|стандартн\w*|қалыпты)\b")


def source_spans(evidence: SearchEvidence, url: HttpUrl) -> list[str]:
    """Return only response contexts associated with this exact cited URL."""
    return [
        citation.context.strip() or citation.text
        for citation in evidence.citations
        if citation.url == url
    ]


def source_titles(evidence: SearchEvidence, url: HttpUrl) -> list[str]:
    """Source titles can identify an event, never supply its session facts."""
    return [citation.title for citation in evidence.citations if citation.url == url]


def _supported(value: str | None, spans: Sequence[str]) -> str | None:
    normalized = normalize_venue_text(value)
    return value if normalized and any(normalized in span for span in spans) else None


def _word(value: str, spans: Sequence[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", span) for span in spans)


def ground_metadata(
    row: CandidateEvent, spans: Sequence[str], *, titles: Sequence[str] = ()
) -> CandidateEvent | None:
    """Drop unsupported metadata; another session URL must support the event title."""
    normalized = [normalize_venue_text(span) for span in spans]
    title = normalize_venue_text(row.title)
    if not title:
        return None
    normalized_titles = [normalize_venue_text(title) for title in titles]
    if _supported(row.title, normalized) is None and not _word(title, normalized_titles):
        return None
    city = normalize_venue_text(row.city)
    names = ASTANA_NAMES if city in ASTANA_NAMES else (city,)
    supported_city = row.city if city and any(_word(name, normalized) for name in names) else None
    return row.model_copy(
        update={
            "city": supported_city,
            "venue_name": _supported(row.venue_name, normalized),
            "venue_address": _supported(row.venue_address, normalized),
        }
    )


def _kind(phrase: str) -> PriceKind | None:
    promotion, regular = bool(PROMOTION.search(phrase)), bool(REGULAR.search(phrase))
    if promotion and regular:
        return None
    if promotion:
        return "promotion"
    if STARTING.search(phrase):
        return "starting"
    return "regular" if regular else "unknown"


def _ambiguous(phrase: str, match: re.Match[str]) -> bool:
    before, after = phrase[: match.start()], phrase[match.end() :]
    return bool(
        re.search(
            r"(?:[-–—]\s*|\d\s*(?:/|to|до)\s*|\b(?:up to|до|less than)\s*"
            r"|\b(?:discount(?: of| in the amount of| amounting to| worth)?"
            r"|скидка(?: на| в размере)?)\s*)$",
            before,
        )
        or re.match(r"\s*[-–—/]\s*\d", after)
        or re.match(r"\s*(?:discount\b|off\b|скидк\w*|жеңілдік\w*)", after)
        or re.search(r"\bдейін\b", after)
        or re.search(r"\b(?:not|не|емес|cashback|refund|кэшбэк|возврат)\b", phrase)
    )


def ground_price(facts: SessionFacts, spans: Sequence[str]) -> Price:
    """Keep a price only with an unambiguous amount/currency phrase in evidence.

    Kind comes from that phrase, not the extractor's label. Explicit free entry
    can support zero without proving a currency. No rate or ordinary-price guess.
    """
    amount = facts.price_from
    if amount is None:
        return UNKNOWN_PRICE
    normalized = [normalize_venue_text(span) for span in spans]
    conditions = _supported(facts.price_conditions, normalized)
    matches: set[tuple[Literal["KZT"] | None, PriceKind]] = set()
    for span in spans:
        for phrase in re.split(r"[;\n]|[.!?](?:\s|$)", span):
            phrase = normalize_venue_text(phrase)
            prices = list(PRICE.finditer(phrase))
            relevant = [
                match
                for match in prices
                if ((match["amount"] or match["prefix_amount"]).replace(" ", "").lstrip("0") or "0")
                == str(amount)
            ]
            if relevant:
                if len(prices) != 1 or _ambiguous(phrase, relevant[0]):
                    return UNKNOWN_PRICE
                kind = _kind(phrase)
                if kind is None:
                    return UNKNOWN_PRICE
                matches.add(("KZT", kind))
            elif amount == 0 and FREE.search(phrase):
                if prices or not (FREE.fullmatch(phrase) or ADMISSION.search(phrase)):
                    continue
                # Free parking/delivery and negated wording do not price admission.
                if re.search(r"\b(?:parking|парковк\w*|delivery|доставк\w*|not|не|емес)\b", phrase):
                    continue
                kind = _kind(phrase)
                if kind is None:
                    return UNKNOWN_PRICE
                currency = "KZT" if re.search(rf"(?<!\w){CURRENCY}(?!\w)", phrase) else None
                matches.add((currency, kind))
    if len(matches) != 1:
        return UNKNOWN_PRICE
    currency, kind = matches.pop()
    return amount, currency, conditions, kind
