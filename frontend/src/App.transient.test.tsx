import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import partial from '../../contracts/examples/transient-event-partial.test.json'
import listing from '../../contracts/examples/transient-event-listing.test.json'
import unknown from '../../contracts/examples/transient-event-unknown.test.json'
import unavailable from '../../contracts/examples/transient-event-unavailable.test.json'
import routeFixture from '../../contracts/examples/route-known.test.json'
import App from './App'
import i18n from './i18n'
import type { RouteRequest, TransientEventSearchResponse } from './lib/types'

beforeEach(async () => {
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  vi.stubEnv('VITE_API_BASE_URL', '/api')
  await act(() => i18n.changeLanguage('en'))
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

async function search(
  fixture: unknown,
  status = 200,
  routeRequests?: RouteRequest[],
) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (url, options) => {
      if (url === '/api/health')
        return new Response('{"status":"ok"}', {
          headers: { 'content-type': 'application/json' },
        })
      if (url === '/api/route' && typeof options?.body === 'string') {
        const body = JSON.parse(options.body) as RouteRequest
        routeRequests?.push(body)
        return new Response(
          JSON.stringify({
            ...routeFixture,
            request_id: body.request_id,
            travel_minutes_estimate: 2,
            return_route: {
              status: 'not_requested',
              reason: 'not_requested',
              duration_seconds: null,
              distance_meters: null,
              provenance: null,
            },
          }),
          { headers: { 'content-type': 'application/json' } },
        )
      }
      if (url !== '/api/events/search' || typeof options?.body !== 'string')
        throw new Error('Unexpected synthetic request')
      const body = JSON.parse(options.body) as { request_id: string }
      return new Response(
        JSON.stringify({ ...(fixture as object), request_id: body.request_id }),
        { status, headers: { 'content-type': 'application/json' } },
      )
    }),
  )
  const user = userEvent.setup()
  render(<App />)
  await user.click(screen.getByRole('button', { name: 'Events' }))
  await user.type(
    screen.getByRole('textbox', { name: 'What would you like to do?' }),
    'TEST ONLY event search',
  )
  if (routeRequests) {
    await user.type(screen.getByLabelText(i18n.t('location.latitude')), '51.13')
    await user.type(
      screen.getByLabelText(i18n.t('location.longitude')),
      '71.43',
    )
  }
  await user.click(screen.getByRole('button', { name: 'Find events' }))
  return user
}

function combinedResponse() {
  const response = structuredClone(partial) as TransientEventSearchResponse
  const card = response.items[0]
  response.listings = [
    {
      ...structuredClone(listing.listings[0]),
      event_id: card.event.id,
      title: card.event.title,
      venue_name: card.event.venue_name,
      venue_address: card.event.venue_address,
      venue: structuredClone(card.session.venue),
      status: 'discovered',
      sessions: [structuredClone(card.session)],
      schedule_hints: [],
      missing_fields: [...card.session.missing_fields],
    },
  ]
  return response
}

describe('published transient events through the real frontend transport', () => {
  it('labels regular price_from as a lower bound and avoids repeating a fully represented event listing', async () => {
    const response = combinedResponse()
    response.items[0].session.price_kind = 'regular'
    response.listings[0].sessions[0].price_kind = 'regular'
    await search(response)
    const card = await screen.findByRole('article')
    expect(within(card).getByText(/From.*1,000/)).toBeVisible()
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(
      screen.getAllByRole('heading', { name: response.items[0].event.title }),
    ).toHaveLength(1)
  })

  it('keeps promotional lower bounds and their source conditions explicit', async () => {
    const response = structuredClone(partial) as TransientEventSearchResponse
    response.items[0].session.price_kind = 'promotion'
    response.items[0].session.price_conditions =
      'TEST ONLY limited promotion conditions'
    await search(response)
    const card = await screen.findByRole('article')
    expect(
      within(card).getByText(/From.*1,000.*Promotional price/),
    ).toBeVisible()
    expect(
      within(card).getByText('TEST ONLY limited promotion conditions'),
    ).toBeVisible()
  })

  it('preserves additional withheld sessions and listing diagnostics without offering them for routing', async () => {
    const response = combinedResponse()
    response.listings[0].schedule_hints = [
      'TEST ONLY additional schedule diagnostic',
    ]
    response.listings[0].sessions.push({
      ...structuredClone(response.items[0].session),
      session_id: 'synthetic:withheld-session',
      venue_name: 'TEST ONLY withheld session venue',
      recommendation_candidate: false,
      status: 'cancelled',
      exclusion_reasons: ['cancelled'],
    })
    await search(response)
    expect(
      await screen.findByText('TEST ONLY withheld session venue'),
    ).toBeVisible()
    expect(
      screen.getByText('TEST ONLY additional schedule diagnostic'),
    ).toBeVisible()
    expect(screen.getByText(i18n.t('events.notAlternative'))).toBeVisible()
    expect(
      screen.getAllByRole('button', { name: i18n.t('card.select') }),
    ).toHaveLength(1)
  })
  it('routes only the explicitly selected transient session using its independent venue coordinates', async () => {
    const response = structuredClone(partial) as TransientEventSearchResponse
    const point = { latitude: 51.14, longitude: 71.44 }
    response.sources.push({
      ...response.sources[0],
      source_id: 'synthetic:venue-source',
      url: 'https://example.invalid/test-only-independent-venue',
    })
    response.items[0].session.venue = {
      poi_id: 'synthetic:venue',
      location: point,
      basis: 'name_address_astana_permitted_poi',
      source_ids: ['synthetic:venue-source'],
      source_urls: [response.sources[1].url],
      coordinate_accuracy: 'unknown',
      geography_basis: 'central_astana_bbox',
    }
    const routes: RouteRequest[] = []
    const user = await search(response, 200, routes)
    await screen.findByRole('article')
    expect(routes).toEqual([])
    await user.click(
      screen.getByRole('button', { name: i18n.t('card.select') }),
    )
    expect(await screen.findByRole('link', { name: '2ГИС' })).toHaveAttribute(
      'href',
      'https://dev.2gis.ru',
    )
    expect(routes).toEqual([
      expect.objectContaining({
        origin: { latitude: 51.13, longitude: 71.43 },
        destination: point,
        return_to_start: false,
      }),
    ])
  })
  it('renders a conditional session card, price-from, explanation and sources', async () => {
    await search(partial)
    const card = await screen.findByRole('article')
    expect(
      within(card).getByRole('heading', { name: partial.items[0].event.title }),
    ).toBeVisible()
    expect(within(card).getByText(partial.items[0].explanation)).toBeVisible()
    expect(within(card).getByText(/From.*1,000/)).toBeVisible()
    expect(
      within(card).getByText('Independent source verification'),
    ).toBeVisible()
    expect(
      within(card).getAllByText('Ticket availability').length,
    ).toBeGreaterThan(0)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.queryByText('No match', { selector: 'strong' }),
    ).not.toBeInTheDocument()
  })

  it('renders a listing separately without presenting it as a routable alternative', async () => {
    await search(listing)
    expect(
      await screen.findByRole('heading', { name: listing.listings[0].title }),
    ).toBeVisible()
    expect(screen.getByText(i18n.t('events.listing'))).toBeVisible()
    expect(screen.getByText(i18n.t('events.noSession'))).toBeVisible()
    expect(
      screen.queryByRole('button', { name: i18n.t('card.select') }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: i18n.t('map.title') }),
    ).not.toBeInTheDocument()
  })

  it.each([
    [unknown, 200],
    [unavailable, 503],
  ])(
    'shows the shared $0.status state without a generic transport error',
    async (fixture, status) => {
      const user = await search(fixture, status)
      expect(
        await screen.findByText(
          i18n.t(`codes.response_status.${fixture.status}`),
          { selector: 'strong' },
        ),
      ).toBeVisible()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(screen.queryByRole('article')).not.toBeInTheDocument()
      await user.click(
        screen.getByText(i18n.t('source.title'), { selector: 'summary' }),
      )
      expect(
        screen.getByRole('link', { name: fixture.sources[0].url }),
      ).toBeVisible()
    },
  )
})
