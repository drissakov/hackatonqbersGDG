"""Playground intent recovery preserves explicit constraints in every UI language."""

import pytest

from backend.app.poi_features import load_feature_catalog
from backend.app.schemas import ActivityCode
from backend.tests.test_constraints import route
from backend.tests.test_poi_features import catalog, curated, feature_service, recommend
from backend.tests.test_recommend import candidate_row, record

PLAYGROUND_QUERIES = [
    ("kk", "Балалар ойын алаңын тап."),
    ("ru", "Найди детскую площадку."),
    ("en", "Find a playground."),
]
FAMILY_WALK_QUERIES = [
    ("kk", "Баламен серуендеуге орын ұсын."),
    ("ru", "Предложи прогулку с ребёнком."),
    ("en", "Suggest a walk with a child."),
]


def playground(**updates):
    values = {
        "id": "test:playground-search",
        "name": "SYNTHETIC TEST ONLY - Search Playground",
        "activity_code": "entertainment",
        "opening_hours_text": "24/7",
        "price_kzt_per_person": 0,
        "indoor": False,
        **updates,
    }
    source = record(**values)
    return curated(poi=source.model_dump(mode="json"))


@pytest.mark.parametrize("categories", [(), ("walk",), ("entertainment",)])
@pytest.mark.parametrize("locale,query", PLAYGROUND_QUERIES)
def test_direct_playground_search_uses_real_catalog_even_when_extractor_loses_child_interest(
    locale, query, categories
):
    checked = load_feature_catalog()
    assert checked is not None and len(checked.records) == 22
    search, repository, client, _ = feature_service(checked, categories=categories)
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "partial" and 1 <= len(result.items) <= 3
    checked_places = {row.poi.id: row for row in checked.records}
    for card in result.items:
        source = checked_places[card.poi.id]
        assert card.poi.activity_code == ActivityCode.ENTERTAINMENT
        assert card.poi == source.poi and card.feature_evidence == source.evidence
        assert not card.poi.is_test and all(not item.is_test for item in card.poi.sources)
        assert "family_playground_match" in card.reason_codes
        assert "child_suitability" not in card.missing_fields
        assert card.visit_minutes_estimate == 18 and card.travel_minutes_estimate == 2
        assert card.visit_minutes_estimate + card.travel_minutes_estimate + 10 == 30
    repository.retrieve_candidates.assert_not_called()
    client.embed.assert_not_called()


@pytest.mark.parametrize("locale,query", PLAYGROUND_QUERIES)
def test_direct_playground_without_type_evidence_stays_unknown_without_city_corpus_fallback(
    locale, query
):
    search, repository, client, router = feature_service(None, categories=("walk",))
    repository.retrieve_candidates.return_value = [candidate_row(playground().poi)]
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "unknown" and not result.items
    assert any("child_suitability" in warning.fields for warning in result.warnings)
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []


@pytest.mark.parametrize("locale,query", FAMILY_WALK_QUERIES)
def test_family_walk_can_select_a_proved_entertainment_playground_without_reclassifying_source(
    locale, query
):
    row = playground()
    source_before = row.poi.model_dump(mode="json")
    search, repository, _, _ = feature_service(catalog(row), categories=("walk",))
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "ok" and len(result.items) == 1
    card = result.items[0]
    assert card.poi.model_dump(mode="json") == source_before
    assert row.poi.model_dump(mode="json") == source_before
    assert card.activity_code == ActivityCode.ENTERTAINMENT
    assert card.visit_minutes_estimate == 18 and card.fit_status == "fits"
    repository.retrieve_candidates.assert_not_called()


@pytest.mark.parametrize(
    "locale,query,generic_name",
    [
        (*PLAYGROUND_QUERIES[0], "балалар ойын алаңы"),
        (*PLAYGROUND_QUERIES[1], "детская площадка"),
        (*PLAYGROUND_QUERIES[2], "playground"),
    ],
)
def test_generic_place_type_in_extracted_names_is_not_treated_as_a_named_venue(
    locale, query, generic_name
):
    row = playground()
    search, _, _, _ = feature_service(catalog(row), categories=("walk",), names=(generic_name,))
    result = recommend(search, query, locale, available_minutes=30)
    assert [card.poi.id for card in result.items] == [row.poi.id]


@pytest.mark.parametrize(
    "locale,query",
    [
        ("kk", "Баламен саябақта серуендеуге орын ұсын."),
        ("kk", "Баламен кафеде серуендеуге орын ұсын."),
        ("ru", "Предложи прогулку с ребёнком в музее."),
        ("en", "Suggest a walk with a child in a cafe."),
    ],
)
@pytest.mark.parametrize("category", ["walk", "entertainment"])
def test_explicit_park_museum_or_cafe_is_not_replaced_by_a_playground(locale, query, category):
    search, _, _, router = feature_service(catalog(playground()), categories=(category,))
    result = recommend(search, query, locale, available_minutes=30)
    assert not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize("category", ["culture", "museum", "food"])
def test_extracted_nonwalk_category_remains_strict_for_a_direct_playground_query(category):
    search, _, _, router = feature_service(catalog(playground()), categories=(category,))
    result = recommend(search, "Find a playground.", available_minutes=30)
    assert not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize("matches", [False, True])
def test_specific_venue_name_filter_is_preserved_instead_of_dropped(matches):
    row = playground()
    name = row.poi.name if matches else "SYNTHETIC TEST ONLY - Different Named Venue"
    search, _, _, router = feature_service(catalog(row), categories=("walk",), names=(name,))
    result = recommend(search, f'Find a playground named "{name}".', available_minutes=30)
    assert [card.poi.id for card in result.items] == ([row.poi.id] if matches else [])
    if not matches:
        router.route.assert_not_called()


def test_explicit_venue_named_playground_does_not_match_an_unnamed_derived_display_label():
    checked = load_feature_catalog()
    assert checked is not None and all(row.name_is_derived for row in checked.records)
    search, _, _, router = feature_service(
        checked, categories=("entertainment",), names=("Playground",)
    )
    result = recommend(search, 'Find a playground named "Playground".', available_minutes=30)
    assert not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "locale,query",
    [
        ("kk", "Unknown Specific Place атты балалар ойын алаңын тап."),
        ("ru", "Найди детскую площадку под названием «Unknown Specific Place»."),
        ("en", 'Find a playground named "Unknown Specific Place".'),
        ("en", "Find a playground 'Sunrise'."),
        ("ru", "Найди детскую площадку ‘Sunrise’."),
    ],
)
def test_lost_explicit_venue_name_never_falls_back_to_an_unrelated_playground(locale, query):
    search, _, _, router = feature_service(catalog(playground()), categories=("walk",), names=())
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "unknown" and not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "locale,query,missing",
    [
        ("kk", "6 жаста баламен ойын алаңына бару.", "age_restrictions"),
        ("ru", "Найди тихую детскую площадку.", None),
        ("en", "Find a playground with a charging point for my phone.", "power_outlets"),
        ("en", "Find a wheelchair accessible playground.", None),
    ],
)
def test_playground_intent_recovery_cannot_prove_unsupported_requirements(locale, query, missing):
    search, _, _, router = feature_service(catalog(playground()), categories=("walk",))
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "unknown" and not result.items
    if missing is not None:
        assert any(missing in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "locale,query",
    [
        ("kk", "Балалар ойын алаңын ұсынба."),
        ("ru", "Не предлагай детскую площадку."),
        ("en", "Do not suggest a playground."),
    ],
)
def test_negative_playground_mention_is_not_promoted_to_a_positive_playground_match(locale, query):
    row = playground()
    search, repository, client, router = feature_service(catalog(row), categories=("walk",))
    # An ordinary city retrieval would otherwise return a known playground.
    repository.retrieve_candidates.return_value = [candidate_row(row.poi)]
    result = recommend(search, query, locale, available_minutes=30)
    assert result.status == "unknown" and not result.items
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []


@pytest.mark.parametrize(
    "locale,query",
    [
        ("kk", "Серуендеуге орын ұсын."),
        ("ru", "Предложи прогулку."),
        ("en", "Suggest a walk."),
    ],
)
def test_general_walk_without_child_requirement_keeps_the_normal_city_retrieval(locale, query):
    search, repository, client, router = feature_service(
        catalog(playground()), categories=("walk",)
    )
    result = recommend(search, query, locale, available_minutes=30)
    assert not result.items
    repository.retrieve_candidates.assert_awaited_once()
    client.embed.assert_awaited_once()
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "locale,query,name",
    [
        ("en", "Find a cafe called Playground.", "Playground"),
        ("ru", "Найди кафе под названием «Детская площадка».", "Детская площадка"),
    ],
)
def test_playground_words_in_a_cafe_name_keep_named_food_retrieval(locale, query, name):
    checked = load_feature_catalog()
    assert checked is not None
    cafe = record(
        id="test:named-cafe-playground",
        name=name,
        activity_code="food",
        opening_hours_text="24/7",
        price_kzt_per_person=0,
        indoor=True,
    )
    search, repository, _, _ = feature_service(checked, categories=("food",), names=(name,))
    repository.retrieve_candidates.return_value = [candidate_row(cafe)]
    result = recommend(search, query, locale)
    assert [card.poi.id for card in result.items] == [cafe.id]
    repository.retrieve_candidates.assert_awaited_once()
    assert repository.retrieve_candidates.await_args.kwargs["names"] == [name]
    assert repository.retrieve_candidates.await_args.kwargs["categories"] == [ActivityCode.FOOD]
    card = result.items[0]
    assert card.poi.name == name and card.activity_code == ActivityCode.FOOD
    assert "family_playground_match" not in card.reason_codes
    assert card.feature_evidence == []


@pytest.mark.parametrize("constraint", ["geography", "budget", "time", "indoor", "return"])
def test_recovered_family_walk_preserves_hard_constraints(constraint):
    updates, request = {}, {"available_minutes": 30}
    if constraint == "geography":
        updates["location"] = {"latitude": 52.0, "longitude": 71.43}
    elif constraint == "budget":
        updates["price_kzt_per_person"] = 2000
        request.update(budget_kzt_per_person=1000, explicit_fields=["budget_kzt_per_person"])
    elif constraint == "time":
        request.update(available_minutes=19, explicit_fields=["available_minutes"])
    elif constraint == "indoor":
        request.update(indoor_only=True, explicit_fields=["indoor_only"])
    else:
        request.update(return_to_start=True, explicit_fields=["return_to_start"])
    search, _, _, router = feature_service(catalog(playground(**updates)), categories=("walk",))
    if constraint == "return":
        router.route.return_value = (route(120), route(3600))
    result = recommend(search, FAMILY_WALK_QUERIES[2][1], **request)
    assert not result.items
    if constraint == "return":
        router.route.assert_awaited_once()
        assert router.route.await_args.args[0].return_to_start is True
    else:
        router.route.assert_not_called()
