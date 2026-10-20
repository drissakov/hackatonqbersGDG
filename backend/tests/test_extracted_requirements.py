"""Explicit requirements extracted beyond the presence audit cannot become fit promises."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.app.constraints import unsupported_requirements
from backend.app.intent import TextIntent
from backend.app.schemas import RouteLeg
from backend.tests.test_event_recommend import search as search_events
from backend.tests.test_event_recommend import service as event_service
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record, service
from backend.tests.test_requirement_preservation import known_fact_request

EXTRACTED_REQUIREMENTS = [
    ("Take the little ones to a museum.", "child_suitability", "child"),
    (
        "My laptop battery is low; somewhere I can plug in.",
        "power_outlets",
        "charg",
    ),
]


@pytest.mark.parametrize(
    "interest,requirement",
    [
        ("child_suitability", "child_suitability"),
        ("child suitability", "child_suitability"),
        ("CHILD-SUITABILITY", "child_suitability"),
        ("child-friendly", "child_suitability"),
        ("family friendly", "child_suitability"),
        ("family_friendly", "child_suitability"),
        ("power_outlets", "power_outlets"),
        ("power outlets", "power_outlets"),
        ("POWER-OUTLETS", "power_outlets"),
    ],
)
def test_canonical_extracted_requirements_and_explicit_aliases_survive(interest, requirement):
    assert unsupported_requirements("Synthetic request", interests=[interest]) == [requirement]


@pytest.mark.parametrize("query,requirement,message_term", EXTRACTED_REQUIREMENTS)
def test_poi_extracted_requirement_stops_before_routes_and_explanations(
    query, requirement, message_term
):
    # Neither query contains a lexical presence-audit match: the model supplies the condition.
    assert unsupported_requirements(query) == []
    poi = record(price_kzt_per_person=500, opening_hours_text="24/7", indoor=True)
    router = AsyncMock()
    provider, repository, client = service(
        [poi],
        extracted=text_intent(categories=["museum"], interests=[requirement]),
        router=router,
    )

    result = asyncio.run(provider.recommend(known_fact_request(query)))

    assert result.status == "unknown" and result.items == result.sources == []
    assert result.warnings[0].code == "missing_input"
    assert message_term in result.warnings[0].message.lower()
    assert requirement not in result.warnings[0].message
    repository.retrieve_candidates.assert_awaited_once()
    router.route.assert_not_called()
    assert client.parse_response.await_count == 1
    assert client.parse_response.await_args.args[1] is TextIntent


@pytest.mark.parametrize("query,requirement,message_term", EXTRACTED_REQUIREMENTS)
def test_event_extracted_requirement_stops_before_discovery_routes_and_explanations(
    query, requirement, message_term
):
    assert unsupported_requirements(query) == []
    router = AsyncMock()
    provider, repository, client = event_service(
        extracted=text_intent(categories=[], interests=[requirement]), router=router
    )

    result = search_events(provider, query=query, locale="en")

    assert result.status == "unknown" and result.items == result.sources == result.listings == []
    assert result.provider_code == "unsupported_fact_requirement"
    assert result.live_web_search == "not_run"
    assert message_term in result.warnings[0].message.lower()
    assert requirement not in result.warnings[0].message
    assert [call[1] for call in client.parse_calls] == [TextIntent]
    assert client.search_calls == []
    assert repository.mock_calls == router.mock_calls == []


@pytest.mark.parametrize("name", ["Children's Museum", "Children’s Museum", "Family Park"])
def test_named_venue_interest_alone_is_not_an_unsupported_requirement(name):
    query = f"Visit {name}."
    assert unsupported_requirements(query, interests=[name]) == []
    poi = record(price_kzt_per_person=500, opening_hours_text="24/7", indoor=True)
    router = AsyncMock()
    router.route.return_value = (
        RouteLeg(status="unavailable", reason="disabled"),
        RouteLeg(status="unavailable", reason="disabled"),
    )
    provider, repository, client = service(
        [poi],
        extracted=text_intent(categories=["museum"], interests=[name], name_queries=[name]),
        router=router,
    )

    result = asyncio.run(provider.recommend(known_fact_request(query)))

    assert result.items and result.status == "partial"
    repository.retrieve_candidates.assert_awaited_once()
    router.route.assert_awaited_once()
    assert client.parse_response.await_count == 2


@pytest.mark.parametrize("name", ["Children's Museum", "Children’s Museum", "Family Park"])
def test_named_event_venue_interest_does_not_prevent_discovery(name):
    provider, _, client = event_service(
        extracted=text_intent(categories=[], interests=[name], name_queries=[name])
    )

    result = search_events(provider, query=f"Visit {name}.", locale="en")

    assert result.live_web_search == "passed" and result.items
    assert len(client.search_calls) == 1
    assert len(client.parse_calls) == 3


def test_extracted_requirement_does_not_replace_poi_constraint_clarification():
    provider, repository, client = service(
        [], text_intent(interests=["child_suitability"], conflicts=["available_minutes"])
    )

    result = asyncio.run(provider.recommend(known_fact_request("Take the little ones out.")))

    assert result.status == "unknown" and result.items == []
    assert [(item.field, item.reason) for item in result.warnings[0].clarifications] == [
        ("available_minutes", "conflicting_constraints")
    ]
    repository.retrieve_candidates.assert_not_called()
    client.embed.assert_not_called()


def test_extracted_requirement_does_not_replace_event_constraint_clarification():
    provider, repository, client = event_service(
        extracted=text_intent(interests=["child_suitability"], conflicts=["available_minutes"])
    )

    result = search_events(provider, query="Take the little ones out.", locale="en")

    assert result.status == "unknown" and result.provider_code == "constraint_clarification"
    assert [(item.field, item.reason) for item in result.warnings[0].clarifications] == [
        ("available_minutes", "conflicting_constraints")
    ]
    assert client.search_calls == [] and repository.mock_calls == []
