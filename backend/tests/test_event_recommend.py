"""Transient event composition through the unchanged D03 discovery/normalizer."""

import asyncio
import copy
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app import event_recommend
from backend.app.database import DatabaseUnavailable
from backend.app.event_extraction import EventExtractionBatch
from backend.app.event_recommend import D03Client, EventRecommendationService
from backend.app.event_schemas import TransientEventSearchResponse
from backend.app.explain import ExplanationBatch
from backend.app.intent import TextIntent
from backend.app.openai_client import ProviderError
from backend.app.schemas import EventSearchRequest, RouteLeg, RouteProvenance
from backend.app.services.events.discover import ALLOWED_DOMAINS
from backend.app.services.events.models import CandidateBatch, EvidenceSource, SearchEvidence
from backend.app.services.events.playground_cases import playground_cases
from backend.app.services.events.venue import VenueMatch
from backend.tests.test_intent import text_intent

NOW = datetime.fromisoformat("2030-01-15T09:00:00+05:00")
DEPARTURE = datetime.fromisoformat("2030-01-15T18:00:00+05:00")


class Client:
    def __init__(self, data, *, extracted=None, search_error=None, extraction_error=None):
        self.data = data
        self.extracted = extracted or text_intent(categories=[])
        self.search_error = search_error
        self.extraction_error = extraction_error
        self.search_calls = []
        self.parse_calls = []

    async def search_web(self, text, **kwargs):
        self.search_calls.append((text, kwargs))
        if self.search_error:
            raise self.search_error
        source = self.data["sources"][0]
        return {
            "status": "completed",
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {"type": "search", "sources": [{"url": source["url"]}]},
                },
                {
                    "type": "message",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": source["text"],
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": source["url"],
                                    "title": "Synthetic D03/S04 composition evidence",
                                    "start_index": 0,
                                    "end_index": len(source["text"]),
                                }
                            ],
                        }
                    ],
                },
            ],
        }

    async def parse_response(self, text, schema, **kwargs):
        self.parse_calls.append((text, schema, kwargs))
        if schema is TextIntent:
            return self.extracted
        if issubclass(schema, CandidateBatch):
            if self.extraction_error:
                raise self.extraction_error
            return schema.model_validate({"events": self.data["events"]})
        assert schema is ExplanationBatch
        packet = json.loads(text)
        return ExplanationBatch.model_validate(
            {
                "locale": packet["locale"],
                "items": [
                    {
                        "item_id": item["item_id"],
                        "source_ids": item["source_ids"],
                        "reason_codes": item["allowed_reason_codes"],
                        "activity_code": item["activity_code"],
                        "idea": item["allowed_ideas"][0],
                    }
                    for item in packet["alternatives"]
                ],
            }
        )


def service(case="matchedvenue", *, router=None, clock=None, **client_options):
    data = copy.deepcopy(next(row["input"] for row in playground_cases() if row["id"] == case))
    repository = AsyncMock()
    repository.retrieve_candidates.return_value = [{"document": row} for row in data["pois"]]
    client = Client(data, **client_options)
    return EventRecommendationService(repository, client, router, clock=clock), repository, client


def request(**changes):
    values = {
        "query": "Synthetic event",
        "locale": "ru",
        "date_time": DEPARTURE,
        "available_minutes": 240,
        "origin": {"latitude": 51.13, "longitude": 71.44},
    }
    values.update(changes)
    return EventSearchRequest(**values)


def search(service, **changes):
    return asyncio.run(service.search(request(**changes), now=NOW))


def leg(seconds=600):
    return RouteLeg(
        status="known",
        duration_seconds=seconds,
        distance_meters=600,
        provenance=RouteProvenance(retrieved_at=NOW, provider_locale="en"),
    )


def test_actual_d03_discovery_produces_separate_conditional_cards_and_sources():
    provider, repository, client = service()
    result = search(provider, budget_kzt_per_person=5000)
    assert result.contract_version == "1.3.0" and result.status == "partial"
    assert result.provider_status == "partial" and result.live_web_search == "passed"
    card = result.items[0]
    assert card.event.title == "Synthetic D03 event"
    assert card.session.price_from == 3000 and card.session.price_kind == "starting"
    assert card.activity_code == "other" and card.visit_minutes_estimate is None
    assert card.fit_status == "unknown" and card.route_status == "unavailable"
    assert {"ticket_availability", "price_kzt_per_person", "source_verification"} <= set(
        card.missing_fields
    )
    assert "within_budget" not in card.reason_codes
    assert card.generated_locale == "ru" and "билет" in card.explanation.lower()
    assert len(result.listings) == 1 and result.listings[0].sessions[0] == card.session
    assert all(
        not source.storage_allowed and not source.indexing_allowed for source in result.sources
    )
    assert all(source.source_updated_at is None for source in result.sources)
    assert set(card.session.venue.source_ids) <= set(card.source_ids)
    assert len(client.search_calls) == 1
    assert client.search_calls[0][1]["allowed_domains"] == ALLOWED_DOMAINS
    assert [call[1] for call in client.parse_calls] == [
        TextIntent,
        EventExtractionBatch,
        ExplanationBatch,
    ]
    assert client.parse_calls[1][2]["max_output_tokens"] == 4096
    assert "at most three" in client.parse_calls[1][2]["instructions"]
    assert repository.retrieve_candidates.await_args.kwargs["vector"] is None
    assert "evidence" not in result.model_dump() and "Citation" not in result.model_dump_json()
    TransientEventSearchResponse.model_validate_json(result.model_dump_json())


def test_unknown_end_does_not_admit_a_start_after_the_users_deadline():
    provider, _, _ = service("missingend")
    result = search(provider, available_minutes=30)
    assert result.items == [] and result.status == "partial"
    assert result.listings[0].sessions[0].recommendation_candidate is False
    assert "insufficient_time" in result.listings[0].sessions[0].exclusion_reasons


@pytest.mark.parametrize("case,field", [("baseline", "location"), ("missingend", "ends_at")])
def test_unknown_source_facts_remain_unknown(case, field):
    provider, _, _ = service(case)
    result = search(provider)
    assert result.status == "partial" and result.items
    assert field in result.items[0].missing_fields
    assert result.items[0].fit_status == "unknown"


@pytest.mark.parametrize(
    "case", ["cancelled", "past", "missingyear", "duplicate_cancelled", "listing"]
)
def test_withheld_or_listing_results_never_become_recommendation_cards_or_no_match(case):
    router = AsyncMock()
    provider, repository, client = service(case, router=router)
    result = search(provider)
    assert result.status == "partial" and result.items == [] and result.listings
    repository.retrieve_candidates.assert_not_called()
    router.route.assert_not_called()
    assert ExplanationBatch not in [call[1] for call in client.parse_calls]


def test_known_budget_conflict_is_filtered_before_database_or_route_calls():
    router = AsyncMock()
    provider, repository, _ = service(router=router)
    result = search(provider, budget_kzt_per_person=2500)
    assert result.items == [] and result.status == "partial"
    assert result.excluded_sessions == 1
    assert "price_above_budget" in result.listings[0].sessions[0].exclusion_reasons
    assert not result.listings[0].sessions[0].recommendation_candidate
    repository.retrieve_candidates.assert_not_called()
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "wording",
    [
        "Cancelled session starts 15 January 2030, 19:00",
        "Сеанс отменён: 15 January 2030, 19:00",
        "15 January 2030, 19:00 — концерт отменен",
        "15 January 2030, 19:00 — күші жойылды",
        "Synthetic D03 event cancelled. Session starts 15 January 2030, 19:00",
        "Synthetic D03 event has been cancelled. Session starts 15 January 2030, 19:00",
    ],
)
def test_source_cancellation_overrides_incorrect_scheduled_extraction(wording):
    router = AsyncMock()
    provider, repository, client = service("cancelled", router=router)
    client.data["events"][0]["sessions"][0]["status"] = "scheduled"
    client.data["sources"][0]["text"] = client.data["sources"][0]["text"].replace(
        "Cancelled session starts 15 January 2030, 19:00", wording
    )
    result = search(provider)
    assert result.items == [] and result.status == "partial"
    session = result.listings[0].sessions[0]
    assert session.status == "scheduled"  # The extracted fact is not rewritten.
    assert not session.recommendation_candidate
    assert "source_cancellation" in session.exclusion_reasons
    assert result.excluded_sessions == 1
    repository.retrieve_candidates.assert_not_called()
    router.route.assert_not_called()
    assert ExplanationBatch not in [call[1] for call in client.parse_calls]


@pytest.mark.parametrize(
    "wording",
    [
        "The session is not cancelled and starts 15 January 2030, 19:00",
        "The session has not been cancelled and starts 15 January 2030, 19:00",
        "Сеанс не отменён: 15 January 2030, 19:00",
        "If the session on 15 January 2030, 19:00 is cancelled, tickets are refunded",
        "Tickets for 15 January 2030, 19:00 are refunded in case the event is cancelled",
        "Scheduled session starts 15 January 2030, 19:00; "
        "cancelled session starts 16 January 2030, 19:00",
        "Scheduled session starts 15 January 2030, 19:00; "
        "cancelled session starts 15 January 2030, 20:00",
        "Scheduled session starts 15 January 2030, 19:00, but 20:00 is cancelled",
        "Scheduled session starts 15 January 2030, 19:00. Synthetic D03 event is not cancelled",
        "Scheduled session starts 15 January 2030, 19:00. "
        "Synthetic D03 event cancelled on 16 January 2030",
        "Scheduled session starts 15 January 2030, 19:00. "
        "Synthetic D03 event refund policy for cancelled shows",
    ],
)
def test_other_cancellation_mentions_do_not_withhold_the_selected_session(wording):
    provider, _, client = service()
    client.data["sources"][0]["text"] = client.data["sources"][0]["text"].replace(
        "Scheduled session starts 15 January 2030, 19:00", wording
    )
    result = search(provider)
    assert result.items and result.items[0].session.recommendation_candidate
    assert "source_cancellation" not in result.items[0].session.exclusion_reasons


def add_second_source(client, *, cancel_second=False, different_branch=False):
    second_url = "https://astanaopera.kz/synthetic-d03-copy"
    second = copy.deepcopy(client.data["events"][0])
    second["source_url"] = second_url
    second["sessions"][0]["source_url"] = second_url
    old_address = second["venue_address"]
    if different_branch:
        second["venue_address"] = "Synthetic different street 2, Astana"
    client.data["events"].append(second)
    original_search = client.search_web

    async def two_sources(*args, **kwargs):
        raw = await original_search(*args, **kwargs)
        raw["output"][0]["action"]["sources"].append({"url": second_url})
        message = copy.deepcopy(raw["output"][1])
        part = message["content"][0]
        if cancel_second:
            part["text"] = part["text"].replace("Scheduled session", "Cancelled session")
        if different_branch:
            part["text"] = part["text"].replace(old_address, second["venue_address"])
        part["annotations"][0].update(url=second_url, end_index=len(part["text"]))
        raw["output"].append(message)
        return raw

    client.search_web = two_sources


@pytest.mark.parametrize("incomplete_identity", [False, True])
def test_same_session_from_two_sources_uses_one_alternative_only_with_full_identity(
    incomplete_identity,
):
    router = AsyncMock()
    router.route.return_value = (leg(), RouteLeg(status="not_requested", reason="not_requested"))
    provider, repository, client = service(router=router)
    add_second_source(client)
    if incomplete_identity:
        for event in client.data["events"]:
            event["venue_address"] = None
    result = search(provider)
    assert len(result.listings) == 2  # Original provenance remains separate.
    assert len(result.items) == (2 if incomplete_identity else 1)
    assert len(client.search_calls) == 1
    if incomplete_identity:
        assert all("location" in card.missing_fields for card in result.items)
        router.route.assert_not_called()
    else:
        assert router.route.await_count == 1
        assert repository.retrieve_candidates.await_count == 1


@pytest.mark.parametrize("different_branch", [False, True])
def test_source_cancellation_blocks_exact_copy_without_merging_another_venue_branch(
    different_branch,
):
    provider, repository, client = service()
    add_second_source(client, cancel_second=True, different_branch=different_branch)
    result = search(provider)
    assert len(result.listings) == 2
    assert len(result.items) == (1 if different_branch else 0)
    assert result.excluded_sessions == (1 if different_branch else 2)
    if not different_branch:
        assert {
            reason
            for listing in result.listings
            for session in listing.sessions
            for reason in session.exclusion_reasons
        } == {"source_cancellation", "unresolved_cancellation"}
        repository.retrieve_candidates.assert_not_called()


def test_normalized_cancelled_dto_withholds_exact_scheduled_copy_without_text_guard(monkeypatch):
    from pydantic import HttpUrl

    provider, repository, _ = service()
    event = search(provider).listings[0].model_copy(deep=True)
    cancelled = event.model_copy(deep=True)
    cancelled.event_id = "synthetic:cancelled-event"
    cancelled.source_url = HttpUrl("https://astanaopera.kz/synthetic-cancelled-copy")
    session = cancelled.sessions[0]
    session.event_id = cancelled.event_id
    session.session_id = "synthetic:cancelled-session"
    session.source_url = cancelled.source_url
    session.status = "cancelled"
    session.recommendation_candidate = False
    session.exclusion_reasons = ["cancelled"]
    monkeypatch.setattr(
        event_recommend,
        "discover_events",
        AsyncMock(
            return_value=event_recommend.DiscoveryResult(
                provider_status="partial",
                live_web_search="passed",
                events=[event, cancelled],
                excluded_sessions=1,
            )
        ),
    )
    repository.retrieve_candidates.reset_mock()
    result = search(provider)
    assert result.items == [] and result.excluded_sessions == 2
    assert result.listings[0].sessions[0].status == "scheduled"
    assert result.listings[1].sessions[0].status == "cancelled"
    assert "unresolved_cancellation" in result.listings[0].sessions[0].exclusion_reasons
    assert {source.url for source in result.sources} >= {event.source_url, cancelled.source_url}
    repository.retrieve_candidates.assert_not_called()


def test_return_route_is_independent_and_a_late_return_withholds_the_card():
    router = AsyncMock()
    router.route.return_value = (leg(), leg(600))
    provider, _, _ = service(router=router)
    result = search(provider, return_to_start=True, available_minutes=195)
    assert result.items[0].route_status == "known"
    assert result.items[0].travel_minutes_estimate == 20
    assert router.route.await_args.args[0].return_to_start is True
    router.route.return_value = (leg(), leg(601))
    result = search(provider, return_to_start=True, available_minutes=195)
    assert not result.items and result.status == "partial"
    assert "insufficient_time" in result.listings[0].sessions[0].exclusion_reasons


def test_failed_return_route_does_not_reuse_outbound_duration():
    router = AsyncMock()
    router.route.return_value = (leg(), RouteLeg(status="unknown", reason="route_not_found"))
    provider, _, _ = service(router=router)
    card = search(provider, return_to_start=True).items[0]
    assert card.route_status == "unknown" and card.travel_minutes_estimate is None
    assert "return_travel_minutes_estimate" in card.missing_fields


def test_missing_database_is_optional_and_cannot_erase_discovered_sessions():
    provider, _, _ = service()
    provider.repository = None
    result = search(provider)
    assert result.items and "location" in result.items[0].missing_fields
    provider, repository, _ = service()
    repository.retrieve_candidates.side_effect = DatabaseUnavailable("database_unavailable")
    assert search(provider).items[0].session.venue.location is None


def test_venue_query_truncation_cannot_establish_a_unique_venue():
    provider, repository, _ = service()
    one = repository.retrieve_candidates.return_value[0]
    repository.retrieve_candidates.return_value = [one] * 30
    result = search(provider)
    assert result.items[0].session.venue.location is None
    assert "location" in result.items[0].missing_fields


@pytest.mark.parametrize(
    "query", ["Quiet event", "Событие с розетками", "Wheelchair accessible concert"]
)
def test_unsupported_amenities_require_clarification_without_provider_calls(query):
    provider, repository, client = service()
    result = search(provider, query=query)
    assert result.status == "unknown" and result.provider_code == "unsupported_fact_requirement"
    assert result.warnings[0].code == "missing_input"
    assert client.parse_calls == client.search_calls == []
    repository.retrieve_candidates.assert_not_called()


def test_intent_conflict_stops_before_search_and_form_text_constraints_are_preserved():
    provider, repository, client = service(extracted=text_intent(conflicts=["date_time"]))
    result = search(provider)
    assert result.status == "unknown" and result.provider_code == "constraint_clarification"
    assert not client.search_calls
    repository.retrieve_candidates.assert_not_called()
    resolved_time = DEPARTURE.replace(hour=17)
    provider, _, client = service(
        extracted=text_intent(categories=[], date_time=resolved_time.isoformat())
    )
    search(provider)
    assert resolved_time.isoformat() in client.search_calls[0][0]


def test_provider_failure_and_bad_extraction_have_distinct_evidence_states():
    provider, _, _ = service(search_error=ProviderError("permission_denied"))
    result = search(provider)
    assert result.status == "unavailable" and result.provider_code == "permission_denied"
    assert result.live_web_search == "failed" and not result.items
    provider, _, _ = service(extraction_error=ProviderError("response_incomplete_or_empty"))
    result = search(provider)
    assert result.status == "unknown" and result.live_web_search == "passed"
    assert result.provider_code == "response_incomplete_or_empty" and not result.items
    assert len(result.sources) == 1 and not result.sources[0].storage_allowed
    assert "evidence" not in result.model_dump()


def test_no_client_and_missing_shared_web_method_remain_unavailable():
    result = search(EventRecommendationService(None, None))
    assert result.status == "unavailable" and result.live_web_search == "not_run"
    provider, _, client = service()
    client.search_web = None
    result = search(provider)
    assert (
        result.status == "unavailable"
        and result.provider_code == "shared_web_search_method_missing"
    )


def test_bounded_empty_search_never_claims_complete_absence():
    provider, _, client = service()
    client.data["events"] = []
    result = search(provider)
    assert result.status == "unknown" and result.provider_code == "no_grounded_events"
    assert result.live_web_search == "passed" and not result.items and not result.listings


def test_adapter_enforces_the_extraction_bound_without_extra_calls():
    provider, _, client = service()
    client.data["events"] *= 4
    with pytest.raises(ProviderError, match="event_extraction_limit"):
        asyncio.run(D03Client(client).create_response("Synthetic data"))
    assert len(client.parse_calls) == 1 and not client.search_calls


def test_s03_resolved_request_reaches_unchanged_discovery_with_bounded_deadline(monkeypatch):
    provider, _, _ = service()
    discovery = AsyncMock(
        return_value=event_recommend.DiscoveryResult(
            provider_status="unknown",
            provider_code="no_grounded_events",
            live_web_search="passed",
        )
    )
    monkeypatch.setattr(event_recommend, "discover_events", discovery)
    search(provider, return_to_start=True)
    passed_request = discovery.await_args.args[1]
    assert passed_request.return_to_start and passed_request.available_minutes == 240
    assert discovery.await_args.kwargs["timeout_seconds"] == 80
    assert "pois" not in discovery.await_args.kwargs


def test_runtime_explanation_never_receives_routes_or_provider_prose():
    router = AsyncMock()
    router.route.return_value = (
        leg(1234),
        RouteLeg(status="not_requested", reason="not_requested"),
    )
    provider, _, client = service(router=router)
    search(provider)
    explanation = next(call[0] for call in client.parse_calls if call[1] is ExplanationBatch)
    packet = json.loads(explanation)["alternatives"][0]
    assert "within_time" not in packet["allowed_reason_codes"]
    assert "route" not in explanation and "1234" not in explanation
    assert client.data["sources"][0]["text"] not in explanation


def test_shortlist_bounds_routes_and_reuses_one_venue_query(monkeypatch):
    router = AsyncMock()
    router.route.return_value = (leg(), leg())
    provider, repository, client = service(router=router)
    original = search(provider)
    events = []
    for index in range(5):
        event = original.listings[0].model_copy(deep=True)
        event.event_id = f"synthetic:bounded:event:{index}"
        event.title = f"Synthetic bounded event {index}"
        event.sessions[0].event_id = event.event_id
        event.sessions[0].session_id = f"synthetic:bounded:session:{index}"
        events.append(event)
    monkeypatch.setattr(
        event_recommend,
        "discover_events",
        AsyncMock(
            return_value=event_recommend.DiscoveryResult(
                provider_status="partial",
                provider_code="unverified_source_facts",
                live_web_search="passed",
                events=events,
            )
        ),
    )
    repository.retrieve_candidates.reset_mock()
    router.route.reset_mock()
    client.parse_calls.clear()
    result = search(provider, return_to_start=True)
    assert len(result.items) == 3 and len(result.listings) == 5
    assert router.route.await_count == 3  # At most six independent legs in the adapter.
    assert all(call.args[0].return_to_start for call in router.route.await_args_list)
    assert repository.retrieve_candidates.await_count == 1
    assert [call[1] for call in client.parse_calls] == [TextIntent, ExplanationBatch]


def test_route_timeout_degrades_to_a_conditional_card(monkeypatch):
    async def route(_):
        await asyncio.sleep(0.05)
        return leg(), leg()

    router = AsyncMock()
    router.route.side_effect = route
    monkeypatch.setattr(event_recommend, "ROUTE_DEADLINE_SECONDS", 0.001)
    provider, _, _ = service(router=router)
    result = search(provider, return_to_start=True)
    assert result.items[0].route_status == "unavailable"
    assert result.items[0].travel_minutes_estimate is None
    assert "return_travel_minutes_estimate" in result.items[0].missing_fields


def test_runtime_and_venue_source_identity_conflict_withholds_only_the_venue():
    from backend.app.event_schemas import transient_source_id

    provider, repository, client = service()
    row = repository.retrieve_candidates.return_value[0]["document"]
    conflicting_id = transient_source_id(client.data["events"][0]["source_url"])
    row["primary_source_id"] = conflicting_id
    row["sources"][0]["source_id"] = conflicting_id
    row["provenance"][0]["source_id"] = conflicting_id
    result = search(provider)
    assert result.items and result.items[0].session.venue.location is None
    assert len(result.sources) == 1


def test_borrowed_shared_client_is_not_closed_by_the_event_service():
    provider, _, client = service()
    client.close = AsyncMock()
    client.aclose = AsyncMock()
    search(provider)
    client.close.assert_not_called()
    client.aclose.assert_not_called()


def test_full_consulted_source_envelope_keeps_venue_unknown_without_losing_references(monkeypatch):
    provider, _, _ = service()
    original = search(provider)
    event = original.listings[0].model_copy(deep=True)
    event.sessions[0].venue = VenueMatch()
    evidence = SearchEvidence(
        text="",
        citations=[],
        sources=[EvidenceSource(url=event.source_url, fetched_at=NOW)]
        + [
            EvidenceSource(url=f"https://ticketon.kz/synthetic-consulted-{index}", fetched_at=NOW)
            for index in range(99)
        ],
    )
    monkeypatch.setattr(
        event_recommend,
        "discover_events",
        AsyncMock(
            return_value=event_recommend.DiscoveryResult(
                provider_status="partial",
                live_web_search="passed",
                events=[event],
                evidence=evidence,
            )
        ),
    )
    result = search(provider)
    assert len(result.sources) == 100
    assert result.items[0].session.venue.location is None
    assert all(not source.storage_allowed for source in result.sources)


def test_normalizer_only_data_is_never_upgraded_to_live_search_evidence(monkeypatch):
    from pydantic import ValidationError

    provider, _, _ = service()
    original = search(provider)
    monkeypatch.setattr(
        event_recommend,
        "discover_events",
        AsyncMock(
            return_value=event_recommend.DiscoveryResult(
                provider_status="partial",
                live_web_search="not_run",
                events=original.listings,
            )
        ),
    )
    with pytest.raises(ValidationError, match="completed live search"):
        search(provider)


def test_discovery_delay_withholds_a_session_that_has_started_without_changing_evidence_anchor():
    state = {"now": NOW}
    provider, repository, client = service(clock=lambda: state["now"])
    original_search = client.search_web

    async def delayed_search(*args, **kwargs):
        evidence = await original_search(*args, **kwargs)
        state["now"] = NOW.replace(hour=19, minute=1)
        return evidence

    client.search_web = delayed_search
    result = asyncio.run(provider.search(request()))
    assert not result.items and result.status == "partial"
    session = result.listings[0].sessions[0]
    assert not session.recommendation_candidate and "past_session" in session.exclusion_reasons
    assert session.source_fetched_at == NOW and result.excluded_sessions == 1
    repository.retrieve_candidates.assert_not_called()
    assert len(client.search_calls) == 1
    assert ExplanationBatch not in [call[1] for call in client.parse_calls]


def test_route_delay_rechecks_arrival_with_the_original_known_leg():
    state = {"now": NOW}
    router = AsyncMock()

    async def delayed_route(_):
        state["now"] = NOW.replace(hour=18, minute=50)
        return leg(), RouteLeg(status="not_requested", reason="not_requested")

    router.route.side_effect = delayed_route
    provider, _, client = service(router=router, clock=lambda: state["now"])
    result = asyncio.run(provider.search(request()))
    assert not result.items and result.excluded_sessions == 1
    assert "insufficient_arrival_time" in result.listings[0].sessions[0].exclusion_reasons
    assert router.route.await_count == 1
    assert ExplanationBatch not in [call[1] for call in client.parse_calls]


@pytest.mark.parametrize(
    "late,reason",
    [
        (NOW.replace(hour=18, minute=50), "insufficient_arrival_time"),
        (NOW.replace(hour=19, minute=1), "past_session"),
    ],
)
def test_explanation_delay_withholds_stale_cards_without_repeating_provider_calls(late, reason):
    state = {"now": NOW}
    router = AsyncMock()
    router.route.return_value = (leg(), RouteLeg(status="not_requested", reason="not_requested"))
    provider, repository, client = service(router=router, clock=lambda: state["now"])
    original_parse = client.parse_response

    async def delayed_explanation(text, schema, **kwargs):
        result = await original_parse(text, schema, **kwargs)
        if schema is ExplanationBatch:
            state["now"] = late
        return result

    client.parse_response = delayed_explanation
    result = asyncio.run(provider.search(request()))
    assert not result.items and result.status == "partial" and result.excluded_sessions == 1
    session = result.listings[0].sessions[0]
    assert not session.recommendation_candidate and reason in session.exclusion_reasons
    assert session.source_fetched_at == NOW
    assert router.route.await_count == 1 and repository.retrieve_candidates.await_count == 1
    assert len(client.search_calls) == 1
    assert [call[1] for call in client.parse_calls] == [
        TextIntent,
        EventExtractionBatch,
        ExplanationBatch,
    ]


def test_explicit_now_keeps_the_callers_deterministic_clock_fixed():
    clock = Mock(return_value=NOW.replace(hour=19, minute=1))
    provider, _, _ = service(clock=clock)
    assert search(provider).items
    clock.assert_not_called()
