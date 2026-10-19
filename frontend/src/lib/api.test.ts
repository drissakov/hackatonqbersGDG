import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import partial from '../../../contracts/examples/recommendation-partial.test.json'
import events from '../../../contracts/examples/event-search-response.test.json'
import {
  ApiError,
  checkHealth,
  getRoute,
  parseRouteResponse,
  parseSearchResponse,
  searchEvents,
  searchRecommendations,
} from './api'
import type {
  Locale,
  RouteLeg,
  RouteRequest,
  RouteResponse,
  SearchRequest,
} from './types'
import {
  syntheticDiscoveryResponse,
  syntheticSession,
} from '../test/eventDiscovery'

const body: SearchRequest = {
  request_id: recommendation.request_id,
  query: 'A quiet indoor activity',
  locale: 'en',
  origin: { latitude: 51.128, longitude: 71.43 },
  available_minutes: 60,
  return_to_start: false,
  budget_kzt_per_person: 0,
  indoor_only: false,
  explicit_fields: ['budget_kzt_per_person', 'return_to_start', 'indoor_only'],
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function unavailableResponse(locale: Locale) {
  const messages = {
    kk: 'Қызмет уақытша қолжетімсіз.',
    ru: 'Сервис временно недоступен.',
    en: 'The service is temporarily unavailable.',
  }
  return {
    status: 'unavailable',
    items: [],
    warnings: [
      {
        code: 'provider_unavailable',
        message: messages[locale],
        fields: [],
      },
    ],
    sources: [],
    request_id: recommendation.request_id,
  }
}

describe('same-origin API transport', () => {
  beforeEach(() => vi.stubEnv('VITE_API_BASE_URL', '/api'))
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('checks real health path and only accepts process health', async () => {
    const fetch = vi.fn().mockResolvedValue(json({ status: 'ok' }))
    vi.stubGlobal('fetch', fetch)
    await expect(checkHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/health',
      expect.objectContaining({ method: 'GET', cache: 'no-store' }),
    )
    fetch.mockResolvedValue(json({ status: 'ok', database: 'ready' }))
    await expect(checkHealth()).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('posts the exact documented body without changing false, zero or explicit fields', async () => {
    const fetch = vi.fn().mockResolvedValue(json(recommendation))
    vi.stubGlobal('fetch', fetch)
    const response = await searchRecommendations(body)
    expect(response.status).toBe('ok')
    expect(fetch).toHaveBeenCalledWith(
      '/api/recommendations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(body),
        credentials: 'same-origin',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
      }),
    )
  })

  it('uses the separate documented event route', async () => {
    const fetch = vi.fn().mockResolvedValue(json(events))
    vi.stubGlobal('fetch', fetch)
    await expect(searchEvents(body)).resolves.toMatchObject({
      status: 'partial',
      items: [{ session: { ends_at: null } }],
    })
    expect(fetch).toHaveBeenCalledWith(
      '/api/events/search',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it.each([
    '2030-01-01T12:00+05:00',
    '2030-01-01 12:00:00+05:00',
    '2030-01-01t12:00:00z',
    '2030-01-01T12:00:00+0500',
  ])(
    'accepts aware ISO datetime forms accepted by the backend: %s',
    async (date_time) => {
      const fetch = vi.fn().mockResolvedValue(json(recommendation))
      vi.stubGlobal('fetch', fetch)
      await expect(
        searchRecommendations({ ...body, date_time }),
      ).resolves.toMatchObject({ status: 'ok' })
      expect(JSON.parse(fetch.mock.calls[0][1].body).date_time).toBe(date_time)
    },
  )

  it('allows surrounding query whitespace for backend normalization', async () => {
    const fetch = vi.fn().mockResolvedValue(json(recommendation))
    vi.stubGlobal('fetch', fetch)
    await expect(
      searchRecommendations({ ...body, query: '  Museum  ' }),
    ).resolves.toMatchObject({ status: 'ok' })
    expect(JSON.parse(fetch.mock.calls[0][1].body).query).toBe('  Museum  ')
  })

  it.each([
    'https://untrusted.invalid/api',
    '//untrusted.invalid/api',
    '/different-api',
  ])('rejects alternate API destinations: %s', async (configured) => {
    vi.stubEnv('VITE_API_BASE_URL', configured)
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(searchRecommendations(body)).rejects.toMatchObject({
      code: 'invalid_configuration',
    })
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    { ...body, explicit_fields: ['origin', 'origin'] },
    { query: 'Activity', explicit_fields: ['origin'] },
    { query: '   ' },
    { ...body, available_minutes: 0 },
    { ...body, origin: { latitude: 91, longitude: 71 } },
    { ...body, date_time: '2030-01-01T12:00:00' },
    { ...body, date_time: '2030-02-30T12:00:00+05:00' },
    { ...body, date_time: '2030-01-01T24:00:00+05:00' },
  ])('rejects invalid requests before sending a query', async (request) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(
      searchRecommendations(request as SearchRequest),
    ).rejects.toMatchObject({ code: 'invalid_request' })
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    [404, 'not_ready'],
    [422, 'invalid_request'],
    [500, 'server_error'],
  ])('sanitizes HTTP %i without reading error bodies', async (status, code) => {
    const response = json(
      { detail: 'Private provider payload and raw input' },
      status as number,
    )
    const readBody = vi.spyOn(response, 'json')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const result = searchRecommendations(body)
    await expect(result).rejects.toMatchObject({ code, status })
    await expect(result).rejects.not.toHaveProperty('detail')
    expect(readBody).not.toHaveBeenCalled()
  })

  describe.each([
    {
      name: 'recommendations',
      search: searchRecommendations,
      cards: recommendation,
    },
    { name: 'events', search: searchEvents, cards: events },
  ])('HTTP 503 $name boundary', ({ name, search, cards }) => {
    it.each([
      { status: 200, unavailable: true },
      { status: 201, unavailable: false },
    ])(
      'rejects an inconsistent successful HTTP/domain status: $status',
      async ({ status, unavailable }) => {
        vi.stubGlobal(
          'fetch',
          vi
            .fn()
            .mockResolvedValue(
              json(unavailable ? unavailableResponse('en') : cards, status),
            ),
        )
        await expect(search(body)).rejects.toMatchObject({
          code: 'invalid_response',
        })
      },
    )
    it.each<Locale>(['kk', 'ru', 'en'])(
      'returns a validated unavailable envelope for the requested %s locale',
      async (locale) => {
        const envelope = unavailableResponse(locale)
        const fetch = vi.fn().mockResolvedValue(json(envelope, 503))
        vi.stubGlobal('fetch', fetch)

        const result = await search({ ...body, locale })

        expect(result).toEqual(
          name === 'events' ? { ...envelope, discovery: null } : envelope,
        )
        expect(result.items).toEqual([])
        expect(result.sources).toEqual([])
        expect(result.warnings).toEqual(envelope.warnings)
        expect(JSON.parse(fetch.mock.calls[0][1].body).locale).toBe(locale)
        // Empty unavailable envelopes have no generated_locale. This checks
        // preservation of warning text, not automatic prose-language detection.
      },
    )

    it.each([
      {
        name: 'HTML',
        response: () =>
          new Response('<html>Private upstream response</html>', {
            status: 503,
            headers: { 'content-type': 'text/html' },
          }),
      },
      {
        name: 'malformed JSON',
        response: () =>
          new Response('{private:broken', {
            status: 503,
            headers: { 'content-type': 'application/json' },
          }),
      },
      {
        name: 'incomplete envelope',
        response: () => json({ status: 'unavailable' }, 503),
      },
      {
        name: 'provider error body',
        response: () => json({ detail: 'Private upstream error' }, 503),
      },
      {
        name: 'no_match domain status',
        response: () =>
          json({ ...unavailableResponse('en'), status: 'no_match' }, 503),
      },
      {
        name: 'unknown domain status',
        response: () =>
          json({ ...unavailableResponse('en'), status: 'unknown' }, 503),
      },
      {
        name: 'unexpected top-level locale',
        response: () =>
          json({ ...unavailableResponse('en'), locale: 'en' }, 503),
      },
    ])('rejects $name with a safe error', async ({ response }) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response()))

      const pending = search(body)

      await expect(pending).rejects.toMatchObject({
        code: 'invalid_response',
        message: 'invalid_response',
        status: 503,
      })
      await expect(pending).rejects.not.toHaveProperty('detail')
    })

    it('still enforces response request correlation', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(
          json(
            {
              ...unavailableResponse('en'),
              request_id: '00000000-0000-4000-8000-000000000009',
            },
            503,
          ),
        ),
      )

      await expect(search(body)).rejects.toMatchObject({
        code: 'invalid_response',
        status: 503,
      })
    })

    it('still validates generated card language before returning a 503 payload', async () => {
      const invalid = structuredClone(cards)
      invalid.status = 'unavailable'
      invalid.items[0].generated_locale = 'ru'
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(invalid, 503)))

      await expect(search(body)).rejects.toMatchObject({
        code: 'locale_mismatch',
      })
    })

    it('preserves cancellation while reading a 503 body', async () => {
      let markBodyStarted: () => void = () => undefined
      const bodyStarted = new Promise<void>((resolve) => {
        markBodyStarted = resolve
      })
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((_url, options: RequestInit) => {
          const response = json(unavailableResponse('en'), 503)
          vi.spyOn(response, 'json').mockImplementation(
            () =>
              new Promise((_resolve, reject) => {
                options.signal!.addEventListener('abort', () =>
                  reject(new DOMException('Aborted', 'AbortError')),
                )
                markBodyStarted()
              }),
          )
          return Promise.resolve(response)
        }),
      )
      const controller = new AbortController()
      const pending = search(body, controller.signal)
      const rejected = expect(pending).rejects.toMatchObject({
        code: 'aborted',
      })
      await bodyStarted
      controller.abort()
      await rejected
    })

    it('preserves timeout and timer cleanup while reading a 503 body', async () => {
      vi.useFakeTimers()
      let markBodyStarted: () => void = () => undefined
      const bodyStarted = new Promise<void>((resolve) => {
        markBodyStarted = resolve
      })
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation((_url, options: RequestInit) => {
          const response = json(unavailableResponse('en'), 503)
          vi.spyOn(response, 'json').mockImplementation(
            () =>
              new Promise((_resolve, reject) => {
                options.signal!.addEventListener('abort', () =>
                  reject(new DOMException('Aborted', 'AbortError')),
                )
                markBodyStarted()
              }),
          )
          return Promise.resolve(response)
        }),
      )
      const pending = search(body)
      const rejected = expect(pending).rejects.toMatchObject({
        code: 'timeout',
      })
      await bodyStarted
      await vi.advanceTimersByTimeAsync(name === 'events' ? 100_000 : 80_000)
      await rejected
      expect(vi.getTimerCount()).toBe(0)
    })
  })

  it('keeps HTTP 503 health failures as server errors', async () => {
    const response = json(unavailableResponse('en'), 503)
    const readBody = vi.spyOn(response, 'json')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))

    await expect(checkHealth()).rejects.toMatchObject({
      code: 'server_error',
      status: 503,
    })
    expect(readBody).not.toHaveBeenCalled()
  })

  it('distinguishes a network failure from no matches', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Sensitive network details')),
    )
    await expect(searchRecommendations(body)).rejects.toEqual(
      new ApiError('network'),
    )
  })

  it('enforces JSON content type and valid JSON', async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response('<html>fallback</html>', {
        headers: { 'content-type': 'text/html' },
      }),
    )
    vi.stubGlobal('fetch', fetch)
    await expect(checkHealth()).rejects.toMatchObject({
      code: 'invalid_response',
    })
    fetch.mockResolvedValue(
      new Response('{broken', {
        headers: { 'content-type': 'application/json' },
      }),
    )
    await expect(checkHealth()).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('rejects cancelled work even when a fetch adapter resolves after cancellation', async () => {
    let finish: ((response: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      ),
    )
    const controller = new AbortController()
    const promise = searchRecommendations(body, controller.signal)
    const rejected = expect(promise).rejects.toMatchObject({ code: 'aborted' })
    controller.abort()
    finish!(json(recommendation))
    await rejected
  })

  it('does not send already cancelled requests', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    const controller = new AbortController()
    controller.abort()
    await expect(checkHealth(controller.signal)).rejects.toMatchObject({
      code: 'aborted',
    })
    expect(fetch).not.toHaveBeenCalled()
  })

  it('times out once, aborts the request and cleans up its timer', async () => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            options.signal!.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            )
          }),
      ),
    )
    const promise = checkHealth()
    const rejected = expect(promise).rejects.toMatchObject({ code: 'timeout' })
    await vi.advanceTimersByTimeAsync(20_000)
    await rejected
    expect(vi.getTimerCount()).toBe(0)
  })

  it('allows the recommendation provider pipeline beyond health timeout and aborts at its own deadline', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | null | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url, options: RequestInit) =>
          new Promise((_resolve, reject) => {
            signal = options.signal
            signal!.addEventListener('abort', () =>
              reject(new DOMException('Aborted', 'AbortError')),
            )
          }),
      ),
    )
    const promise = searchRecommendations(body)
    const rejected = expect(promise).rejects.toMatchObject({ code: 'timeout' })
    await vi.advanceTimersByTimeAsync(20_000)
    expect(signal!.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(59_999)
    expect(signal!.aborted).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    await rejected
    expect(signal!.aborted).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('rejects mismatched response correlation IDs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        json({
          ...recommendation,
          request_id: '00000000-0000-4000-8000-000000000009',
        }),
      ),
    )
    await expect(searchRecommendations(body)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })
})

describe('v1 runtime response boundaries', () => {
  it('preserves unknown facts and all source evidence from valid fixtures', () => {
    expect(parseSearchResponse(partial, 'recommendations', 'en')).toEqual(
      partial,
    )
    expect(parseSearchResponse(events, 'events', 'en')).toEqual({
      ...events,
      discovery: null,
    })
  })

  it('applies declared response defaults without mutating the wire payload', () => {
    const value = structuredClone(recommendation)
    const source = value.sources[0] as Partial<(typeof value.sources)[number]>
    delete source.indexing_allowed
    const recordSource = value.items[0].poi.sources[0] as Partial<
      (typeof value.items)[number]['poi']['sources'][number]
    >
    delete recordSource.indexing_allowed
    const parsed = parseSearchResponse(value, 'recommendations', 'en')
    expect(parsed.sources[0].indexing_allowed).toBe(false)
    expect(source).not.toHaveProperty('indexing_allowed')
  })

  it.each(['recommendations', 'events'] as const)(
    'fills optional warning fields for %s without mutating the wire body',
    (kind) => {
      const wire = {
        request_id: recommendation.request_id,
        status: 'unavailable',
        items: [],
        sources: [],
        warnings: [{ code: 'provider_unavailable', message: 'Unavailable' }],
      }
      const parsed =
        kind === 'events'
          ? parseSearchResponse(wire, kind, 'en')
          : parseSearchResponse(wire, kind, 'en')
      expect(parsed.warnings[0].fields).toEqual([])
      expect(wire.warnings[0]).not.toHaveProperty('fields')
      expect(() =>
        parseSearchResponse(
          { ...wire, warnings: [{ ...wire.warnings[0], fields: null }] },
          'recommendations',
          'en',
        ),
      ).toThrowError(new ApiError('invalid_response'))
    },
  )

  it('rejects generated output in a different language', () => {
    expect(() =>
      parseSearchResponse(recommendation, 'recommendations', 'kk'),
    ).toThrowError(new ApiError('locale_mismatch'))
  })

  it.each([
    (value: typeof recommendation) => {
      value.items[0].poi.location.latitude = Number.NaN
    },
    (value: typeof recommendation) => {
      value.items[0].action.url = 'javascript:alert(1)'
    },
    (value: typeof recommendation) => {
      value.items[0].travel_minutes_estimate = -1
    },
    (value: typeof recommendation) => {
      value.items[0].route_status = 'unknown'
    },
    (value: typeof recommendation) => {
      value.items[0].fit_status = 'does_not_fit'
    },
    (value: typeof recommendation) => {
      value.items[0].provenance[0].source_id = 'missing'
    },
    (value: typeof recommendation) => {
      value.sources[0].url = 'https://example.invalid/different'
    },
    (value: typeof recommendation) => {
      value.items.push(structuredClone(value.items[0]))
    },
    (value: typeof recommendation) => {
      value.status = 'no_match'
    },
    (value: typeof recommendation) => {
      value.items[0].poi.is_test = false
    },
    (value: typeof recommendation) => {
      value.sources[0].provider = 'unknown-provider'
    },
    (value: typeof recommendation) => {
      Object.assign(value, { extra: 'unexpected' })
    },
    (value: typeof recommendation) => {
      delete (value.items[0] as Partial<(typeof value.items)[0]>).reason_codes
    },
    (value: typeof recommendation) => {
      delete (value.items[0] as Partial<(typeof value.items)[0]>).provenance
    },
    (value: typeof recommendation) => {
      const poi = value.items[0].poi
      delete (poi as Partial<typeof poi>).sources
    },
    (value: typeof recommendation) => {
      const poi = value.items[0].poi
      delete (poi as Partial<typeof poi>).provenance
    },
  ])('rejects structurally invalid or dishonest alternatives', (mutate) => {
    const value = structuredClone(recommendation)
    mutate(value)
    expect(() =>
      parseSearchResponse(value, 'recommendations', 'en'),
    ).toThrowError(new ApiError('invalid_response'))
  })

  it('requires partial warnings and honest unknown fit limitations', () => {
    const value = structuredClone(partial)
    value.warnings = []
    expect(() =>
      parseSearchResponse(value, 'recommendations', 'en'),
    ).toThrowError(new ApiError('invalid_response'))
    value.warnings = partial.warnings
    value.items[0].missing_fields = []
    expect(() =>
      parseSearchResponse(value, 'recommendations', 'en'),
    ).toThrowError(new ApiError('invalid_response'))
  })

  it('rejects cancelled sessions, incorrect event links and reversed session times', () => {
    const cancelled = structuredClone(events)
    cancelled.items[0].session.status = 'cancelled'
    expect(() => parseSearchResponse(cancelled, 'events', 'en')).toThrowError(
      new ApiError('invalid_response'),
    )
    const wrongEvent = structuredClone(events)
    wrongEvent.items[0].session.event_id = 'different-event'
    expect(() => parseSearchResponse(wrongEvent, 'events', 'en')).toThrowError(
      new ApiError('invalid_response'),
    )
    const wrongTime = structuredClone(events)
    Object.assign(wrongTime.items[0].session, {
      ends_at: '2029-01-01T00:00:00Z',
    })
    expect(() => parseSearchResponse(wrongTime, 'events', 'en')).toThrowError(
      new ApiError('invalid_response'),
    )
  })
})

describe('transient D03 response boundary', () => {
  it('normalizes omitted discovery factory fields without mutating valid wire data', () => {
    const empty = {
      ...unavailableResponse('en'),
      discovery: { provider_status: 'unavailable', live_web_search: 'not_run' },
    }
    expect(
      parseSearchResponse(empty, 'events', 'en').discovery?.events,
    ).toEqual([])
    expect(empty.discovery).not.toHaveProperty('events')

    const value = syntheticDiscoveryResponse()
    const session = syntheticSession()
    delete (session as Partial<typeof session>).verified_fields
    for (const venue of [value.discovery!.events[0].venue, session.venue]) {
      delete (venue as Partial<typeof venue>).source_ids
      delete (venue as Partial<typeof venue>).source_urls
    }
    value.discovery!.events[0].sessions = [session]
    const parsed = parseSearchResponse(value, 'events', 'en')
    expect(parsed.discovery!.events[0].sessions[0].verified_fields).toEqual([])
    expect(parsed.discovery!.events[0].venue.source_urls).toEqual([])
    expect(parsed.discovery!.events[0].sessions[0].venue.source_ids).toEqual([])
    expect(session).not.toHaveProperty('verified_fields')
  })

  it.each([
    { basis: 'unknown', location: { latitude: 51.13, longitude: 71.43 } },
    { basis: 'ambiguous', poi_id: 'test-venue' },
    {
      basis: 'name_address_astana_permitted_poi',
      poi_id: 'test-venue',
      location: { latitude: 51.13, longitude: 71.43 },
      geography_basis: 'central_astana_bbox',
    },
  ])('rejects unsupported event and session venue coordinates: %j', (venue) => {
    for (const record of ['event', 'session'] as const) {
      const value = syntheticDiscoveryResponse()
      const session = syntheticSession()
      value.discovery!.events[0].sessions = [session]
      Object.assign(
        record === 'event' ? value.discovery!.events[0].venue : session.venue,
        venue,
      )
      expect(() => parseSearchResponse(value, 'events', 'en')).toThrowError(
        new ApiError('invalid_response'),
      )
    }
  })

  it('accepts independently grounded event and session venue coordinates', () => {
    const value = syntheticDiscoveryResponse()
    const session = syntheticSession()
    value.discovery!.events[0].sessions = [session]
    for (const venue of [value.discovery!.events[0].venue, session.venue])
      Object.assign(venue, {
        basis: 'name_address_astana_permitted_poi',
        poi_id: 'test-venue',
        location: { latitude: 51.13, longitude: 71.43 },
        source_ids: ['test-source'],
        source_urls: ['https://example.invalid/test-venue'],
        geography_basis: 'central_astana_bbox',
      })
    expect(parseSearchResponse(value, 'events', 'en')).toEqual(value)
  })

  it.each([
    'sessions',
    'citations',
    'verified_fields',
    'source_ids',
    'events',
  ] as const)(
    'rejects missing required or explicitly null optional discovery arrays: %s',
    (field) => {
      const value = syntheticDiscoveryResponse()
      const event = value.discovery!.events[0]
      const session = syntheticSession()
      event.sessions = [session]
      if (field === 'sessions') delete (event as Partial<typeof event>).sessions
      if (field === 'citations') {
        const evidence = value.discovery!.evidence!
        delete (evidence as Partial<typeof evidence>).citations
      }
      if (field === 'verified_fields')
        Object.assign(session, { verified_fields: null })
      if (field === 'source_ids')
        Object.assign(session.venue, { source_ids: null })
      if (field === 'events') Object.assign(value.discovery!, { events: null })
      expect(() => parseSearchResponse(value, 'events', 'en')).toThrowError(
        new ApiError('invalid_response'),
      )
    },
  )

  it.each([
    { field: 'price_from', value: 1 },
    { field: 'price_from', value: '5000' },
    { field: 'ends_at', value: '2030-01-02T20:00:00+05:00' },
    { checked_at: '2029-12-31T10:00:00+05:00' },
  ])(
    'rejects a verification check with a mismatched field value or stale observation: %j',
    (change) => {
      const value = syntheticDiscoveryResponse()
      const session = syntheticSession()
      session.verification_status = 'verified'
      session.verified_fields = [
        {
          session_id: session.session_id,
          field: 'price_from',
          value: session.price_from!,
          source_url: session.source_url,
          checked_at: session.source_fetched_at,
          method: 'manual_source',
        },
      ]
      Object.assign(session.verified_fields[0], change)
      value.discovery!.events[0].sessions = [session]
      expect(() => parseSearchResponse(value, 'events', 'en')).toThrowError(
        new ApiError('invalid_response'),
      )
    },
  )

  it('accepts timestamp checks for the same aware instant written with another offset', () => {
    const value = syntheticDiscoveryResponse()
    const session = syntheticSession()
    session.verification_status = 'verified'
    session.verified_fields = [
      {
        session_id: session.session_id,
        field: 'starts_at',
        value: '2030-01-02T13:00:00Z',
        source_url: session.source_url,
        checked_at: session.source_fetched_at,
        method: 'manual_source',
      },
    ]
    value.discovery!.events[0].sessions = [session]
    expect(parseSearchResponse(value, 'events', 'en')).toEqual(value)
  })

  it('accepts a listing with no persistent card or invented session and preserves false storage rights', () => {
    const value = syntheticDiscoveryResponse()
    expect(parseSearchResponse(value, 'events', 'ru')).toEqual(value)
    expect(value.discovery!.events[0].sessions).toEqual([])
    expect(value.discovery!.evidence!.sources[0].storage_allowed).toBe(false)
  })

  it.each([
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      value.discovery!.provider_status = 'unavailable'
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      value.discovery!.evidence = null
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      value.discovery!.events[0].source_url = 'https://example.invalid/uncited'
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      value.discovery!.evidence!.citations[0].url = 'javascript:alert(1)'
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      value.discovery!.events.push(structuredClone(value.discovery!.events[0]))
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      const session = syntheticSession()
      session.status = 'cancelled'
      value.discovery!.events[0].sessions = [session]
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      const session = syntheticSession()
      session.event_id = 'different-event'
      value.discovery!.events[0].sessions = [session]
    },
    (value: ReturnType<typeof syntheticDiscoveryResponse>) => {
      const session = syntheticSession()
      session.verification_status = 'verified'
      value.discovery!.events[0].sessions = [session]
    },
  ])('rejects inconsistent or unsupported discovered facts', (mutate) => {
    const value = syntheticDiscoveryResponse()
    mutate(value)
    expect(() => parseSearchResponse(value, 'events', 'en')).toThrowError(
      new ApiError('invalid_response'),
    )
  })
})

const routeRequest: RouteRequest = {
  request_id: recommendation.request_id,
  origin: { latitude: 51.128, longitude: 71.43 },
  destination: { latitude: 51.12, longitude: 71.42 },
  return_to_start: true,
  locale: 'en',
}

function knownLeg(seconds = 61): RouteLeg {
  return {
    status: 'known',
    distance_meters: 100,
    duration_seconds: seconds,
    provenance: {
      provider: 'twogis',
      endpoint: 'https://routing.api.2gis.com/routing/7.0.0/global',
      retrieved_at: '2030-01-01T12:00:00+05:00',
      transport: 'walking',
      provider_locale: 'en',
      storage_allowed: false,
      indexing_allowed: false,
      ai_allowed: false,
    },
    reason: null,
  }
}

function routeResponse(): RouteResponse {
  return {
    request_id: recommendation.request_id,
    status: 'known',
    travel_minutes_estimate: 3,
    outbound: knownLeg(61),
    return_route: knownLeg(62),
    destination_precision: 'approximate',
    warnings: [],
  }
}

describe('walking route transport and honest totals', () => {
  beforeEach(() => vi.stubEnv('VITE_API_BASE_URL', '/api'))
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('posts to the real route endpoint and keeps independently obtained leg metrics', async () => {
    const response = routeResponse()
    const fetch = vi.fn().mockResolvedValue(json(response))
    vi.stubGlobal('fetch', fetch)
    await expect(getRoute(routeRequest)).resolves.toEqual(response)
    expect(fetch).toHaveBeenCalledWith(
      '/api/route',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(routeRequest),
        cache: 'no-store',
      }),
    )
  })

  it('keeps a known outbound leg when the return is unavailable without a full trip total', async () => {
    const response = routeResponse()
    response.status = 'unavailable'
    response.travel_minutes_estimate = null
    response.return_route = {
      status: 'unavailable',
      reason: 'timeout',
      distance_meters: null,
      duration_seconds: null,
      provenance: null,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response, 503)))
    await expect(getRoute(routeRequest)).resolves.toEqual(response)
  })

  it('keeps a missing-origin route unknown and a no-return leg explicitly not requested', async () => {
    const response: RouteResponse = {
      ...routeResponse(),
      status: 'unknown',
      travel_minutes_estimate: null,
      outbound: {
        status: 'unknown',
        reason: 'missing_origin',
        distance_meters: null,
        duration_seconds: null,
        provenance: null,
      },
      return_route: {
        status: 'not_requested',
        reason: 'not_requested',
        distance_meters: null,
        duration_seconds: null,
        provenance: null,
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response)))
    await expect(
      getRoute({ ...routeRequest, origin: null, return_to_start: false }),
    ).resolves.toEqual(response)
  })

  it('accepts zero-duration routes and rounds the combined duration only once', () => {
    const response = routeResponse()
    response.outbound = knownLeg(0)
    response.return_route = knownLeg(0)
    response.travel_minutes_estimate = 0
    expect(parseRouteResponse(response)).toEqual(response)
    response.outbound = knownLeg(1)
    response.return_route = knownLeg(1)
    response.travel_minutes_estimate = 1
    expect(parseRouteResponse(response).travel_minutes_estimate).toBe(1)
  })

  it('applies declared and factory response defaults without changing the wire body', () => {
    const wire = { request_id: recommendation.request_id, warnings: [] }
    expect(parseRouteResponse(wire)).toMatchObject({
      status: 'unavailable',
      travel_minutes_estimate: null,
      outbound: { status: 'unavailable', reason: 'disabled' },
      return_route: { status: 'not_requested', reason: 'not_requested' },
      destination_precision: 'approximate',
    })
    expect(wire).not.toHaveProperty('outbound')
  })

  it.each([
    (value: RouteResponse) => {
      value.travel_minutes_estimate = 4
    },
    (value: RouteResponse) => {
      value.status = 'unknown'
    },
    (value: RouteResponse) => {
      value.outbound.provenance = null
    },
    (value: RouteResponse) => {
      value.outbound.duration_seconds = null
    },
    (value: RouteResponse) => {
      value.outbound.reason = 'timeout'
    },
    (value: RouteResponse) => {
      value.outbound.duration_seconds = -1
    },
    (value: RouteResponse) => {
      value.outbound.status = 'not_requested'
    },
    (value: RouteResponse) => {
      value.return_route.status = 'unavailable'
      value.return_route.reason = 'timeout'
    },
    (value: RouteResponse) => {
      value.outbound.provenance!.storage_allowed = true as false
    },
    (value: RouteResponse) => {
      Object.assign(value, { geometry: {} })
    },
  ])('rejects contradictory route facts and unsupported geometry', (mutate) => {
    const response = routeResponse()
    mutate(response)
    expect(() => parseRouteResponse(response)).toThrowError(
      new ApiError('invalid_response'),
    )
  })

  it.each([
    { ...routeRequest, destination: { latitude: 91, longitude: 71 } },
    { ...routeRequest, origin: { latitude: Number.NaN, longitude: 71 } },
    { ...routeRequest, request_id: 'bad-id' },
    { ...routeRequest, locale: 'de' },
    { ...routeRequest, destination: undefined },
    { ...routeRequest, query: 'unsupported' },
  ])('rejects malformed route requests before network access', async (body) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(getRoute(body as RouteRequest)).rejects.toMatchObject({
      code: 'invalid_request',
    })
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each([
    [503, routeResponse()],
    [201, routeResponse()],
    [
      200,
      {
        ...routeResponse(),
        request_id: '00000000-0000-4000-8000-000000000009',
      },
    ],
  ])(
    'rejects HTTP/domain status or request correlation mismatch',
    async (status, response) => {
      vi.stubGlobal(
        'fetch',
        vi.fn().mockResolvedValue(json(response, status as number)),
      )
      await expect(getRoute(routeRequest)).rejects.toMatchObject({
        code: 'invalid_response',
      })
    },
  )

  it('requires the requested independent return leg', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(routeResponse())))
    await expect(
      getRoute({ ...routeRequest, return_to_start: false }),
    ).rejects.toMatchObject({ code: 'invalid_response' })
  })

  it('does not accept an unavailable route on HTTP 200', async () => {
    const response = routeResponse()
    response.status = 'unavailable'
    response.travel_minutes_estimate = null
    response.outbound = {
      status: 'unavailable',
      reason: 'disabled',
      distance_meters: null,
      duration_seconds: null,
      provenance: null,
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(response)))
    await expect(getRoute(routeRequest)).rejects.toMatchObject({
      code: 'invalid_response',
    })
  })

  it('ignores cancelled work even if the transport resolves late', async () => {
    let finish: ((value: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      ),
    )
    const controller = new AbortController()
    const pending = getRoute(routeRequest, controller.signal)
    const rejected = expect(pending).rejects.toMatchObject({ code: 'aborted' })
    controller.abort()
    finish!(json(routeResponse()))
    await rejected
  })
})
