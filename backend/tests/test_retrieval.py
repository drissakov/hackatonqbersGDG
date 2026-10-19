"""Retrieval outcomes keep infrastructure failures and unresolved fit separate."""

import asyncio
from unittest.mock import AsyncMock

from backend.app.database import DatabaseUnavailable
from backend.app.openai_client import ProviderError
from backend.app.retrieval import Retriever
from backend.app.schemas import POIRecord, RecommendationRequest
from backend.tests.test_intent import text_intent
from backend.tests.test_repository import poi


def test_unavailable_database_is_not_no_match():
    repository = AsyncMock()
    repository.retrieve_candidates.side_effect = DatabaseUnavailable("synthetic")
    result = asyncio.run(Retriever(repository).retrieve(RecommendationRequest(query="Synthetic")))
    assert result.status == "unavailable" and not result.candidates
    repository.retrieve_candidates.side_effect = None
    repository.retrieve_candidates.return_value = []
    result = asyncio.run(Retriever(repository).retrieve(RecommendationRequest(query="Synthetic")))
    assert result.status == "no_match" and result.diagnostics["mode"] == "lexical"
    assert not result.diagnostics["constraints_resolved"]


def test_clarification_does_not_query_database_or_embed():
    client, repository = AsyncMock(), AsyncMock()
    client.parse_response.return_value = text_intent(indoor=["outdoor"])
    result = asyncio.run(
        Retriever(repository, client).retrieve(
            RecommendationRequest(
                query="Synthetic", indoor_only=True, explicit_fields=["indoor_only"]
            )
        )
    )
    assert result.status == "clarification"
    repository.retrieve_candidates.assert_not_called()
    client.embed.assert_not_called()


def test_candidates_contain_sourced_facts_missing_fields_and_selection_evidence():
    repository = AsyncMock()
    row = POIRecord.model_validate(poi()).model_dump(mode="json")
    row.update(indoor=None, price_kzt_per_person=None)
    repository.retrieve_candidates.return_value = [
        {
            "document": row,
            "lexical_score": 1.0,
            "semantic_score": None,
            "category_match": False,
            "score": 2.0,
            "distance_m": None,
            "metadata": None,
        }
    ]
    result = asyncio.run(Retriever(repository).retrieve(RecommendationRequest(query="Synthetic")))
    assert result.status == "ok"
    candidate = result.candidates[0]
    assert candidate.id == row["id"] and candidate.poi.sources
    assert "price_kzt_per_person" in candidate.missing_fields
    assert "travel_minutes_estimate" in candidate.missing_fields
    assert "origin" in candidate.missing_fields and "date_time" in candidate.missing_fields
    assert candidate.diagnostics["selection_bases"] == ["name_or_alias"]
    assert result.diagnostics["fit_evaluation"] == "not_run_s04"


def test_embedding_outage_uses_lexical_candidates_without_hiding_provider_failure():
    client, repository = AsyncMock(), AsyncMock()
    client.parse_response.return_value = text_intent()
    client.embed.side_effect = ProviderError("rate_limit_or_quota")
    repository.retrieve_candidates.return_value = []
    result = asyncio.run(
        Retriever(repository, client).retrieve(RecommendationRequest(query="Synthetic"))
    )
    assert result.status == "no_match" and result.diagnostics["mode"] == "lexical"
    assert result.diagnostics["embedding_failure"] == "rate_limit_or_quota"
    assert repository.retrieve_candidates.call_args.kwargs["vector"] is None
