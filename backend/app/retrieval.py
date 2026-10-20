"""Bounded candidate selection for S04; no opening, budget, route or fit promises."""

from typing import Literal

from pydantic import Field

from backend.app.database import DatabaseUnavailable
from backend.app.intent import IntentExtractor, IntentResult, form_intent
from backend.app.openai_client import AIClient, ProviderError
from backend.app.playground_intent import (
    can_expand_playground_categories,
    has_explicit_place_name,
    has_other_place_requirement,
    is_generic_playground_name,
    playground_query_kind,
    playgrounds_excluded,
)
from backend.app.poi_features import FeatureCatalog
from backend.app.schemas import (
    ActivityCode,
    ContractModel,
    MissingField,
    POIRecord,
    RecommendationRequest,
)


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
    def __init__(
        self,
        repository,
        client: AIClient | None = None,
        *,
        feature_catalog: FeatureCatalog | None = None,
    ):
        self.repository = repository
        self.client = client
        self.extractor = IntentExtractor(client)
        self.feature_catalog = feature_catalog

    async def retrieve(self, request: RecommendationRequest, *, radius_m=5000, limit=12):
        extracted = await self.extractor.extract(request)
        if extracted.status == "clarification":
            return RetrievalResult(status="clarification", intent=extracted)
        intent = extracted.intent or form_intent(request)
        from backend.app.constraints import unsupported_requirements

        playground_kind = playground_query_kind(request.query, interests=intent.interests)
        if playground_kind:
            updates = {}
            if can_expand_playground_categories(request.query, intent.categories):
                # Walking describes the outing, while playground is a destination
                # type. Keep existing categories and every other resolved constraint.
                updates["categories"] = list(
                    dict.fromkeys([*intent.categories, ActivityCode.ENTERTAINMENT])
                )
            if not has_explicit_place_name(request.query):
                updates["name_queries"] = [
                    name for name in intent.name_queries if not is_generic_playground_name(name)
                ]
            intent = intent.model_copy(update=updates)
            extracted = extracted.model_copy(update={"intent": intent})
        requirements = [
            code
            for code in unsupported_requirements(request.query, interests=intent.interests)
            if code in {"child_suitability", "power_outlets"}
        ]
        if playground_kind and "child_suitability" not in requirements:
            requirements.append("child_suitability")
        if requirements and self.feature_catalog is not None and extracted.status == "ok":
            selected = self.feature_catalog.select(intent, requirements, radius_m=radius_m)
            if "child_suitability" in requirements and (
                playgrounds_excluded(request.query) or has_other_place_requirement(request.query)
            ):
                # Playground facts cannot prove a park, museum or cafe requirement,
                # even if extraction omitted the requested place type.
                selected = []
            if has_explicit_place_name(request.query) and not any(
                name.strip() for name in intent.name_queries
            ):
                # Losing a named-place restriction is not permission to substitute
                # an unrelated playground from the source supplement.
                selected = []
            # Evaluate every eligible supplement before the route shortlist. No city
            # retrieval LIMIT can hide a proven feature behind ordinary cafe records.
            candidates = [
                Candidate(
                    id=row.poi.id,
                    poi=row.poi,
                    missing_fields=[],
                    diagnostics={
                        "selection_bases": ["source_checked_feature"],
                        "score": 2 if row.fact("public_access") is True else 1,
                        "curated": row,
                    },
                )
                for row in selected
            ]
            return RetrievalResult(
                status="ok" if candidates else "no_match",
                candidates=candidates,
                intent=extracted,
                diagnostics={"feature_catalog": True, "scope_limited": True},
            )
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
