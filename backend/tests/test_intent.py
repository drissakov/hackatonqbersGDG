"""Constraint precedence and conflicts are deterministic after structured extraction."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.app.intent import IntentExtractor, TextIntent, merge_intent
from backend.app.openai_client import ProviderError
from backend.app.schemas import RecommendationRequest


def text_intent(**updates):
    values = dict(
        language="ru",
        interests=[],
        categories=[],
        name_queries=[],
        available_minutes=None,
        budget_kzt_per_person=None,
        indoor=[],
        return_to_start=[],
        date_time=None,
        conflicts=[],
    )
    return TextIntent.model_validate({**values, **updates})


def test_text_language_and_explicit_constraints_override_defaults():
    request = RecommendationRequest(
        query="Synthetic museum", locale="kk", available_minutes=120, indoor_only=True
    )
    result = merge_intent(
        request,
        text_intent(
            language="en",
            categories=["museum"],
            indoor=["outdoor"],
            available_minutes={"minimum": None, "maximum": 30},
            return_to_start=[True],
        ),
    )
    assert result.status == "ok"
    assert result.intent.language == "en" and result.intent.available_minutes == 30
    assert result.intent.indoor == "outdoor" and result.intent.return_to_start
    assert result.intent.categories == ["museum"]


def test_compatible_explicit_upper_bounds_use_the_stricter_limit():
    request = RecommendationRequest(
        query="Synthetic",
        available_minutes=60,
        budget_kzt_per_person=3000,
        explicit_fields=["available_minutes", "budget_kzt_per_person"],
    )
    result = merge_intent(
        request,
        text_intent(
            available_minutes={"minimum": 15, "maximum": 30},
            budget_kzt_per_person={"minimum": None, "maximum": 5000},
        ),
    )
    assert result.status == "ok"
    assert result.intent.available_minutes == 30 and result.intent.minimum_minutes == 15
    assert result.intent.budget_kzt_per_person == 3000
    assert result.intent.constraint_sources["available_minutes"] == "form+text"


@pytest.mark.parametrize(
    "form,text,field",
    [
        (
            {"available_minutes": 20, "explicit_fields": ["available_minutes"]},
            {"available_minutes": {"minimum": 40, "maximum": None}},
            "available_minutes",
        ),
        (
            {"budget_kzt_per_person": 0, "explicit_fields": ["budget_kzt_per_person"]},
            {"budget_kzt_per_person": {"minimum": 1, "maximum": None}},
            "budget_kzt_per_person",
        ),
        (
            {"indoor_only": True, "explicit_fields": ["indoor_only"]},
            {"indoor": ["outdoor"]},
            "indoor_only",
        ),
        (
            {"return_to_start": False, "explicit_fields": ["return_to_start"]},
            {"return_to_start": [True]},
            "return_to_start",
        ),
        ({}, {"indoor": ["indoor", "outdoor"]}, "indoor_only"),
        ({}, {"return_to_start": [False, True]}, "return_to_start"),
        ({}, {"available_minutes": {"minimum": 60, "maximum": 20}}, "available_minutes"),
        ({}, {"conflicts": ["date_time"]}, "date_time"),
    ],
)
def test_explicit_contradictions_require_clarification(form, text, field):
    result = merge_intent(RecommendationRequest(query="Synthetic", **form), text_intent(**text))
    assert result.status == "clarification" and result.intent is None
    assert field in result.clarification_fields


def test_no_indoor_preference_is_compatible_with_a_text_requirement_and_zero_budget():
    result = merge_intent(
        RecommendationRequest(
            query="Synthetic",
            indoor_only=False,
            budget_kzt_per_person=0,
            explicit_fields=["indoor_only", "budget_kzt_per_person"],
        ),
        text_intent(indoor=["indoor"]),
    )
    assert result.status == "ok" and result.intent.indoor == "indoor"
    assert result.intent.budget_kzt_per_person == 0


def test_structured_client_receives_text_without_ui_locale_or_form_defaults():
    client = AsyncMock()
    client.parse_response.return_value = text_intent(language="kk", name_queries=["Әлем Test"])
    result = asyncio.run(
        IntentExtractor(client).extract(RecommendationRequest(query="Әлем Test", locale="en"))
    )
    args, kwargs = client.parse_response.call_args
    assert args == ("Әлем Test", TextIntent)
    assert "untrusted" in kwargs["instructions"]
    assert result.intent.name_queries == ["Әлем Test"]


def test_provider_failure_remains_unavailable_with_form_constraints():
    client = AsyncMock()
    client.parse_response.side_effect = ProviderError("rate_limit_or_quota")
    request = RecommendationRequest(query="Synthetic", available_minutes=20)
    result = asyncio.run(IntentExtractor(client).extract(request))
    assert result.status == "unavailable" and result.reason == "rate_limit_or_quota"
    assert result.intent.available_minutes == 20


@pytest.mark.parametrize(
    "query",
    [
        "Есть 45 минут, до 1500 тенге",
        "60 минутым бар, 2000 теңгеге дейін",
        "I have 1 hour and 1500 KZT",
        "I have 90 minutes, budget KZT 3000",
    ],
)
def test_omitted_explicit_quantities_retry_once_then_require_clarification(query):
    client = AsyncMock()
    client.parse_response.return_value = text_intent()
    result = asyncio.run(IntentExtractor(client).extract(RecommendationRequest(query=query)))
    assert result.status == "clarification" and result.intent is None
    assert set(result.clarification_fields) == {"available_minutes", "budget_kzt_per_person"}
    assert client.parse_response.call_count == 2


def test_presence_audit_retry_can_recover_extracted_constraints():
    client = AsyncMock()
    client.parse_response.side_effect = [
        text_intent(),
        text_intent(
            available_minutes={"minimum": None, "maximum": 45},
            budget_kzt_per_person={"minimum": None, "maximum": 1500},
        ),
    ]
    result = asyncio.run(
        IntentExtractor(client).extract(RecommendationRequest(query="Есть 45 минут, до 1500 тенге"))
    )
    assert result.status == "ok" and result.intent.available_minutes == 45
    assert result.intent.budget_kzt_per_person == 1500
    assert client.parse_response.call_count == 2


@pytest.mark.parametrize(
    "field,value", [("available_minutes", 60), ("budget_kzt_per_person", 1500)]
)
def test_empty_extracted_ranges_preserve_form_defaults(field, value):
    result = merge_intent(
        RecommendationRequest(query="Synthetic museum", **{field: value}),
        text_intent(**{field: {"minimum": None, "maximum": None}}),
    )
    assert result.status == "ok" and getattr(result.intent, field) == value
    assert field not in result.intent.constraint_sources


@pytest.mark.parametrize(
    "query,excerpt",
    [
        ("Find a museum that is open 24 hours", "24 hours"),
        ("Find an exhibition about 5000 KZT banknotes", "5000 KZT"),
        ("Find an exhibition about KZT 5000 banknotes", "KZT 5000"),
        ("Find the cafe named 24 hours", "24 hours"),
    ],
)
def test_non_constraint_quantities_do_not_require_time_or_budget(query, excerpt):
    client = AsyncMock()
    client.parse_response.return_value = text_intent(non_constraint_quantities=[excerpt])
    result = asyncio.run(IntentExtractor(client).extract(RecommendationRequest(query=query)))
    assert result.status == "ok"
    assert result.intent.available_minutes is None and result.intent.budget_kzt_per_person is None
    assert client.parse_response.call_count == 1


@pytest.mark.parametrize("bounds", [None, {"minimum": None, "maximum": 20}])
def test_venue_hours_do_not_hide_a_separate_personal_time_limit(bounds):
    client = AsyncMock()
    client.parse_response.return_value = text_intent(
        available_minutes=bounds, non_constraint_quantities=["24 hours"]
    )
    result = asyncio.run(
        IntentExtractor(client).extract(
            RecommendationRequest(query="Find a museum open 24 hours; I have 20 minutes")
        )
    )
    if bounds is None:
        assert result.status == "clarification"
        assert result.clarification_fields == ["available_minutes"]
        assert client.parse_response.call_count == 2
    else:
        assert result.status == "ok" and result.intent.available_minutes == 20
        assert client.parse_response.call_count == 1


def test_quantity_exclusions_must_match_the_exact_quantity_in_the_query():
    client = AsyncMock()
    client.parse_response.return_value = text_intent(
        non_constraint_quantities=["30 minutes", "I have 20 minutes"]
    )
    result = asyncio.run(
        IntentExtractor(client).extract(RecommendationRequest(query="I have 20 minutes"))
    )
    assert result.status == "clarification" and result.clarification_fields == ["available_minutes"]


def test_retry_preserves_prior_constraints_and_intersects_numeric_bounds():
    client = AsyncMock()
    client.parse_response.side_effect = [
        text_intent(
            interests=["art"],
            categories=["museum"],
            name_queries=["Synthetic Museum"],
            available_minutes={"minimum": 10, "maximum": 60},
            indoor=["indoor"],
            return_to_start=[True],
            date_time="2026-10-19T12:00:00+05:00",
        ),
        text_intent(
            interests=["history"],
            name_queries=["Synthetic Gallery"],
            available_minutes={"minimum": 15, "maximum": 30},
            budget_kzt_per_person={"minimum": None, "maximum": 1500},
        ),
    ]
    result = asyncio.run(
        IntentExtractor(client).extract(
            RecommendationRequest(query="Indoor museum, 30 minutes and 1500 KZT")
        )
    )
    assert result.status == "ok"
    assert result.intent.interests == ["art", "history"]
    assert result.intent.categories == ["museum"]
    assert result.intent.name_queries == ["Synthetic Museum", "Synthetic Gallery"]
    assert result.intent.minimum_minutes == 15 and result.intent.available_minutes == 30
    assert result.intent.budget_kzt_per_person == 1500
    assert result.intent.indoor == "indoor" and result.intent.return_to_start
    assert result.intent.date_time.isoformat() == "2026-10-19T12:00:00+05:00"


@pytest.mark.parametrize(
    "first,retry,field",
    [
        ({"indoor": ["indoor"]}, {"indoor": ["outdoor"]}, "indoor_only"),
        ({"return_to_start": [True]}, {"return_to_start": [False]}, "return_to_start"),
        (
            {"available_minutes": {"minimum": 45, "maximum": None}},
            {"available_minutes": {"minimum": None, "maximum": 30}},
            "available_minutes",
        ),
        (
            {"date_time": "2026-10-19T12:00:00+05:00"},
            {"date_time": "2026-10-19T13:00:00+05:00"},
            "date_time",
        ),
    ],
)
def test_retry_disagreements_require_clarification(first, retry, field):
    client = AsyncMock()
    client.parse_response.side_effect = [
        text_intent(**first),
        text_intent(budget_kzt_per_person={"minimum": None, "maximum": 1500}, **retry),
    ]
    result = asyncio.run(
        IntentExtractor(client).extract(RecommendationRequest(query="Museum, 1500 KZT"))
    )
    assert result.status == "clarification" and field in result.clarification_fields
