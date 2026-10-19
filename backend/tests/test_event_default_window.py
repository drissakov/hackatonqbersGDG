"""Synthetic future sessions do not acquire an unrequested current-day restriction."""

from datetime import timedelta

from backend.app.event_constraints import evaluate_event_session
from backend.tests.test_event_constraints import DEPARTURE, NOW, intent, known_leg, session_for


def future_session():
    session = session_for()
    return session.model_copy(
        update={
            "starts_at": session.starts_at + timedelta(days=2),
            "ends_at": session.ends_at + timedelta(days=2),
        }
    )


def test_missing_date_and_duration_keep_future_session_conditional():
    result = evaluate_event_session(
        future_session(),
        intent(date_time=None, available_minutes=None),
        known_leg(),
        now=NOW,
        window_start=NOW,
    )

    assert not result.rejected
    assert result.fit_status == "unknown"
    assert "outside_selected_date" not in result.exclusion_reasons
    assert {"date_time", "available_minutes", "ticket_availability"} <= set(result.missing_fields)


def test_explicit_selected_date_still_rejects_later_date():
    result = evaluate_event_session(
        future_session(),
        intent(date_time=DEPARTURE, available_minutes=None),
        known_leg(),
        now=NOW,
    )

    assert result.rejected and result.fit_status == "does_not_fit"
    assert "outside_selected_date" in result.exclusion_reasons


def test_missing_date_preserves_explicit_duration_deadline():
    result = evaluate_event_session(
        future_session(),
        intent(date_time=None, available_minutes=240),
        known_leg(),
        now=NOW,
        window_start=NOW,
    )

    assert result.rejected and result.fit_status == "does_not_fit"
    assert "insufficient_time" in result.exclusion_reasons
    assert "outside_selected_date" not in result.exclusion_reasons


def test_missing_date_still_rejects_past_sessions():
    session = session_for().model_copy(
        update={"starts_at": NOW - timedelta(hours=2), "ends_at": NOW - timedelta(hours=1)}
    )
    result = evaluate_event_session(
        session,
        intent(date_time=None, available_minutes=None),
        known_leg(),
        now=NOW,
    )

    assert result.rejected and result.fit_status == "does_not_fit"
    assert "past_session" in result.exclusion_reasons
