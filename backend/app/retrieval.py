"""Bounded candidate selection for S04; no opening, budget, route or fit promises."""

from typing import Literal

from pydantic import Field

from backend.app.database import DatabaseUnavailable
from backend.app.intent import IntentExtractor, IntentResult, form_intent
from backend.app.openai_client import AIClient, ProviderError
from backend.app.schemas import ContractModel, MissingField, POIRecord, RecommendationRequest


class Candidate(ContractModel):
    id: str
    poi: POIRecord
    missing_fields: list[MissingField]
    diagnostics: dict


class RetrievalResult(ContractModel):
    status: Literal["ok", "no_match", "unavailable", "clarification"]
    candidates: list[Candidate] = Field(default_factory=list)
    intent: IntentResult
    diagnostics: dict = Field(default_factory=dict)


class Retriever:
    def __init__(self, repository, client: AIClient | None = None):
        self.repository = repository
        self.client = client
        self.extractor = IntentExtractor(client)

    async def retrieve(self, request: RecommendationRequest, *, radius_m=5000, limit=12):
        extracted = await self.extractor.extract(request)
        if extracted.status == "clarification":
            return RetrievalResult(status="clarification", intent=extracted)
        intent = extracted.intent or form_intent(request)
        vector, mode, reason = None, "lexical", "embedding_client_unavailable"
        if self.client is not None:
            try:
                vector = await self.client.embed(request.query)
                mode = "hybrid"
                reason = None
            except ProviderError as exc:
                reason = exc.code
        diagnostics = {
            "mode": mode,
            "embedding_failure": reason,
            "intent_status": extracted.status,
            "constraints_resolved": extracted.status == "ok",
            "geo_radius_m": radius_m if intent.origin else None,
            "radius_is_retrieval_policy": True,
            "fit_evaluation": "not_run_s04",
        }
        try:
            rows = await self.repository.retrieve_candidates(
                intent.query,
                names=intent.name_queries,
                categories=intent.categories,
                origin=intent.origin,
                radius_m=radius_m,
                vector=vector,
                limit=limit,
            )
        except DatabaseUnavailable:
            return RetrievalResult(
                status="unavailable",
                intent=extracted,
                diagnostics={**diagnostics, "reason": "database_unavailable"},
            )
        diagnostics["vector_scored_candidates"] = sum(
            row["semantic_score"] is not None for row in rows
        )
        candidates = []
        for row in rows:
            poi = POIRecord.model_validate(row["document"])
            missing = [
                field
                for field, value in (
                    (MissingField.ORIGIN, intent.origin),
                    (MissingField.AVAILABLE_MINUTES, intent.available_minutes),
                    (MissingField.DATE_TIME, intent.date_time),
                    (MissingField.LOCATION, poi.location),
                    (MissingField.PRICE, poi.price_kzt_per_person),
                    (MissingField.INDOOR, poi.indoor),
                    (MissingField.OPENING_HOURS, poi.opening_hours_text),
                    (MissingField.VISIT_MINUTES, poi.visit_minutes_estimate),
                    (MissingField.TRAVEL_MINUTES, None),
                )
                if value is None
            ]
            bases = []
            if row["lexical_score"] >= 0.35:
                bases.append("name_or_alias")
            if row["category_match"]:
                bases.append("canonical_category")
            if row["semantic_score"] is not None and row["semantic_score"] >= 0.25:
                bases.append("vector_similarity")
            if intent.origin:
                bases.append("geo_prefilter")
            metadata = row.get("metadata") or {}
            candidates.append(
                Candidate(
                    id=poi.id,
                    poi=poi,
                    missing_fields=missing,
                    diagnostics={
                        "selection_bases": bases,
                        "lexical_score": row["lexical_score"],
                        "semantic_score": row["semantic_score"],
                        "score": row["score"],
                        "straight_line_distance_m": row["distance_m"],
                        "sidecar_available": metadata.get("sidecar_available", False),
                        "coordinate_precision": (metadata.get("sidecar") or {}).get("coordinates"),
                        "source_facts_verified": False,
                    },
                )
            )
        return RetrievalResult(
            status="ok" if candidates else "no_match",
            candidates=candidates,
            intent=extracted,
            diagnostics=diagnostics,
        )
