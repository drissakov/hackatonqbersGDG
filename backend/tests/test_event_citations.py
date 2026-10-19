"""Synthetic provider citation variants remain bound to observed allowed pages."""

import pytest

from backend.app.openai_client import ProviderError
from backend.app.services.events.discover import parse_search_evidence
from backend.tests.test_events import NOW, OTHER_SYNTHETIC_URL, SYNTHETIC_URL, raw_search


@pytest.mark.parametrize("source_has_tracking", [False, True])
@pytest.mark.parametrize("marker", ["openai", "chatgpt.com"])
def test_provider_attribution_marker_does_not_drop_a_consulted_source(source_has_tracking, marker):
    raw = raw_search()
    tracked = SYNTHETIC_URL + f"?utm_source={marker}"
    source_url, citation_url = (
        (tracked, SYNTHETIC_URL) if source_has_tracking else (SYNTHETIC_URL, tracked)
    )
    raw["output"][0]["action"]["sources"][0]["url"] = source_url
    raw["output"][1]["content"][0]["annotations"][0]["url"] = citation_url
    evidence = parse_search_evidence(raw, fetched_at=NOW)
    assert str(evidence.citations[0].url) == citation_url
    assert citation_url in {str(source.url) for source in evidence.sources}


@pytest.mark.parametrize("action", ["open_page", "find_in_page"])
def test_completed_page_action_can_supply_a_source_after_search(action):
    raw = raw_search()
    raw["output"][1]["content"][0]["annotations"][0]["url"] = OTHER_SYNTHETIC_URL
    raw["output"].insert(
        1,
        {
            "type": "web_search_call",
            "status": "completed",
            "action": {"type": action, "url": OTHER_SYNTHETIC_URL},
        },
    )
    evidence = parse_search_evidence(raw, fetched_at=NOW)
    assert str(evidence.citations[0].url) == OTHER_SYNTHETIC_URL


@pytest.mark.parametrize("status", ["searching", "failed", None])
def test_unfinished_page_action_does_not_supply_citation_provenance(status):
    raw = raw_search()
    raw["output"][1]["content"][0]["annotations"][0]["url"] = OTHER_SYNTHETIC_URL
    raw["output"].insert(
        1,
        {
            "type": "web_search_call",
            "status": status,
            "action": {"type": "open_page", "url": OTHER_SYNTHETIC_URL},
        },
    )
    with pytest.raises(ProviderError, match="web_search_citations_missing"):
        parse_search_evidence(raw, fetched_at=NOW)


@pytest.mark.parametrize(
    "citation_url",
    [
        SYNTHETIC_URL + "?date=2030-01-01&utm_source=openai",
        SYNTHETIC_URL + "?utm_source=unrecognized",
        OTHER_SYNTHETIC_URL + "?utm_source=openai",
        "https://ticketon.kz.evil.invalid/synthetic?utm_source=openai",
    ],
)
def test_tracking_match_cannot_change_business_parameters_page_or_domain(citation_url):
    raw = raw_search()
    raw["output"][1]["content"][0]["annotations"][0]["url"] = citation_url
    with pytest.raises(ProviderError, match="web_search_citations_missing"):
        parse_search_evidence(raw, fetched_at=NOW)


def test_rejection_counters_do_not_log_provider_text_urls_or_titles(caplog):
    raw = raw_search()
    part = raw["output"][1]["content"][0]
    part["annotations"][0]["end_index"] = len(part["text"]) + 1
    with pytest.raises(ProviderError, match="web_search_citations_missing"):
        parse_search_evidence(raw, fetched_at=NOW)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.args == (1, 1, 0, 1, 0)
    assert "event_citations_missing" in record.message
    assert "Synthetic" not in record.message and "https://" not in record.message
