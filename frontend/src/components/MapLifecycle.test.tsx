import { act, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import { DestinationMap } from './DestinationMap'
import { MapPicker } from './MapPicker'

type TestMap = {
  handlers: Map<string, (event: { lngLat: number[] }) => void>
  destroy: ReturnType<typeof vi.fn>
  fitBounds: ReturnType<typeof vi.fn>
}
const mock = vi.hoisted(() => ({
  load: vi.fn(),
  mapConstructor: vi.fn(),
  markerConstructor: vi.fn(),
  maps: [] as TestMap[],
  markers: [] as { destroy: ReturnType<typeof vi.fn> }[],
  failBounds: false,
  failMarker: false,
}))
vi.mock('@2gis/mapgl', () => ({ load: mock.load }))

const origin = { latitude: 51.13, longitude: 71.43 }
const destinations = [
  {
    id: 'one',
    name: 'TEST ONLY first',
    location: { latitude: 51.2, longitude: 71.2 },
  },
  {
    id: 'two',
    name: 'TEST ONLY second',
    location: { latitude: 51.1, longitude: 71.6 },
  },
  {
    id: 'three',
    name: 'TEST ONLY third',
    location: { latitude: 51.3, longitude: 71.5 },
  },
  {
    id: 'four',
    name: 'TEST ONLY excluded fourth',
    location: { latitude: 52, longitude: 72 },
  },
]

beforeEach(async () => {
  vi.clearAllMocks()
  mock.maps.length = 0
  mock.markers.length = 0
  mock.failBounds = false
  mock.failMarker = false
  vi.stubEnv('VITE_TWOGIS_MAP_KEY', 'synthetic-public-test-key')
  await act(() => i18n.changeLanguage('en'))
  mock.load.mockResolvedValue({
    Map: class {
      handlers = new Map<string, (event: { lngLat: number[] }) => void>()
      destroy = vi.fn()
      fitBounds = vi.fn(() => {
        if (mock.failBounds)
          throw new Error('TEST ONLY private provider bounds failure')
      })
      constructor(container: HTMLElement, options: unknown) {
        mock.mapConstructor(container, options)
        mock.maps.push(this)
      }
      on(type: string, handler: (event: { lngLat: number[] }) => void) {
        this.handlers.set(type, handler)
      }
    },
    Marker: class {
      destroy = vi.fn()
      constructor(map: unknown, options: unknown) {
        if (mock.failMarker)
          throw new Error('TEST ONLY private provider marker failure')
        mock.markerConstructor(map, options)
        mock.markers.push(this)
      }
    },
  })
})

afterEach(() => vi.unstubAllEnvs())

describe('optional MapGL lifecycle', () => {
  it('recreates the selected-point marker after a public map key changes', async () => {
    const onSelect = vi.fn()
    const view = render(
      <MapPicker
        publicKey="TEST ONLY first key"
        latitude="51.13"
        longitude="71.43"
        onSelect={onSelect}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledOnce())
    view.rerender(
      <MapPicker
        publicKey="TEST ONLY replacement key"
        latitude="51.13"
        longitude="71.43"
        onSelect={onSelect}
      />,
    )
    await waitFor(() => expect(mock.mapConstructor).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledTimes(2))
    expect(mock.markerConstructor.mock.calls[1][1]).toEqual({
      coordinates: [71.43, 51.13],
    })
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    expect(mock.markers[0].destroy).toHaveBeenCalledOnce()
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('releases a failed picker immediately and ignores its stale click handler', async () => {
    const onSelect = vi.fn()
    const view = render(
      <MapPicker
        publicKey="TEST ONLY public key"
        latitude="51.13"
        longitude="71.43"
        onSelect={onSelect}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledOnce())
    act(() => mock.maps[0].handlers.get('error')?.({ lngLat: [] }))
    expect(screen.getByText(i18n.t('location.mapUnavailable'))).toBeVisible()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    expect(mock.markers[0].destroy).toHaveBeenCalledOnce()
    act(() => mock.maps[0].handlers.get('click')?.({ lngLat: [71.5, 51.2] }))
    expect(onSelect).not.toHaveBeenCalled()
    view.unmount()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    expect(mock.markers[0].destroy).toHaveBeenCalledOnce()
  })

  it('contains picker marker construction failure so manual coordinates remain usable', async () => {
    mock.failMarker = true
    render(
      <MapPicker
        publicKey="TEST ONLY public key"
        latitude="51.13"
        longitude="71.43"
        onSelect={vi.fn()}
      />,
    )
    expect(
      await screen.findByText(i18n.t('location.mapUnavailable')),
    ).toBeVisible()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    expect(
      screen.queryByText('TEST ONLY private provider marker failure'),
    ).not.toBeInTheDocument()
  })

  it('does not construct maps from a late loader after both optional views have unmounted', async () => {
    const provider = await mock.load()
    let complete!: (api: unknown) => void
    mock.load.mockClear().mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const view = render(
      <>
        <MapPicker
          publicKey="TEST ONLY public key"
          latitude="51.13"
          longitude="71.43"
          onSelect={vi.fn()}
        />
        <DestinationMap
          origin={origin}
          destinations={destinations}
          selectedId={null}
          onSelect={vi.fn()}
        />
      </>,
    )
    await waitFor(() => expect(mock.load).toHaveBeenCalledTimes(2))
    await act(() => i18n.changeLanguage('kk'))
    expect(mock.load).toHaveBeenCalledTimes(2)
    view.unmount()
    await act(async () => {
      complete(provider)
    })
    expect(mock.mapConstructor).not.toHaveBeenCalled()
    expect(mock.markerConstructor).not.toHaveBeenCalled()
  })

  it('fits the origin and at most three alternatives, and language or selection does not reload the provider', async () => {
    const onSelect = vi.fn()
    const view = render(
      <DestinationMap
        origin={origin}
        destinations={destinations}
        selectedId={null}
        onSelect={onSelect}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledTimes(4))
    expect(
      mock.markerConstructor.mock.calls.map((call) => call[1].coordinates),
    ).toEqual([
      [71.43, 51.13],
      [71.2, 51.2],
      [71.6, 51.1],
      [71.5, 51.3],
    ])
    const [bounds, options] = mock.maps[0].fitBounds.mock.calls[0]
    for (const point of [
      origin,
      ...destinations.slice(0, 3).map((item) => item.location),
    ]) {
      expect(bounds.southWest[0]).toBeLessThanOrEqual(point.longitude)
      expect(bounds.southWest[1]).toBeLessThanOrEqual(point.latitude)
      expect(bounds.northEast[0]).toBeGreaterThanOrEqual(point.longitude)
      expect(bounds.northEast[1]).toBeGreaterThanOrEqual(point.latitude)
    }
    expect(bounds.northEast[0]).toBeLessThan(destinations[3].location.longitude)
    expect(bounds.northEast[1]).toBeLessThan(destinations[3].location.latitude)
    expect(options).toEqual(expect.objectContaining({ maxZoom: 14 }))
    await act(() => i18n.changeLanguage('ru'))
    view.rerender(
      <DestinationMap
        origin={origin}
        destinations={destinations}
        selectedId="two"
        onSelect={onSelect}
      />,
    )
    expect(mock.load).toHaveBeenCalledOnce()
    expect(mock.mapConstructor).toHaveBeenCalledOnce()
    expect(screen.queryByText(destinations[3].name)).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /TEST ONLY second/ }),
    ).toHaveAttribute('aria-pressed', 'true')
  })

  it('releases all destination markers and the map after provider failure while preserving coordinate fallback', async () => {
    const view = render(
      <DestinationMap
        origin={origin}
        destinations={destinations}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledTimes(4))
    act(() => mock.maps[0].handlers.get('error')?.({ lngLat: [] }))
    expect(screen.getByText(i18n.t('map.unavailable'))).toBeVisible()
    expect(
      screen.getByRole('img', { name: i18n.t('map.coordinateView') }),
    ).toBeVisible()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    for (const marker of mock.markers)
      expect(marker.destroy).toHaveBeenCalledOnce()
    view.unmount()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
  })

  it('releases a partially initialized destination map if viewport fitting throws', async () => {
    mock.failBounds = true
    render(
      <DestinationMap
        origin={origin}
        destinations={destinations}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByText(i18n.t('map.unavailable'))).toBeVisible()
    expect(mock.maps[0].destroy).toHaveBeenCalledOnce()
    for (const marker of mock.markers)
      expect(marker.destroy).toHaveBeenCalledOnce()
    expect(
      screen.queryByText('TEST ONLY private provider bounds failure'),
    ).not.toBeInTheDocument()
  })
})
