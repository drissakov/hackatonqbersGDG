import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import i18n from './i18n'
import { formatMinutes } from './lib/format'
import type {
  Locale,
  RecommendationResponse,
  RouteRequest,
  SearchRequest,
} from './lib/types'
import placeFixture from '../../contracts/examples/recommendation-ok.test.json'
import routeFixture from '../../contracts/examples/route-known.test.json'
import {
  syntheticDiscoveryResponse,
  syntheticSession,
} from './test/eventDiscovery'

const narrative = 'TEST ONLY English model narrative for the requested outing.'
const placeName = 'TEST ONLY source museum name'
const languageNames = { kk: 'Қазақша', ru: 'Русский', en: 'English' }
const locales: Locale[] = ['kk', 'ru', 'en']

function text(key: string, locale?: Locale) {
  return i18n.t(key, locale ? { lng: locale } : undefined)
}

function json(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function place(body: SearchRequest, name = placeName): RecommendationResponse {
  const result = structuredClone(placeFixture) as RecommendationResponse
  result.request_id = body.request_id!
  result.items[0].poi.name = name
  result.items[0].generated_locale = body.locale ?? 'kk'
  result.items[0].explanation = narrative
  return result
}

function knownRoute(body: RouteRequest) {
  return {
    ...structuredClone(routeFixture),
    request_id: body.request_id,
    travel_minutes_estimate: 2,
    return_route: {
      status: 'not_requested',
      distance_meters: null,
      duration_seconds: null,
      provenance: null,
      reason: 'not_requested',
    },
  }
}

interface CapturedRequest {
  path: string
  body: SearchRequest & Partial<RouteRequest>
  signal: AbortSignal
}

function transport(
  reply: (request: CapturedRequest) => Response | Promise<Response>,
) {
  const requests: CapturedRequest[] = []
  const fetch = vi.fn<typeof globalThis.fetch>(async (input, options) => {
    if (input === '/api/health') return json({ status: 'ok' })
    if (options?.method !== 'POST' || typeof options.body !== 'string')
      throw new Error('Unexpected synthetic HTTP request')
    const request = {
      path: String(input),
      body: JSON.parse(options.body),
      signal: options.signal as AbortSignal,
    }
    requests.push(request)
    return reply(request)
  })
  vi.stubGlobal('fetch', fetch)
  return { requests, fetch }
}

async function fillQuery(locale: Locale = 'en') {
  const user = userEvent.setup()
  await user.type(
    screen.getByRole('textbox', { name: text('search.query', locale) }),
    'TEST ONLY quiet museum',
  )
  return user
}

beforeEach(async () => {
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: undefined,
  })
})

describe('D04 complete flows through real frontend HTTP transport', () => {
  it('keeps received place and selected walking route while translating codes locally, then searches explicitly in the next locale', async () => {
    const { requests } = transport(({ path, body }) => {
      if (path === '/api/recommendations') return json(place(body))
      if (path === '/api/route') return json(knownRoute(body as RouteRequest))
      throw new Error('Unexpected synthetic endpoint')
    })
    render(<App />)
    const user = await fillQuery()
    await user.type(screen.getByLabelText(text('location.latitude')), '51.13')
    await user.type(screen.getByLabelText(text('location.longitude')), '71.43')
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    const card = await screen.findByRole('article', { name: placeName })
    expect(within(card).getByText(narrative)).toBeVisible()
    expect(requests.map((request) => request.path)).toEqual([
      '/api/recommendations',
    ])
    await user.click(
      within(card).getByRole('button', { name: text('card.select') }),
    )
    expect(
      await screen.findAllByText(text('codes.route_status.known')),
    ).not.toHaveLength(0)
    expect(requests).toHaveLength(2)
    expect(requests[1].body).toMatchObject({
      origin: { latitude: 51.13, longitude: 71.43 },
      destination: { latitude: 51.128, longitude: 71.43 },
      locale: 'en',
    })
    for (const locale of ['ru', 'kk', 'en'] as const) {
      await user.click(
        screen.getByRole('button', { name: languageNames[locale] }),
      )
      expect(screen.getByRole('article', { name: placeName })).toBeVisible()
      expect(
        within(card).getByText(text('codes.reason_codes.query_match', locale)),
      ).toBeVisible()
      expect(
        within(card).getByText(text('codes.activity_code.museum', locale)),
      ).toBeVisible()
      expect(
        screen.getAllByText(text('codes.route_status.known', locale)),
      ).not.toHaveLength(0)
      expect(requests).toHaveLength(2)
      if (locale === 'en')
        expect(within(card).getByText(narrative)).toBeVisible()
      else expect(within(card).queryByText(narrative)).not.toBeInTheDocument()
    }
    await user.click(screen.getByRole('button', { name: 'Русский' }))
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    expect(
      await screen.findByRole('article', { name: placeName }),
    ).toBeVisible()
    expect(requests).toHaveLength(3)
    expect(requests[2].body.locale).toBe('ru')
  })

  it('renders a sourced event session, ticket-check link and unknown availability without promising a purchase', async () => {
    const response = syntheticDiscoveryResponse()
    response.discovery!.events[0].status = 'discovered'
    response.discovery!.events[0].sessions = [syntheticSession()]
    const { requests } = transport(({ path, body }) => {
      expect(path).toBe('/api/events/search')
      return json({ ...response, request_id: body.request_id })
    })
    render(<App />)
    const user = await fillQuery()
    await user.click(
      screen.getByRole('button', { name: text('states.events') }),
    )
    await user.click(
      screen.getByRole('button', { name: text('search.submitEvents') }),
    )
    const card = await screen.findByRole('article', {
      name: response.discovery!.events[0].title,
    })
    expect(within(card).getByText(text('events.ticketsUnknown'))).toBeVisible()
    expect(within(card).getByText(text('events.fitUnknown'))).toBeVisible()
    const ticket = within(card).getByRole('link', {
      name: text('events.checkTickets'),
    })
    expect(ticket).toHaveAttribute('href', syntheticSession().source_url)
    expect(ticket).toHaveAttribute('rel', 'noopener noreferrer')
    for (const locale of ['ru', 'kk'] as const) {
      await user.click(
        screen.getByRole('button', { name: languageNames[locale] }),
      )
      expect(
        within(card).getByText(text('events.ticketsUnknown', locale)),
      ).toBeVisible()
      expect(
        within(card).getByText(text('codes.session_status.scheduled', locale)),
      ).toBeVisible()
      expect(
        within(card).getByRole('link', {
          name: text('events.checkTickets', locale),
        }),
      ).toHaveAttribute('href', syntheticSession().source_url)
    }
    expect(requests).toHaveLength(1)
  })

  it('keeps the event destination unknown when eligible sessions have different venue coordinates instead of routing to the first session', async () => {
    const response = syntheticDiscoveryResponse()
    const event = response.discovery!.events[0]
    event.status = 'discovered'
    const first = syntheticSession()
    first.venue = {
      poi_id: 'TEST ONLY first permitted venue',
      location: { latitude: 51.14, longitude: 71.44 },
      basis: 'name_address_astana_permitted_poi',
      source_ids: ['TEST ONLY venue OSM source'],
      source_urls: ['https://example.invalid/test-only/venue-source'],
      coordinate_accuracy: 'unknown',
      geography_basis: 'central_astana_bbox',
    }
    const second = structuredClone(first)
    second.session_id = 'test-session-at-another-venue'
    second.venue.poi_id = 'TEST ONLY second permitted venue'
    second.venue.location = { latitude: 51.15, longitude: 71.45 }
    event.sessions = [first, second]
    const { requests } = transport(({ path, body }) => {
      if (path === '/api/events/search')
        return json({ ...response, request_id: body.request_id })
      throw new Error('An ambiguous event destination must not request a route')
    })
    render(<App />)
    const user = await fillQuery()
    await user.type(screen.getByLabelText(text('location.latitude')), '51.13')
    await user.type(screen.getByLabelText(text('location.longitude')), '71.43')
    await user.click(
      screen.getByRole('button', { name: text('states.events') }),
    )
    await user.click(
      screen.getByRole('button', { name: text('search.submitEvents') }),
    )
    const card = await screen.findByRole('article', { name: event.title })
    await user.click(
      within(card).getByRole('button', { name: text('card.select') }),
    )
    const details = screen.getByRole('region', { name: text('map.title') })
    expect(within(details).getByText(text('map.noPoints'))).toBeVisible()
    expect(
      within(details).getByText(text('codes.missing_fields.location'), {
        exact: false,
        selector: 'span',
      }),
    ).toBeVisible()
    expect(details.querySelectorAll('.destination-pin')).toHaveLength(0)
    expect(requests.map((request) => request.path)).toEqual([
      '/api/events/search',
    ])
  })

  it('retries a failed walking request for the same selected card and uses the current locale without another search', async () => {
    let routeAttempts = 0
    const { requests } = transport(({ path, body }) => {
      if (path === '/api/recommendations') return json(place(body))
      if (path === '/api/route') {
        routeAttempts += 1
        return routeAttempts === 1
          ? json({ diagnostic: 'TEST ONLY private route failure' }, 500)
          : json(knownRoute(body as RouteRequest))
      }
      throw new Error('Unexpected synthetic endpoint')
    })
    render(<App />)
    const user = await fillQuery()
    await user.type(screen.getByLabelText(text('location.latitude')), '51.13')
    await user.type(screen.getByLabelText(text('location.longitude')), '71.43')
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    const card = await screen.findByRole('article', { name: placeName })
    await user.click(
      within(card).getByRole('button', { name: text('card.select') }),
    )
    const details = screen.getByRole('region', { name: text('map.title') })
    expect(await within(details).findByText(text('route.error'))).toBeVisible()
    expect(
      screen.queryByText('TEST ONLY private route failure'),
    ).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Русский' }))
    expect(requests).toHaveLength(2)
    await user.click(
      within(details).getByRole('button', { name: text('states.retry') }),
    )
    expect(
      await within(details).findByText(
        `${formatMinutes(2, 'ru')} · ${text('codes.route_status.known')}`,
      ),
    ).toBeVisible()
    expect(requests.map((request) => request.path)).toEqual([
      '/api/recommendations',
      '/api/route',
      '/api/route',
    ])
    expect(requests[2].body).toMatchObject({
      origin: requests[1].body.origin,
      destination: requests[1].body.destination,
      locale: 'ru',
    })
    expect(requests[2].body.request_id).not.toBe(requests[1].body.request_id)
    expect(
      within(card).getByRole('button', { name: text('card.selected') }),
    ).toHaveAttribute('aria-pressed', 'true')
  })

  it('ignores an old walking response after another card is selected and clears route details when the origin changes', async () => {
    const routes: {
      request: CapturedRequest
      finish: (response: Response) => void
    }[] = []
    transport((request) => {
      if (request.path === '/api/recommendations') {
        const response = place(request.body)
        const second = structuredClone(response.items[0])
        second.poi.id = 'test:poi-002'
        second.poi.name = 'TEST ONLY second source name'
        second.poi.location = { latitude: 51.14, longitude: 71.44 }
        response.items.push(second)
        return json(response)
      }
      if (request.path === '/api/route')
        return new Promise((finish) => routes.push({ request, finish }))
      throw new Error('Unexpected synthetic endpoint')
    })
    render(<App />)
    const user = await fillQuery()
    await user.type(screen.getByLabelText(text('location.latitude')), '51.13')
    await user.type(screen.getByLabelText(text('location.longitude')), '71.43')
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    const first = await screen.findByRole('article', { name: placeName })
    const second = screen.getByRole('article', {
      name: 'TEST ONLY second source name',
    })
    await user.click(
      within(first).getByRole('button', { name: text('card.select') }),
    )
    await user.click(
      within(second).getByRole('button', { name: text('card.select') }),
    )
    expect(routes).toHaveLength(2)
    expect(routes[0].request.signal.aborted).toBe(true)
    const current = knownRoute(routes[1].request.body as RouteRequest)
    current.outbound.duration_seconds = 600
    current.travel_minutes_estimate = 10
    await act(async () => {
      routes[1].finish(json(current))
    })
    const details = screen.getByRole('region', { name: text('map.title') })
    expect(
      await within(details).findByText(
        `${formatMinutes(10, 'en')} · ${text('codes.route_status.known')}`,
      ),
    ).toBeVisible()
    await act(async () => {
      routes[0].finish(json(knownRoute(routes[0].request.body as RouteRequest)))
    })
    expect(
      within(details).getByText(
        `${formatMinutes(10, 'en')} · ${text('codes.route_status.known')}`,
      ),
    ).toBeVisible()
    expect(
      within(details).queryByText(
        `${formatMinutes(2, 'en')} · ${text('codes.route_status.known')}`,
      ),
    ).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(text('location.latitude')), {
      target: { value: '51.15' },
    })
    expect(
      screen.queryByRole('region', { name: text('map.title') }),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it.each(locales)(
    'keeps incomplete, unavailable and no-match outcomes distinct in %s without leaking provider prose',
    async (locale) => {
      await act(() => i18n.changeLanguage(locale))
      const statuses = ['unknown', 'unavailable', 'no_match'] as const
      const { requests } = transport(({ body }) => {
        const status = statuses[requests.length - 1]
        return json(
          {
            status,
            request_id: body.request_id,
            items: [],
            sources: [],
            warnings:
              status === 'no_match'
                ? []
                : [
                    {
                      code:
                        status === 'unknown'
                          ? 'data_unknown'
                          : 'provider_unavailable',
                      message:
                        'TEST ONLY private provider prose must not become a UI string',
                      fields: [],
                    },
                  ],
          },
          status === 'unavailable' ? 503 : 200,
        )
      })
      render(<App />)
      const user = await fillQuery(locale)
      for (const status of statuses) {
        await user.click(
          screen.getByRole('button', { name: text('search.submit', locale) }),
        )
        expect(
          await screen.findByText(
            text(`codes.response_status.${status}`, locale),
            { selector: 'strong' },
          ),
        ).toBeVisible()
        expect(
          screen.getByText(
            text(`states.${status === 'no_match' ? 'empty' : status}`, locale),
          ),
        ).toBeVisible()
        for (const other of statuses.filter((value) => value !== status)) {
          expect(
            screen.queryByText(text(`codes.response_status.${other}`, locale), {
              selector: 'strong',
            }),
          ).not.toBeInTheDocument()
        }
        expect(
          screen.queryByText(
            'TEST ONLY private provider prose must not become a UI string',
          ),
        ).not.toBeInTheDocument()
      }
    },
  )

  it.each(locales)(
    'localizes loading and safe error state in %s',
    async (locale) => {
      await act(() => i18n.changeLanguage(locale))
      let finish!: (response: Response) => void
      const { requests } = transport(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }),
      )
      render(<App />)
      const user = await fillQuery(locale)
      await user.click(
        screen.getByRole('button', { name: text('search.submit', locale) }),
      )
      expect(screen.getByText(text('states.loading', locale))).toBeVisible()
      await act(async () => {
        finish(
          new Response('<html>TEST ONLY private upstream diagnostic</html>', {
            status: 500,
            headers: { 'content-type': 'text/html' },
          }),
        )
      })
      expect(await screen.findByRole('alert')).toHaveTextContent(
        text('states.error', locale),
      )
      expect(
        screen.queryByText(/TEST ONLY private upstream diagnostic/),
      ).not.toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: text('states.retry', locale) }),
      ).toBeEnabled()
      expect(requests).toHaveLength(1)
    },
  )

  it('uses the current UI language for a pending English search and does not display its mismatched free explanation', async () => {
    let finish!: (response: Response) => void
    const { requests } = transport(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    render(<App />)
    const user = await fillQuery()
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    await user.click(screen.getByRole('button', { name: 'Русский' }))
    expect(requests[0].signal.aborted).toBe(false)
    await act(async () => {
      finish(json(place(requests[0].body)))
    })
    const card = await screen.findByRole('article', { name: placeName })
    expect(
      within(card).getByText(text('codes.reason_codes.query_match', 'ru')),
    ).toBeVisible()
    expect(within(card).queryByText(narrative)).not.toBeInTheDocument()
    expect(requests).toHaveLength(1)
  })

  it.each(['query', 'origin', 'budget', 'indoor'] as const)(
    'invalidates pending and received results when %s changes; a late response cannot replace the newer search',
    async (field) => {
      const pending: {
        request: CapturedRequest
        finish: (response: Response) => void
      }[] = []
      const { requests } = transport(
        (request) => new Promise((finish) => pending.push({ request, finish })),
      )
      render(<App />)
      const user = await fillQuery()
      await user.click(
        screen.getByRole('button', { name: text('search.submit') }),
      )
      const edit = () => {
        if (field === 'query')
          fireEvent.change(screen.getByLabelText(text('search.query')), {
            target: { value: `TEST ONLY changed query ${requests.length}` },
          })
        if (field === 'origin') {
          fireEvent.change(screen.getByLabelText(text('location.latitude')), {
            target: { value: `${51 + requests.length / 100}` },
          })
          fireEvent.change(screen.getByLabelText(text('location.longitude')), {
            target: { value: '71.43' },
          })
        }
        if (field === 'budget')
          fireEvent.change(screen.getByLabelText(text('search.budget')), {
            target: { value: `${1000 * requests.length}` },
          })
        if (field === 'indoor')
          fireEvent.click(screen.getByLabelText(text('search.indoor')))
      }
      edit()
      expect(requests[0].signal.aborted).toBe(true)
      expect(
        screen.getByRole('button', { name: text('search.submit') }),
      ).toBeEnabled()
      await user.click(
        screen.getByRole('button', { name: text('search.submit') }),
      )
      await act(async () => {
        pending[1].finish(
          json(place(pending[1].request.body, 'TEST ONLY newer source name')),
        )
      })
      expect(
        await screen.findByRole('article', {
          name: 'TEST ONLY newer source name',
        }),
      ).toBeVisible()
      await act(async () => {
        pending[0].finish(
          json(place(pending[0].request.body, 'TEST ONLY stale source name')),
        )
      })
      expect(
        screen.queryByRole('article', { name: 'TEST ONLY stale source name' }),
      ).not.toBeInTheDocument()
      expect(
        screen.getByRole('article', { name: 'TEST ONLY newer source name' }),
      ).toBeVisible()
      edit()
      expect(screen.queryByRole('article')).not.toBeInTheDocument()
      expect(requests).toHaveLength(2)
    },
  )

  it('lets a person deny GPS, enter a manual point, and complete a real API search', async () => {
    const getCurrentPosition = vi.fn(
      (_success, reject: PositionErrorCallback) =>
        reject({ code: 1 } as GeolocationPositionError),
    )
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    })
    const { requests } = transport(({ body }) => json(place(body)))
    render(<App />)
    const user = await fillQuery()
    expect(getCurrentPosition).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: text('location.gps') }))
    expect(screen.getByText(text('location.gpsDenied'))).toBeVisible()
    await user.type(screen.getByLabelText(text('location.latitude')), '51.13')
    await user.type(screen.getByLabelText(text('location.longitude')), '71.43')
    await user.click(
      screen.getByRole('button', { name: text('search.submit') }),
    )
    expect(
      await screen.findByRole('article', { name: placeName }),
    ).toBeVisible()
    expect(requests[0].body).toMatchObject({
      origin: { latitude: 51.13, longitude: 71.43 },
      explicit_fields: ['origin'],
    })
    expect(getCurrentPosition).toHaveBeenCalledOnce()
  })
})
