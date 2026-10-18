import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MapPicker } from './MapPicker'

const mock = vi.hoisted(() => ({
  load: vi.fn(),
  mapConstructor: vi.fn(),
  markerConstructor: vi.fn(),
  destroyMap: vi.fn(),
  destroyMarker: vi.fn(),
  handlers: new Map<string, (event: { lngLat: number[] }) => void>(),
}))

vi.mock('@2gis/mapgl', () => ({ load: mock.load }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  mock.handlers.clear()
  mock.load.mockResolvedValue({
    Map: class {
      constructor(container: HTMLElement, options: unknown) {
        mock.mapConstructor(container, options)
      }
      on(type: string, handler: (event: { lngLat: number[] }) => void) {
        mock.handlers.set(type, handler)
      }
      destroy() {
        mock.destroyMap()
      }
    },
    Marker: class {
      constructor(map: unknown, options: unknown) {
        mock.markerConstructor(map, options)
      }
      destroy() {
        mock.destroyMarker()
      }
    },
  })
})

describe('optional public MapGL picker', () => {
  it('treats the map viewport as display only and reads clicks as longitude/latitude', async () => {
    const onSelect = vi.fn()
    const { unmount } = render(
      <MapPicker
        publicKey="synthetic-public-test-key"
        latitude=""
        longitude=""
        onSelect={onSelect}
      />,
    )
    await waitFor(() => expect(mock.mapConstructor).toHaveBeenCalledOnce())
    expect(onSelect).not.toHaveBeenCalled()
    expect(mock.markerConstructor).not.toHaveBeenCalled()
    act(() => mock.handlers.get('click')?.({ lngLat: [71.43, 51.13] }))
    expect(onSelect).toHaveBeenCalledWith(51.13, 71.43)
    unmount()
    expect(mock.destroyMap).toHaveBeenCalledOnce()
  })

  it('updates and releases the marker and map during edits and unmount', async () => {
    const { rerender, unmount } = render(
      <MapPicker
        publicKey="synthetic-public-test-key"
        latitude="51"
        longitude="71"
        onSelect={vi.fn()}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledOnce())
    expect(mock.markerConstructor).toHaveBeenCalledWith(expect.anything(), {
      coordinates: [71, 51],
    })
    rerender(
      <MapPicker
        publicKey="synthetic-public-test-key"
        latitude="52"
        longitude="72"
        onSelect={vi.fn()}
      />,
    )
    await waitFor(() => expect(mock.markerConstructor).toHaveBeenCalledTimes(2))
    expect(mock.destroyMarker).toHaveBeenCalledOnce()
    unmount()
    expect(mock.destroyMarker).toHaveBeenCalledTimes(2)
    expect(mock.destroyMap).toHaveBeenCalledOnce()
  })

  it('reports a failed optional loader without exposing provider errors', async () => {
    mock.load.mockRejectedValue(new Error('Synthetic provider details'))
    render(
      <MapPicker
        publicKey="synthetic-public-test-key"
        latitude=""
        longitude=""
        onSelect={vi.fn()}
      />,
    )
    expect(
      await screen.findByText('location.mapUnavailable'),
    ).toBeInTheDocument()
    expect(
      screen.queryByText('Synthetic provider details'),
    ).not.toBeInTheDocument()
    expect(mock.mapConstructor).not.toHaveBeenCalled()
  })
})
