"""Synthetic cited date phrases exercise session grounding without provider calls."""

import logging
from datetime import datetime

import pytest

from backend.app.services.events.normalize import _timestamp

START = "2026-10-19T19:00:00+05:00"


@pytest.mark.parametrize(
    "phrase",
    [
        "19 October 2026, 19:00",
        "October 19, 2026 at 19:00",
        "19 октября 2026 года в 19:00",
        "19 октября 2026 г. в 19:00",
        "19 октября 2026 г., 19:00",
        "19.10.2026 — 19:00",
        "19.10.2026 – 19:00",
        "19.10.2026 | 19:00",
        "19.10.2026; 19:00",
        "19.10.2026: 19:00",
        "2026-10-19T19:00",
        "19 October 2026** — **19:00",
        "2026 жылғы 19 қазан сағат 19:00",
    ],
)
def test_explicit_date_and_adjacent_clock_survive_source_punctuation(phrase):
    assert _timestamp(START, phrase, [f"Synthetic event: {phrase}."]) == datetime.fromisoformat(
        START
    )


@pytest.mark.parametrize(
    ("quoted_date", "phrase"),
    [
        ("19 October 2026", "19 October 2026, 19:00"),
        ("19 октября 2026", "19 октября 2026 года в 19:00"),
        ("19.10.2026", "19.10.2026 — 19:00"),
        ("19 October 2026", "19 October 2026** — **19:00"),
        ("Date: 19 October 2026", "Date: 19 October 2026, 19:00"),
        ("**19 October 2026**", "**19 October 2026** — 19:00"),
        ("2026 жылғы 19 қазан", "2026 жылғы 19 қазан сағат 19:00"),
    ],
)
def test_date_only_quote_can_use_its_immediately_following_source_clock(quoted_date, phrase):
    assert _timestamp(START, quoted_date, [f"Synthetic Straße event: {phrase}."]) is not None


def test_numeric_dates_do_not_require_leading_zeroes():
    assert (
        _timestamp("2026-01-09T19:00:00+05:00", "9.1.2026", ["Synthetic event: 9.1.2026, 19:00."])
        is not None
    )


@pytest.mark.parametrize(
    ("quote", "spans"),
    [
        ("19 October, 19:00", ["19 October 2026, 19:00; 19 October, 19:00"]),
        ("19 October 2026", ["19 October 2026, 18:00; ends 20 October 2026, 19:00"]),
        ("19 October 2026, 18:00", ["19 October 2026, 18:00; 19 October 2026, 19:00"]),
        ("19 October 2026", ["19 October 2026", "19:00"]),
        ("19 October 2026", ["19 October 2026. Another event starts at 19:00"]),
        ("19 October 2026", ["19 October 2026 — event description — 19:00"]),
        ("19 October 2026", ["19 October 2026\n\n19:00"]),
        ("19 October\n\n2026", ["19 October\n\n2026, 19:00"]),
        ("19 October 2026", ["20 October 2026, 19:00"]),
        ("19 October 2030", ["19 October 2030, 19:00"]),
        ("19 October 2026", ["19 October 2026, 19:00:30"]),
        ("19 October 2026", ["19 October 2026, 19:00.123456"]),
    ],
)
def test_missing_or_conflicting_source_facts_cannot_create_a_start(quote, spans):
    assert _timestamp(START, quote, spans) is None


@pytest.mark.parametrize("value", ["2026-10-19T19:00:30+05:00", "2026-10-19T19:00:00.123456+05:00"])
def test_extracted_seconds_remain_unsupported(value):
    assert _timestamp(value, "19 October 2026", ["19 October 2026, 19:00"]) is None


@pytest.mark.parametrize(
    "suffix",
    [
        " UTC",
        " GMT",
        "Z",
        " MSK",
        " МСК",
        " по МСК",
        " UTC+5",
        "+00:00",
        " -03:30",
        "−05:00",
        "+0500",
        " +5",
        " (UTC)",
        " [UTC]",
        ", GMT",
        "** UTC",
        "\u00a0GMT",
        " AM",
        " PM",
        " p.m.",
        "a.m.",
    ],
)
@pytest.mark.parametrize("quote_kind", ["date_only", "full_clock", "full_suffix"])
def test_unsupported_clock_suffix_is_not_silently_treated_as_astana_time(suffix, quote_kind):
    date = "19 October 2026"
    clock = f"{date} at 19:00"
    phrase = clock + suffix
    quote = {"date_only": date, "full_clock": clock, "full_suffix": phrase}[quote_kind]
    assert _timestamp(START, quote, [f"Synthetic event: {phrase}."]) is None


@pytest.mark.parametrize("quote", ["19 October 2026", "19 October 2026 at 7:00 PM"])
def test_twelve_hour_clock_does_not_confirm_an_incorrect_morning_start(quote):
    assert _timestamp("2026-10-19T07:00:00+05:00", quote, ["19 October 2026 at 7:00 PM"]) is None


def test_local_clock_can_precede_an_unrelated_sentence_about_a_timezone():
    phrase = "19 October 2026 at 19:00. UTC appears in an unrelated synthetic sentence."
    assert _timestamp(START, "19 October 2026", [phrase]) is not None


@pytest.mark.parametrize(
    ("date", "phrase"),
    [
        ("30 октября 2026", "30 октября 2026 года. Время: 19:00"),
        ("30 октября 2026", "30 октября 2026 г. Время начала: 19:00"),
        ("30 October 2026", "30 October 2026; start time: 19:00"),
        ("30 қазан 2026", "30 қазан 2026 жыл. Уақыты:19:00"),
        ("30 октября 2026", "30 октября 2026 года\nНачало: 19:00"),
        ("30 October 2026", "30 October 2026\r\nTime: 19:00"),
        ("30 қазан 2026", "30 қазан 2026 жылы\nБасталу уақыты: сағат 19:00"),
        ("30 October 2026", "30 October 2026. **Start time:** 19:00"),
    ],
)
@pytest.mark.parametrize("quote_kind", ["date_only", "full_phrase"])
def test_date_binds_to_known_time_label_without_crossing_prose(date, phrase, quote_kind):
    value = "2026-10-30T19:00:00+05:00"
    quote = date if quote_kind == "date_only" else phrase
    assert _timestamp(value, quote, [f"Synthetic event: {phrase}."]) is not None


@pytest.mark.parametrize(
    ("date", "phrase"),
    [
        ("30 October 2026", "30 October 2026\n\nTime: 19:00"),
        ("30 October 2026", "30 October 2026. Another synthetic event. Time: 19:00"),
        ("30 October 2026", "30 October 2026; 31 October 2026; start time: 19:00"),
        ("30 October 2026", "30 October 2026. Time: 18:00; another start time: 19:00"),
        ("30 октября 2026", "30 октября 2026 года. Время окончания: 19:00"),
        ("30 October 2026", "30 October 2026. Time: 19:00 UTC"),
        ("30 October 2026", "30 October 2026. Time: 19:00+00:00"),
        ("30 October 2026", "30 October 2026. Time: 19:00 PM"),
    ],
)
def test_time_labels_do_not_relax_session_or_clock_boundaries(date, phrase):
    assert _timestamp("2026-10-30T19:00:00+05:00", date, [phrase]) is None


@pytest.mark.parametrize(
    ("value", "quote", "spans", "code"),
    [
        (None, "Synthetic date quote", ["Synthetic date quote"], "extracted_datetime_missing"),
        (START, "Synthetic quote", ["Different synthetic quote"], "source_quote_not_literal"),
        (START, "19 October", ["19 October, 19:00"], "source_year_missing"),
        (
            START,
            "19 October 2030",
            ["19 October 2030, 19:00"],
            "source_date_mismatch_or_unsupported",
        ),
        (START, "19 October 2026", ["19 October 2026. Synthetic prose. 19:00"], "clock_not_bound"),
        (START, "19 October 2026", ["19 October 2026, 19:00 UTC"], "clock_suffix_unsupported"),
    ],
)
def test_failed_timestamp_logs_only_a_static_reason(value, quote, spans, code, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        assert _timestamp(value, quote, spans) is None
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.msg == "event_timestamp_unknown code=%s"
    assert record.args == (code,)
    assert record.getMessage() == f"event_timestamp_unknown code={code}"


def test_expected_missing_timestamp_does_not_emit_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        assert _timestamp(None, None, []) is None
    assert caplog.records == []


@pytest.mark.parametrize(
    "quote",
    [
        "Дата проведения: 30 октября 2026 года; Время: 19:00",
        "30 October 2026, 19:00",
        "October 30, 2026 at 19:00",
        "2026-10-30T19:00",
        "30.10.2026 — 19:00",
        "30 қазан 2026 жыл. Уақыты:19:00",
        "2026 жылғы 30 қазан сағат 19:00",
    ],
)
def test_missing_model_timestamp_is_derived_from_one_literal_full_date_and_clock(quote):
    assert _timestamp(None, quote, [quote], derive_missing=True) == datetime.fromisoformat(
        "2026-10-30T19:00:00+05:00"
    )


def test_missing_model_timestamp_can_use_the_date_quotes_immediately_following_clock():
    quote = "30 October 2026"
    assert _timestamp(
        None, quote, [f"Synthetic event: {quote}; start time: 19:00"], derive_missing=True
    ) == datetime.fromisoformat("2026-10-30T19:00:00+05:00")


@pytest.mark.parametrize(
    ("quote", "spans"),
    [
        ("30 October", ["30 October, 19:00. Retrieved in 2026."]),
        ("30 October 2026", ["30 October 2026"]),
        ("30 October 2026", ["30 October 2026", "19:00"]),
        ("30 October 2026, 19:00", ["31 October 2026, 19:00"]),
        ("30 October 2026", ["30 October 2026\n\nTime: 19:00"]),
        ("30 October 2026", ["30 October 2026. Synthetic prose. Time: 19:00"]),
        ("30 October 2026", ["30 October 2026. 31 October 2026. Time: 19:00"]),
        ("30 October 2026", ["30 October 2026, 19:00 UTC"]),
        ("30 October 2026", ["30 October 2026, 19:00+00:00"]),
        ("30 October 2026", ["30 October 2026, 7:00 PM"]),
        ("30 October 2026", ["30 October 2026, 19:00:30"]),
        ("30 October 2026", ["30 October 2026, 19:00:00.123456"]),
        ("31 February 2026, 19:00", ["31 February 2026, 19:00"]),
        ("30 October 2026", ["30 October 2026" + " " * 81 + "Time: 19:00"]),
    ],
)
def test_missing_model_timestamp_cannot_borrow_or_invent_source_facts(quote, spans):
    assert _timestamp(None, quote, spans, derive_missing=True) is None


@pytest.mark.parametrize(
    ("quote", "span"),
    [
        (
            "30 October 2026, 19:00; 31 October 2026, 20:00",
            "30 October 2026, 19:00; 31 October 2026, 20:00",
        ),
        (
            "30 October 2026, 19:00; 30 October 2026, 20:00",
            "30 October 2026, 19:00; 30 October 2026, 20:00",
        ),
        ("30 October 2026", "30 October 2026, 19:00; 30 October 2026, 20:00"),
    ],
)
def test_ambiguous_source_sessions_do_not_create_a_model_missing_start(quote, span, caplog):
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        assert _timestamp(None, quote, [span], derive_missing=True) is None
    # Candidate probes are silent; only the final anonymous failure is recorded.
    assert len(caplog.records) == 1
    assert caplog.records[0].args == ("extracted_datetime_missing",)


def test_missing_timestamp_derivation_requires_the_callers_grounded_city_opt_in():
    quote = "30 October 2026, 19:00"
    assert _timestamp(None, quote, [quote]) is None


def test_invalid_nonempty_model_timestamp_is_not_replaced_by_source_derivation():
    quote = "30 October 2026, 19:00"
    assert _timestamp("invalid", quote, [quote], derive_missing=True) is None


@pytest.mark.parametrize("value", [None, "2026-10-30T19:00:00+05:00"])
@pytest.mark.parametrize(
    "quote",
    [
        "Дата проведения: 30 октября 2026 года; Время: 19:00",
        "Дата проведения: 30 октября 2026 года",
    ],
)
def test_reformatted_quote_must_agree_with_the_actual_source_date_and_clock(value, quote):
    actual = "Synthetic event. **Дата проведения:** 30 октября 2026 года; **Время**: 19:00"
    assert _timestamp(value, quote, [actual], derive_missing=True) == datetime.fromisoformat(
        "2026-10-30T19:00:00+05:00"
    )


@pytest.mark.parametrize("value", [None, "2026-10-30T19:00:00+05:00"])
def test_literal_markdown_quote_can_use_the_same_validated_source_facts(value):
    actual = "30 октября 2026 года; **Время**: 19:00"
    assert _timestamp(value, actual, [actual], derive_missing=True) is not None


@pytest.mark.parametrize(
    ("quote", "spans"),
    [
        ("Date: 30 October; Time: 19:00", ["30 October 2026, 19:00"]),
        ("Date: 30 October 2026; Time: 19:00", ["31 October 2026, 19:00"]),
        ("Date: 30 October 2026; Time: 19:00", ["30 October 2026, 20:00"]),
        ("Date: 30 October 2026; Time: 19:00", ["30 October 2026", "Time: 19:00"]),
        ("Date: 30 October 2026; Time: 19:00", ["30 October 2026\n\nTime: 19:00"]),
        ("Date: 30 October 2026; Time: 19:00", ["30 October 2026. Other event. Time: 19:00"]),
        (
            "Date: 30 October 2026; Time: 19:00",
            ["30 October 2026, 19:00; 30 October 2026, 20:00"],
        ),
        (
            "Date: 30 October 2026; Time: 19:00",
            ["30 October 2026, 19:00", "30 October 2026, 20:00"],
        ),
        ("Date: 30 October 2026; Time: 19:00", ["30 October 2026, 19:00 UTC"]),
        ("Date: 30 October 2026; Time: 19:00 UTC", ["30 October 2026, 19:00"]),
    ],
)
def test_equivalent_quote_cannot_change_missing_conflicting_or_ambiguous_source_facts(quote, spans):
    assert _timestamp(None, quote, spans, derive_missing=True) is None


def test_equivalent_quote_cannot_replace_a_conflicting_nonempty_model_time():
    actual = "30 October 2026, 19:00"
    assert (
        _timestamp(
            "2026-10-30T20:00:00+05:00",
            "Date: 30 October 2026; Time: 19:00",
            [actual],
            derive_missing=True,
        )
        is None
    )
