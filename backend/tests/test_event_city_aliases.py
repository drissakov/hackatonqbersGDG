"""Synthetic city wording must not discard Astana or admit another venue city."""

import pytest

from backend.tests.test_events import SYNTHETIC_TEXT, candidate, evidence, normalize


@pytest.mark.parametrize(
    "city",
    ["г. Астана", "Астане", "в Астане", "Астана қ.", "Астанада", "Астана қаласында", "Astana city"],
)
def test_normalized_astana_city_wording_preserves_the_event(city):
    proof = evidence(SYNTHETIC_TEXT.replace("Astana;", city + ";"))
    result = normalize(candidate(city=city), proof=proof)
    assert result.rejected_events == 0
    assert result.events[0].sessions[0].recommendation_candidate


@pytest.mark.parametrize("city", ["г. Алматы", "Astana International Hotel"])
def test_other_city_or_hotel_named_astana_does_not_become_the_city(city):
    proof = evidence(SYNTHETIC_TEXT.replace("Astana;", city + ";"))
    result = normalize(candidate(city=city), proof=proof)
    assert result.events == []
    assert result.rejected_events == 1


def test_astana_in_a_hotel_name_cannot_ground_the_session_city():
    text = (
        "Synthetic D03 event. City: Almaty. Venue: Astana International Hotel. "
        "19 October 2026, 19:00."
    )
    result = normalize(
        candidate(city="Astana", venue_name="Astana International Hotel"), proof=evidence(text)
    )
    session = result.events[0].sessions[0]
    assert session.city is None
    assert not session.recommendation_candidate
    assert "city_unknown" in session.exclusion_reasons


def test_typographic_title_quotes_do_not_change_event_identity():
    text = SYNTHETIC_TEXT.replace("Synthetic D03 event", "Synthetic “D03” event")
    result = normalize(candidate(title='Synthetic "D03" event'), proof=evidence(text))
    assert len(result.events) == 1
    assert result.events[0].sessions[0].recommendation_candidate


@pytest.mark.parametrize("label", ["City", "Город", "Қала"])
def test_explicit_city_is_preserved_when_the_venue_has_the_same_name(label):
    text = f"Synthetic D03 event. {label}: Astana. Venue: Astana. 19 October 2026, 19:00."
    result = normalize(candidate(city="Astana", venue_name="Astana"), proof=evidence(text))
    session = result.events[0].sessions[0]
    assert session.city == "Astana"
    assert session.recommendation_candidate
