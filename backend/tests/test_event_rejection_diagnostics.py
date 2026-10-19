"""Rejected synthetic events log anonymous reason codes, never discovery payloads."""

import logging

import pytest

from backend.app.services.events.normalize import normalize_events
from backend.tests.test_events import (
    NOW,
    SELECTED,
    SYNTHETIC_TEXT,
    SYNTHETIC_URL,
    candidate,
    evidence,
)

CANARY = "SYNTHETIC_PRIVATE_PAYLOAD_CANARY"


@pytest.mark.parametrize("code", ["url_not_observed", "title_not_supported", "other_city"])
def test_event_rejection_logs_only_a_static_reason(code, caplog):
    proof = evidence(SYNTHETIC_TEXT + f" {CANARY}")
    if code == "url_not_observed":
        row = candidate(source_url=f"{SYNTHETIC_URL}?synthetic-query={CANARY}")
    elif code == "title_not_supported":
        row = candidate(title=f"Synthetic unsupported event {CANARY}")
    else:
        row = candidate(city="Almaty")
        proof = evidence(SYNTHETIC_TEXT.replace("Astana", "Almaty") + f" {CANARY}")
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        result = normalize_events([row], proof, now=NOW, selected_at=SELECTED)

    assert result.provider_status == "unknown" and result.rejected_events == 1
    assert result.events == []
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.msg == "event_rejected code=%s"
    assert record.args == (code,)
    assert record.getMessage() == f"event_rejected code={code}"
    assert CANARY not in caplog.text and "https://" not in caplog.text
    assert "Astana" not in caplog.text and "Almaty" not in caplog.text


def test_source_without_a_citation_remains_rejected_without_logging_its_url(caplog):
    proof = evidence().model_copy(update={"citations": []})
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        result = normalize_events([candidate()], proof, now=NOW, selected_at=SELECTED)
    assert result.rejected_events == 1 and result.events == []
    assert caplog.records[0].args == ("url_not_observed",)
    assert SYNTHETIC_URL not in caplog.text


def test_supported_event_does_not_emit_rejection_diagnostics(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.app.services.events.normalize"):
        result = normalize_events([candidate()], evidence(), now=NOW, selected_at=SELECTED)
    assert result.rejected_events == 0 and len(result.events) == 1
    assert caplog.records == []
