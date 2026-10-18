/** Contract v1.0.0. Response types include the Pydantic defaults applied by api.ts. */
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
export type EventSearchResponse = SearchResponse<EventCardData>
