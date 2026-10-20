"""Constraint clarifications reach both search consumers as bounded stable codes."""

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import ValidationError

from backend.app import api, main
from backend.app.event_schemas import TransientEventSearchResponse
from backend.app.intent import (
    IntentExtractor,
    IntentResult,
    constraint_clarifications,
    merge_intent,
)
from backend.app.schemas import (
    ConstraintClarification,
    ExplicitField,
    RecommendationRequest,
    RecommendationResponse,
    Warning,
)
from backend.tests.test_api import request
from backend.tests.test_intent import text_intent

REQUEST_ID = "00000000-0000-4000-8000-000000000083"
CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
CONFLICTS = [
    pytest.param(
        {"available_minutes": 20, "explicit_fields": ["available_minutes"]},
        {"available_minutes": {"minimum": 40, "maximum": None}},
        "available_minutes",
        id="time",
    ),
    pytest.param(
        {"budget_kzt_per_person": 500, "explicit_fields": ["budget_kzt_per_person"]},
        {"budget_kzt_per_person": {"minimum": 600, "maximum": None}},
        "budget_kzt_per_person",
        id="budget",
    ),
    pytest.param(
        {"indoor_only": True, "explicit_fields": ["indoor_only"]},
        {"indoor": ["outdoor"]},
        "indoor_only",
        id="indoor",
    ),
    pytest.param(
        {"return_to_start": False, "explicit_fields": ["return_to_start"]},
        {"return_to_start": [True]},
        "return_to_start",
        id="return",
    ),
    pytest.param(
        {"date_time": "2030-01-15T12:00:00+05:00", "explicit_fields": ["date_time"]},
        {"date_time": "2030-01-15T13:00:00+05:00"},
        "date_time",
        id="date",
    ),
    pytest.param(
        {"origin": {"latitude": 51.13, "longitude": 71.44}, "explicit_fields": ["origin"]},
        {"conflicts": ["origin"]},
        "origin",
        id="origin",
    ),
]
ALIASES = [
    ("/api/recommendations", False),
    ("/api/v1/recommendations", False),
    ("/api/events/search", True),
    ("/api/v2/events/search", True),
]
NUMERIC_QUERIES = [
    ("kk", "TEST ONLY: 30 минутым бар, 1500 теңгеге дейін."),
    ("ru", "TEST ONLY: Есть 30 минут, бюджет до 1500 тенге."),
    ("en", "TEST ONLY: I have 30 minutes and a 1500 KZT budget."),
]
MIXED_FORM = {
    "origin": {"latitude": 51.13, "longitude": 71.44},
    "indoor_only": True,
    "return_to_start": False,
    "date_time": "2030-01-15T12:00:00+05:00",
    "explicit_fields": ["origin", "indoor_only", "return_to_start", "date_time"],
}
MIXED_TEXT = {
    "conflicts": ["origin", "origin"],
    "indoor": ["outdoor"],
    "return_to_start": [True],
    "date_time": "2030-01-15T13:00:00+05:00",
}
MIXED_DETAILS = [
    {"field": "available_minutes", "reason": "unparsed_constraint"},
    {"field": "budget_kzt_per_person", "reason": "unparsed_constraint"},
    {"field": "date_time", "reason": "conflicting_constraints"},
    {"field": "indoor_only", "reason": "conflicting_constraints"},
    {"field": "origin", "reason": "conflicting_constraints"},
    {"field": "return_to_start", "reason": "conflicting_constraints"},
]
OVERLAPPING_MISSES = [
    ("TEST ONLY: I have 30 minutes.", "available_minutes"),
    ("TEST ONLY: My budget is 1500 KZT.", "budget_kzt_per_person"),
]


def public_details(result):
    return [item.model_dump(mode="json") for item in constraint_clarifications(result)]


@lru_cache
def response_validator(event_mode):
    name = "transient-event-search-response" if event_mode else "recommendation-response"
    schema = json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize("form,text,field", CONFLICTS)
def test_real_merge_conflicts_produce_a_specific_public_field_and_reason(form, text, field):
    result = merge_intent(
        RecommendationRequest(query="TEST ONLY: Synthetic constraint conflict.", **form),
        text_intent(**text),
    )

    assert result.status == "clarification" and result.intent is None
    assert result.reason == "conflicting_constraints"
    assert public_details(result) == [{"field": field, "reason": "conflicting_constraints"}]
    assert all(isinstance(value, ExplicitField) for value in result.clarification_fields)


def test_combined_merge_conflicts_are_complete_and_deduplicated():
    result = merge_intent(
        RecommendationRequest(
            query="TEST ONLY: Synthetic combined constraints.",
            available_minutes=20,
            budget_kzt_per_person=500,
            indoor_only=True,
            return_to_start=False,
            date_time="2030-01-15T12:00:00+05:00",
            explicit_fields=[
                "available_minutes",
                "budget_kzt_per_person",
                "indoor_only",
                "return_to_start",
                "date_time",
            ],
        ),
        text_intent(
            available_minutes={"minimum": 40, "maximum": None},
            budget_kzt_per_person={"minimum": 600, "maximum": None},
            indoor=["outdoor"],
            return_to_start=[True],
            date_time="2030-01-15T13:00:00+05:00",
            conflicts=["origin", "origin", "available_minutes", "date_time"],
        ),
    )

    assert result.status == "clarification"
    details = public_details(result)
    assert len(details) == 6
    assert {item["field"] for item in details} == {field.value for field in ExplicitField}
    assert {item["reason"] for item in details} == {"conflicting_constraints"}
    duplicate_result = result.model_copy(
        update={"clarification_fields": result.clarification_fields * 2}
    )
    assert public_details(duplicate_result) == details


@pytest.mark.parametrize("locale,query", NUMERIC_QUERIES)
def test_omitted_numeric_limits_after_two_attempts_have_a_distinct_public_reason(locale, query):
    client = AsyncMock()
    client.parse_response.return_value = text_intent()

    result = asyncio.run(
        IntentExtractor(client).extract(RecommendationRequest(query=query, locale=locale))
    )

    assert result.status == "clarification" and result.intent is None
    assert result.reason == "explicit_numeric_constraint_not_extracted"
    assert public_details(result) == [
        {"field": "available_minutes", "reason": "unparsed_constraint"},
        {"field": "budget_kzt_per_person", "reason": "unparsed_constraint"},
    ]
    assert client.parse_response.await_count == 2


@pytest.mark.parametrize("locale,query", NUMERIC_QUERIES)
def test_numeric_omission_keeps_all_prior_conflicts_and_their_separate_reasons(locale, query):
    client = AsyncMock()
    client.parse_response.side_effect = [text_intent(**MIXED_TEXT), text_intent()]

    result = asyncio.run(
        IntentExtractor(client).extract(
            RecommendationRequest(query=query, locale=locale, **MIXED_FORM)
        )
    )

    assert result.status == "clarification" and result.intent is None
    assert public_details(result) == MIXED_DETAILS
    assert result.unparsed_fields == ["available_minutes", "budget_kzt_per_person"]
    assert len(result.clarification_fields) == len(set(result.clarification_fields)) == 6
    assert client.parse_response.await_count == 2


@pytest.mark.parametrize("query,field", OVERLAPPING_MISSES)
def test_detected_conflict_takes_priority_when_same_numeric_field_is_also_unparsed(query, field):
    client = AsyncMock()
    client.parse_response.side_effect = [text_intent(conflicts=[field]), text_intent()]

    result = asyncio.run(IntentExtractor(client).extract(RecommendationRequest(query=query)))

    assert result.status == "clarification" and result.intent is None
    assert result.clarification_fields == [field] and result.unparsed_fields == []
    assert public_details(result) == [{"field": field, "reason": "conflicting_constraints"}]
    assert client.parse_response.await_count == 2


def call_http(monkeypatch, path, payload, extracted):
    repository, router, client = AsyncMock(), AsyncMock(), AsyncMock()
    client.parse_response.return_value = text_intent(**extracted)
    lifecycle = {"entered": False, "closed": False}

    class ClientContext:
        async def __aenter__(self):
            lifecycle["entered"] = True
            return client

        async def __aexit__(self, *_):
            lifecycle["closed"] = True

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    response = request(main.create_app(), "POST", path, json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert lifecycle == {"entered": True, "closed": True}
    assert repository.mock_calls == router.mock_calls == []
    client.embed.assert_not_called()
    client.search_web.assert_not_called()
    return response.json(), client


def assert_clarification_response(data, event_mode, expected):
    response_type = TransientEventSearchResponse if event_mode else RecommendationResponse
    result = response_type.model_validate(data)
    response_validator(event_mode).validate(data)
    assert result.status == "unknown" and str(result.request_id) == REQUEST_ID
    assert result.items == result.sources == []
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code == "missing_input" and warning.fields == []
    assert [item.model_dump(mode="json") for item in warning.clarifications] == expected
    if event_mode:
        assert result.provider_status == "unknown"
        assert result.provider_code == "constraint_clarification"
        assert result.live_web_search == "not_run" and result.listings == []


@pytest.mark.parametrize("path,event_mode", ALIASES)
@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
@pytest.mark.parametrize("form,text,field", CONFLICTS)
def test_all_http_aliases_transport_real_conflicts_before_search_work(
    path, event_mode, locale, form, text, field, monkeypatch
):
    payload = {
        "query": "TEST ONLY: Synthetic private constraint conflict.",
        "locale": locale,
        "request_id": REQUEST_ID,
        **form,
    }

    data, client = call_http(monkeypatch, path, payload, text)

    assert_clarification_response(
        data, event_mode, [{"field": field, "reason": "conflicting_constraints"}]
    )
    assert client.parse_response.await_count == 1
    assert payload["query"] not in json.dumps(data, ensure_ascii=False)


@pytest.mark.parametrize("path,event_mode", ALIASES)
@pytest.mark.parametrize("locale,query", NUMERIC_QUERIES)
def test_all_http_aliases_transport_unparsed_numeric_fields_after_bounded_retry(
    path, event_mode, locale, query, monkeypatch
):
    data, client = call_http(
        monkeypatch, path, {"query": query, "locale": locale, "request_id": REQUEST_ID}, {}
    )

    assert_clarification_response(
        data,
        event_mode,
        [
            {"field": "available_minutes", "reason": "unparsed_constraint"},
            {"field": "budget_kzt_per_person", "reason": "unparsed_constraint"},
        ],
    )
    assert client.parse_response.await_count == 2


@pytest.mark.parametrize("path,event_mode", ALIASES)
@pytest.mark.parametrize("locale,query", NUMERIC_QUERIES)
def test_all_http_aliases_preserve_mixed_reasons_for_all_six_fields(
    path, event_mode, locale, query, monkeypatch
):
    data, client = call_http(
        monkeypatch,
        path,
        {"query": query, "locale": locale, "request_id": REQUEST_ID, **MIXED_FORM},
        MIXED_TEXT,
    )

    assert_clarification_response(data, event_mode, MIXED_DETAILS)
    assert client.parse_response.await_count == 2
    assert "unparsed_fields" not in json.dumps(data)


@pytest.mark.parametrize("path,event_mode", ALIASES)
@pytest.mark.parametrize("query,field", OVERLAPPING_MISSES)
def test_all_http_aliases_report_one_conflict_when_a_numeric_field_has_both_reasons(
    path, event_mode, query, field, monkeypatch
):
    data, client = call_http(
        monkeypatch,
        path,
        {"query": query, "locale": "en", "request_id": REQUEST_ID},
        {"conflicts": [field]},
    )

    assert_clarification_response(
        data, event_mode, [{"field": field, "reason": "conflicting_constraints"}]
    )
    assert client.parse_response.await_count == 2


@pytest.mark.parametrize("event_mode", [False, True])
def test_older_response_warnings_remain_valid_without_clarification_metadata(event_mode):
    data = {
        "status": "unknown",
        "items": [],
        "sources": [],
        "request_id": REQUEST_ID,
        "warnings": [
            {"code": "missing_input", "message": "Synthetic legacy warning.", "fields": []}
        ],
    }
    if event_mode:
        data.update(
            contract_version="1.3.0",
            provider_status="unknown",
            provider_code="constraint_clarification",
            live_web_search="not_run",
            listings=[],
        )
    response_type = TransientEventSearchResponse if event_mode else RecommendationResponse

    result = response_type.model_validate(data)

    response_validator(event_mode).validate(data)
    assert result.warnings[0].clarifications == []


@pytest.mark.parametrize("status", ["ok", "unavailable"])
def test_ordinary_intent_states_do_not_invent_clarifications(status):
    assert (
        constraint_clarifications(IntentResult(status=status, clarification_fields=["origin"]))
        == []
    )


@pytest.mark.parametrize("code", ["data_unknown", "provider_unavailable", "route_unavailable"])
def test_ordinary_warnings_have_empty_clarification_metadata(code):
    warning = Warning(code=code, message="Synthetic ordinary warning.", fields=["opening_hours"])
    assert warning.clarifications == []


@pytest.mark.parametrize(
    "clarification",
    [
        {"field": "provider prose or private query", "reason": "conflicting_constraints"},
        {"field": "child_suitability", "reason": "conflicting_constraints"},
        {"field": "origin", "reason": "internal_error"},
        {"field": None, "reason": "unparsed_constraint"},
        {"field": "origin", "reason": None},
        {"field": "origin", "reason": "unparsed_constraint", "value": "private input"},
    ],
)
def test_public_clarifications_reject_unknown_codes_nulls_and_input_values(clarification):
    with pytest.raises(ValidationError):
        ConstraintClarification.model_validate(clarification)
    with pytest.raises(ValidationError):
        Warning(
            code="missing_input",
            message="Synthetic invalid warning.",
            clarifications=[clarification],
        )


@pytest.mark.parametrize(
    "clarifications", [None, [{"field": "origin", "reason": "unparsed_constraint"}] * 7]
)
def test_warning_clarifications_are_nonnullable_and_bounded(clarifications):
    with pytest.raises(ValidationError):
        Warning(
            code="missing_input",
            message="Synthetic invalid warning.",
            clarifications=clarifications,
        )


def test_internal_conflict_fields_reject_unstructured_provider_prose():
    with pytest.raises(ValidationError):
        text_intent(conflicts=["private provider prose"])
    with pytest.raises(ValidationError):
        IntentResult(status="clarification", clarification_fields=["private provider prose"])


@pytest.mark.parametrize("event_mode", [False, True])
@pytest.mark.parametrize(
    "clarifications",
    [
        None,
        [{"field": "opening_hours", "reason": "conflicting_constraints"}],
        [{"field": "origin", "reason": "provider_internal_reason"}],
        [{"field": None, "reason": "unparsed_constraint"}],
        [{"field": "origin", "reason": None}],
        [{"field": "origin", "reason": "unparsed_constraint", "value": "private input"}],
        [{"field": "origin", "reason": "unparsed_constraint"}] * 7,
    ],
)
def test_both_wire_schemas_reject_invalid_clarification_metadata(event_mode, clarifications):
    data = {
        "status": "unknown",
        "items": [],
        "sources": [],
        "request_id": REQUEST_ID,
        "warnings": [
            {
                "code": "missing_input",
                "message": "Synthetic invalid clarification.",
                "fields": [],
                "clarifications": clarifications,
            }
        ],
    }
    if event_mode:
        data.update(
            contract_version="1.3.0",
            provider_status="unknown",
            provider_code="constraint_clarification",
            live_web_search="not_run",
            listings=[],
        )
    response_type = TransientEventSearchResponse if event_mode else RecommendationResponse

    with pytest.raises(ValidationError):
        response_type.model_validate(data)
    with pytest.raises(SchemaValidationError):
        response_validator(event_mode).validate(data)
