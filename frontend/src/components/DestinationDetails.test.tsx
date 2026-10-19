import { act, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import { getRoute, parseRouteResponse } from '../lib/api'
import { formatMinutes } from '../lib/format'
import type { RouteResponse } from '../lib/types'
import { DestinationDetails } from './DestinationDetails'
import routeFixture from '../../../contracts/examples/route-known.test.json'

vi.mock('../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
  getRoute: vi.fn(),
}))

const origin = { latitude: 51.13, longitude: 71.43 }
const destinations = [
  {
    id: 'test-only',
    name: 'TEST ONLY source destination',
    location: { latitude: 51.14, longitude: 71.44 },
  },
]

function props() {
  return {
    destinations,
    origin,
    returnToStart: true,
    locale: 'en' as const,
    selectedId: destinations[0].id,
    onSelect: vi.fn(),
    synthetic: false,
  }
}

beforeEach(async () => {
  vi.clearAllMocks()
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
  await act(() => i18n.changeLanguage('en'))
})

afterEach(() => vi.unstubAllEnvs())

describe('selected walking route details', () => {
  it.each(['known', 'unknown', 'unavailable'] as const)(
    'keeps outbound and return-leg %s status and duration separate',
    async (status) => {
      const response = structuredClone(routeFixture) as RouteResponse
      response.status = status
      response.warnings = []
      if (status === 'known') {
        response.return_route.duration_seconds = 300
        response.travel_minutes_estimate = 7
      } else {
        response.travel_minutes_estimate = null
        response.return_route = {
          status,
          distance_meters: null,
          duration_seconds: null,
          provenance: null,
          reason: status === 'unknown' ? 'route_not_found' : 'network_error',
        }
      }
      vi.mocked(getRoute).mockResolvedValue(parseRouteResponse(response))
      render(<DestinationDetails {...props()} />)
      const outbound = await screen.findByText(
        `${formatMinutes(2, 'en')} · ${i18n.t('codes.route_status.known')}`,
      )
      expect(outbound).toBeVisible()
      const returning = screen.getByText(
        `${formatMinutes(status === 'known' ? 5 : null, 'en')} · ${i18n.t(`codes.route_status.${status}`)}`,
      )
      expect(returning).toBeVisible()
      expect(
        within(outbound.parentElement!).getByText(i18n.t('route.walking')),
      ).toBeVisible()
      expect(
        within(returning.parentElement!).getByText(i18n.t('route.return')),
      ).toBeVisible()
      expect(
        screen.getByText(i18n.t('route.approximateDestination')),
      ).toBeVisible()
      expect(screen.getAllByRole('link', { name: '2GIS' })).toHaveLength(
        status === 'known' ? 2 : 1,
      )
      expect(getRoute).toHaveBeenCalledOnce()
      expect(getRoute).toHaveBeenCalledWith(
        expect.objectContaining({
          origin,
          destination: destinations[0].location,
          return_to_start: true,
          locale: 'en',
        }),
        expect.any(AbortSignal),
      )
    },
  )

  it('keeps a pending route on language change and renders the completed legs in the current UI language', async () => {
    let complete!: (response: RouteResponse) => void
    vi.mocked(getRoute).mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const view = render(<DestinationDetails {...props()} />)
    expect(screen.getByText(i18n.t('route.loading'))).toBeVisible()
    const signal = vi.mocked(getRoute).mock.calls[0][1]!
    await act(() => i18n.changeLanguage('ru'))
    view.rerender(<DestinationDetails {...props()} locale="ru" />)
    expect(signal.aborted).toBe(false)
    expect(getRoute).toHaveBeenCalledOnce()
    expect(screen.getByText(i18n.t('route.loading'))).toBeVisible()
    await act(async () => {
      complete(parseRouteResponse(routeFixture))
    })
    expect(
      await screen.findAllByText(
        `${formatMinutes(2, 'ru')} · ${i18n.t('codes.route_status.known')}`,
      ),
    ).toHaveLength(2)
    expect(getRoute).toHaveBeenCalledOnce()
  })
})
