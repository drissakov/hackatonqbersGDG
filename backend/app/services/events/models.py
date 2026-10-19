"""D03 runtime DTOs, not persistent EventRecord/EventSession or the shared wire API."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, HttpUrl

from backend.app.schemas import ContractModel, Money, ResponseStatus, Text
from backend.app.services.events.venue import VenueMatch


class EvidenceSource(ContractModel):
    url: HttpUrl
    # Caller-supplied observation anchor, not a guaranteed origin fetch/modification time.
    fetched_at: AwareDatetime
    storage_allowed: Literal[False] = False
    indexing_allowed: Literal[False] = False


class Citation(ContractModel):
    url: HttpUrl
    title: str
    start_index: Annotated[int, Field(ge=0, strict=True)]
    end_index: Annotated[int, Field(ge=0, strict=True)]
    text: str
    # Bounded cited Responses text, not a quotation fetched from the original page.
    context: str = ""


class SearchEvidence(ContractModel):
    text: Annotated[str, Field(max_length=40000)]
    sources: Annotated[list[EvidenceSource], Field(max_length=100)]
    citations: Annotated[list[Citation], Field(max_length=100)]


class SessionFacts(ContractModel):
    source_url: HttpUrl | None = None
    date_text: Annotated[str, Field(max_length=150)] | None = None
    date_basis: Literal["session", "publication", "index", "unknown"] = "unknown"
    starts_at: str | None = None
    ends_at: str | None = None
    end_text: Annotated[str, Field(max_length=150)] | None = None
    price_from: Money | None = None
    currency: Literal["KZT"] | None = None
    price_conditions: Annotated[str, Field(max_length=300)] | None = None
    price_kind: Literal["starting", "regular", "promotion", "unknown"] = "unknown"
    status: Literal["scheduled", "cancelled", "unknown"] = "unknown"


class CandidateEvent(ContractModel):
    title: Text
    source_url: HttpUrl
    page_kind: Literal["listing", "event", "session"]
    city: Annotated[str, Field(max_length=150)] | None = None
    venue_name: Annotated[str, Field(max_length=300)] | None = None
    venue_address: Annotated[str, Field(max_length=300)] | None = None
    sessions: Annotated[list[SessionFacts], Field(max_length=20)] = Field(default_factory=list)


class CandidateBatch(ContractModel):
    events: Annotated[list[CandidateEvent], Field(max_length=10)]


CheckedField = Literal[
    "city",
    "venue_name",
    "venue_address",
    "starts_at",
    "ends_at",
    "price_from",
    "currency",
    "price_conditions",
    "status",
]


class FieldCheck(ContractModel):
    """Trusted caller's source check, never accepted from model extraction JSON."""

    session_id: Annotated[str, Field(min_length=1, max_length=200)]
    field: CheckedField
    value: str | Annotated[int, Field(strict=True)]
    source_url: HttpUrl
    checked_at: AwareDatetime
    method: Literal["manual_source", "licensed_feed"]


class NormalizedSession(ContractModel):
    session_id: str
    event_id: str
    source_url: HttpUrl
    source_fetched_at: AwareDatetime
    city: str | None
    venue_name: str | None
    venue_address: str | None
    venue: VenueMatch
    starts_at: AwareDatetime | None
    ends_at: AwareDatetime | None
    price_from: Money | None
    currency: Literal["KZT"] | None
    price_conditions: str | None
    price_kind: Literal["starting", "regular", "promotion", "unknown"]
    status: Literal["scheduled", "cancelled", "unknown"]
    verification_status: Literal["discovered", "verified"] = "discovered"
    verified_fields: list[FieldCheck] = Field(default_factory=list)
    ticket_availability: Literal["unknown"] = "unknown"
    missing_fields: list[str]
    recommendation_candidate: bool
    exclusion_reasons: list[str]


class NormalizedEvent(ContractModel):
    event_id: str
    title: Text
    source_url: HttpUrl
    source_fetched_at: AwareDatetime
    city: str | None
    venue_name: str | None
    venue_address: str | None
    venue: VenueMatch
    status: Literal["listing", "discovered"]
    schedule_hints: list[str]
    missing_fields: list[str]
    sessions: list[NormalizedSession]


class DiscoveryResult(ContractModel):
    provider_status: ResponseStatus
    provider_code: str | None = None
    live_web_search: Literal["not_run", "passed", "failed"]
    evidence: SearchEvidence | None = None
    events: list[NormalizedEvent] = Field(default_factory=list)
    excluded_sessions: int = 0
    rejected_events: int = 0
