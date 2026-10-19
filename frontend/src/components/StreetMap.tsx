import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Coordinates } from '../lib/types'
import type { Destination } from './DestinationDetails'

type Point = { x: number; y: number }
type View = Point & { zoom: number }
type Size = { width: number; height: number }

const TILE_SIZE = 256
const MIN_ZOOM = 2
const MAX_ZOOM = 19
const LATITUDE_LIMIT = 85.05112878
const wrap = (value: number) => ((value % 1) + 1) % 1
const worldDelta = (value: number) => wrap(value + 0.5) - 0.5
const scaleAt = (zoom: number) => TILE_SIZE * 2 ** zoom

function validPoint(point: Coordinates): boolean {
  return (
    Number.isFinite(point.latitude) &&
    Number.isFinite(point.longitude) &&
    Math.abs(point.latitude) <= 90 &&
    Math.abs(point.longitude) <= 180
  )
}

function project(point: Coordinates): Point {
  const latitude = Math.max(
    -LATITUDE_LIMIT,
    Math.min(LATITUDE_LIMIT, point.latitude),
  )
  const sine = Math.sin((latitude * Math.PI) / 180)
  return {
    x: wrap((point.longitude + 180) / 360),
    y: Math.max(
      0,
      Math.min(1, 0.5 - Math.log((1 + sine) / (1 - sine)) / (4 * Math.PI)),
    ),
  }
}

function bounded(view: View, size: Size): View {
  const margin = Math.min(0.5, size.height / (2 * scaleAt(view.zoom)))
  return {
    ...view,
    x: wrap(view.x),
    y: Math.max(margin, Math.min(1 - margin, view.y)),
  }
}

function fitPoints(points: Point[], size: Size): View {
  if (!points.length) return { x: 0.5, y: 0.5, zoom: MIN_ZOOM }
  const xs = points.map(
    (point) => points[0].x + worldDelta(point.x - points[0].x),
  )
  const ys = points.map((point) => point.y)
  const minX = Math.min(...xs),
    maxX = Math.max(...xs)
  const minY = Math.min(...ys),
    maxY = Math.max(...ys)
  const zoom = Math.max(
    MIN_ZOOM,
    Math.min(
      16,
      Math.floor(
        Math.log2(
          Math.min(
            Math.max(1, size.width - 96) / (TILE_SIZE * (maxX - minX)),
            Math.max(1, size.height - 96) / (TILE_SIZE * (maxY - minY)),
          ),
        ),
      ),
    ),
  )
  return bounded({ x: (minX + maxX) / 2, y: (minY + maxY) / 2, zoom }, size)
}

/** Visible street tiles and source coordinates only; no route geometry is inferred. */
export function StreetMap({
  origin,
  destinations,
  selectedId,
  onSelect,
}: {
  origin: Coordinates | null
  destinations: Destination[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const { t } = useTranslation()
  const container = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<Size>({ width: 800, height: 420 })
  const markers = destinations.flatMap((destination, index) =>
    destination.location && validPoint(destination.location)
      ? [{ ...destination, location: destination.location, index }]
      : [],
  )
  const validOrigin = origin && validPoint(origin) ? origin : null
  const pointKey = JSON.stringify([
    ...(validOrigin ? [validOrigin] : []),
    ...markers.map((marker) => marker.location),
  ])
  const points = (JSON.parse(pointKey) as Coordinates[]).map(project)
  const hasPoints = points.length > 0
  const fitted = fitPoints(points, size)
  const viewKey = `${pointKey}:${size.width}:${size.height}`
  const [customView, setCustomView] = useState<{
    key: string
    view: View
  } | null>(null)
  const view = customView?.key === viewKey ? customView.view : fitted
  const [failedTiles, setFailedTiles] = useState<Set<string>>(() => new Set())
  const drag = useRef<{ id: number; x: number; y: number; view: View } | null>(
    null,
  )
  const lastWheel = useRef(-Infinity)

  function updateView(change: (previous: View) => View) {
    setCustomView((previous) => ({
      key: viewKey,
      view: bounded(
        change(previous?.key === viewKey ? previous.view : fitted),
        size,
      ),
    }))
  }

  function zoomBy(step: number, offset: Point = { x: 0, y: 0 }) {
    updateView((previous) => {
      const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, previous.zoom + step))
      return {
        zoom,
        x:
          previous.x +
          offset.x / scaleAt(previous.zoom) -
          offset.x / scaleAt(zoom),
        y:
          previous.y +
          offset.y / scaleAt(previous.zoom) -
          offset.y / scaleAt(zoom),
      }
    })
  }

  const handleWheel = useEffectEvent((event: WheelEvent) => {
    event.preventDefault()
    if (!event.deltaY || event.timeStamp - lastWheel.current < 120) return
    lastWheel.current = event.timeStamp
    const rect = container.current!.getBoundingClientRect()
    zoomBy(event.deltaY < 0 ? 1 : -1, {
      x: event.clientX - rect.left - size.width / 2,
      y: event.clientY - rect.top - size.height / 2,
    })
  })

  useEffect(() => {
    const element = container.current
    if (!element) return
    const measure = () => {
      const rect = element.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return
      setSize((previous) =>
        previous.width === rect.width && previous.height === rect.height
          ? previous
          : { width: rect.width, height: rect.height },
      )
    }
    measure()
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(element)
    element.addEventListener('wheel', handleWheel, { passive: false })
    return () => {
      observer?.disconnect()
      element.removeEventListener('wheel', handleWheel)
    }
  }, [hasPoints])

  if (!hasPoints) return <p>{t('map.noPoints')}</p>
  const scale = scaleAt(view.zoom)
  const left = view.x * scale - size.width / 2
  const top = view.y * scale - size.height / 2
  const count = 2 ** view.zoom
  const tiles = []
  for (
    let y = Math.max(0, Math.floor(top / TILE_SIZE));
    y <= Math.min(count - 1, Math.floor((top + size.height - 1) / TILE_SIZE));
    y++
  ) {
    for (
      let x = Math.floor(left / TILE_SIZE);
      x <= Math.floor((left + size.width - 1) / TILE_SIZE);
      x++
    ) {
      const wrappedX = ((x % count) + count) % count
      tiles.push({
        key: `${view.zoom}/${x}/${y}`,
        url: `https://tile.openstreetmap.org/${view.zoom}/${wrappedX}/${y}.png`,
        left: x * TILE_SIZE - left,
        top: y * TILE_SIZE - top,
      })
    }
  }
  const position = (coordinate: Coordinates) => {
    const point = project(coordinate)
    return {
      left: size.width / 2 + worldDelta(point.x - view.x) * scale,
      top: size.height / 2 + (point.y - view.y) * scale,
      position: 'absolute' as const,
      transform: 'translate(-50%, -50%)',
    }
  }
  const finishDrag = (id: number) => {
    if (drag.current?.id !== id) return
    drag.current = null
    if (container.current?.hasPointerCapture?.(id))
      container.current.releasePointerCapture(id)
  }

  return (
    <div
      ref={container}
      className="street-map"
      role="region"
      aria-label={t('map.streetView')}
      tabIndex={0}
      style={{
        position: 'relative',
        overflow: 'hidden',
        touchAction: 'none',
        userSelect: 'none',
      }}
      onKeyDown={(event) => {
        if (event.altKey || event.ctrlKey || event.metaKey) return
        const movement: Record<string, Point> = {
          ArrowLeft: { x: -80, y: 0 },
          ArrowRight: { x: 80, y: 0 },
          ArrowUp: { x: 0, y: -80 },
          ArrowDown: { x: 0, y: 80 },
        }
        if (movement[event.key]) {
          event.preventDefault()
          updateView((previous) => ({
            ...previous,
            x: previous.x + movement[event.key].x / scaleAt(previous.zoom),
            y: previous.y + movement[event.key].y / scaleAt(previous.zoom),
          }))
        } else if (['+', '=', '-'].includes(event.key)) {
          event.preventDefault()
          zoomBy(event.key === '-' ? -1 : 1)
        }
      }}
      onPointerDown={(event) => {
        if (
          event.button !== 0 ||
          drag.current ||
          (event.target as HTMLElement).closest('button, a')
        )
          return
        drag.current = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          view,
        }
        event.currentTarget.setPointerCapture?.(event.pointerId)
      }}
      onPointerMove={(event) => {
        const start = drag.current
        if (!start || start.id !== event.pointerId) return
        setCustomView({
          key: viewKey,
          view: bounded(
            {
              ...start.view,
              x:
                start.view.x -
                (event.clientX - start.x) / scaleAt(start.view.zoom),
              y:
                start.view.y -
                (event.clientY - start.y) / scaleAt(start.view.zoom),
            },
            size,
          ),
        })
      }}
      onPointerUp={(event) => finishDrag(event.pointerId)}
      onPointerCancel={(event) => finishDrag(event.pointerId)}
      onLostPointerCapture={() => {
        drag.current = null
      }}
    >
      <div className="street-map-tiles" aria-hidden="true">
        {tiles.map((tile) => (
          <img
            key={tile.key}
            src={tile.url}
            alt=""
            draggable={false}
            referrerPolicy="strict-origin-when-cross-origin"
            style={{
              position: 'absolute',
              left: tile.left,
              top: tile.top,
              width: TILE_SIZE,
              height: TILE_SIZE,
              maxWidth: 'none',
              pointerEvents: 'none',
            }}
            onError={() =>
              setFailedTiles((previous) =>
                previous.has(tile.url)
                  ? previous
                  : new Set([...previous, tile.url]),
              )
            }
            onLoad={() =>
              setFailedTiles((previous) => {
                if (!previous.has(tile.url)) return previous
                const next = new Set(previous)
                next.delete(tile.url)
                return next
              })
            }
          />
        ))}
      </div>
      {validOrigin ? (
        <span
          className="street-map-origin"
          role="img"
          aria-label={t('map.origin')}
          title={t('map.origin')}
          style={position(validOrigin)}
        >
          ◎<span className="street-map-origin-label">{t('map.origin')}</span>
        </span>
      ) : null}
      {markers.map((marker) => (
        <button
          key={marker.id}
          type="button"
          className={`street-map-marker${marker.id === selectedId ? ' street-map-marker-selected' : ''}`}
          style={position(marker.location)}
          aria-pressed={marker.id === selectedId}
          aria-label={`${t('map.alternative', { index: marker.index + 1 })}: ${marker.name}`}
          title={marker.name}
          onClick={() => onSelect(marker.id)}
        >
          {marker.index + 1}
        </button>
      ))}
      <div
        className="street-map-controls"
        style={{ position: 'absolute', top: 12, right: 12 }}
      >
        <button
          type="button"
          aria-label={t('map.zoomIn')}
          disabled={view.zoom === MAX_ZOOM}
          onClick={() => zoomBy(1)}
        >
          +
        </button>
        <button
          type="button"
          aria-label={t('map.zoomOut')}
          disabled={view.zoom === MIN_ZOOM}
          onClick={() => zoomBy(-1)}
        >
          −
        </button>
        <button type="button" onClick={() => setCustomView(null)}>
          {t('map.fitAll')}
        </button>
      </div>
      {tiles.some((tile) => failedTiles.has(tile.url)) ? (
        <p className="street-map-status" role="status">
          {t('map.tilesUnavailable')}
        </p>
      ) : null}
      <div
        className="street-map-attribution"
        style={{ position: 'absolute', right: 0, bottom: 0 }}
      >
        ©{' '}
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenStreetMap contributors
        </a>
      </div>
    </div>
  )
}
