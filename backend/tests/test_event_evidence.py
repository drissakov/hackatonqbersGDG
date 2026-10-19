"""Narrow cancellation evidence checks never borrow another source's status."""

from backend.app.event_evidence import has_source_cancellation
from backend.app.services.events.models import Citation, EvidenceSource, SearchEvidence
from backend.tests.test_event_constraints import NOW, session_for


def test_cancellation_on_another_url_cannot_cancel_the_selected_source():
    session = session_for()
    url = "https://astanaopera.kz/synthetic-other-session"
    text = "Cancelled session starts 15 January 2030, 19:00"
    evidence = SearchEvidence(
        text=text,
        sources=[EvidenceSource(url=url, fetched_at=NOW)],
        citations=[
            Citation(
                url=url,
                title="Synthetic other source",
                start_index=0,
                end_index=len(text),
                text=text,
                context=text,
            )
        ],
    )
    assert not has_source_cancellation(session, evidence)
    assert not has_source_cancellation(session, None)
