import requestSchema from '../../../contracts/recommendation-request.schema.json'
import recommendationSchema from '../../../contracts/recommendation-response.schema.json'
import routeRequestSchema from '../../../contracts/route-request.schema.json'
import routeResponseSchema from '../../../contracts/route-response.schema.json'
import transientEventSchema from '../../../contracts/transient-event-search-response.schema.json'
// Compatibility validation for older envelopes and development fixtures only.
import eventSchema from './event-search-response.schema.json'
import type {
  CardDetails,
  DiscoveredSession,
  EventCardData,
  EventDiscovery,
  EventSearchResponse,
  EventVenue,
  Locale,
  RecommendationCard,
  RecommendationResponse,
  RouteRequest,
  RouteResponse,
  SearchRequest,
  SearchResponse,
  SearchWarning,
  Source,
  SourcedRecord,
  TransientEventSearchResponse,
} from './types'

export type ApiErrorCode =
  | 'invalid_configuration'
  | 'invalid_request'
  | 'network'
  | 'timeout'
  | 'aborted'
  | 'not_ready'
  | 'server_error'
  | 'invalid_response'
  | 'locale_mismatch'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status?: number

  constructor(code: ApiErrorCode, status?: number) {
    // Only stable local codes reach the UI; never expose provider/server bodies.
    super(code)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

type Schema = {
  $ref?: string
  $defs?: Record<string, Schema>
  type?: string
  anyOf?: Schema[]
  enum?: unknown[]
  const?: unknown
  properties?: Record<string, Schema>
  required?: string[]
  additionalProperties?: boolean
  items?: Schema
  minItems?: number
  maxItems?: number
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  format?: string
  default?: unknown
  pattern?: string
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const awareDateTime =
  /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-](\d{2}):?(\d{2}))$/i

function validDateTime(value: string): boolean {
  const match = awareDateTime.exec(value)
  if (!match) return false
  const [
    ,
    yearText,
    monthText,
    dayText,
    hourText,
    minuteText,
    secondText = '0',
    offsetHour = '0',
    offsetMinute = '0',
  ] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return (
    year > 0 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= days[month - 1] &&
    Number(hourText) < 24 &&
    Number(minuteText) < 60 &&
    Number(secondText) < 60 &&
    Number(offsetHour) < 24 &&
    Number(offsetMinute) < 60 &&
    Number.isFinite(Date.parse(value))
  )
}

/** Pydantic wire timestamps retain microseconds that Date.parse discards. */
function dateTimeMicros(value: string): bigint | null {
  if (!validDateTime(value)) return null
  const fraction = /\.(\d+)/u.exec(value)?.[1] ?? ''
  return (
    BigInt(Date.parse(value.replace(/\.\d+/u, ''))) * 1000n +
    BigInt(fraction.padEnd(6, '0').slice(0, 6))
  )
}

function dateTimeFollows(value: string, previous: string): boolean {
  const instant = dateTimeMicros(value)
  const earlier = dateTimeMicros(previous)
  return instant !== null && earlier !== null && instant > earlier
}

function httpUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return (
      (url.protocol === 'https:' || url.protocol === 'http:') &&
      Boolean(url.hostname)
    )
  } catch {
    return false
  }
}

/** Validates the JSON Schema keywords used by the checked-in v1 wire schemas.
 * Defaults are copied only into responses; user requests are sent unchanged.
 */
function conforms(
  value: unknown,
  schema: Schema,
  root: Schema,
  defaults: boolean,
): boolean {
  if (schema.$ref) {
    const name = schema.$ref.replace('#/$defs/', '')
    const target = root.$defs?.[name]
    return Boolean(target && conforms(value, target, root, defaults))
  }
  if (
    schema.anyOf &&
    !schema.anyOf.some((part) => conforms(value, part, root, defaults))
  )
    return false
  if (schema.enum && !schema.enum.includes(value)) return false
  if ('const' in schema && schema.const !== value) return false
  if (schema.type === 'null') return value === null
  if (schema.type === 'boolean') return typeof value === 'boolean'
  if (schema.type === 'string') {
    if (typeof value !== 'string') return false
    // ContractModel strips surrounding text whitespace before length checks.
    // Keep the user's wire body unchanged; the server owns normalization.
    const length = Array.from(schema.format ? value : value.trim()).length
    if (
      length < (schema.minLength ?? 0) ||
      length > (schema.maxLength ?? Infinity)
    )
      return false
    if (schema.format === 'uri' && !httpUrl(value)) return false
    if (schema.format === 'uuid' && !uuid.test(value)) return false
    if (schema.format === 'date-time' && !validDateTime(value)) return false
    if (schema.pattern && !new RegExp(schema.pattern, 'u').test(value))
      return false
  }
  if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value)) return false
    if (schema.type === 'integer' && !Number.isSafeInteger(value)) return false
    if (
      value < (schema.minimum ?? -Infinity) ||
      value > (schema.maximum ?? Infinity)
    )
      return false
    if (
      schema.exclusiveMinimum !== undefined &&
      value <= schema.exclusiveMinimum
    )
      return false
  }
  if (schema.type === 'array') {
    if (
      !Array.isArray(value) ||
      value.length < (schema.minItems ?? 0) ||
      value.length > (schema.maxItems ?? Infinity)
    )
      return false
    if (
      schema.items &&
      !value.every((item) => conforms(item, schema.items!, root, defaults))
    )
      return false
  }
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value))
      return false
    const object = value as Record<string, unknown>
    if (schema.required?.some((key) => !Object.hasOwn(object, key)))
      return false
    if (
      schema.additionalProperties === false &&
      Object.keys(object).some(
        (key) => !Object.hasOwn(schema.properties ?? {}, key),
      )
    )
      return false
    for (const [key, property] of Object.entries(schema.properties ?? {})) {
      if (Object.hasOwn(object, key)) {
        if (!conforms(object[key], property, root, defaults)) return false
      } else if (defaults && 'default' in property) {
        object[key] = structuredClone(property.default)
      }
    }
  }
  return true
}

function sourceIsValid(source: Source): boolean {
  return (
    !(source.indexing_allowed && !source.storage_allowed) &&
    (!(source.storage_allowed || source.indexing_allowed) ||
      Boolean(source.license && source.rights_basis_url)) &&
    (source.provider !== 'test_fixture' || source.is_test)
  )
}

function uniqueSources(sources: Source[]): boolean {
  return (
    new Set(sources.map((source) => source.source_id)).size === sources.length
  )
}

function sourcedRecordIsValid(
  record: SourcedRecord,
  envelope: Map<string, Source>,
): boolean {
  const ids = new Set(record.sources.map((source) => source.source_id))
  return (
    uniqueSources(record.sources) &&
    record.provenance.every((item) => ids.has(item.source_id)) &&
    record.sources.every((source) => {
      const included = envelope.get(source.source_id)
      return (
        sourceIsValid(source) &&
        source.storage_allowed &&
        source.provider !== 'twogis' &&
        Boolean(
          included &&
          Object.entries(source).every(
            ([key, value]) => included[key as keyof Source] === value,
          ),
        )
      )
    }) &&
    (!record.sources.some((source) => source.is_test) || record.is_test)
  )
}

function cardIsValid(card: CardDetails, locale: Locale): boolean {
  const hasRoute =
    card.route_status === 'known' || card.route_status === 'estimated'
  return (
    card.generated_locale === locale &&
    hasRoute === (card.travel_minutes_estimate !== null) &&
    card.fit_status !== 'does_not_fit' &&
    (card.fit_status !== 'fits' || card.missing_fields.length === 0) &&
    (card.fit_status !== 'unknown' || card.missing_fields.length > 0)
  )
}

function featureEvidenceIsValid(card: RecommendationCard): boolean {
  const facts = card.feature_evidence ?? []
  if (new Set(facts.map((fact) => fact.field)).size !== facts.length)
    return false
  const mappings: Record<string, Record<string, boolean>> = {
    'family_playground:leisure': { playground: true },
    'public_access:access': {
      yes: true,
      public: true,
      no: false,
      private: false,
    },
    'power_outlets:service:electricity': {
      yes: true,
      limited: true,
      no: false,
    },
    'power_outlets:power_supply': { yes: true, no: false },
  }
  if (
    !facts.every((fact) => {
      const source = card.poi.sources.find(
        (entry) => entry.source_id === fact.source_id,
      )
      const checked = dateTimeMicros(fact.checked_at)
      const updated = dateTimeMicros(fact.source_updated_at)
      const retrieved = source ? dateTimeMicros(source.retrieved_at) : null
      const mapping = mappings[`${fact.field}:${fact.source_field}`]
      return (
        source !== undefined &&
        (source.provider === 'osm' || source.provider === 'test_fixture') &&
        publicSourceUrl(source.url) &&
        source.storage_allowed &&
        source.indexing_allowed &&
        fact.observed_at === null &&
        checked !== null &&
        updated !== null &&
        retrieved !== null &&
        updated <= checked &&
        checked <= retrieved &&
        mapping !== undefined &&
        Object.hasOwn(mapping, fact.source_value) &&
        mapping[fact.source_value] === fact.value
      )
    })
  )
    return false
  return (
    (!card.reason_codes.includes('family_playground_match') ||
      facts.some((fact) => fact.field === 'family_playground' && fact.value)) &&
    (!card.reason_codes.includes('power_outlets_match') ||
      facts.some((fact) => fact.field === 'power_outlets' && fact.value))
  )
}

function normalizeDiscoveryFactories(discovery: EventDiscovery): void {
  discovery.events ??= []
  for (const event of discovery.events) {
    for (const venue of [
      event.venue,
      ...event.sessions.map((session) => session.venue),
    ]) {
      venue.source_ids ??= []
      venue.source_urls ??= []
    }
    for (const session of event.sessions) session.verified_fields ??= []
  }
}

/** Called only after schema validation so explicit null or malformed lists fail. */
function normalizeWarningFactories(warnings: SearchWarning[]): void {
  for (const warning of warnings) {
    warning.fields ??= []
    warning.clarifications ??= []
  }
}

function venueIsValid(venue: EventVenue): boolean {
  if (venue.basis !== 'name_address_astana_permitted_poi')
    return venue.poi_id === null && venue.location === null
  return Boolean(
    venue.poi_id &&
    venue.location &&
    venue.source_ids.length &&
    venue.source_urls.length &&
    venue.geography_basis === 'central_astana_bbox',
  )
}

function fieldChecksAreValid(session: DiscoveredSession): boolean {
  return session.verified_fields.every((check) => {
    const actual = session[check.field]
    const checked = dateTimeMicros(check.checked_at)
    const observed = dateTimeMicros(session.source_fetched_at)
    const sameValue =
      check.field === 'starts_at' || check.field === 'ends_at'
        ? typeof check.value === 'string' &&
          typeof actual === 'string' &&
          validDateTime(check.value) &&
          dateTimeMicros(actual) === dateTimeMicros(check.value)
        : actual === check.value
    return (
      actual !== null &&
      sameValue &&
      check.session_id === session.session_id &&
      check.source_url === session.source_url &&
      checked !== null &&
      observed !== null &&
      checked >= observed
    )
  })
}

function discoveryIsValid(discovery: EventDiscovery): boolean {
  const evidence = discovery.evidence
  if (discovery.events.length > 0 && discovery.provider_status !== 'partial')
    return false
  if (discovery.events.length > 0 && !evidence) return false
  if (
    discovery.live_web_search === 'passed' &&
    (!evidence || !evidence.sources.length || !evidence.citations.length)
  )
    return false
  if (!evidence) return discovery.events.length === 0
  const responseText = Array.from(evidence.text)
  const urls = new Set(evidence.sources.map((source) => source.url))
  const eventIds = discovery.events.map((event) => event.event_id)
  const sessionIds = discovery.events.flatMap((event) =>
    event.sessions.map((session) => session.session_id),
  )
  return (
    urls.size === evidence.sources.length &&
    new Set(eventIds).size === eventIds.length &&
    new Set(sessionIds).size === sessionIds.length &&
    evidence.sources.every(
      (source) => !source.storage_allowed && !source.indexing_allowed,
    ) &&
    evidence.citations.every(
      (citation) =>
        urls.has(citation.url) &&
        citation.end_index > citation.start_index &&
        citation.end_index <= responseText.length &&
        responseText
          .slice(citation.start_index, citation.end_index)
          .join('') === citation.text,
    ) &&
    discovery.events.every(
      (event) =>
        urls.has(event.source_url) &&
        venueIsValid(event.venue) &&
        event.sessions.every(
          (session) =>
            session.event_id === event.event_id &&
            urls.has(session.source_url) &&
            venueIsValid(session.venue) &&
            session.ticket_availability === 'unknown' &&
            (!session.recommendation_candidate ||
              (session.status === 'scheduled' &&
                session.starts_at !== null &&
                session.exclusion_reasons.length === 0)) &&
            (session.ends_at === null ||
              (session.starts_at !== null &&
                Date.parse(session.ends_at) > Date.parse(session.starts_at))) &&
            (session.verification_status === 'verified') ===
              Boolean(session.verified_fields.length) &&
            fieldChecksAreValid(session),
        ),
    )
  )
}

const transientMissingFields = new Set([
  'city',
  'venue_name',
  'venue_address',
  'starts_at',
  'ends_at',
  'status',
  'sessions',
  'origin',
  'date_time',
  'available_minutes',
  'location',
  'travel_minutes_estimate',
  'return_travel_minutes_estimate',
  'price_kzt_per_person',
  'price_from',
  'currency',
  'price_conditions',
  'indoor',
  'source_verification',
  'ticket_availability',
])
const astanaNames = new Set([
  'astana',
  'astana city',
  'астана',
  'астане',
  'в астане',
  'astana qalasy',
  'астана қаласы',
  'астана қ.',
  'г. астана',
  'астанада',
  'астана қаласында',
])
function isAstana(value: string): boolean {
  return astanaNames.has(
    value.normalize('NFC').toLocaleLowerCase().replace(/\s+/gu, ' ').trim(),
  )
}
function publicSourceUrl(value: string): boolean {
  const url = new URL(value)
  return !url.username && !url.password
}

/** Validate S04's actual transient wire DTO before adapting it to the existing UI. */
function parseTransientEvents(
  value: unknown,
  locale: Locale,
): EventSearchResponse {
  const copy: unknown = structuredClone(value)
  if (!conforms(copy, transientEventSchema, transientEventSchema, true))
    throw new ApiError('invalid_response')
  const result = copy as TransientEventSearchResponse
  normalizeWarningFactories(result.warnings)
  const sources = new Map(
    result.sources.map((source) => [source.source_id, source]),
  )
  const urls = new Set(result.sources.map((source) => source.url))
  const hasData = Boolean(result.items.length || result.listings.length)
  const boundedId = (id: string) =>
    id.trim().length > 0 && Array.from(id).length <= 200
  const validMissing = (fields: string[]) =>
    fields.length <= 32 &&
    fields.every((field) => transientMissingFields.has(field))
  const sessionIsValid = (session: DiscoveredSession) => {
    session.verified_fields ??= []
    session.venue.source_ids ??= []
    session.venue.source_urls ??= []
    return (
      boundedId(session.session_id) &&
      boundedId(session.event_id) &&
      venueIsValid(session.venue) &&
      urls.has(session.source_url) &&
      session.venue.source_urls.every((url) => urls.has(url)) &&
      session.verified_fields.length <= 32 &&
      validMissing(session.missing_fields) &&
      (session.verification_status === 'verified') ===
        Boolean(session.verified_fields.length) &&
      fieldChecksAreValid(session) &&
      session.ticket_availability === 'unknown'
    )
  }
  if (result.items.some((card) => card.generated_locale !== locale))
    throw new ApiError('locale_mismatch')
  const valid =
    result.status !== 'no_match' &&
    result.status !== 'ok' &&
    (result.status === 'partial') === hasData &&
    (result.status !== 'partial' || result.warnings.length > 0) &&
    (result.provider_status !== 'unavailable' ||
      result.status === 'unavailable') &&
    (!hasData || result.live_web_search === 'passed') &&
    sources.size === result.sources.length &&
    result.sources.every(
      (source) =>
        publicSourceUrl(source.url) &&
        !source.storage_allowed &&
        !source.indexing_allowed,
    ) &&
    new Set(result.items.map((card) => card.session.session_id)).size ===
      result.items.length &&
    new Set(result.listings.map((event) => event.event_id)).size ===
      result.listings.length &&
    result.items.every((card) => {
      const session = card.session
      const knownRoute =
        card.route_status === 'known' || card.route_status === 'estimated'
      const checked = new Set(
        session.verified_fields?.map((check) => check.field) ?? [],
      )
      const requiredMissing = [
        'ticket_availability',
        ...(!knownRoute ? ['travel_minutes_estimate'] : []),
        ...(session.ends_at === null ? ['ends_at'] : []),
        ...([
          'city',
          'venue_name',
          'venue_address',
          'starts_at',
          'ends_at',
          'status',
        ].every((field) =>
          checked.has(
            field as (typeof session.verified_fields)[number]['field'],
          ),
        )
          ? []
          : ['source_verification']),
      ]
      const citedUrls = new Set(
        card.source_ids.map((id) => sources.get(id)?.url),
      )
      return (
        sessionIsValid(session) &&
        session.event_id === card.event.id &&
        session.status === 'scheduled' &&
        (session.ends_at === null ||
          (session.starts_at !== null &&
            dateTimeFollows(session.ends_at, session.starts_at))) &&
        session.starts_at !== null &&
        session.city !== null &&
        isAstana(session.city) &&
        (card.event.city === null || isAstana(card.event.city)) &&
        session.recommendation_candidate &&
        session.exclusion_reasons.length === 0 &&
        card.fit_status === 'unknown' &&
        knownRoute === (card.travel_minutes_estimate !== null) &&
        new Set(card.source_ids).size === card.source_ids.length &&
        card.source_ids.every((id) => sources.has(id)) &&
        card.source_ids.includes(card.event.source_id) &&
        citedUrls.has(session.source_url) &&
        citedUrls.has(card.action.url) &&
        new Set(card.missing_fields).size === card.missing_fields.length &&
        validMissing(card.missing_fields) &&
        requiredMissing.every((field) => card.missing_fields.includes(field)) &&
        !card.reason_codes.includes('within_budget') &&
        !card.reason_codes.includes('indoor_match') &&
        (card.visit_minutes_estimate === null ||
          card.reason_codes.includes('visit_duration_estimate'))
      )
    }) &&
    result.listings.every((event) => {
      event.venue.source_ids ??= []
      event.venue.source_urls ??= []
      return (
        boundedId(event.event_id) &&
        urls.has(event.source_url) &&
        (event.city === null || isAstana(event.city)) &&
        venueIsValid(event.venue) &&
        event.venue.source_urls.every((url) => urls.has(url)) &&
        event.sessions.length <= 20 &&
        event.schedule_hints.length <= 32 &&
        validMissing(event.missing_fields) &&
        event.sessions.every(
          (session) =>
            session.event_id === event.event_id && sessionIsValid(session),
        )
      )
    })
  if (!valid) throw new ApiError('invalid_response')
  return {
    request_id: result.request_id,
    status: result.status,
    items: [],
    sources: [],
    warnings: result.warnings,
    transient: result,
  }
}

export function parseSearchResponse(
  value: unknown,
  kind: 'recommendations',
  locale: Locale,
): RecommendationResponse
export function parseSearchResponse(
  value: unknown,
  kind: 'events',
  locale: Locale,
): EventSearchResponse
export function parseSearchResponse(
  value: unknown,
  kind: 'recommendations' | 'events',
  locale: Locale,
): RecommendationResponse | EventSearchResponse {
  if (
    kind === 'events' &&
    value &&
    typeof value === 'object' &&
    ('provider_status' in value ||
      'contract_version' in value ||
      'listings' in value)
  )
    return parseTransientEvents(value, locale)
  const schema = kind === 'recommendations' ? recommendationSchema : eventSchema
  const copy: unknown = structuredClone(value)
  if (!conforms(copy, schema, schema, true))
    throw new ApiError('invalid_response')
  const result = copy as SearchResponse<RecommendationCard | EventCardData>
  // Warning lists use Pydantic default factories absent from JSON Schema.
  normalizeWarningFactories(result.warnings)
  for (const item of result.items) {
    if ('poi' in item) item.feature_evidence ??= []
  }
  const discovery =
    kind === 'events' ? (copy as EventSearchResponse).discovery : null
  if (discovery) normalizeDiscoveryFactories(discovery)
  if (result.items.some((item) => item.generated_locale !== locale))
    throw new ApiError('locale_mismatch')
  const hasItems = result.status === 'ok' || result.status === 'partial'
  const sources = new Map(
    result.sources.map((source) => [source.source_id, source]),
  )
  const identities = result.items.map((item) =>
    'poi' in item ? item.poi.id : item.session.id,
  )
  const valid =
    hasItems === Boolean(result.items.length || discovery?.events.length) &&
    (result.status !== 'partial' || result.warnings.length > 0) &&
    (!discovery ||
      (result.items.length === 0 &&
        result.sources.length === 0 &&
        result.status === discovery.provider_status &&
        discoveryIsValid(discovery))) &&
    uniqueSources(result.sources) &&
    result.sources.every(sourceIsValid) &&
    new Set(identities).size === identities.length &&
    result.items.every((item) => {
      if (
        !cardIsValid(item, locale) ||
        (result.status === 'ok' && item.fit_status !== 'fits')
      )
        return false
      if (
        !item.provenance.every((provenance) =>
          sources.has(provenance.source_id),
        )
      )
        return false
      if ('poi' in item) {
        return (
          item.activity_code === item.poi.activity_code &&
          sourcedRecordIsValid(item.poi, sources) &&
          featureEvidenceIsValid(item) &&
          item.poi.sources.some(
            (source) => source.source_id === item.poi.primary_source_id,
          )
        )
      }
      return (
        item.session.event_id === item.event.id &&
        item.activity_code === item.event.activity_code &&
        item.session.status !== 'cancelled' &&
        (item.session.ends_at === null ||
          Date.parse(item.session.ends_at) >
            Date.parse(item.session.starts_at)) &&
        sourcedRecordIsValid(item.event, sources) &&
        sourcedRecordIsValid(item.session, sources)
      )
    })
  if (!valid) throw new ApiError('invalid_response')
  return result as RecommendationResponse | EventSearchResponse
}

function apiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL || '/api'
  // Same-origin /api only: sending precise coordinates or queries elsewhere is prohibited.
  if (configured !== '/api' && configured !== '/api/')
    throw new ApiError('invalid_configuration')
  return '/api'
}

const timeoutMs = 20_000
const recommendationTimeoutMs = 80_000
const eventTimeoutMs = 100_000

interface JsonResponse {
  data: unknown
  status: number
}

async function request(
  path: string,
  body?: SearchRequest | RouteRequest,
  signal?: AbortSignal,
  allowUnavailable = false,
  requestTimeoutMs = timeoutMs,
): Promise<JsonResponse> {
  const base = apiBase()
  if (signal?.aborted) throw new ApiError('aborted')
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  const timer = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, requestTimeoutMs)
  try {
    const response = await fetch(`${base}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: {
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: controller.signal,
      credentials: 'same-origin',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'same-origin',
    })
    if (controller.signal.aborted) throw new ApiError('aborted')
    if (!response.ok && !(allowUnavailable && response.status === 503)) {
      if (response.status === 404)
        throw new ApiError('not_ready', response.status)
      if (response.status === 422)
        throw new ApiError('invalid_request', response.status)
      throw new ApiError('server_error', response.status)
    }
    if (
      response.headers
        .get('content-type')
        ?.split(';')[0]
        .trim()
        .toLowerCase() !== 'application/json'
    )
      throw new ApiError(
        'invalid_response',
        response.status === 503 ? response.status : undefined,
      )
    let result: unknown
    try {
      result = await response.json()
    } catch {
      throw new ApiError(
        'invalid_response',
        response.status === 503 ? response.status : undefined,
      )
    }
    if (controller.signal.aborted) throw new ApiError('aborted')
    return { data: result, status: response.status }
  } catch (error) {
    if (timedOut) throw new ApiError('timeout')
    if (signal?.aborted || controller.signal.aborted)
      throw new ApiError('aborted')
    if (error instanceof ApiError) throw error
    throw new ApiError('network')
  } finally {
    window.clearTimeout(timer)
    signal?.removeEventListener('abort', abort)
  }
}

function validateSearchResponse<
  T extends RecommendationResponse | EventSearchResponse,
>(response: JsonResponse, parse: (value: unknown) => T, requestId?: string): T {
  try {
    const result = parse(response.data)
    // Unavailable search envelopes use 503; completed searches use 200.
    if (
      (response.status !== 200 && response.status !== 503) ||
      (response.status === 503) !== (result.status === 'unavailable') ||
      (requestId && result.request_id !== requestId)
    )
      throw new ApiError('invalid_response')
    return result
  } catch (error) {
    if (response.status === 503 && error instanceof ApiError)
      throw new ApiError(error.code, response.status)
    throw error
  }
}

function validateRequest(body: SearchRequest): void {
  if (!conforms(body, requestSchema, requestSchema, false))
    throw new ApiError('invalid_request')
  const fields = body.explicit_fields ?? []
  if (
    new Set(fields).size !== fields.length ||
    fields.some((field) => !Object.hasOwn(body, field))
  )
    throw new ApiError('invalid_request')
}

export async function checkHealth(
  signal?: AbortSignal,
): Promise<{ status: 'ok' }> {
  const { data: result } = await request('/health', undefined, signal)
  if (
    !result ||
    typeof result !== 'object' ||
    Array.isArray(result) ||
    Object.keys(result).length !== 1 ||
    (result as { status?: unknown }).status !== 'ok'
  )
    throw new ApiError('invalid_response')
  return { status: 'ok' }
}

export async function searchRecommendations(
  body: SearchRequest,
  signal?: AbortSignal,
): Promise<RecommendationResponse> {
  validateRequest(body)
  return validateSearchResponse(
    await request(
      '/recommendations',
      body,
      signal,
      true,
      recommendationTimeoutMs,
    ),
    (value) =>
      parseSearchResponse(value, 'recommendations', body.locale ?? 'kk'),
    body.request_id,
  )
}

export async function searchEvents(
  body: SearchRequest,
  signal?: AbortSignal,
): Promise<EventSearchResponse> {
  validateRequest(body)
  return validateSearchResponse(
    await request('/events/search', body, signal, true, eventTimeoutMs),
    (value) => parseSearchResponse(value, 'events', body.locale ?? 'kk'),
    body.request_id,
  )
}

export function parseRouteResponse(value: unknown): RouteResponse {
  const copy: unknown = structuredClone(value)
  if (!conforms(copy, routeResponseSchema, routeResponseSchema, true))
    throw new ApiError('invalid_response')
  const result = copy as RouteResponse
  // Pydantic default factories are not emitted as JSON Schema defaults.
  result.outbound ??= {
    status: 'unavailable',
    reason: 'disabled',
    distance_meters: null,
    duration_seconds: null,
    provenance: null,
  }
  result.return_route ??= {
    status: 'not_requested',
    reason: 'not_requested',
    distance_meters: null,
    duration_seconds: null,
    provenance: null,
  }
  normalizeWarningFactories(result.warnings)
  const legs = [result.outbound, result.return_route]
  if (
    result.outbound.status === 'not_requested' ||
    legs.some((leg) => {
      const known = leg.status === 'known'
      return (
        known !==
          (leg.distance_meters !== null &&
            leg.duration_seconds !== null &&
            leg.provenance !== null) ||
        (known && leg.reason !== null) ||
        (!known &&
          (leg.reason === null ||
            leg.distance_meters !== null ||
            leg.duration_seconds !== null ||
            leg.provenance !== null)) ||
        (leg.status === 'not_requested') !== (leg.reason === 'not_requested')
      )
    })
  )
    throw new ApiError('invalid_response')
  const requested = legs.filter((leg) => leg.status !== 'not_requested')
  const expectedStatus = requested.every((leg) => leg.status === 'known')
    ? 'known'
    : requested.some((leg) => leg.status === 'unavailable')
      ? 'unavailable'
      : 'unknown'
  const expectedMinutes =
    expectedStatus === 'known'
      ? Math.ceil(
          requested.reduce((sum, leg) => sum + leg.duration_seconds!, 0) / 60,
        )
      : null
  if (
    result.status !== expectedStatus ||
    result.travel_minutes_estimate !== expectedMinutes
  )
    throw new ApiError('invalid_response')
  return result
}

export async function getRoute(
  body: RouteRequest,
  signal?: AbortSignal,
): Promise<RouteResponse> {
  if (!conforms(body, routeRequestSchema, routeRequestSchema, false))
    throw new ApiError('invalid_request')
  const response = await request('/route', body, signal, true)
  try {
    const result = parseRouteResponse(response.data)
    if (
      (response.status !== 200 && response.status !== 503) ||
      (body.request_id && result.request_id !== body.request_id) ||
      (response.status === 503) !== (result.status === 'unavailable') ||
      (result.return_route.status !== 'not_requested') !==
        Boolean(body.return_to_start)
    )
      throw new ApiError('invalid_response')
    return result
  } catch (error) {
    if (response.status === 503 && error instanceof ApiError)
      throw new ApiError(error.code, response.status)
    throw error
  }
}
