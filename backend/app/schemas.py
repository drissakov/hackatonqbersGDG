"""Version 1 shared contracts. Export JSON Schema with scripts/export_contracts.py."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Minutes = Annotated[int, Field(gt=0, le=10080, strict=True)]
TravelMinutes = Annotated[int, Field(ge=0, le=10080, strict=True)]
Money = Annotated[int, Field(ge=0, strict=True)]
Locale = Literal["kk", "ru", "en"]


class ResponseStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    NO_MATCH = "no_match"


class RouteStatus(StrEnum):
    KNOWN = "known"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    NOT_REQUESTED = "not_requested"


class FitStatus(StrEnum):
    FITS = "fits"
    DOES_NOT_FIT = "does_not_fit"
    UNKNOWN = "unknown"


class ActivityCode(StrEnum):
    WALK = "walk"
    MUSEUM = "museum"
    FOOD = "food"
    CULTURE = "culture"
    SPORT = "sport"
    SHOPPING = "shopping"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class ReasonCode(StrEnum):
    QUERY_MATCH = "query_match"
    NEARBY = "nearby"
    WITHIN_TIME = "within_time"
    WITHIN_BUDGET = "within_budget"
    INDOOR_MATCH = "indoor_match"
    TIME_UNKNOWN = "time_unknown"
    BUDGET_UNKNOWN = "budget_unknown"
    HOURS_UNKNOWN = "hours_unknown"
    ROUTE_UNKNOWN = "route_unknown"
    VISIT_DURATION_ESTIMATE = "visit_duration_estimate"
    WEATHER_UNKNOWN = "weather_unknown"
    SCHEDULE_UNKNOWN = "schedule_unknown"


class WarningCode(StrEnum):
    MISSING_INPUT = "missing_input"
    DATA_UNKNOWN = "data_unknown"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    ROUTE_UNAVAILABLE = "route_unavailable"
    WEATHER_UNAVAILABLE = "weather_unavailable"
    SOURCE_STALE = "source_stale"
    TEST_DATA = "test_data"


class ExplicitField(StrEnum):
    ORIGIN = "origin"
    AVAILABLE_MINUTES = "available_minutes"
    RETURN_TO_START = "return_to_start"
    BUDGET = "budget_kzt_per_person"
    INDOOR_ONLY = "indoor_only"
    DATE_TIME = "date_time"


class MissingField(StrEnum):
    ORIGIN = "origin"
    AVAILABLE_MINUTES = "available_minutes"
    DATE_TIME = "date_time"
    LOCATION = "location"
    PRICE = "price_kzt_per_person"
    INDOOR = "indoor"
    OPENING_HOURS = "opening_hours"
    VISIT_MINUTES = "visit_minutes_estimate"
    TRAVEL_MINUTES = "travel_minutes_estimate"
    WEATHER = "weather"
    SESSION_TIME = "session_time"


class SourceProvider(StrEnum):
    OSM = "osm"
    MUNICIPAL = "municipal"
    ORGANIZER = "organizer"
    TWOGIS = "twogis"
    TEST_FIXTURE = "test_fixture"
    OTHER = "other"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Coordinates(ContractModel):
    latitude: Annotated[float, Field(ge=-90, le=90, strict=True)]
    longitude: Annotated[float, Field(ge=-180, le=180, strict=True)]


class RecommendationRequest(ContractModel):
    request_id: UUID = Field(default_factory=uuid4)
    query: Annotated[str, Field(min_length=1, max_length=2000)]
    locale: Locale = "kk"
    origin: Coordinates | None = None
    available_minutes: Annotated[int, Field(gt=0, le=1440, strict=True)] | None = None
    return_to_start: StrictBool = False
    budget_kzt_per_person: Money | None = None
    indoor_only: StrictBool = False
    date_time: AwareDatetime | None = None
    explicit_fields: list[ExplicitField] = Field(default_factory=list)

    @model_validator(mode="after")
    def explicit_fields_are_supplied(self) -> Self:
        if len(set(self.explicit_fields)) != len(self.explicit_fields):
            raise ValueError("explicit_fields must be unique")
        if any(field.value not in self.model_fields_set for field in self.explicit_fields):
            raise ValueError("Every explicit field must be present in the request")
        return self


class EventSearchRequest(RecommendationRequest):
    """Same constraints; date_time is the earliest session start when supplied."""


class Source(ContractModel):
    source_id: Identifier
    provider: SourceProvider
    url: HttpUrl
    retrieved_at: AwareDatetime
    license: Text | None = None
    rights_basis_url: HttpUrl | None = None
    storage_allowed: StrictBool = False
    indexing_allowed: StrictBool = False
    is_test: StrictBool = False

    @model_validator(mode="after")
    def rights_are_explicit(self) -> Self:
        if self.indexing_allowed and not self.storage_allowed:
            raise ValueError("Indexing requires storage permission")
        if (self.storage_allowed or self.indexing_allowed) and not (
            self.license and self.rights_basis_url
        ):
            raise ValueError("Storage and indexing require documented rights")
        if self.provider == SourceProvider.TEST_FIXTURE and not self.is_test:
            raise ValueError("Synthetic sources must be marked is_test")
        return self


class Provenance(ContractModel):
    source_id: Identifier
    external_id: Identifier
    fields: Annotated[list[Identifier], Field(min_length=1)]
    observed_at: AwareDatetime | None = None


def validate_source_references(sources: list[Source], provenance: list[Provenance]) -> None:
    ids = {source.source_id for source in sources}
    if len(ids) != len(sources):
        raise ValueError("Source IDs must be unique")
    if any(item.source_id not in ids for item in provenance):
        raise ValueError("Provenance must reference an included source")


class SourcedRecord(ContractModel):
    sources: Annotated[list[Source], Field(min_length=1)]
    provenance: Annotated[list[Provenance], Field(min_length=1)]
    is_test: StrictBool = False

    @model_validator(mode="after")
    def persistence_rights(self) -> Self:
        validate_source_references(self.sources, self.provenance)
        if any(not source.storage_allowed for source in self.sources):
            raise ValueError("Persistent records require storage permission for every source")
        if any(source.provider == SourceProvider.TWOGIS for source in self.sources):
            raise ValueError("2GIS persistence requires a separate reviewed rights decision")
        if any(source.is_test for source in self.sources) and not self.is_test:
            raise ValueError("Synthetic records must be marked is_test")
        return self


class POIRecord(SourcedRecord):
    id: Identifier
    primary_source_id: Identifier
    external_id: Identifier
    name: Text
    description: Text | None = None
    location: Coordinates | None = None
    address: Text | None = None
    activity_code: ActivityCode
    indoor: StrictBool | None = None
    price_kzt_per_person: Money | None = None
    visit_minutes_estimate: Minutes | None = None
    opening_hours_text: Text | None = None

    @model_validator(mode="after")
    def primary_source_exists(self) -> Self:
        if self.primary_source_id not in {source.source_id for source in self.sources}:
            raise ValueError("primary_source_id must reference an included source")
        return self


class EventRecord(SourcedRecord):
    id: Identifier
    title: Text
    description: Text | None = None
    activity_code: ActivityCode


class EventSession(SourcedRecord):
    id: Identifier
    event_id: Identifier
    poi_id: Identifier | None = None
    location: Coordinates | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None
    price_kzt_per_person: Money | None = None
    status: Literal["scheduled", "cancelled", "unknown"]
    booking_url: HttpUrl | None = None

    @model_validator(mode="after")
    def time_order(self) -> Self:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must follow starts_at")
        return self


class Action(ContractModel):
    code: Literal["open_source", "open_map"]
    url: HttpUrl


class CardDetails(ContractModel):
    provenance: Annotated[list[Provenance], Field(min_length=1)]
    reason_codes: Annotated[list[ReasonCode], Field(min_length=1)]
    activity_code: ActivityCode
    visit_minutes_estimate: Minutes | None
    route_status: RouteStatus
    travel_minutes_estimate: TravelMinutes | None
    fit_status: FitStatus
    missing_fields: list[MissingField]
    explanation: Text
    generated_locale: Locale
    action: Action

    @model_validator(mode="after")
    def honest_estimates(self) -> Self:
        has_route = self.route_status in (RouteStatus.KNOWN, RouteStatus.ESTIMATED)
        if has_route != (self.travel_minutes_estimate is not None):
            raise ValueError("Only known or estimated routes have travel durations")
        if self.fit_status == FitStatus.FITS and self.missing_fields:
            raise ValueError("A confirmed fit cannot have missing constraint data")
        if self.fit_status == FitStatus.UNKNOWN and not self.missing_fields:
            raise ValueError("Unknown fit must identify missing data")
        return self


class POICard(CardDetails):
    poi: POIRecord

    @model_validator(mode="after")
    def matching_activity(self) -> Self:
        if self.activity_code != self.poi.activity_code:
            raise ValueError("Card and POI activity codes must match")
        return self


class EventCard(CardDetails):
    event: EventRecord
    session: EventSession

    @model_validator(mode="after")
    def matching_event(self) -> Self:
        if self.session.event_id != self.event.id:
            raise ValueError("Session must belong to the event")
        if self.activity_code != self.event.activity_code:
            raise ValueError("Card and event activity codes must match")
        return self


class Warning(ContractModel):
    code: WarningCode
    message: Text
    fields: list[MissingField] = Field(default_factory=list)


class SearchResponse[T: CardDetails](ContractModel):
    status: ResponseStatus
    items: Annotated[list[T], Field(max_length=3)]
    warnings: list[Warning]
    sources: list[Source]
    request_id: UUID

    @model_validator(mode="after")
    def consistent_status(self) -> Self:
        has_items = self.status in (ResponseStatus.OK, ResponseStatus.PARTIAL)
        if has_items != bool(self.items):
            raise ValueError("Only ok and partial responses contain one to three items")
        if self.status == ResponseStatus.PARTIAL and not self.warnings:
            raise ValueError("Partial responses must explain their limitations")
        if self.status == ResponseStatus.OK and any(
            item.fit_status != FitStatus.FITS for item in self.items
        ):
            raise ValueError("Uncertain or failed fits require partial status")
        if any(item.fit_status == FitStatus.DOES_NOT_FIT for item in self.items):
            raise ValueError("Known hard-constraint violations cannot be alternatives")
        identities = [
            item.poi.id if isinstance(item, POICard) else item.session.id for item in self.items
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("Alternatives must be distinct")
        if any(
            isinstance(item, EventCard) and item.session.status == "cancelled"
            for item in self.items
        ):
            raise ValueError("Cancelled sessions cannot be alternatives")
        validate_source_references(self.sources, [p for i in self.items for p in i.provenance])
        envelope = {s.source_id: s for s in self.sources}
        for item in self.items:
            records = [item.poi] if isinstance(item, POICard) else [item.event, item.session]
            for record in records:
                if any(envelope.get(s.source_id) != s for s in record.sources):
                    raise ValueError("Envelope must include every record source unchanged")
        return self


class RecommendationResponse(SearchResponse[POICard]):
    pass


class EventSearchResponse(SearchResponse[EventCard]):
    pass


class RejectedPOI(ContractModel):
    index: Annotated[int, Field(ge=0, strict=True)]
    code: Literal["invalid_record", "duplicate_in_batch", "storage_not_permitted", "stale_record"]


class UpsertResult(ContractModel):
    inserted: Annotated[int, Field(ge=0, strict=True)]
    updated: Annotated[int, Field(ge=0, strict=True)]
    rejected: Annotated[int, Field(ge=0, strict=True)]
    rejections: list[RejectedPOI]

    @model_validator(mode="after")
    def rejected_count(self) -> Self:
        if self.rejected != len(self.rejections):
            raise ValueError("rejected must match the number of rejections")
        if len({row.index for row in self.rejections}) != self.rejected:
            raise ValueError("Rejection indexes must be unique")
        return self


class ImportRunCounts(ContractModel):
    total: Annotated[int, Field(ge=0)]
    failed: Annotated[int, Field(ge=0)]
    rejected_records: Annotated[int, Field(ge=0)]


class CoverageResponse(ContractModel):
    status: Literal["ok"] = "ok"
    production_pois: Annotated[int, Field(ge=0)]
    test_pois: Annotated[int, Field(ge=0)]
    located_pois: Annotated[int, Field(ge=0)]
    missing_location_pois: Annotated[int, Field(ge=0)]
    embedded_pois: Annotated[int, Field(ge=0)]
    by_source: dict[str, Annotated[int, Field(ge=0)]]
    import_runs: ImportRunCounts
    city_coverage: Literal["unknown"] = "unknown"
    is_production_dataset: bool


class RouteRequest(ContractModel):
    request_id: UUID = Field(default_factory=uuid4)
    origin: Coordinates | None = None
    destination: Coordinates
    return_to_start: StrictBool = False
    locale: Locale = "kk"


RouteFailureReason = Literal[
    "invalid_settings",
    "disabled",
    "key_missing",
    "rights_unconfirmed",
    "access_denied",
    "timeout",
    "rate_limited",
    "http_error",
    "network_error",
    "provider_fail",
    "route_not_found",
    "invalid_response",
    "missing_origin",
    "not_requested",
]


class RouteProvenance(ContractModel):
    provider: Literal["twogis"] = "twogis"
    endpoint: Literal["https://routing.api.2gis.com/routing/7.0.0/global"] = (
        "https://routing.api.2gis.com/routing/7.0.0/global"
    )
    retrieved_at: AwareDatetime
    transport: Literal["walking"] = "walking"
    provider_locale: Literal["ru", "en"]
    storage_allowed: Literal[False] = False
    indexing_allowed: Literal[False] = False
    ai_allowed: Literal[False] = False


class RouteLeg(ContractModel):
    status: Literal["known", "unknown", "unavailable", "not_requested"]
    distance_meters: Annotated[int, Field(ge=0, strict=True)] | None = None
    duration_seconds: Annotated[int, Field(ge=0, strict=True)] | None = None
    provenance: RouteProvenance | None = None
    reason: RouteFailureReason | None = None

    @model_validator(mode="after")
    def metrics_require_success(self) -> Self:
        metrics = (self.distance_meters, self.duration_seconds, self.provenance)
        if self.status == "known":
            if any(value is None for value in metrics) or self.reason is not None:
                raise ValueError("Known routes require metrics/provenance and no failure reason")
        elif any(value is not None for value in metrics) or self.reason is None:
            raise ValueError("Unsuccessful routes require a reason and cannot contain metrics")
        if (self.status == "not_requested") != (self.reason == "not_requested"):
            raise ValueError("not_requested status and reason must agree")
        return self


class RouteResponse(ContractModel):
    request_id: UUID
    status: Literal["known", "unknown", "unavailable"] = "unavailable"
    travel_minutes_estimate: Annotated[int, Field(ge=0, strict=True)] | None = None
    outbound: RouteLeg = Field(
        default_factory=lambda: RouteLeg(status="unavailable", reason="disabled")
    )
    return_route: RouteLeg = Field(
        default_factory=lambda: RouteLeg(status="not_requested", reason="not_requested")
    )
    destination_precision: Literal["approximate"] = "approximate"
    warnings: list[Warning]

    @model_validator(mode="after")
    def total_requires_all_requested_legs(self) -> Self:
        legs = [self.outbound]
        if self.outbound.status == "not_requested":
            raise ValueError("Outbound route must be requested")
        if self.return_route.status != "not_requested":
            legs.append(self.return_route)
        if all(leg.status == "known" for leg in legs):
            expected_status = "known"
            expected_minutes = (sum(leg.duration_seconds for leg in legs) + 59) // 60
        else:
            expected_status = (
                "unavailable" if any(leg.status == "unavailable" for leg in legs) else "unknown"
            )
            expected_minutes = None
        if self.status != expected_status or self.travel_minutes_estimate != expected_minutes:
            raise ValueError("Route status and total must reflect all requested legs")
        return self
