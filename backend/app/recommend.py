"""Compose bounded single-destination alternatives without inventing missing facts."""

import asyncio

from backend.app.constraints import (
    evaluate_poi,
    hard_reject,
    sourced_field,
    unsupported_requirements,
)
from backend.app.database import DatabaseUnavailable
from backend.app.explain import ExplanationService, fallback_explanation
from backend.app.openai_client import AIClient
from backend.app.retrieval import Retriever
from backend.app.schemas import (
    Action,
    POICard,
    ReasonCode,
    RecommendationRequest,
    RecommendationResponse,
    RouteLeg,
    RouteRequest,
    Warning,
)

MESSAGES = {
    "kk": {
        "unavailable": "Іздеу қызметі қолжетімсіз. Кейінірек қайталап көріңіз.",
        "clarification": "Талаптарды нақтылаңыз: {fields}.",
        "conditional": "Шартты нұсқалар: белгісіз деректерді дереккөзден тексеріңіз.",
        "facts": "Тыныштық, розеткалар немесе қолжетімділік туралы расталған деректер жоқ.",
        "fallback": "Түсіндірме қауіпсіз үлгімен берілді.",
        "shortlist": "Тексерілген қысқа тізімде сәйкес нұсқа жоқ; іздеуді нақтылаңыз.",
        "corpus": "Іздеуге дайын қала деректері жоқ.",
        "approximate": "Мақсат нүктесі жуық; қолжетімді кіреберіс расталмаған.",
    },
    "ru": {
        "unavailable": "Поиск недоступен. Повторите попытку позже.",
        "clarification": "Уточните ограничения: {fields}.",
        "conditional": "Условные варианты: проверьте неизвестные данные по источнику.",
        "facts": "Нет подтверждённых фактов о тишине, розетках или доступности.",
        "fallback": "Объяснение сформировано безопасным шаблоном.",
        "shortlist": "В проверенном коротком списке подходящих вариантов нет; уточните поиск.",
        "corpus": "Городской корпус пока не готов к поиску.",
        "approximate": "Точка назначения приблизительная; доступный вход не подтверждён.",
    },
    "en": {
        "unavailable": "Search is unavailable. Please try again later.",
        "clarification": "Clarify these constraints: {fields}.",
        "conditional": "Conditional alternatives: check missing facts with the source.",
        "facts": "Verified quietness, power outlet or accessibility facts are missing.",
        "fallback": "The explanation uses a safe template.",
        "shortlist": "No suitable alternative in the checked shortlist; refine the search.",
        "corpus": "The city corpus is not ready for search.",
        "approximate": "The destination is approximate; an accessible entrance is unconfirmed.",
    },
}

# Per request: <=12 retrieved rows, <=3 destinations, <=6 independent route legs,
# <=2 intent attempts, one embedding and one batch explanation. No route retries.
SHORTLIST_LIMIT = 3
ROUTE_DEADLINE_SECONDS = 18.0


def empty_response(request, status, code=None, message=None):
    return RecommendationResponse(
        request_id=request.request_id,
        status=status,
        items=[],
        sources=[],
        warnings=[Warning(code=code, message=message)] if code else [],
    )


class RecommendationService:
    def __init__(self, repository, client: AIClient | None, router=None, *, timezone="Asia/Almaty"):
        self.retriever = Retriever(repository, client)
        self.client = client
        self.router = router
        self.timezone = timezone

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        messages = MESSAGES[request.locale]
        if self.client is None:
            return empty_response(
                request, "unavailable", "provider_unavailable", messages["unavailable"]
            )
        unsupported = unsupported_requirements(request.query)
        if unsupported:
            return empty_response(request, "unknown", "missing_input", messages["facts"])
        result = await self.retriever.retrieve(request, limit=12)
        if result.status == "unavailable" or result.intent.status == "unavailable":
            return empty_response(
                request, "unavailable", "provider_unavailable", messages["unavailable"]
            )
        if result.status == "clarification":
            return empty_response(
                request,
                "unknown",
                "missing_input",
                messages["clarification"].format(
                    fields=", ".join(result.intent.clarification_fields)
                ),
            )
        if not result.candidates:
            if result.diagnostics.get("embedding_failure"):
                return empty_response(
                    request, "unavailable", "provider_unavailable", messages["unavailable"]
                )
            try:
                coverage = await self.retriever.repository.coverage()
            except DatabaseUnavailable:
                return empty_response(
                    request, "unavailable", "provider_unavailable", messages["unavailable"]
                )
            if not coverage["production_pois"] or not coverage["embedded_pois"]:
                return empty_response(request, "unknown", "data_unknown", messages["corpus"])
        intent = result.intent.intent
        unique = {}
        for candidate in result.candidates:
            if not hard_reject(candidate.poi, intent):
                unique.setdefault(candidate.id, candidate)
        shortlist = list(unique.values())[:SHORTLIST_LIMIT]
        evaluated = []
        for candidate in shortlist:
            outbound, back = await self._route(request, intent, candidate.poi)
            fit = evaluate_poi(candidate.poi, intent, outbound, back, timezone=self.timezone)
            if not fit.rejected:
                evaluated.append((candidate, fit))
        if not evaluated:
            if len(unique) > SHORTLIST_LIMIT:
                return empty_response(request, "unknown", "data_unknown", messages["shortlist"])
            return empty_response(request, "no_match")
        # Fit certainty precedes retrieval score; alternatives are independent trips.
        evaluated.sort(
            key=lambda pair: (
                pair[1].fit_status != "fits",
                len(pair[1].missing_fields),
                -float(pair[0].diagnostics.get("score") or 0),
                pair[0].id,
            )
        )
        cards, warnings, sources = [], [], {}
        for candidate, fit in evaluated:
            poi = candidate.poi
            source = next(s for s in poi.sources if s.source_id == poi.primary_source_id)
            card = POICard(
                poi=poi,
                provenance=poi.provenance,
                reason_codes=(
                    [ReasonCode.QUERY_MATCH] if candidate.diagnostics.get("selection_bases") else []
                )
                + list(fit.reason_codes),
                activity_code=poi.activity_code,
                visit_minutes_estimate=fit.visit_minutes_estimate,
                route_status=fit.route_status,
                travel_minutes_estimate=fit.travel_minutes_estimate,
                fit_status=fit.fit_status,
                missing_fields=list(fit.missing_fields),
                explanation=messages["conditional"],
                generated_locale=request.locale,
                action=Action(code="open_source", url=source.url),
            )
            card.explanation = fallback_explanation(card, request.locale)
            cards.append(card)
            warnings.extend(fit.warnings)
            if fit.route_status == "known":
                warnings.append(Warning(code="data_unknown", message=messages["approximate"]))
            elif fit.route_status == "unavailable":
                warnings.append(Warning(code="route_unavailable", message=messages["conditional"]))
            for item in poi.sources:
                if item.source_id in sources and sources[item.source_id] != item:
                    return empty_response(
                        request, "unknown", "data_unknown", messages["conditional"]
                    )
                sources[item.source_id] = item
        explanation = await ExplanationService(self.client).explain(cards, request.locale)
        for card, text in zip(cards, explanation.explanations, strict=True):
            card.explanation = text
        if explanation.used_fallback:
            warnings.append(Warning(code="data_unknown", message=messages["fallback"]))
        if result.diagnostics.get("embedding_failure"):
            warnings.append(Warning(code="provider_unavailable", message=messages["unavailable"]))
        uncertain = any(card.fit_status != "fits" for card in cards)
        if uncertain:
            warnings.append(Warning(code="data_unknown", message=messages["conditional"]))
        warnings = list({(w.code, w.message, tuple(w.fields)): w for w in warnings}.values())
        return RecommendationResponse(
            request_id=request.request_id,
            status="partial"
            if uncertain or result.diagnostics.get("embedding_failure") or explanation.used_fallback
            else "ok",
            items=cards,
            sources=list(sources.values()),
            warnings=warnings,
        )

    async def _route(self, request, intent, poi):
        unknown = RouteLeg(status="unknown", reason="missing_origin")
        absent = RouteLeg(status="not_requested", reason="not_requested")
        if intent.origin is None or not sourced_field(poi, "location"):
            return unknown, unknown if intent.return_to_start else absent
        unavailable = RouteLeg(status="unavailable", reason="disabled")
        if self.router is None:
            return unavailable, unavailable if intent.return_to_start else absent
        try:
            async with asyncio.timeout(ROUTE_DEADLINE_SECONDS):
                return await self.router.route(
                    RouteRequest(
                        request_id=request.request_id,
                        origin=intent.origin,
                        destination=poi.location,
                        return_to_start=intent.return_to_start,
                        locale=request.locale,
                    )
                )
        except TimeoutError:
            leg = RouteLeg(status="unavailable", reason="timeout")
            return leg, leg if intent.return_to_start else absent
