import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import recommendation from '../../../contracts/examples/recommendation-ok.test.json'
import partial from '../../../contracts/examples/recommendation-partial.test.json'
import events from '../../../contracts/examples/event-search-response.test.json'
import {
  ApiError,
  checkHealth,
  parseSearchResponse,
  searchEvents,
  searchRecommendations,
} from './api'
import type { Locale, SearchRequest } from './types'

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
      '/api/v1/recommendations',
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
      '/api/v1/events/search',
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
  ])('HTTP 503 $name boundary', ({ search, cards }) => {
    it.each<Locale>(['kk', 'ru', 'en'])(
      'returns a validated unavailable envelope for the requested %s locale',
      async (locale) => {
        const envelope = unavailableResponse(locale)
        const fetch = vi.fn().mockResolvedValue(json(envelope, 503))
        vi.stubGlobal('fetch', fetch)

        const result = await search({ ...body, locale })

        expect(result).toEqual(envelope)
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
      await vi.advanceTimersByTimeAsync(20_000)
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
    expect(parseSearchResponse(events, 'events', 'en')).toEqual(events)
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
