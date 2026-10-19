"""Bounded event discovery, runtime venue matching and independent session alternatives."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from backend.app.constraints import MAX_CARD_TRAVEL_MINUTES, unsupported_requirements
from backend.app.database import DatabaseUnavailable
from backend.app.event_constraints import evaluate_event_session
from backend.app.event_evidence import has_source_cancellation
from backend.app.event_extraction import EventExtractionBatch
from backend.app.event_schemas import (
    TransientEvent,
    TransientEventCard,
    TransientEventSearchResponse,
    TransientEventSource,
    transient_source_id,
)
from backend.app.explain import ExplanationService, fallback_explanation
from backend.app.intent import IntentExtractor
from backend.app.openai_client import AIClient, ProviderError
from backend.app.recommend import MESSAGES, ROUTE_DEADLINE_SECONDS, SHORTLIST_LIMIT
from backend.app.schemas import (
    Action,
    EventSearchRequest,
    POIRecord,
    RouteLeg,
    RouteRequest,
    Warning,
)
from backend.app.services.events.discover import discover_events
from backend.app.services.events.models import CandidateBatch, DiscoveryResult
from backend.app.services.events.normalize import ASTANA_NAMES, require_aware
from backend.app.services.events.venue import VenueMatch, match_venue, normalize_venue_text

DISCOVERY_TIMEOUT_SECONDS = 80.0
EXTRACTION_MAX_OUTPUT_TOKENS = 4096
VENUE_CANDIDATE_LIMIT = 30
MAX_VENUE_SOURCE_REFERENCES = 20
EXTRACTION_POLICY = (
    "\nReturn at most three relevant events and at most three sessions per event. "
    "This is a bounded discovery sample, never a complete city inventory."
)
SEARCH_RESULT_POLICY = (
    "\nReturn at most three events with at most one dated session each, in at most 600 words. "
    "Use at most three total web-search actions, including search, page opening and finding. "
    "After that budget, stop using tools and finish the answer with citations to already "
    "consulted sources. Keep missing fields unknown; insufficient evidence is acceptable."
)


class D03Client:
    """Borrow the shared client; structured extraction replaces its legacy text budget."""

    def __init__(self, client: AIClient):
        self.client = client

    async def search_web(self, text, *, instructions="", allowed_domains):
        return await self.client.search_web(
            text, instructions=instructions + SEARCH_RESULT_POLICY, allowed_domains=allowed_domains
        )

    async def create_response(self, text, *, instructions=""):
        batch = await self.client.parse_response(
            text,
            EventExtractionBatch,
            instructions=instructions + EXTRACTION_POLICY,
            max_output_tokens=EXTRACTION_MAX_OUTPUT_TOKENS,
        )
        if (
            not isinstance(batch, CandidateBatch)
            or len(batch.events) > 3
            or any(len(event.sessions) > 3 for event in batch.events)
        ):
            raise ProviderError("event_extraction_limit")
        return batch.model_dump_json()


def _empty(request, *, status, code, locale_message, provider_status=None, live="not_run"):
    return TransientEventSearchResponse(
        request_id=request.request_id,
        status=status,
        provider_status=provider_status or status,
        provider_code=code,
        live_web_search=live,
        items=[],
        listings=[],
        sources=[],
        warnings=[
            Warning(
                code="provider_unavailable" if status == "unavailable" else "missing_input",
                message=locale_message,
            )
        ],
    )


def _card_route(intent, session, outbound, back):
    legs = [outbound, back] if intent.return_to_start else [outbound]
    if (
        intent.origin is not None
        and session.venue.location is not None
        and all(leg.status == "known" for leg in legs)
    ):
        minutes = (sum(leg.duration_seconds for leg in legs) + 59) // 60
        if minutes <= MAX_CARD_TRAVEL_MINUTES:
            return "known", minutes
    return "unavailable" if any(leg.status == "unavailable" for leg in legs) else "unknown", None


def _session_identity(event, session):
    names = (
        normalize_venue_text(event.title),
        normalize_venue_text(session.venue_name),
        normalize_venue_text(session.venue_address),
    )
    if not all(names) or session.starts_at is None:
        return None
    return (*names, session.starts_at.astimezone(UTC))


class EventRecommendationService:
    def __init__(
        self,
        repository,
        client: AIClient | None,
        router=None,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.repository = repository
        self.client = client
        self.router = router
        self.clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def search(
        self, request: EventSearchRequest, *, now: datetime | None = None
    ) -> TransientEventSearchResponse:
        def current_time() -> datetime:
            value = now if now is not None else self.clock()
            require_aware(value)
            return value

        observed = current_time()
        messages = MESSAGES[request.locale]
        if unsupported_requirements(request.query):
            return _empty(
                request,
                status="unknown",
                code="unsupported_fact_requirement",
                locale_message=messages["facts"],
            )
        if self.client is None:
            return _empty(
                request,
                status="unavailable",
                code="intent_provider_unavailable",
                locale_message=messages["unavailable"],
            )
        extracted = await IntentExtractor(self.client).extract(request)
        if extracted.status == "clarification":
            return _empty(
                request,
                status="unknown",
                code="constraint_clarification",
                locale_message=messages["clarification"].format(
                    fields=", ".join(extracted.clarification_fields)
                ),
            )
        if extracted.status != "ok" or extracted.intent is None:
            return _empty(
                request,
                status="unavailable",
                code=extracted.reason or "intent_provider_unavailable",
                locale_message=messages["unavailable"],
            )
        if not callable(getattr(self.client, "search_web", None)):
            return _empty(
                request,
                status="unavailable",
                code="shared_web_search_method_missing",
                locale_message=messages["unavailable"],
            )
        intent = extracted.intent
        resolved_request = request.model_copy(
            update={
                "origin": intent.origin,
                "date_time": intent.date_time,
                "available_minutes": intent.available_minutes,
                "budget_kzt_per_person": intent.budget_kzt_per_person,
                "return_to_start": intent.return_to_start,
                "indoor_only": intent.indoor == "indoor",
            }
        )
        try:
            discovered = await discover_events(
                D03Client(self.client),
                resolved_request,
                now=observed,
                timeout_seconds=DISCOVERY_TIMEOUT_SECONDS,
            )
        except (OverflowError, ValueError):
            return _empty(
                request,
                status="unknown",
                code="date_out_of_range",
                locale_message=messages["conditional"],
            )
        if discovered.provider_status == "unavailable":
            return _empty(
                request,
                status="unavailable",
                code=discovered.provider_code or "provider_failed",
                locale_message=messages["unavailable"],
                live=discovered.live_web_search,
            )
        return await self._compose(request, intent, discovered, observed, current_time)

    async def _compose(self, request, intent, discovered: DiscoveryResult, observed, current_time):
        messages = MESSAGES[request.locale]
        sources: dict[str, TransientEventSource] = {}
        venue_cache = {}
        warnings = [Warning(code="data_unknown", message=messages["conditional"])]
        pending = []
        evaluated_trips = {}
        events = [event.model_copy(deep=True) for event in discovered.events]
        initially_eligible = {
            session.session_id
            for event in events
            for session in event.sessions
            if session.recommendation_candidate and not session.exclusion_reasons
        }

        def source(url, retrieved_at, source_id=None):
            identifier = source_id or transient_source_id(url)
            candidate = TransientEventSource(
                source_id=identifier,
                url=url,
                retrieved_at=retrieved_at,
            )
            previous = sources.get(identifier)
            if previous is not None and previous.url != candidate.url:
                raise ValueError("Conflicting runtime source identity")
            if previous is None or previous.retrieved_at > candidate.retrieved_at:
                sources[identifier] = candidate
            return identifier

        if discovered.evidence is not None:
            for consulted in discovered.evidence.sources:
                source(consulted.url, consulted.fetched_at)
        cancelled_identities = set()
        for event in events:
            for session in event.sessions:
                source_cancelled = has_source_cancellation(
                    session, discovered.evidence, event_title=event.title
                )
                if source_cancelled:
                    # Preserve D03's extracted status, but withhold conflicting evidence.
                    session.recommendation_candidate = False
                    session.exclusion_reasons = list(
                        dict.fromkeys([*session.exclusion_reasons, "source_cancellation"])
                    )
                if source_cancelled or session.status == "cancelled":
                    identity = _session_identity(event, session)
                    if identity is not None:
                        cancelled_identities.add(identity)
        for event in events:
            source(event.source_url, event.source_fetched_at)
            for session in event.sessions:
                source(session.source_url, session.source_fetched_at)
                if (
                    _session_identity(event, session) in cancelled_identities
                    and session.status == "scheduled"
                    and "source_cancellation" not in session.exclusion_reasons
                ):
                    # Another source with a complete identical identity cannot
                    # erase an explicit cancellation. Distinct branches stay separate.
                    session.recommendation_candidate = False
                    session.exclusion_reasons = list(
                        dict.fromkeys([*session.exclusion_reasons, "unresolved_cancellation"])
                    )
                evaluation = evaluate_event_session(
                    session, intent, now=current_time(), window_start=observed
                )
                if evaluation.rejected:
                    session.recommendation_candidate = False
                    session.exclusion_reasons = list(evaluation.exclusion_reasons)
                else:
                    pending.append((event, session))
        # Stable earliest-session order is a bounded selection policy, not city coverage.
        pending.sort(key=lambda pair: (pair[1].starts_at, pair[0].event_id, pair[1].session_id))
        distinct = []
        seen = set()
        for event, session in pending:
            identity = _session_identity(event, session)
            # Incomplete identities cannot justify merging different venue branches.
            if identity is not None:
                if identity in seen:
                    continue
                seen.add(identity)
            distinct.append((event, session))
        cards = []
        for event, session in distinct[:SHORTLIST_LIMIT]:
            venue, poi_sources = await self._venue(session, venue_cache)
            if (
                any(
                    item.source_id in sources and sources[item.source_id].url != item.url
                    for item in poi_sources
                )
                or len(sources.keys() | {item.source_id for item in poi_sources}) > 100
            ):
                # Conflicting or unrepresentable references cannot justify a route.
                venue, poi_sources = VenueMatch(), []
            session.venue = venue
            session.missing_fields = [
                field for field in session.missing_fields if field != "location"
            ]
            if venue.location is None:
                session.missing_fields.append("location")
            for poi_source in poi_sources:
                source(poi_source.url, poi_source.retrieved_at, poi_source.source_id)
            # Database enrichment can also consume the remaining arrival margin.
            evaluation = evaluate_event_session(
                session, intent, now=current_time(), window_start=observed
            )
            if evaluation.rejected:
                session.recommendation_candidate = False
                session.exclusion_reasons = list(evaluation.exclusion_reasons)
                continue
            outbound, back = await self._route(request, intent, session)
            evaluation = evaluate_event_session(
                session,
                intent,
                outbound,
                back,
                now=current_time(),
                window_start=observed,
            )
            if evaluation.rejected:
                session.recommendation_candidate = False
                session.exclusion_reasons = list(evaluation.exclusion_reasons)
                continue
            route_status, minutes = _card_route(intent, session, outbound, back)
            missing = list(evaluation.missing_fields)
            if minutes is None and "travel_minutes_estimate" not in missing:
                missing.append("travel_minutes_estimate")
            event_source_id = source(event.source_url, event.source_fetched_at)
            session_source_id = source(session.source_url, session.source_fetched_at)
            refs = list(dict.fromkeys([event_source_id, session_source_id, *venue.source_ids]))
            card = TransientEventCard(
                event=TransientEvent(
                    id=event.event_id,
                    title=event.title,
                    city=event.city,
                    venue_name=event.venue_name,
                    venue_address=event.venue_address,
                    source_id=event_source_id,
                ),
                session=session,
                source_ids=refs,
                reason_codes=list(evaluation.reason_codes),
                route_status=route_status,
                travel_minutes_estimate=minutes,
                fit_status=evaluation.fit_status,
                missing_fields=missing,
                explanation=messages["conditional"],
                generated_locale=request.locale,
                action=Action(code="open_source", url=session.source_url),
            )
            card.explanation = fallback_explanation(card, request.locale)
            cards.append(card)
            evaluated_trips[session.session_id] = (session, outbound, back)
            if route_status == "unavailable":
                warnings.append(Warning(code="route_unavailable", message=messages["conditional"]))
            elif route_status == "known":
                warnings.append(Warning(code="data_unknown", message=messages["approximate"]))
        cards.sort(
            key=lambda card: (
                len(card.missing_fields),
                card.session.starts_at,
                card.session.session_id,
            )
        )
        if cards:
            explanation = await ExplanationService(self.client).explain(cards, request.locale)
            for card, text in zip(cards, explanation.explanations, strict=True):
                card.explanation = text
            if explanation.used_fallback:
                warnings.append(Warning(code="data_unknown", message=messages["fallback"]))
        # Reuse the original legs and availability window after the last provider call.
        # A session can have started or become unreachable while explanation ran.
        final_now = current_time()
        current_cards = []
        for card in cards:
            session, outbound, back = evaluated_trips[card.session.session_id]
            evaluation = evaluate_event_session(
                session,
                intent,
                outbound,
                back,
                now=final_now,
                window_start=observed,
            )
            if evaluation.rejected:
                session.recommendation_candidate = False
                session.exclusion_reasons = list(evaluation.exclusion_reasons)
            else:
                current_cards.append(card)
        cards = current_cards
        # Keep normalized listings and withheld sessions separate from recommendation cards.
        # Raw search prose/citation contexts are deliberately absent from the HTTP envelope.
        for event in events:
            for url in event.venue.source_urls:
                source(url, event.source_fetched_at)
            for session in event.sessions:
                for check in session.verified_fields:
                    source(check.source_url, session.source_fetched_at)
                for url in session.venue.source_urls:
                    if not any(item.url == url for item in sources.values()):
                        source(url, session.source_fetched_at)
        extra_excluded = sum(
            session.session_id in initially_eligible and not session.recommendation_candidate
            for event in events
            for session in event.sessions
        )
        return TransientEventSearchResponse(
            request_id=request.request_id,
            status="partial" if cards or events else "unknown",
            provider_status=discovered.provider_status,
            provider_code=discovered.provider_code,
            live_web_search=discovered.live_web_search,
            items=cards,
            listings=events,
            sources=list(sources.values()),
            warnings=list({(w.code, w.message): w for w in warnings}.values()),
            excluded_sessions=discovered.excluded_sessions + extra_excluded,
            rejected_events=discovered.rejected_events,
        )

    async def _venue(self, session, cache):
        pair = (
            normalize_venue_text(session.venue_name),
            normalize_venue_text(session.venue_address),
        )
        if not all(pair) or normalize_venue_text(session.city) not in ASTANA_NAMES:
            return VenueMatch(), []
        if pair in cache:
            return cache[pair]
        if self.repository is None or len(cache) >= SHORTLIST_LIMIT:
            return VenueMatch(), []
        cache[pair] = VenueMatch(), []
        try:
            rows = await self.repository.retrieve_candidates(
                session.venue_name,
                names=[session.venue_name],
                categories=[],
                origin=None,
                vector=None,
                limit=VENUE_CANDIDATE_LIMIT,
            )
            # A truncated set cannot establish a unique exact venue match.
            if len(rows) >= VENUE_CANDIDATE_LIMIT:
                return cache[pair]
            pois = [POIRecord.model_validate(row["document"]) for row in rows]
            venue = match_venue(session.venue_name, session.venue_address, pois)
            winner = next((poi for poi in pois if poi.id == venue.poi_id), None)
            if winner is not None and len(winner.sources) > MAX_VENUE_SOURCE_REFERENCES:
                # Keep the entire HTTP reference envelope within its explicit bound.
                return cache[pair]
            cache[pair] = venue, list(winner.sources) if winner else []
        except (DatabaseUnavailable, ValidationError, ValueError):
            pass
        return cache[pair]

    async def _route(self, request, intent, session):
        absent = RouteLeg(status="not_requested", reason="not_requested")
        reason = "missing_origin" if intent.origin is None else "route_not_found"
        unknown = RouteLeg(status="unknown", reason=reason)
        if intent.origin is None or session.venue.location is None:
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
                        destination=session.venue.location,
                        return_to_start=intent.return_to_start,
                        locale=request.locale,
                    )
                )
        except TimeoutError:
            leg = RouteLeg(status="unavailable", reason="timeout")
            return leg, leg if intent.return_to_start else absent
