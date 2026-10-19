"""Synthetic regressions for source-bound titles and the default event window."""

import asyncio
import json

import pytest

from backend.app.event_schemas import TransientEventSearchResponse
from backend.app.schemas import EventSearchRequest
from backend.app.services.events.discover import (
    build_search_prompt,
    discover_events,
    parse_search_evidence,
)
from backend.app.services.events.normalize import normalize_events
from backend.tests.test_event_recommend import search, service
from backend.tests.test_events import (
    NOW,
    OTHER_SYNTHETIC_URL,
    SELECTED,
    SYNTHETIC_TEXT,
    SYNTHETIC_URL,
    SyntheticSearchClient,
    candidate,
    raw_search,
)


def heading_search(*, cited_title="Synthetic D03 event — synthetic tickets"):
    raw = raw_search()
    part = raw["output"][1]["content"][0]
    part["text"] = "## Synthetic D03 event\n\n" + SYNTHETIC_TEXT.split(": ", 1)[1] + " [1]"
    part["annotations"][0].update(
        title=cited_title,
        start_index=len(part["text"]) - 3,
        end_index=len(part["text"]),
    )
    return raw


def test_source_title_preserves_event_when_search_uses_a_separate_heading():
    evidence = parse_search_evidence(heading_search(), fetched_at=NOW)
    assert not evidence.citations[0].context.startswith("## Synthetic D03 event")
    result = normalize_events([candidate()], evidence, now=NOW, selected_at=SELECTED)
    assert result.rejected_events == 0
    assert result.provider_status == "partial"
    session = result.events[0].sessions[0]
    assert session.starts_at.isoformat() == "2026-10-19T19:00:00+05:00"
    assert session.recommendation_candidate


def test_source_title_from_another_url_cannot_identify_the_event():
    raw = heading_search(cited_title="Unrelated synthetic page")
    raw["output"][0]["action"]["sources"].append({"url": OTHER_SYNTHETIC_URL})
    annotation = dict(raw["output"][1]["content"][0]["annotations"][0])
    annotation.update(url=OTHER_SYNTHETIC_URL, title="Synthetic D03 event")
    raw["output"][1]["content"][0]["annotations"].append(annotation)
    evidence = parse_search_evidence(raw, fetched_at=NOW)
    result = normalize_events([candidate()], evidence, now=NOW, selected_at=SELECTED)
    assert result.events == []
    assert result.rejected_events == 1


def test_source_title_must_contain_the_complete_event_name():
    evidence = parse_search_evidence(
        heading_search(cited_title="Synthetic D03 eventual unrelated page"), fetched_at=NOW
    )
    result = normalize_events([candidate()], evidence, now=NOW, selected_at=SELECTED)
    assert result.events == []
    assert result.rejected_events == 1


def test_source_title_does_not_supply_city_venue_or_timestamp():
    raw = heading_search(
        cited_title="Synthetic D03 event Astana Synthetic venue 19 October 2026, 19:00"
    )
    part = raw["output"][1]["content"][0]
    part["text"] = "## Synthetic D03 event\n\nSee this synthetic event page. [1]"
    part["annotations"][0].update(start_index=len(part["text"]) - 3, end_index=len(part["text"]))
    evidence = parse_search_evidence(raw, fetched_at=NOW)
    result = normalize_events([candidate()], evidence, now=NOW, selected_at=SELECTED)
    event = result.events[0]
    assert str(event.source_url) == SYNTHETIC_URL
    assert event.city is None and event.venue_name is None and event.venue_address is None
    assert event.sessions[0].starts_at is None
    assert not event.sessions[0].recommendation_candidate


def test_blank_date_searches_upcoming_window_but_selected_date_stays_exact():
    upcoming = build_search_prompt(
        EventSearchRequest(query="Synthetic events", locale="ru"), selected_at=NOW
    )
    assert "upcoming from 2026-10-19 through 2026-11-18" in upcoming
    exact = build_search_prompt(
        EventSearchRequest(query="Synthetic events", locale="ru", date_time=SELECTED),
        selected_at=SELECTED,
    )
    assert "for the full date 2026-10-19" in exact
    assert "2026-11-18" not in exact


def test_discovery_keeps_future_dated_event_when_no_date_was_requested():
    raw = raw_search()
    part = raw["output"][1]["content"][0]
    part["text"] = part["text"].replace("19 October 2026", "30 October 2026")
    part["annotations"][0]["end_index"] = len(part["text"])
    row = candidate().model_dump(mode="json")
    session = row["sessions"][0]
    for field in ("starts_at", "ends_at"):
        session[field] = session[field].replace("2026-10-19", "2026-10-30")
    for field in ("date_text", "end_text"):
        session[field] = session[field].replace("19 October 2026", "30 October 2026")
    client = SyntheticSearchClient(response=raw, normalization=json.dumps({"events": [row]}))
    result = asyncio.run(
        discover_events(client, EventSearchRequest(query="Synthetic events", locale="ru"), now=NOW)
    )
    assert result.provider_status == "partial"
    assert result.events[0].sessions[0].recommendation_candidate
    assert result.events[0].sessions[0].starts_at.day == 30


@pytest.mark.parametrize("locale", ["kk", "ru", "en"])
def test_default_search_composes_future_event_card_with_date_and_source(locale):
    provider, _, client = service("baseline")
    session = client.data["events"][0]["sessions"][0]
    for field in ("starts_at", "ends_at"):
        session[field] = session[field].replace("2030-01-15", "2030-01-20")
    for field in ("date_text", "end_text"):
        session[field] = session[field].replace("15 January", "20 January")
    client.data["sources"][0]["text"] = client.data["sources"][0]["text"].replace(
        "15 January", "20 January"
    )
    result = search(provider, date_time=None, available_minutes=None, origin=None, locale=locale)
    TransientEventSearchResponse.model_validate_json(result.model_dump_json())
    assert result.status == "partial" and result.live_web_search == "passed"
    assert len(result.items) == 1
    card = result.items[0]
    assert card.session.starts_at.isoformat() == "2030-01-20T19:00:00+05:00"
    assert card.event.title == "Synthetic D03 event"
    assert card.action.url == card.session.source_url
    assert card.generated_locale == locale and card.fit_status == "unknown"
    assert "ticket_availability" in card.missing_fields
    assert all(
        not source.storage_allowed and not source.indexing_allowed for source in result.sources
    )


def test_literal_schedule_survives_a_missing_model_iso_timestamp():
    provider, _, client = service("baseline")
    facts = client.data["events"][0]["sessions"][0]
    facts.update(starts_at=None, ends_at=None)
    result = search(provider, date_time=None, available_minutes=None, origin=None)
    assert result.status == "partial" and len(result.items) == 1
    card = result.items[0]
    assert card.session.starts_at.isoformat() == "2030-01-15T19:00:00+05:00"
    assert card.session.ends_at.isoformat() == "2030-01-15T21:00:00+05:00"
    assert card.action.url == card.session.source_url
    assert card.fit_status == "unknown"
    assert "ticket_availability" in card.missing_fields
