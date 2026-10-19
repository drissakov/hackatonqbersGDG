"""Additive v1.3 transient event HTTP models; never persistence or embedding inputs."""

import hashlib
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, HttpUrl, field_validator, model_validator

from backend.app.schemas import (
    Action,
    ActivityCode,
    ContractModel,
    FitStatus,
    Identifier,
    Locale,
    Minutes,
    ReasonCode,
    ResponseStatus,
    RouteStatus,
    Text,
    TravelMinutes,
    Warning,
)
from backend.app.services.events.models import NormalizedEvent, NormalizedSession
from backend.app.services.events.normalize import ASTANA_NAMES
from backend.app.services.events.venue import normalize_venue_text

TRANSIENT_MISSING_FIELDS = [
    "city",
    "venue_name",
    "venue_address",
    "starts_at",
    "ends_at",
    "status",
    "sessions",
    "origin",
    "date_time",
    "available_minutes",
    "location",
    "travel_minutes_estimate",
    "return_travel_minutes_estimate",
    "price_kzt_per_person",
    "price_from",
    "currency",
    "price_conditions",
    "indoor",
    "source_verification",
    "ticket_availability",
]

MissingNames = Annotated[list[Identifier], Field(max_length=32)]


def transient_source_id(url: str | HttpUrl) -> str:
    """Stable request-independent URL identity; no source content enters this hash."""
    return "event-source:" + hashlib.sha256(str(url).encode()).hexdigest()[:24]


def _public_url(url: HttpUrl) -> HttpUrl:
    if url.username or url.password:
        raise ValueError("Public source URLs must not contain credentials")
    return url


class TransientEventSource(ContractModel):
    source_id: Identifier
    url: HttpUrl
    retrieved_at: AwareDatetime
    source_updated_at: AwareDatetime | None = None
    storage_allowed: Literal[False] = False
    indexing_allowed: Literal[False] = False

    _no_credentials = field_validator("url")(_public_url)

    @field_validator("storage_allowed", "indexing_allowed", mode="before")
    @classmethod
    def rights_remain_literal_false(cls, value):
        if value is not False:
            raise ValueError("Transient source rights must be the boolean false")
        return value


class TransientEvent(ContractModel):
    id: Identifier
    title: Text
    city: Annotated[str, Field(min_length=1, max_length=150)] | None = None
    venue_name: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    venue_address: Annotated[str, Field(min_length=1, max_length=300)] | None = None
    source_id: Identifier


class TransientEventCard(ContractModel):
    event: TransientEvent
    # Reuse Damir's actual normalized runtime DTO without inventing storage rights.
    session: NormalizedSession
    source_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1, max_length=16)]
    activity_code: ActivityCode = ActivityCode.OTHER
    visit_minutes_estimate: Minutes | None = None
    route_status: RouteStatus
    travel_minutes_estimate: TravelMinutes | None
    fit_status: FitStatus
    missing_fields: MissingNames
    explanation: Text
    generated_locale: Locale
    action: Action

    @model_validator(mode="after")
    def honest_session_card(self) -> Self:
        session = self.session
        if session.event_id != self.event.id:
            raise ValueError("Session must belong to the event header")
        if not session.session_id or len(session.session_id) > 200:
            raise ValueError("Session ID must be a bounded nonempty identifier")
        if (
            session.status != "scheduled"
            or session.starts_at is None
            or session.city is None
            or normalize_venue_text(session.city) not in ASTANA_NAMES
            or not session.recommendation_candidate
            or session.exclusion_reasons
        ):
            raise ValueError("Only eligible scheduled Astana sessions can become cards")
        if session.ends_at is not None and session.ends_at <= session.starts_at:
            raise ValueError("Session end must follow its start")
        if (
            self.event.city is not None
            and normalize_venue_text(self.event.city) not in ASTANA_NAMES
        ):
            raise ValueError("Event city must not contradict Astana eligibility")
        if self.fit_status == FitStatus.DOES_NOT_FIT:
            raise ValueError("Known hard-constraint conflicts cannot be alternatives")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Card source IDs must be unique")
        if self.event.source_id not in self.source_ids:
            raise ValueError("Card must cite its event header source")
        if len(set(self.missing_fields)) != len(self.missing_fields):
            raise ValueError("Missing fields must be unique")
        known_route = self.route_status in (RouteStatus.KNOWN, RouteStatus.ESTIMATED)
        if known_route != (self.travel_minutes_estimate is not None):
            raise ValueError("Only known or estimated routes have travel durations")
        required_missing = {"ticket_availability"}
        if not known_route:
            required_missing.add("travel_minutes_estimate")
        if session.ends_at is None:
            required_missing.add("ends_at")
        checked = {check.field for check in session.verified_fields}
        if not {"city", "venue_name", "venue_address", "starts_at", "ends_at", "status"} <= checked:
            required_missing.add("source_verification")
        if not required_missing.issubset(self.missing_fields):
            raise ValueError("Unknown ticket, route and end data must remain explicit")
        if any(field not in TRANSIENT_MISSING_FIELDS for field in self.missing_fields):
            raise ValueError("Missing-field codes must use the transient code list")
        if (
            ReasonCode.WITHIN_BUDGET in self.reason_codes
            or ReasonCode.INDOOR_MATCH in self.reason_codes
        ):
            raise ValueError("D03 lower-bound prices and absent indoor facts cannot prove a fit")
        # D03 has no ticket-inventory verifier: even a checked schedule is conditional.
        if self.fit_status != FitStatus.UNKNOWN:
            raise ValueError("Unknown ticket availability cannot prove a confirmed fit")
        if (
            self.visit_minutes_estimate is not None
            and ReasonCode.VISIT_DURATION_ESTIMATE not in self.reason_codes
        ):
            raise ValueError("Suggested visit duration must be labelled as an estimate")
        return self


class TransientEventSearchResponse(ContractModel):
    request_id: UUID
    contract_version: Literal["1.3.0"] = "1.3.0"
    status: ResponseStatus
    provider_status: Literal["partial", "unknown", "unavailable"]
    provider_code: (
        Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$")] | None
    ) = None
    live_web_search: Literal["not_run", "passed", "failed"]
    items: Annotated[list[TransientEventCard], Field(max_length=3)]
    listings: Annotated[list[NormalizedEvent], Field(max_length=10)]
    sources: Annotated[list[TransientEventSource], Field(max_length=100)]
    warnings: Annotated[list[Warning], Field(max_length=100)]
    excluded_sessions: Annotated[int, Field(ge=0, strict=True)] = 0
    rejected_events: Annotated[int, Field(ge=0, strict=True)] = 0

    @model_validator(mode="after")
    def safe_runtime_response(self) -> Self:
        has_data = bool(self.items or self.listings)
        if self.status == ResponseStatus.NO_MATCH:
            raise ValueError("Bounded discovery cannot establish complete absence")
        if (self.status in (ResponseStatus.OK, ResponseStatus.PARTIAL)) != has_data:
            raise ValueError("Only ok or partial responses contain cards or listings")
        if self.status == ResponseStatus.PARTIAL and not self.warnings:
            raise ValueError("Partial discovery must explain its limitations")
        if self.status == ResponseStatus.OK and (
            not self.items
            or self.listings
            or any(c.fit_status != FitStatus.FITS for c in self.items)
        ):
            raise ValueError("Only fully confirmed cards could form an ok response")
        if self.provider_status == "unavailable" and self.status != ResponseStatus.UNAVAILABLE:
            raise ValueError("Provider failure must remain unavailable")
        if has_data and self.live_web_search != "passed":
            raise ValueError("Runtime discoveries require completed live search evidence")
        sources = {source.source_id: source for source in self.sources}
        urls = {source.url for source in self.sources}
        if len(sources) != len(self.sources):
            raise ValueError("Source IDs must be unique")
        card_ids = [card.session.session_id for card in self.items]
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("Session alternatives must be distinct")
        listing_ids = [listing.event_id for listing in self.listings]
        if len(set(listing_ids)) != len(listing_ids):
            raise ValueError("Listing event IDs must be unique")
        for card in self.items:
            if any(source_id not in sources for source_id in card.source_ids):
                raise ValueError("Card references must exist in the source envelope")
            cited_urls = {sources[source_id].url for source_id in card.source_ids}
            if card.session.source_url not in cited_urls or card.action.url not in cited_urls:
                raise ValueError("Session and action URLs must match cited sources")
            self._session_sources(card.session, urls)
        for listing in self.listings:
            if not listing.event_id or len(listing.event_id) > 200:
                raise ValueError("Listing ID must be a bounded nonempty identifier")
            if listing.source_url not in urls:
                raise ValueError("Listing source must exist in the envelope")
            if listing.city is not None and normalize_venue_text(listing.city) not in ASTANA_NAMES:
                raise ValueError("Listings must not claim another known city")
            if len(listing.sessions) > 20 or len(listing.schedule_hints) > 32:
                raise ValueError("Listing session and hint counts must be bounded")
            if len(listing.missing_fields) > 32:
                raise ValueError("Listing missing-field count must be bounded")
            if any(field not in TRANSIENT_MISSING_FIELDS for field in listing.missing_fields):
                raise ValueError("Listing missing fields must use the transient code list")
            if any(url not in urls for url in listing.venue.source_urls):
                raise ValueError("Venue source URLs must exist in the envelope")
            for session in listing.sessions:
                if session.event_id != listing.event_id:
                    raise ValueError("Listing sessions must belong to their event")
                self._session_sources(session, urls)
        return self

    @staticmethod
    def _session_sources(session: NormalizedSession, urls: set[HttpUrl]) -> None:
        if session.source_url not in urls or any(
            url not in urls for url in session.venue.source_urls
        ):
            raise ValueError("Session and venue sources must exist in the envelope")
        if len(session.verified_fields) > 32 or len(session.missing_fields) > 32:
            raise ValueError("Session field-check and missing-field counts must be bounded")
        if any(not value or len(value) > 200 for value in (session.session_id, session.event_id)):
            raise ValueError("Session identities must be bounded nonempty identifiers")
        if any(field not in TRANSIENT_MISSING_FIELDS for field in session.missing_fields):
            raise ValueError("Session missing fields must use the transient code list")
        if bool(session.verified_fields) != (session.verification_status == "verified"):
            raise ValueError("Verification status must reflect explicit field checks")
        for check in session.verified_fields:
            actual = getattr(session, check.field)
            expected = actual.isoformat() if hasattr(actual, "isoformat") else actual
            if (
                check.session_id != session.session_id
                or check.source_url != session.source_url
                or check.checked_at < session.source_fetched_at
                or check.value != expected
            ):
                raise ValueError("Field checks must identify the same current session source")
