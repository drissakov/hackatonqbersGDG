"""Bounded playground intent guards; source facts and hard constraints stay elsewhere."""

import re
from collections.abc import Iterable
from typing import Literal

PlaygroundQueryKind = Literal["playground", "family_walk"]
_QUOTED_NAMES = (
    r'[«“"]([^»”"]+)[»”"]',
    r"(?<!\w)'([^']+)'(?!\w)",
    r"(?<!\w)‘([^’]+)’(?!\w)",
)

_PLAYGROUND = (
    r"(?:\bдетск\w+\s+(?:игров\w+\s+)?площад(?:к\w*|ок)\b|"
    r"\bигров\w+\s+площад(?:к\w*|ок)\b|"
    r"\b(?:балалар(?:ға\s+арналған)?\s+)?ойын\s+алаң\w*\b|"
    r"\bбалалар\s+алаң\w*\b|\bplay[ -]?grounds?\b)"
)
_PLAYGROUND_REFERENCE = rf"(?:{_PLAYGROUND}|\bплощад(?:к\w*|ок)\b|\bалаң\w*\b)"
_WALK = r"\b(?:прогул\w*|погуля\w*|гуля\w*|серуен\w*|walk\w*|stroll\w*)\b"
_FAMILY = (
    r"\bс\s+(?:(?:моим|нашим|своим|маленьким)\s+)?"
    r"(?:ребен\w*|детьми|малыш\w*|семьей)\b|"
    r"\bдля\s+(?:ребен\w*|детей|всей\s+семьи)\b|"
    r"\bсемейн\w*\b|"
    r"\b(?:баламен|баламмен|балалармен|балаларыммен|отбасымен)\b|"
    r"\b(?:бала|балалар)\s+үшін\b|"
    r"\b(?:with|for)\s+(?:(?:a|the|my|our|young|little)\s+){0,3}"
    r"(?:child(?:ren)?|kids?|family)\b|\bfamily[ -]friendly\b"
)
_OTHER_DESTINATION = re.compile(
    r"\b(?:парк\w*|сквер\w*|набереж\w*|лес\w*|музе\w*|кафе\w*|кофейн\w*|"
    r"ресторан\w*|театр\w*|кинотеатр\w*|магазин\w*|бассейн\w*|спортзал\w*|"
    r"саябақ\w*|мұражай\w*|кофехана\w*|мейрамхана\w*|дәмхана\w*|дүкен\w*|"
    r"parks?|museums?|caf[eé]s?|coffee\s+shops?|restaurants?|theat(?:er|re)s?|"
    r"cinemas?|malls?|shops?|shopping|zoos?|gyms?|swimming\s+pools?)\b"
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold().replace("ё", "е")).strip()


def _without_place_names(query: str) -> str:
    """A venue's name cannot independently introduce a playground requirement."""
    text = _normalized(query)

    def keep_generic(match):
        return match.group(0) if is_generic_playground_name(match.group(1)) else " "

    for pattern in _QUOTED_NAMES:
        text = re.sub(pattern, keep_generic, text)
    # These constructions put the venue name after the marker. Preserve a type
    # before it, such as "playground named Sunrise", without parsing free prose.
    text = re.sub(r"\b(?:named|called|под\s+названием|по\s+имени)\s+[^,;.!?]*", " ", text)
    # Kazakh naming normally precedes the place type. Retain the type after the
    # marker, as in "Sunrise атты балалар ойын алаңы".
    return re.sub(r"(?:^|[,;.!?])[^,;.!?]*?\b(?:атты|деп\s+аталатын)\b", " ", text)


def playgrounds_excluded(query: str) -> bool:
    """Recognize explicit nearby exclusions, including an exclusion after the noun."""
    text = _normalized(query)
    before = (
        r"(?:\b(?:без|кроме|исключая|исключить)\s+|"
        r"\bне\s+(?:(?:на|в|нужна?|надо|хочу|предлаг\w*|предлож\w*|"
        r"совету\w*|показыва\w*|покаж\w*|ищи\w*|искать|"
        r"идти|ходить|пойду|пойдем)\s+){0,3}|"
        r"\b(?:no|without|avoid|avoiding|exclude|excluding|except)\s+|"
        r"\bnot\s+(?:(?:at|on|a|the|to|any)\s+){0,3}|"
        r"\b(?:don't|do\s+not)\s+(?:(?:want|show|suggest|recommend)\s+)?)"
    )
    determiners = r"(?:(?:a|the|any|children's|kids'|никак\w*)\s+){0,2}"
    after = (
        r"(?:\s+(?:не\s+(?:нужн\w*|надо|хочу|предлагать)|"
        r"емес|керек\s+емес|қажет\s+емес|болмасын|"
        r"бармай\w*|барғым\s+келмейді|ұсынба\w*)|"
        r"\s+(?:is\s+|are\s+)?(?:not\s+(?:wanted|needed|required)|excluded))\b"
    )
    return bool(
        re.search(rf"{before}{determiners}{_PLAYGROUND_REFERENCE}", text)
        or re.search(rf"{_PLAYGROUND_REFERENCE}{after}", text)
        or re.search(r"\b(?:ойын\s+)?алаң(?:ын)?сыз\b", text)
    )


def _playgrounds_ambiguous(query: str) -> bool:
    """An optional or hypothetical mention cannot introduce a destination category."""
    text = _normalized(query)
    before = (
        r"(?:\b(?:maybe|perhaps|optional)\s+(?:(?:a|the)\s+)?|"
        r"\b(?:может\s+быть|необязательно|не\s+обязательно)\s+|"
        r"\bмүмкін\s+)"
    )
    after = r"\s+(?:(?:is|are)\s+)?(?:optional|не\s*обязательн\w*|міндетті\s+емес)\b"
    return bool(
        re.search(rf"{before}{_PLAYGROUND_REFERENCE}", text)
        or re.search(rf"{_PLAYGROUND_REFERENCE}{after}", text)
    )


def playground_query_kind(
    query: str, *, interests: Iterable[str] = ()
) -> PlaygroundQueryKind | None:
    """Use raw positive wording; extracted interests cannot override raw exclusions.

    The interests argument keeps the shared policy interface explicit. It deliberately
    cannot create a playground request absent a matching phrase in the original query.
    """
    if playgrounds_excluded(query) or _playgrounds_ambiguous(query):
        return None
    text = _without_place_names(query)
    if re.search(_PLAYGROUND, text):
        return "playground"
    # Keep family and walk in one short clause, rather than linking unrelated requests.
    for clause in re.split(r"[.!?;\n]", text):
        walk = re.search(_WALK, clause)
        family = re.search(_FAMILY, clause)
        if walk and family and abs(walk.start() - family.start()) <= 100:
            return "family_walk"
    return None


def is_generic_playground_name(name: str) -> bool:
    """Only exact category descriptors may be removed from an extracted name filter."""
    normalized = _normalized(name).strip(" \"'«»“”‘’.,:;!?")
    return normalized in {
        "детская площадка",
        "детские площадки",
        "детскую площадку",
        "детских площадок",
        "игровая площадка",
        "игровую площадку",
        "балалар ойын алаңы",
        "балалар ойын алаңын",
        "балалар алаңы",
        "ойын алаңы",
        "ойын алаңын",
        "playground",
        "playgrounds",
        "children's playground",
        "children’s playground",
        "kids' playground",
        "kids’ playground",
    }


def has_explicit_place_name(query: str) -> bool:
    """Protect explicit naming constructions and non-generic quoted names."""
    text = _normalized(query)
    if re.search(
        r"\b(?:named|called)\s+\S|\bпод\s+названием\s+\S|"
        r"\bпо\s+имени\s+\S|\bатты\b|\bдеп\s+аталатын\b",
        text,
    ):
        return True
    quoted = [name for pattern in _QUOTED_NAMES for name in re.findall(pattern, text)]
    return any(not is_generic_playground_name(name) for name in quoted)


def has_other_place_requirement(query: str) -> bool:
    """Keep a literal park, museum or food choice even if extraction loses its category."""
    return bool(_OTHER_DESTINATION.search(_normalized(query)))


def can_expand_playground_categories(query: str, categories: Iterable[str]) -> bool:
    """Add only a compatible category; the caller retains and applies venue names."""
    return bool(
        playground_query_kind(query)
        and set(categories).issubset({"walk", "entertainment"})
        and not has_other_place_requirement(query)
    )
