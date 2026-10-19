/** Shared wire contract. Response types include defaults applied by api.ts. */
export type Locale = 'kk' | 'ru' | 'en'
export type ResponseStatus =
  'ok' | 'partial' | 'unknown' | 'unavailable' | 'no_match'
export type RouteStatus =
  'known' | 'estimated' | 'unknown' | 'unavailable' | 'not_requested'
export type FitStatus = 'fits' | 'does_not_fit' | 'unknown'
export type ActivityCode =
  | 'walk'
  | 'museum'
  | 'food'
  | 'culture'
  | 'sport'
  | 'shopping'
  | 'entertainment'
  | 'other'
export type ReasonCode =
  | 'query_match'
  | 'nearby'
  | 'within_time'
  | 'within_budget'
  | 'indoor_match'
  | 'time_unknown'
  | 'budget_unknown'
  | 'hours_unknown'
  | 'route_unknown'
  | 'visit_duration_estimate'
  | 'weather_unknown'
  | 'schedule_unknown'
export type WarningCode =
  | 'missing_input'
  | 'data_unknown'
  | 'provider_unavailable'
  | 'route_unavailable'
  | 'weather_unavailable'
  | 'source_stale'
  | 'test_data'
export type ConstraintField =
  | 'origin'
  | 'available_minutes'
  | 'return_to_start'
  | 'budget_kzt_per_person'
  | 'indoor_only'
  | 'date_time'
export type MissingField =
  | 'origin'
  | 'available_minutes'
  | 'date_time'
  | 'location'
  | 'price_kzt_per_person'
  | 'indoor'
  | 'opening_hours'
  | 'visit_minutes_estimate'
  | 'travel_minutes_estimate'
  | 'weather'
  | 'session_time'
export type SourceProvider =
  'osm' | 'municipal' | 'organizer' | 'twogis' | 'test_fixture' | 'other'

export interface Coordinates {
  latitude: number
  longitude: number
}

export interface SearchRequest {
  request_id?: string
  query: string
  locale?: Locale
  origin?: Coordinates | null
  available_minutes?: number | null
  return_to_start?: boolean
  budget_kzt_per_person?: number | null
  indoor_only?: boolean
  date_time?: string | null
  explicit_fields?: ConstraintField[]
}

export interface RouteRequest {
  request_id?: string
  origin?: Coordinates | null
  destination: Coordinates
  return_to_start?: boolean
  locale?: Locale
}

export type RouteFailureReason =
  | 'invalid_settings'
  | 'disabled'
  | 'key_missing'
  | 'rights_unconfirmed'
  | 'access_denied'
  | 'timeout'
  | 'rate_limited'
  | 'http_error'
  | 'network_error'
  | 'provider_fail'
  | 'route_not_found'
  | 'invalid_response'
  | 'missing_origin'
  | 'not_requested'

export interface RouteProvenance {
  provider: 'twogis'
  endpoint: 'https://routing.api.2gis.com/routing/7.0.0/global'
  retrieved_at: string
  transport: 'walking'
  provider_locale: 'ru' | 'en'
  storage_allowed: false
  indexing_allowed: false
  ai_allowed: false
}

export interface RouteLeg {
  status: 'known' | 'unknown' | 'unavailable' | 'not_requested'
  distance_meters: number | null
  duration_seconds: number | null
  provenance: RouteProvenance | null
  reason: RouteFailureReason | null
}

export interface RouteResponse {
  request_id: string
  status: 'known' | 'unknown' | 'unavailable'
  travel_minutes_estimate: number | null
  outbound: RouteLeg
  return_route: RouteLeg
  destination_precision: 'approximate'
  warnings: SearchWarning[]
}

export interface Source {
  source_id: string
  provider: SourceProvider
  url: string
  retrieved_at: string
  license: string | null
  rights_basis_url: string | null
  storage_allowed: boolean
  indexing_allowed: boolean
  is_test: boolean
}

export interface Provenance {
  source_id: string
  external_id: string
  fields: string[]
  observed_at: string | null
}

export interface SourcedRecord {
  sources: Source[]
  provenance: Provenance[]
  is_test: boolean
}

export interface POIRecord extends SourcedRecord {
  id: string
  primary_source_id: string
  external_id: string
  name: string
  description: string | null
  location: Coordinates | null
  address: string | null
  activity_code: ActivityCode
  indoor: boolean | null
  price_kzt_per_person: number | null
  visit_minutes_estimate: number | null
  opening_hours_text: string | null
}

export interface EventRecord extends SourcedRecord {
  id: string
  title: string
  description: string | null
  activity_code: ActivityCode
}

export interface EventSession extends SourcedRecord {
  id: string
  event_id: string
  poi_id: string | null
  location: Coordinates | null
  starts_at: string
  ends_at: string | null
  price_kzt_per_person: number | null
  status: 'scheduled' | 'cancelled' | 'unknown'
  booking_url: string | null
}

export interface Action {
  code: 'open_source' | 'open_map'
  url: string
}

export interface CardDetails {
  provenance: Provenance[]
  reason_codes: ReasonCode[]
  activity_code: ActivityCode
  visit_minutes_estimate: number | null
  route_status: RouteStatus
  travel_minutes_estimate: number | null
  fit_status: FitStatus
  missing_fields: MissingField[]
  explanation: string
  generated_locale: Locale
  action: Action
}

export interface RecommendationCard extends CardDetails {
  poi: POIRecord
}
export interface EventCardData extends CardDetails {
  event: EventRecord
  session: EventSession
}
export interface SearchWarning {
  code: WarningCode
  message: string
  fields: MissingField[]
}
export interface SearchResponse<T extends CardDetails> {
  status: ResponseStatus
  items: T[]
  warnings: SearchWarning[]
  sources: Source[]
  request_id: string
}
export type RecommendationResponse = SearchResponse<RecommendationCard>
export interface LegacyEventSearchResponse extends SearchResponse<EventCardData> {
  discovery?: EventDiscovery | null
}

/** UI envelope: the transient wire response stays separate from persistent records. */
export interface EventSearchResponse extends LegacyEventSearchResponse {
  transient?: TransientEventSearchResponse
}

export interface TransientEventSource {
  source_id: string
  url: string
  retrieved_at: string
  source_updated_at: string | null
  storage_allowed: false
  indexing_allowed: false
}

export interface TransientEvent {
  id: string
  title: string
  city: string | null
  venue_name: string | null
  venue_address: string | null
  source_id: string
}

export interface TransientEventCardData {
  event: TransientEvent
  session: DiscoveredSession
  source_ids: string[]
  reason_codes: ReasonCode[]
  activity_code: ActivityCode
  visit_minutes_estimate: number | null
  route_status: RouteStatus
  travel_minutes_estimate: number | null
  fit_status: FitStatus
  missing_fields: string[]
  explanation: string
  generated_locale: Locale
  action: Action
}

export interface TransientEventSearchResponse {
  request_id: string
  contract_version: '1.3.0'
  status: ResponseStatus
  provider_status: 'partial' | 'unknown' | 'unavailable'
  provider_code: string | null
  live_web_search: 'not_run' | 'passed' | 'failed'
  items: TransientEventCardData[]
  listings: DiscoveredEvent[]
  sources: TransientEventSource[]
  warnings: SearchWarning[]
  excluded_sessions: number
  rejected_events: number
}

/** Ephemeral discovery facts; these are not persistent EventRecord sources. */
export interface EventEvidenceSource {
  url: string
  fetched_at: string
  storage_allowed: false
  indexing_allowed: false
}

export interface EventCitation {
  url: string
  title: string
  start_index: number
  end_index: number
  text: string
  context: string
}

export interface EventEvidence {
  text: string
  sources: EventEvidenceSource[]
  citations: EventCitation[]
}

export interface EventVenue {
  poi_id: string | null
  location: Coordinates | null
  basis: 'name_address_astana_permitted_poi' | 'unknown' | 'ambiguous'
  source_ids: string[]
  source_urls: string[]
  coordinate_accuracy: 'unknown'
  geography_basis: 'central_astana_bbox' | 'unknown'
}

export interface EventFieldCheck {
  session_id: string
  field:
    | 'city'
    | 'venue_name'
    | 'venue_address'
    | 'starts_at'
    | 'ends_at'
    | 'price_from'
    | 'currency'
    | 'price_conditions'
    | 'status'
  value: string | number
  source_url: string
  checked_at: string
  method: 'manual_source' | 'licensed_feed'
}

export interface DiscoveredSession {
  session_id: string
  event_id: string
  source_url: string
  source_fetched_at: string
  city: string | null
  venue_name: string | null
  venue_address: string | null
  venue: EventVenue
  starts_at: string | null
  ends_at: string | null
  price_from: number | null
  currency: 'KZT' | null
  price_conditions: string | null
  price_kind: 'starting' | 'regular' | 'promotion' | 'unknown'
  status: 'scheduled' | 'cancelled' | 'unknown'
  verification_status: 'discovered' | 'verified'
  verified_fields: EventFieldCheck[]
  ticket_availability: 'unknown'
  missing_fields: string[]
  recommendation_candidate: boolean
  exclusion_reasons: string[]
}

export interface DiscoveredEvent {
  event_id: string
  title: string
  source_url: string
  source_fetched_at: string
  city: string | null
  venue_name: string | null
  venue_address: string | null
  venue: EventVenue
  status: 'listing' | 'discovered'
  schedule_hints: string[]
  missing_fields: string[]
  sessions: DiscoveredSession[]
}

export interface EventDiscovery {
  provider_status: ResponseStatus
  provider_code: string | null
  live_web_search: 'not_run' | 'passed' | 'failed'
  evidence: EventEvidence | null
  events: DiscoveredEvent[]
  excluded_sessions: number
  rejected_events: number
}
