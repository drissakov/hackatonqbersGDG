import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import { StreetMap } from './StreetMap'

const origin = { latitude: 51.13, longitude: 71.43 }
const destinations = [
  {
    id: 'synthetic-east',
    name: 'TEST ONLY east',
    location: { latitude: 51.14, longitude: 71.47 },
  },
  {
    id: 'synthetic-west',
    name: 'TEST ONLY west',
    location: { latitude: 51.15, longitude: 71.4 },
  },
]

function props() {
  return {
    origin,
    destinations,
    selectedId: destinations[0].id,
    onSelect: vi.fn(),
  }
}

function tileLayout(container: HTMLElement) {
  return [...container.querySelectorAll('.street-map-tiles img')].map(
    (tile) => [tile.getAttribute('src'), tile.getAttribute('style')],
  )
}

beforeEach(async () => {
  await act(() => i18n.changeLanguage('en'))
})
afterEach(() => vi.unstubAllGlobals())

describe('keyless street map', () => {
  it('renders actual visible street tiles, source markers and attribution without route lines', () => {
    const values = props()
    const { container } = render(<StreetMap {...values} />)
    const tiles = [...container.querySelectorAll('.street-map-tiles img')]
    expect(tiles.length).toBeGreaterThan(0)
    expect(tiles.length).toBeLessThanOrEqual(15)
    for (const tile of tiles) {
      expect(tile.getAttribute('src')).toMatch(
        /^https:\/\/tile\.openstreetmap\.org\/\d+\/\d+\/\d+\.png$/,
      )
      expect(tile).toHaveAttribute(
        'referrerpolicy',
        'strict-origin-when-cross-origin',
      )
    }
    expect(
      screen.getByRole('link', { name: 'OpenStreetMap contributors' }),
    ).toHaveAttribute('href', 'https://www.openstreetmap.org/copyright')
    expect(
      screen.getByRole('img', { name: i18n.t('map.origin') }),
    ).toBeVisible()
    const first = screen.getByRole('button', { name: /TEST ONLY east/ })
    const second = screen.getByRole('button', { name: /TEST ONLY west/ })
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(second).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(second)
    expect(values.onSelect).toHaveBeenCalledWith(destinations[1].id)
    expect(container.querySelector('svg, polyline, path')).toBeNull()
    for (const marker of [first, second]) {
      const style = (marker as HTMLElement).style
      expect(parseFloat(style.left)).toBeGreaterThan(24)
      expect(parseFloat(style.left)).toBeLessThan(776)
      expect(parseFloat(style.top)).toBeGreaterThan(24)
      expect(parseFloat(style.top)).toBeLessThan(396)
    }
  })

  it('supports zoom, keyboard pan and fit while locale and selection preserve the viewport', async () => {
    const values = props()
    const view = render(<StreetMap {...values} />)
    const map = screen.getByRole('region', { name: i18n.t('map.streetView') })
    const fitted = tileLayout(view.container)
    fireEvent.keyDown(map, { key: 'ArrowRight' })
    const panned = tileLayout(view.container)
    expect(panned).not.toEqual(fitted)
    view.rerender(<StreetMap {...values} selectedId={destinations[1].id} />)
    await act(() => i18n.changeLanguage('ru'))
    expect(tileLayout(view.container)).toEqual(panned)
    fireEvent.click(screen.getByRole('button', { name: i18n.t('map.zoomIn') }))
    expect(tileLayout(view.container)).not.toEqual(panned)
    fireEvent.click(screen.getByRole('button', { name: i18n.t('map.fitAll') }))
    expect(tileLayout(view.container)).toEqual(fitted)
    fireEvent.keyDown(map, { key: '-' })
    expect(tileLayout(view.container)).not.toEqual(fitted)
  })

  it('pans with a touch pointer without starting a drag on marker buttons', () => {
    vi.stubGlobal(
      'PointerEvent',
      class extends MouseEvent {
        readonly pointerId: number
        constructor(type: string, options: PointerEventInit) {
          super(type, options)
          this.pointerId = options.pointerId ?? 1
        }
      },
    )
    const view = render(<StreetMap {...props()} />)
    const map = screen.getByRole('region', { name: i18n.t('map.streetView') })
    const fitted = tileLayout(view.container)
    fireEvent.pointerDown(
      screen.getByRole('button', { name: /TEST ONLY east/ }),
      { pointerId: 1, button: 0, clientX: 100, clientY: 100 },
    )
    fireEvent.pointerMove(map, { pointerId: 1, clientX: 160, clientY: 140 })
    expect(tileLayout(view.container)).toEqual(fitted)
    fireEvent.pointerDown(map, {
      pointerId: 1,
      button: 0,
      clientX: 100,
      clientY: 100,
    })
    fireEvent.pointerMove(map, { pointerId: 1, clientX: 160, clientY: 140 })
    expect(tileLayout(view.container)).not.toEqual(fitted)
    fireEvent.pointerUp(map, { pointerId: 1 })
  })

  it('reports failed tiles honestly and clears the status after a successful load', () => {
    const view = render(<StreetMap {...props()} />)
    const tile = view.container.querySelector('.street-map-tiles img')!
    fireEvent.error(tile)
    expect(screen.getByRole('status')).toHaveTextContent(
      i18n.t('map.tilesUnavailable'),
    )
    fireEvent.load(tile)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('fits points across the date line and wraps only visible tile columns', () => {
    const view = render(
      <StreetMap
        origin={{ latitude: 0, longitude: 179.9 }}
        destinations={[
          {
            id: 'synthetic-date-line',
            name: 'TEST ONLY date line',
            location: { latitude: 0, longitude: -179.9 },
          },
        ]}
        selectedId={null}
        onSelect={vi.fn()}
      />,
    )
    const tiles = [
      ...view.container.querySelectorAll('.street-map-tiles img'),
    ].map((tile) => new URL(tile.getAttribute('src')!).pathname.split('/'))
    const zoom = Number(tiles[0][1])
    const columns = tiles.map((tile) => Number(tile[2]))
    expect(zoom).toBeGreaterThan(10)
    expect(columns).toContain(0)
    expect(columns).toContain(2 ** zoom - 1)
    expect(columns.every((column) => column >= 0 && column < 2 ** zoom)).toBe(
      true,
    )
    const marker = screen.getByRole('button', { name: /TEST ONLY date line/ })
    expect(parseFloat(marker.style.left)).toBeGreaterThan(24)
    expect(parseFloat(marker.style.left)).toBeLessThan(776)
  })

  it('fits a resized viewport and disconnects its size observer on unmount', () => {
    const observe = vi.fn(),
      disconnect = vi.fn()
    let resized!: () => void
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: () => void) {
          resized = callback
        }
        observe = observe
        disconnect = disconnect
      },
    )
    const view = render(<StreetMap {...props()} />)
    const map = screen.getByRole('region', { name: i18n.t('map.streetView') })
    vi.spyOn(map, 'getBoundingClientRect').mockReturnValue({
      width: 400,
      height: 240,
    } as DOMRect)
    act(() => resized())
    expect(observe).toHaveBeenCalledWith(map)
    for (const marker of view.container.querySelectorAll(
      '.street-map-marker, .street-map-origin',
    )) {
      const style = (marker as HTMLElement).style
      expect(parseFloat(style.left)).toBeGreaterThan(24)
      expect(parseFloat(style.left)).toBeLessThan(376)
      expect(parseFloat(style.top)).toBeGreaterThan(24)
      expect(parseFloat(style.top)).toBeLessThan(216)
    }
    view.unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })
})
