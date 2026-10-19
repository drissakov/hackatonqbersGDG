"""D05 child/age and charging requests cannot acquire unsupported confirmed fits."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.app.constraints import evaluate_poi
from backend.app.schemas import RecommendationRequest, RecommendationResponse
from backend.tests.test_constraints import intent, poi, route
from backend.tests.test_recommend import service


@pytest.mark.parametrize(
    ("query", "locale", "activity"),
    [
        (
            "A museum suitable for my six-year-old child; say if age restrictions are unknown.",
            "en",
            "museum",
        ),
        ("Предложи музей для посещения с шестилетним ребенком.", "ru", "museum"),
        ("Алты жастағы баламен баруға болатын мұражай ұсын.", "kk", "museum"),
        ("Coffee with a charging point for my laptop.", "en", "food"),
        ("Кофе с зарядкой для телефона.", "ru", "food"),
        ("Телефонды зарядтауға болатын кафе керек.", "kk", "food"),
    ],
)
def test_unmodeled_requirement_stops_before_otherwise_complete_poi_fit(query, locale, activity):
    record = poi(activity_code=activity)
    supported = intent()
    assert evaluate_poi(record, supported, route()).fit_status == "fits"
    router = AsyncMock()
    search, repository, client = service([record], router=router)

    response = asyncio.run(
        search.recommend(
            RecommendationRequest(
                query=query,
                locale=locale,
                origin=supported.origin,
                available_minutes=supported.available_minutes,
                budget_kzt_per_person=supported.budget_kzt_per_person,
                date_time=supported.date_time,
            )
        )
    )

    assert response.status == "unknown"
    assert response.items == [] and response.sources == []
    assert response.warnings[0].code == "missing_input"
    RecommendationResponse.model_validate_json(response.model_dump_json())
    repository.retrieve_candidates.assert_not_called()
    client.parse_response.assert_not_called()
    client.embed.assert_not_called()
    router.route.assert_not_called()
