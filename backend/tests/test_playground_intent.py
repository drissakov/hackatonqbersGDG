"""Three-language playground query policy without model-dependent category guesses."""

import pytest

from backend.app.playground_intent import (
    can_expand_playground_categories,
    has_explicit_place_name,
    has_other_place_requirement,
    is_generic_playground_name,
    playground_query_kind,
    playgrounds_excluded,
)
from backend.app.schemas import ActivityCode


@pytest.mark.parametrize(
    "query",
    [
        "Найди детскую площадку",
        "Детская площадка на 30 минут",
        "Хочу на детские площадки",
        "Балалар ойын алаңын тап",
        "Маған балалар ойын алаңы керек",
        "Ойын алаңын іздеймін",
        "Find a playground",
        "Playgrounds nearby",
        "A children's playground for 30 minutes",
    ],
)
def test_direct_playground_requests_do_not_depend_on_extracted_child_interests(query):
    assert playground_query_kind(query) == "playground"
    assert not playgrounds_excluded(query)
    assert can_expand_playground_categories(query, [])


@pytest.mark.parametrize(
    "query",
    [
        "Прогулка с ребёнком",
        "Хочу погулять с детьми",
        "Семейная прогулка на 30 минут",
        "Баламен серуен",
        "Балалармен серуендегім келеді",
        "Отбасымен серуендеу",
        "Walk with a child",
        "Take a stroll with my kids",
        "A family-friendly walk",
    ],
)
def test_family_walk_requests_can_offer_playgrounds(query):
    assert playground_query_kind(query) == "family_walk"
    assert can_expand_playground_categories(query, [ActivityCode.WALK])
    assert can_expand_playground_categories(query, ["walk", "entertainment"])


@pytest.mark.parametrize(
    "query",
    [
        "Прогулка с ребёнком, не на детской площадке",
        "Прогулка с ребёнком без детских площадок",
        "С ребёнком гулять, только не площадку",
        "Детскую площадку не надо",
        "Не ищи детскую площадку для прогулки с ребёнком",
        "Не хочу никакую детскую площадку",
        "Не предлагай детскую площадку.",
        "Не предложи детскую площадку",
        "Не советуй детскую площадку",
        "Не показывай детскую площадку",
        "Не покажи детскую площадку",
        "Баламен серуен, ойын алаңы емес",
        "Балалар ойын алаңы керек емес",
        "Баламен серуен, ойын алаңына бармаймыз",
        "Балалар ойын алаңын ұсынбаңыз",
        "Walk with a child, not a playground",
        "Walk with a child without playgrounds",
        "Avoid playgrounds for a walk with my child",
        "A playground is not wanted, walk with a child",
        "Don't show a playground for a walk with my child",
        "No children's playgrounds for a walk with my child",
        "Find a playground named Sunrise but not a playground",
    ],
)
def test_explicit_exclusions_block_positive_mentions_and_extracted_interests(query):
    assert playgrounds_excluded(query)
    assert playground_query_kind(query, interests=["child_suitability", "playground"]) is None
    assert not can_expand_playground_categories(query, [])


@pytest.mark.parametrize(
    "query",
    [
        "Прогулка с ребёнком, может быть детская площадка",
        "Детская площадка необязательна",
        "Баламен серуен, мүмкін ойын алаңы",
        "Ойын алаңы міндетті емес",
        "Walk with a child, maybe a playground",
        "A playground is optional for a walk with a child",
    ],
)
def test_optional_playground_mentions_do_not_expand_categories(query):
    assert playground_query_kind(query) is None
    assert not can_expand_playground_categories(query, ["walk"])


@pytest.mark.parametrize(
    "query",
    [
        "Прогулка с ребёнком в парке",
        "Детская площадка в музее",
        "Баламен саябақта серуен",
        "Баламен кафеде серуендеуге орын ұсын.",
        "Балалар ойын алаңы бар дәмхана",
        "Walk with a child in a park",
        "A playground at a cafe",
        "Walk with a child near the museum",
    ],
)
def test_other_explicit_destination_kinds_are_not_silently_replaced(query):
    assert playground_query_kind(query) is not None
    assert has_other_place_requirement(query)
    assert not can_expand_playground_categories(query, ["walk"])


@pytest.mark.parametrize("categories", [["museum"], ["food"], ["walk", "sport"], ["other"]])
def test_incompatible_extracted_categories_remain_restrictive(categories):
    assert not can_expand_playground_categories("Walk with a child", categories)


@pytest.mark.parametrize(
    "query",
    [
        'Детская площадка под названием "Playground"',
        "Find a playground 'Sunrise'.",
        "Найди детскую площадку ‘Sunrise’.",
        "Playground named Central",
        'Walk with a child at a place called "Playground"',
        "«Кенесары» атты балалар ойын алаңы",
        "Прогулка с ребёнком в «Жетысу»",
    ],
)
def test_explicit_names_protect_name_filters_even_if_the_name_is_generic(query):
    assert has_explicit_place_name(query)
    assert can_expand_playground_categories(query, ["walk"])


@pytest.mark.parametrize(
    "name",
    [
        "детская площадка",
        "ДЕТСКУЮ ПЛОЩАДКУ",
        '"детские площадки"',
        "балалар ойын алаңы",
        "ойын алаңын",
        "Playground",
        "children's playground",
    ],
)
def test_only_exact_generic_descriptors_can_be_removed_as_name_queries(name):
    assert is_generic_playground_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "Детская площадка Кенесары",
        "Жетысу",
        "Балалар ойын алаңы Арай",
        "Central Playground",
        "Playground Cafe",
        "MEGA Silk Way",
        "детская",
        "",
    ],
)
def test_specific_and_ambiguous_names_are_preserved(name):
    assert not is_generic_playground_name(name)


@pytest.mark.parametrize(
    "query", ['Find "playground"', "Найди «детскую площадку»", "«ойын алаңын» тап"]
)
def test_quoting_a_category_alone_does_not_claim_a_specific_place_name(query):
    assert not has_explicit_place_name(query)


@pytest.mark.parametrize(
    "query",
    [
        "Найди площадку для концерта",
        "Гулять одному",
        "Балалар мұражайын тап",
        "Find a museum for my child",
        "I want a walk. My child wants a museum.",
        "PlayStation shop",
    ],
)
def test_interests_do_not_invent_a_raw_playground_request(query):
    assert playground_query_kind(query, interests=["playground", "child_suitability"]) is None


@pytest.mark.parametrize(
    "query",
    [
        "Find a cafe called Playground",
        "Find a cafe named Playground",
        "Найди кафе под названием «Детская площадка»",
        "«Playground Cafe» атты кафе тап",
        'Find "Central Playground"',
        "Find 'Central Playground'",
        "Найди «Детская площадка Кенесары»",
        "«Балалар ойын алаңы Арай» тап",
    ],
)
def test_a_venue_name_alone_does_not_create_a_playground_requirement(query):
    assert playground_query_kind(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Find a playground named Sunrise",
        "Найди детскую площадку под названием «Рассвет»",
        "«Кенесары» атты балалар ойын алаңы",
        "Кенесары атты балалар ойын алаңы",
        'Find a playground near "Central Playground"',
    ],
)
def test_a_separate_playground_type_survives_masking_of_the_place_name(query):
    assert playground_query_kind(query) == "playground"


@pytest.mark.parametrize(
    "query", ['Find "playground"', "Найди «детскую площадку»", "«ойын алаңын» тап"]
)
def test_a_quoted_generic_type_remains_a_positive_playground_request(query):
    assert playground_query_kind(query) == "playground"
