"""Compose bounded single-destination alternatives without inventing missing facts."""

import asyncio
import re
from dataclasses import replace

from backend.app.constraints import (
    evaluate_poi,
    hard_reject,
    sourced_field,
    unsupported_requirement_fields,
    unsupported_requirements,
)
from backend.app.database import DatabaseUnavailable
from backend.app.explain import ExplanationService, fallback_explanation
from backend.app.intent import constraint_clarifications
from backend.app.openai_client import AIClient
from backend.app.playground_intent import playground_query_kind, playgrounds_excluded
from backend.app.poi_features import FeatureCatalog
from backend.app.retrieval import Retriever
from backend.app.schemas import (
    Action,
    FeatureField,
    FitStatus,
    MissingField,
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
        "clarification": "Қайшы немесе танылмаған талаптарды нақтылаңыз.",
        "conditional": "Шартты нұсқалар: белгісіз деректерді дереккөзден тексеріңіз.",
        "facts": "Мына талаптарды тексеруге расталған деректер жоқ: {requirements}.",
        "fallback": "Түсіндірме қауіпсіз үлгімен берілді.",
        "shortlist": "Тексерілген қысқа тізімде сәйкес нұсқа жоқ; іздеуді нақтылаңыз.",
        "search_limited": "Уақыт немесе тексеру шегі аяқталды; қалған нұсқалар тексерілмеді.",
        "playground_exclusion": (
            "Ойын алаңдарын алып тастау талабын сенімді тексеру әзірге мүмкін емес."
        ),
        "corpus": "Іздеуге дайын қала деректері жоқ.",
        "approximate": "Мақсат нүктесі жуық; қолжетімді кіреберіс расталмаған.",
    },
    "ru": {
        "unavailable": "Поиск недоступен. Повторите попытку позже.",
        "clarification": "Уточните противоречивые или нераспознанные ограничения.",
        "conditional": "Условные варианты: проверьте неизвестные данные по источнику.",
        "facts": "Нет подтверждённых данных для проверки условий: {requirements}.",
        "fallback": "Объяснение сформировано безопасным шаблоном.",
        "shortlist": "В проверенном коротком списке подходящих вариантов нет; уточните поиск.",
        "search_limited": "Достигнут лимит времени или проверок; остальные варианты не проверены.",
        "playground_exclusion": "Исключение детских площадок пока нельзя надёжно проверить.",
        "corpus": "Городской корпус пока не готов к поиску.",
        "approximate": "Точка назначения приблизительная; доступный вход не подтверждён.",
    },
    "en": {
        "unavailable": "Search is unavailable. Please try again later.",
        "clarification": "Clarify conflicting or unrecognized constraints.",
        "conditional": "Conditional alternatives: check missing facts with the source.",
        "facts": "Verified facts are missing for these requirements: {requirements}.",
        "fallback": "The explanation uses a safe template.",
        "shortlist": "No suitable alternative in the checked shortlist; refine the search.",
        "search_limited": (
            "Search reached its time or evaluation limit; remaining alternatives were not checked."
        ),
        "playground_exclusion": "Excluding playgrounds cannot yet be reliably verified.",
        "corpus": "The city corpus is not ready for search.",
        "approximate": "The destination is approximate; an accessible entrance is unconfirmed.",
    },
}

UNSUPPORTED_FACT_LABELS = {
    "kk": {
        "quiet": "тыныштық",
        "power_outlets": "розеткалар мен құрылғыны қуаттау",
        "accessibility": "қолжетімділік",
        "child_suitability": "балаларға жарамдылық пен жас шектеулері",
    },
    "ru": {
        "quiet": "тишина",
        "power_outlets": "розетки и зарядка устройств",
        "accessibility": "доступность",
        "child_suitability": "пригодность для детей и возрастные ограничения",
    },
    "en": {
        "quiet": "quietness",
        "power_outlets": "power outlets and device charging",
        "accessibility": "accessibility",
        "child_suitability": "child suitability and age restrictions",
    },
}


def unsupported_requirement_message(locale, requirements):
    """Name only detected unsupported conditions, without exposing internal keys."""
    labels = UNSUPPORTED_FACT_LABELS[locale]
    return MESSAGES[locale]["facts"].format(
        requirements=", ".join(labels[requirement] for requirement in requirements)
    )


# Per request: <=12 evaluated candidates, <=3 returned destinations, <=24 route
# legs, <=2 intent attempts, one embedding and one batch explanation. No retries.
SHORTLIST_LIMIT = 3
MAX_CANDIDATE_EVALUATIONS = 12
ROUTE_DEADLINE_SECONDS = 18.0
# Preserve the former worst-case route budget of three 18-second evaluations.
ROUTE_SEARCH_DEADLINE_SECONDS = SHORTLIST_LIMIT * ROUTE_DEADLINE_SECONDS


def empty_response(request, status, code=None, message=None, *, fields=(), clarifications=()):
    return RecommendationResponse(
        request_id=request.request_id,
        status=status,
        items=[],
        sources=[],
        warnings=[
            Warning(
                code=code,
                message=message,
                fields=list(fields),
                clarifications=list(clarifications),
            )
        ]
        if code
        else [],
    )


class RecommendationService:
    def __init__(
        self,
        repository,
        client: AIClient | None,
        router=None,
        *,
        timezone="Asia/Almaty",
        feature_catalog: FeatureCatalog | None = None,
    ):
        self.retriever = Retriever(repository, client, feature_catalog=feature_catalog)
        self.client = client
        self.router = router
        self.timezone = timezone
        self.feature_catalog = feature_catalog

    def _unsupported(self, query, *, interests=()):
        unsupported = unsupported_requirements(query, interests=interests)
        fields = unsupported_requirement_fields(query, interests=interests)
        if (
            playground_query_kind(query, interests=interests)
            and "child_suitability" not in unsupported
        ):
            # A requested playground needs positive type evidence even when the
            # extraction or the raw child guard did not mention child suitability.
            unsupported.append("child_suitability")
            if MissingField.CHILD_SUITABILITY not in fields:
                fields.append(MissingField.CHILD_SUITABILITY)
        text = " ".join((query, *interests))
        unresolved_polarity = {
            "child_suitability": (
                r"child[ -]free|kid[ -]free|без\s+(?:дет\w*|реб[её]н\w*)|баласыз|балаларсыз|"
                r"\bnot\s+(?:necessarily\s+)?(?:child|kid|family)[ -]friendly\b|"
                r"не\s+подход\w*\s+для\s+дет\w*|балаларға\s+арналмаған|"
                r"не\s+для\s+дет\w*|дет\w*\s+(?:нельзя|не\s+нуж\w*)|"
                r"(?:child|kid|family)[ -]friendly\s+(?:is\s+)?optional\b|"
                r"\b(?:no|without)\s+(?:children|kids|a\s+child)\b|"
                r"\b(?:bab(?:y|ies)|infants?|toddlers?)\b|младен\w*|нәрест\w*|бүлдіршін\w*"
            ),
            "power_outlets": (
                r"\b(?:no|without)\s+(?:\w+\s+){0,3}(?:outlets?|sockets?|charg\w*)\b|"
                r"\b(?:outlets?|sockets?|charging)\s+(?:(?:is|are)\s+)?(?:not\s+(?:needed|required)|optional)\b|"
                r"\boptional\s+(?:charging|outlets?|sockets?)\b|"
                r"без\s+(?:розет\w*|заряд\w*)|(?:розет\w*|заряд\w*)\s+(?:не\s+(?:нуж\w*|обязат\w*)|необязат\w*)|"
                r"розеткасыз|қуаттаусыз|(?:розет\w*|қуатта\w*)\s+(?:жоқ|міндетті\s+емес)"
            ),
        }
        if self.feature_catalog is not None:
            for requirement in ("child_suitability", "power_outlets"):
                if requirement == "child_suitability" and MissingField.AGE_RESTRICTIONS in fields:
                    continue
                if re.search(unresolved_polarity[requirement], text, re.I):
                    continue
                if requirement == "power_outlets" and re.search(
                    r"\b(?:cars?|vehicles?|ev|wireless|usb\w*|qi)\b|электромоб\w*|автомоб\w*|"
                    r"беспровод\w*|сымсыз|type[ -]?c|\d+\s*(?:вольт|volts?\b|[вv]\b)",
                    text,
                    re.I,
                ):
                    continue
                if requirement in unsupported and self.feature_catalog.supports(requirement):
                    unsupported.remove(requirement)
                    fields = [field for field in fields if field.value != requirement]
        return unsupported, fields

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        messages = MESSAGES[request.locale]
        if self.client is None:
            return empty_response(
                request, "unavailable", "provider_unavailable", messages["unavailable"]
            )
        if playgrounds_excluded(request.query):
            return empty_response(
                request, "unknown", "missing_input", messages["playground_exclusion"]
            )
        unsupported, missing_requirements = self._unsupported(request.query)
        if unsupported:
            return empty_response(
                request,
                "unknown",
                "missing_input",
                unsupported_requirement_message(request.locale, unsupported),
                fields=missing_requirements,
            )
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
                messages["clarification"],
                clarifications=constraint_clarifications(result.intent),
            )
        intent = result.intent.intent
        unsupported, missing_requirements = self._unsupported(
            request.query, interests=intent.interests
        )
        if unsupported:
            return empty_response(
                request,
                "unknown",
                "missing_input",
                unsupported_requirement_message(request.locale, unsupported),
                fields=missing_requirements,
            )
        if not result.candidates:
            if result.diagnostics.get("feature_catalog"):
                return empty_response(
                    request,
                    "unknown",
                    "data_unknown",
                    messages["shortlist"],
                    fields=unsupported_requirement_fields(
                        request.query, interests=intent.interests
                    ),
                )
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
        unique = {}
        for candidate in result.candidates:
            curated = candidate.diagnostics.get("curated")
            playground = (
                curated is not None and curated.fact(FeatureField.FAMILY_PLAYGROUND) is True
            )
            if not hard_reject(candidate.poi, intent, playground=playground):
                unique.setdefault(candidate.id, candidate)
        evaluated = []
        search_incomplete = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + ROUTE_SEARCH_DEADLINE_SECONDS
        for index, candidate in enumerate(unique.values()):
            if len(evaluated) == SHORTLIST_LIMIT:
                break
            remaining = deadline - loop.time()
            if index >= MAX_CANDIDATE_EVALUATIONS or remaining <= 0:
                search_incomplete = True
                break
            try:
                async with asyncio.timeout(remaining):
                    outbound, back = await self._route(request, intent, candidate.poi)
            except TimeoutError:
                search_incomplete = True
                break
            curated = candidate.diagnostics.get("curated")
            playground = (
                curated is not None and curated.fact(FeatureField.FAMILY_PLAYGROUND) is True
            )
            fit = evaluate_poi(
                candidate.poi,
                intent,
                outbound,
                back,
                timezone=self.timezone,
                playground=playground,
            )
            if curated is not None:
                reasons = list(fit.reason_codes)
                if curated.fact(FeatureField.FAMILY_PLAYGROUND) is True:
                    reasons.append(ReasonCode.FAMILY_PLAYGROUND_MATCH)
                if curated.fact(FeatureField.POWER_OUTLETS) is True:
                    reasons.append(ReasonCode.POWER_OUTLETS_MATCH)
                missing = list(fit.missing_fields)
                if curated.fact(FeatureField.PUBLIC_ACCESS) is None:
                    missing.append(MissingField.PUBLIC_ACCESS)
                fit = replace(
                    fit,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                    missing_fields=tuple(dict.fromkeys(missing)),
                    fit_status=FitStatus.DOES_NOT_FIT
                    if fit.rejected
                    else FitStatus.UNKNOWN
                    if missing
                    else FitStatus.FITS,
                )
            if not fit.rejected:
                evaluated.append((candidate, fit))
        if not evaluated:
            if search_incomplete:
                return empty_response(
                    request, "unknown", "data_unknown", messages["search_limited"]
                )
            if result.diagnostics.get("feature_catalog"):
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
                feature_evidence=candidate.diagnostics["curated"].evidence
                if candidate.diagnostics.get("curated") is not None
                else [],
                name_is_derived=candidate.diagnostics["curated"].name_is_derived
                if candidate.diagnostics.get("curated") is not None
                else False,
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
        if search_incomplete:
            warnings.append(Warning(code="data_unknown", message=messages["search_limited"]))
        if result.diagnostics.get("embedding_failure"):
            warnings.append(Warning(code="provider_unavailable", message=messages["unavailable"]))
        uncertain = any(card.fit_status != "fits" for card in cards)
        if uncertain:
            warnings.append(Warning(code="data_unknown", message=messages["conditional"]))
        warnings = list({(w.code, w.message, tuple(w.fields)): w for w in warnings}.values())
        return RecommendationResponse(
            request_id=request.request_id,
            status="partial"
            if uncertain
            or search_incomplete
            or result.diagnostics.get("embedding_failure")
            or explanation.used_fallback
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
