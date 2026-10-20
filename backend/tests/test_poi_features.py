"""Source-backed feature selection uses synthetic facts, never inferred amenities."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from backend.app import api, main, poi_features
from backend.app.explain import ExplanationBatch
from backend.app.intent import TextIntent
from backend.app.openai_client import ProviderError
from backend.app.poi_features import CuratedPOI, FeatureCatalog, load_feature_catalog
from backend.app.recommend import RecommendationService
from backend.app.schemas import (
    ActivityCode,
    FeatureEvidence,
    POICard,
    RecommendationRequest,
    RecommendationResponse,
    RouteLeg,
    RouteProvenance,
)
from backend.tests.test_api import request
from backend.tests.test_contracts import fixture
from backend.tests.test_intent import text_intent
from backend.tests.test_recommend import record

ROOT = Path(__file__).resolve().parents[2]
CHECKED = "2030-01-16T10:00:00+05:00"
UPDATED = "2030-01-15T10:00:00+05:00"
FAMILY_QUERIES = [
    ("kk", "Балалар үшін ойын алаңын ұсын."),
    ("ru", "Предложи прогулку с ребёнком."),
    ("en", "Suggest a playground for children."),
]
POWER_QUERIES = [
    ("kk", "Телефонды зарядтауға болатын кафе керек."),
    ("ru", "Найди кафе с розетками."),
    ("en", "A cafe with a charging point for my phone."),
]


def evidence(field="family_playground", **updates):
    source_field, source_value = {
        "family_playground": ("leisure", "playground"),
        "public_access": ("access", "yes"),
        "power_outlets": ("service:electricity", "yes"),
    }[field]
    return {
        "field": field,
        "value": True,
        "source_id": "test-source-001",
        "source_field": source_field,
        "source_value": source_value,
        "source_version": 1,
        "source_updated_at": UPDATED,
        "checked_at": CHECKED,
        "observed_at": None,
        **updates,
    }


def curated(*, fields=("family_playground", "public_access"), **updates):
    poi = record(
        id="test:features-001",
        name="SYNTHETIC TEST ONLY - Fictional Playground",
        activity_code="walk",
        indoor=False,
        price_kzt_per_person=0,
        opening_hours_text="24/7",
        location={"latitude": 51.12, "longitude": 71.43},
    )
    values = {
        "poi": poi.model_dump(mode="json"),
        "name_is_derived": False,
        "coordinate_precision": "node",
        "evidence": [evidence(field) for field in fields],
        **updates,
    }
    for source in values["poi"]["sources"]:
        source["retrieved_at"] = CHECKED
    if values["name_is_derived"]:
        for provenance in values["poi"]["provenance"]:
            provenance["fields"] = [field for field in provenance["fields"] if field != "name"]
    return CuratedPOI.model_validate(values)


def catalog(*rows):
    return FeatureCatalog.model_validate(
        {
            "format_version": "qadam-poi-features-v1",
            "checked_at": CHECKED,
            "records": [row.model_dump(mode="json") for row in rows],
        }
    )


def feature_service(feature_catalog, *, categories=("walk",), names=(), interests=()):
    repository, client, router = AsyncMock(), AsyncMock(), AsyncMock()
    repository.retrieve_candidates.return_value = []
    repository.coverage.return_value = {"production_pois": 985, "embedded_pois": 985}
    client.embed.return_value = [0.5] * 1536
    known = RouteLeg(
        status="known",
        duration_seconds=120,
        distance_meters=100,
        provenance=RouteProvenance(retrieved_at=CHECKED, provider_locale="ru"),
    )
    absent = RouteLeg(status="not_requested", reason="not_requested")
    router.route.return_value = (known, absent)

    async def parse(text, schema, **_kwargs):
        if schema is TextIntent:
            return text_intent(
                categories=list(categories), name_queries=list(names), interests=list(interests)
            )
        packet = json.loads(text)
        return ExplanationBatch(
            locale=packet["locale"],
            items=[
                {
                    "item_id": item["item_id"],
                    "source_ids": item["source_ids"],
                    "reason_codes": item["allowed_reason_codes"],
                    "activity_code": item["activity_code"],
                    "idea": item["allowed_ideas"][0],
                }
                for item in packet["alternatives"]
            ],
        )

    client.parse_response.side_effect = parse
    service = RecommendationService(repository, client, router, feature_catalog=feature_catalog)
    return service, repository, client, router


def feature_request(query, locale="en", **updates):
    return RecommendationRequest.model_validate(
        {
            "query": query,
            "locale": locale,
            "origin": {"latitude": 51.12, "longitude": 71.43},
            "available_minutes": 120,
            "date_time": "2030-01-16T10:00:00+05:00",
            **updates,
        }
    )


def recommend(service, query, locale="en", **updates):
    return asyncio.run(service.recommend(feature_request(query, locale, **updates)))


@pytest.mark.parametrize("field", ["family_playground", "public_access", "power_outlets"])
def test_source_evidence_retains_lookup_source_update_and_unknown_observation(field):
    fact = FeatureEvidence.model_validate(evidence(field))
    assert fact.field == field and fact.value is True
    assert fact.observed_at is None
    assert fact.source_updated_at < fact.checked_at
    assert fact.source_version == 1
    assert fact.model_dump(mode="json")["source_value"] == evidence(field)["source_value"]


@pytest.mark.parametrize(
    "updates",
    [
        {"value": "true"},
        {"value": 1},
        {"value": None},
        {"source_version": 0},
        {"source_version": True},
        {"source_updated_at": "2030-01-15T10:00:00"},
        {"checked_at": "2030-01-16T10:00:00"},
        {"observed_at": "2030-01-16T10:00:00"},
        {"observed_at": UPDATED},
        {"source_updated_at": "2030-01-17T10:00:00+05:00"},
        {"observed_at": "2030-01-17T10:00:00+05:00"},
        {"field": "age_restrictions"},
    ],
)
def test_evidence_rejects_coercion_unknown_flags_unsupported_claims_and_impossible_dates(updates):
    values = {**evidence(), **updates}
    with pytest.raises(ValidationError):
        FeatureEvidence.model_validate(values)


@pytest.mark.parametrize(
    "field,source_field,source_value",
    [
        ("power_outlets", "internet_access", "wlan"),
        ("power_outlets", "socket", "unknown"),
        ("power_outlets", "socket", "yes"),
        ("power_outlets", "electricity", "yes"),
        ("power_outlets", "name", "SYNTHETIC Charging Cafe"),
        ("family_playground", "name", "SYNTHETIC Family Park"),
        ("family_playground", "leisure", "park"),
        ("public_access", "opening_hours", "24/7"),
    ],
)
def test_curated_facts_do_not_infer_features_from_wifi_names_categories_or_hours(
    field, source_field, source_value
):
    row = curated().model_dump(mode="json")
    row["evidence"] = [evidence(field, source_field=source_field, source_value=source_value)]
    with pytest.raises(ValidationError):
        CuratedPOI.model_validate(row)


@pytest.mark.parametrize("mode", ["unknown_source", "no_storage", "no_indexing", "no_license"])
def test_curated_facts_require_included_sources_and_documented_persistence_rights(mode):
    row = curated().model_dump(mode="json")
    if mode == "unknown_source":
        row["evidence"][0]["source_id"] = "missing-source"
    else:
        source = row["poi"]["sources"][0]
        if mode == "no_storage":
            source.update(storage_allowed=False, indexing_allowed=False)
        elif mode == "no_indexing":
            source["indexing_allowed"] = False
        else:
            source["license"] = None
    with pytest.raises(ValidationError):
        CuratedPOI.model_validate(row)


@pytest.mark.parametrize("mode", ["duplicate_place", "duplicate_fact", "catalog_date"])
def test_catalog_rejects_ambiguous_identity_and_fact_generations(mode):
    values = catalog(curated()).model_dump(mode="json")
    if mode == "duplicate_place":
        values["records"].append(copy.deepcopy(values["records"][0]))
    elif mode == "duplicate_fact":
        values["records"][0]["evidence"].append(copy.deepcopy(values["records"][0]["evidence"][0]))
    else:
        values["checked_at"] = "2030-01-14T10:00:00+05:00"
    with pytest.raises(ValidationError):
        FeatureCatalog.model_validate(values)


@pytest.mark.parametrize("mode", ["no_coordinates", "unattributed_coordinates", "derived_name"])
def test_curated_record_requires_honest_coordinates_and_display_name_provenance(mode):
    row = curated().model_dump(mode="json")
    if mode == "no_coordinates":
        row["poi"]["location"] = None
    elif mode == "unattributed_coordinates":
        for provenance in row["poi"]["provenance"]:
            provenance["fields"].remove("location")
    else:
        row["name_is_derived"] = True
    with pytest.raises(ValidationError):
        CuratedPOI.model_validate(row)


@pytest.mark.parametrize(
    "source_field,source_value,value",
    [
        ("service:electricity", "yes", True),
        ("service:electricity", "limited", True),
        ("service:electricity", "no", False),
        ("power_supply", "yes", True),
        ("power_supply", "no", False),
    ],
)
def test_explicit_electricity_tags_preserve_positive_limited_and_negative_claims(
    source_field, source_value, value
):
    fact = FeatureEvidence.model_validate(
        evidence("power_outlets", source_field=source_field, source_value=source_value, value=value)
    )
    assert fact.value is value
    assert fact.source_value == source_value


@pytest.mark.parametrize("mode", ["missing", "invalid_json", "oversized", "synthetic"])
def test_catalog_loader_fails_closed_without_fixture_or_empty_corpus_fallback(
    mode, tmp_path, monkeypatch
):
    path = tmp_path / "poi-features.json"
    if mode == "invalid_json":
        path.write_text("{", encoding="utf-8")
    elif mode == "oversized":
        path.write_bytes(b" " * 2_000_001)
    elif mode == "synthetic":
        path.write_text(catalog(curated()).model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(poi_features, "CATALOG_PATH", path)
    load_feature_catalog.cache_clear()
    try:
        assert load_feature_catalog() is None
    finally:
        load_feature_catalog.cache_clear()


@pytest.mark.parametrize("locale,query", FAMILY_QUERIES)
def test_generic_family_search_can_return_a_source_proved_playground(locale, query):
    row = curated()
    service, _, _, _ = feature_service(catalog(row))
    result = recommend(service, query, locale)
    assert result.status in {"ok", "partial"}
    assert [item.poi.id for item in result.items] == [row.poi.id]
    card = result.items[0]
    assert "child_suitability" not in card.missing_fields
    assert "public_access" not in card.missing_fields
    assert card.feature_evidence == row.evidence
    assert card.name_is_derived is False
    assert set(fact.source_id for fact in card.feature_evidence) <= {
        source.source_id for source in result.sources
    }
    RecommendationResponse.model_validate_json(result.model_dump_json())


@pytest.mark.parametrize("locale,query", POWER_QUERIES)
def test_positive_synthetic_socket_evidence_enables_charging_search(locale, query):
    row = curated(fields=("power_outlets", "public_access"))
    row.poi.activity_code = ActivityCode.FOOD
    service, _, _, _ = feature_service(catalog(row), categories=("food",))
    result = recommend(service, query, locale)
    assert [card.poi.id for card in result.items] == [row.poi.id]
    assert "power_outlets" not in result.items[0].missing_fields
    assert any(fact.field == "power_outlets" for fact in result.items[0].feature_evidence)


@pytest.mark.parametrize("value", [False, None])
def test_missing_or_negative_socket_fact_never_becomes_a_charging_match(value):
    facts = [evidence("public_access")]
    if value is False:
        facts.append(evidence("power_outlets", value=False, source_value="no"))
    row = curated(evidence=facts)
    row.poi.activity_code = ActivityCode.FOOD
    service, _, _, router = feature_service(catalog(row), categories=("food",))
    result = recommend(service, "A cafe with a charging point for my phone.")
    assert result.status == "unknown" and not result.items
    assert any("power_outlets" in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "query,expected",
    [
        ("A playground for my six-year-old child.", "age_restrictions"),
        ("A quiet playground for children.", "child_suitability"),
        ("A wheelchair accessible playground for children.", "child_suitability"),
    ],
)
def test_available_playground_facts_never_prove_age_quietness_or_accessibility(query, expected):
    service, _, _, router = feature_service(catalog(curated()))
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    if expected == "age_restrictions":
        assert any(expected in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


def test_combined_family_and_charging_requires_both_positive_facts_on_the_same_place():
    family_only = curated()
    power_only = curated(
        fields=("power_outlets", "public_access"),
        poi=record(id="test:power-only", activity_code="walk").model_dump(mode="json"),
    )
    both = curated(
        fields=("family_playground", "power_outlets", "public_access"),
        poi=record(id="test:both", activity_code="walk").model_dump(mode="json"),
    )
    service, _, _, _ = feature_service(catalog(family_only, power_only, both))
    result = recommend(service, "A playground for children with a charging point for my phone.")
    assert [card.poi.id for card in result.items] == [both.poi.id]


@pytest.mark.parametrize(
    "query",
    [
        "A cafe to charge my car.",
        "A cafe with an EV charging point.",
        "A cafe with wireless charging for my phone.",
        "A cafe with a USB charging point.",
        "A cafe with a Type-C charging point.",
        "A cafe with a 230V charging point.",
        "Кафе с зарядкой для электромобиля.",
        "Кафе с зарядкой для телефона, нужна беспроводная зарядка.",
        "Телефонды сымсыз зарядтауға болатын кафе керек.",
    ],
)
def test_generic_power_evidence_cannot_prove_connector_voltage_or_vehicle_compatibility(query):
    row = curated(fields=("power_outlets", "public_access"))
    row.poi.activity_code = ActivityCode.FOOD
    service, repository, client, router = feature_service(catalog(row), categories=("food",))
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    assert any("power_outlets" in warning.fields for warning in result.warnings)
    assert repository.mock_calls == client.mock_calls == router.mock_calls == []


def test_extracted_device_compatibility_survives_generic_power_evidence_before_routing():
    row = curated(fields=("power_outlets", "public_access"))
    row.poi.activity_code = ActivityCode.FOOD
    service, repository, client, router = feature_service(
        catalog(row), categories=("food",), interests=("power_outlets", "wireless charging")
    )
    result = recommend(service, "Suggest a cafe.")
    assert result.status == "unknown" and not result.items
    assert any("power_outlets" in warning.fields for warning in result.warnings)
    assert repository.mock_calls == router.mock_calls == []
    assert client.parse_response.await_count == 1


@pytest.mark.parametrize(
    "query,requirement",
    [
        ("Find a child-free place.", "child_suitability"),
        ("A place with no children.", "child_suitability"),
        ("A place that is not child-friendly.", "child_suitability"),
        ("Место без детей.", "child_suitability"),
        ("Место не для детей.", "child_suitability"),
        ("Балаларсыз тынығатын орын ұсын.", "child_suitability"),
        ("Балаларға арналмаған орын.", "child_suitability"),
        ("A place without power outlets.", "power_outlets"),
        ("A place without charging points.", "power_outlets"),
        ("Кафе без розеток.", "power_outlets"),
        ("Розеткасыз кафе керек.", "power_outlets"),
    ],
)
def test_negative_requirements_never_turn_into_positive_family_or_charging_matches(
    query, requirement
):
    row = curated(fields=("family_playground", "power_outlets", "public_access"))
    service, _, _, router = feature_service(catalog(row), interests=(requirement,))
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    assert any(requirement in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "A cafe, charging is optional.",
        "A cafe with optional charging.",
        "Кафе, розетки не обязательны.",
        "Розетка міндетті емес кафе керек.",
    ],
)
def test_optional_charging_is_not_silently_promoted_to_a_proven_required_amenity(query):
    row = curated(fields=("power_outlets", "public_access"))
    row.poi.activity_code = ActivityCode.FOOD
    service, _, _, router = feature_service(
        catalog(row), categories=("food",), interests=("power_outlets",)
    )
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "A place for infants.",
        "A playground for a toddler.",
        "Площадка для младенца.",
        "Нәрестемен баратын орын ұсын.",
    ],
)
def test_generic_playground_evidence_does_not_establish_infant_or_toddler_suitability(query):
    service, _, _, router = feature_service(catalog(curated()))
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    router.route.assert_not_called()


@pytest.mark.parametrize(
    "query",
    [
        "Предложи площадку для ребёнка, которому 6 лет.",
        "Ребенку шесть лет, предложи площадку.",
        "6 лет ребёнку, куда сходить?",
        "A playground for children between 6 and 8 years.",
        "6 жаста баламен ойын алаңына бару.",
    ],
)
def test_raw_age_presence_audit_survives_an_extractor_that_loses_the_age_requirement(query):
    service, _, _, router = feature_service(catalog(curated()))
    result = recommend(service, query)
    assert result.status == "unknown" and not result.items
    assert any("age_restrictions" in warning.fields for warning in result.warnings)
    router.route.assert_not_called()


def test_unknown_public_access_is_visible_as_partial_instead_of_an_admission_guarantee():
    row = curated(fields=("family_playground",))
    service, _, _, _ = feature_service(catalog(row))
    result = recommend(service, "A playground for children.")
    assert result.status == "partial" and len(result.items) == 1
    assert "public_access" in result.items[0].missing_fields
    assert result.items[0].fit_status == "unknown"


def test_known_private_access_is_rejected_before_requesting_a_route():
    row = curated(
        evidence=[
            evidence(),
            evidence("public_access", value=False, source_value="private"),
        ]
    )
    service, _, _, router = feature_service(catalog(row))
    result = recommend(service, "A playground for children.")
    assert not result.items and result.status in {"unknown", "no_match"}
    router.route.assert_not_called()


def test_publicly_accessible_candidates_are_preferred_before_the_three_place_limit():
    rows = [
        curated(
            fields=("family_playground",),
            poi=record(id=f"test:unknown-access-{index:02}", activity_code="walk").model_dump(
                mode="json"
            ),
        )
        for index in range(15)
    ]
    verified = curated()
    service, _, _, _ = feature_service(catalog(*rows, verified))
    result = recommend(service, "A playground for children.")
    assert result.items[0].poi.id == verified.poi.id
    assert len(result.items) <= 3


@pytest.mark.parametrize(
    "case",
    ["outside_radius", "category", "budget", "time", "indoor", "name"],
)
def test_positive_feature_evidence_cannot_relax_other_explicit_constraints(case):
    row = curated()
    options = {}
    categories, names = ("walk",), ()
    if case == "outside_radius":
        row.poi.location.latitude = 52.0
    elif case == "category":
        categories = ("food",)
    elif case == "budget":
        row.poi.price_kzt_per_person = 2000
        options["budget_kzt_per_person"] = 1000
    elif case == "time":
        options["available_minutes"] = 10
    elif case == "indoor":
        options["indoor_only"] = True
    else:
        names = ("SYNTHETIC DIFFERENT NAMED VENUE",)
    service, _, _, router = feature_service(catalog(row), categories=categories, names=names)
    result = recommend(service, "A playground for children.", **options)
    assert result.status == "unknown" and not result.items
    router.route.assert_not_called()


def test_intent_provider_outage_does_not_turn_source_checked_places_into_matches():
    service, _, client, router = feature_service(catalog(curated()))
    client.parse_response.side_effect = ProviderError("network_unavailable_or_timeout")
    result = recommend(service, "A playground for children.")
    assert result.status == "unavailable" and not result.items
    router.route.assert_not_called()


def test_old_response_defaults_do_not_require_feature_evidence_or_change_poi_record_shape():
    old = fixture("recommendation-partial")
    assert "feature_evidence" not in old["items"][0]
    assert "name_is_derived" not in old["items"][0]
    result = RecommendationResponse.model_validate(old)
    assert result.items[0].feature_evidence == []
    assert result.items[0].name_is_derived is False
    assert set(result.items[0].poi.model_dump()) == set(old["items"][0]["poi"])


def test_feature_card_cannot_detach_evidence_from_the_included_place_sources():
    service, _, _, _ = feature_service(catalog(curated()))
    result = recommend(service, "A playground for children.")
    card = result.items[0].model_dump(mode="json")
    card["feature_evidence"][0]["source_id"] = "source-not-included-with-this-place"
    with pytest.raises(ValidationError):
        POICard.model_validate(card)


def test_checked_in_catalog_contains_real_attributed_places_without_invented_charging_facts():
    checked_catalog = load_feature_catalog()
    assert checked_catalog is not None
    assert 20 <= len(checked_catalog.records) <= 30
    assert len({row.poi.id for row in checked_catalog.records}) == len(checked_catalog.records)
    assert all(not row.poi.is_test for row in checked_catalog.records)
    for row in checked_catalog.records:
        sources = {source.source_id: source for source in row.poi.sources}
        assert all(
            not source.is_test
            and source.storage_allowed
            and source.indexing_allowed
            and source.license
            and source.rights_basis_url
            for source in sources.values()
        )
        assert row.evidence
        assert all(fact.source_id in sources for fact in row.evidence)
        assert all(fact.observed_at is None for fact in row.evidence)
        assert not any(fact.field == "power_outlets" and fact.value for fact in row.evidence)


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/v1/recommendations"])
@pytest.mark.parametrize("locale,query", FAMILY_QUERIES)
def test_http_aliases_serialize_feature_provenance_using_the_shared_schema(
    path, locale, query, monkeypatch
):
    checked_catalog = catalog(curated(name_is_derived=True))
    _, repository, client, router = feature_service(checked_catalog)

    class ClientContext:
        async def __aenter__(self):
            return client

        async def __aexit__(self, *_):
            pass

    monkeypatch.setattr(main, "get_repository", lambda _: repository)
    monkeypatch.setattr(main, "get_twogis", lambda: router)
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(app_timezone="Asia/Almaty"))
    monkeypatch.setattr(api, "OpenAIClient", lambda _: ClientContext())
    monkeypatch.setattr(api, "load_feature_catalog", lambda: checked_catalog)
    payload = feature_request(query, locale).model_dump(mode="json")
    response = request(main.create_app(), "POST", path, json=payload)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["request_id"] == payload["request_id"]
    assert body["items"][0]["name_is_derived"] is True
    assert body["items"][0]["feature_evidence"]
    schema = json.loads((ROOT / "contracts/recommendation-response.schema.json").read_text("utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(body)
    RecommendationResponse.model_validate(body)
