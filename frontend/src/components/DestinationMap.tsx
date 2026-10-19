import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Coordinates } from '../lib/types'
import type { Destination } from './DestinationDetails'

type MapApi = Awaited<ReturnType<(typeof import('@2gis/mapgl'))['load']>>

/** Coordinates only: no guessed streets, destination coordinates or route geometry. */
export function DestinationMap({
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
  const visible = destinations.slice(0, 3)
  const points = visible.flatMap((item, index) =>
    item.location ? [{ ...item, location: item.location, index }] : [],
  )
  const allPoints = [
    ...(origin ? [origin] : []),
    ...points.map((point) => point.location),
  ]
  const container = useRef<HTMLDivElement>(null)
  const publicKey = import.meta.env.VITE_TWOGIS_MAP_KEY
  // The search result owns these points. UI language and selected card never reload the map.
  const pointKey = JSON.stringify([
    ...(origin ? [{ ...origin, number: null }] : []),
    ...points.map((point) => ({ ...point.location, number: point.index + 1 })),
  ])
  const mapKey = `${publicKey}:${pointKey}`
  const [mapState, setMapState] = useState<{
    key: string
    value: 'ready' | 'failed'
  } | null>(null)
  const state = mapState?.key === mapKey ? mapState.value : 'loading'
  useEffect(() => {
    const mapPoints = JSON.parse(pointKey) as (Coordinates & {
      number: number | null
    })[]
    if (!publicKey || mapPoints.length === 0) return
    let active = true
    let map: InstanceType<MapApi['Map']> | undefined
    const markers: InstanceType<MapApi['Marker']>[] = []
    const cleanup = () => {
      markers.splice(0).forEach((marker) => marker.destroy())
      const current = map
      map = undefined
      current?.destroy()
    }
    const fail = () => {
      if (!active) return
      cleanup()
      setMapState({ key: mapKey, value: 'failed' })
    }
    void import('@2gis/mapgl')
      .then(({ load }) => load())
      .then((api) => {
        if (!active || !container.current) return
        map = new api.Map(container.current, {
          key: publicKey,
          center: [mapPoints[0].longitude, mapPoints[0].latitude],
          zoom: 12,
        })
        map.on('error', fail)
        mapPoints.forEach((point) => {
          const icon = `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30"><circle cx="15" cy="15" r="12" fill="${point.number === null ? '#fff' : '#294332'}" stroke="${point.number === null ? '#294332' : '#fff'}" stroke-width="3"/>${point.number === null ? '' : `<text x="15" y="20" text-anchor="middle" font-family="sans-serif" font-size="14" fill="white">${point.number}</text>`}</svg>`
          markers.push(
            new api.Marker(map!, {
              coordinates: [point.longitude, point.latitude],
              icon: `data:image/svg+xml,${encodeURIComponent(icon)}`,
              size: [30, 30],
            }),
          )
        })
        map.fitBounds(
          {
            southWest: [
              Math.min(...mapPoints.map((point) => point.longitude)) - 0.002,
              Math.min(...mapPoints.map((point) => point.latitude)) - 0.002,
            ],
            northEast: [
              Math.max(...mapPoints.map((point) => point.longitude)) + 0.002,
              Math.max(...mapPoints.map((point) => point.latitude)) + 0.002,
            ],
          },
          {
            padding: { top: 30, right: 30, bottom: 30, left: 30 },
            maxZoom: 14,
          },
        )
        setMapState({ key: mapKey, value: 'ready' })
      })
      .catch(fail)
    return () => {
      active = false
      cleanup()
    }
    // pointKey represents the exact coordinates; locale has no provider dependency.
  }, [publicKey, pointKey, mapKey])

  if (allPoints.length === 0) return <p>{t('map.noPoints')}</p>
  const minLat = Math.min(...allPoints.map((point) => point.latitude)) - 0.003
  const maxLat = Math.max(...allPoints.map((point) => point.latitude)) + 0.003
  const minLon = Math.min(...allPoints.map((point) => point.longitude)) - 0.005
  const maxLon = Math.max(...allPoints.map((point) => point.longitude)) + 0.005
  const x = (point: Coordinates) =>
    28 + (344 * (point.longitude - minLon)) / (maxLon - minLon)
  const y = (point: Coordinates) =>
    190 - (160 * (point.latitude - minLat)) / (maxLat - minLat)
  return (
    <>
      {publicKey ? (
        <div
          ref={container}
          className="map-canvas"
          role="region"
          aria-label={t('map.title')}
          hidden={state === 'failed'}
        />
      ) : null}
      {publicKey && state !== 'ready' ? (
        <p role="status">
          {t(state === 'failed' ? 'map.unavailable' : 'location.mapLoading')}
        </p>
      ) : null}
      <svg
        className="coordinate-map"
        viewBox="0 0 400 220"
        role="img"
        aria-label={t('map.coordinateView')}
      >
        <title>{t('map.coordinateView')}</title>
        <path
          d="M0 55H400M0 110H400M0 165H400M100 0V220M200 0V220M300 0V220"
          className="coordinate-grid"
        />
        {origin ? (
          <g>
            <circle
              cx={x(origin)}
              cy={y(origin)}
              r="9"
              className="origin-pin"
            />
            <text x={x(origin)} y={y(origin) - 16} textAnchor="middle">
              {t('map.origin')}
            </text>
          </g>
        ) : null}
        {points.map((point) => (
          <g key={point.id}>
            <circle
              cx={x(point.location)}
              cy={y(point.location)}
              r={point.id === selectedId ? 13 : 10}
              className="destination-pin"
            />
            <text
              x={x(point.location)}
              y={y(point.location) + 4}
              textAnchor="middle"
              className="pin-number"
            >
              {point.index + 1}
            </text>
          </g>
        ))}
      </svg>
      <p className="field-hint">{t('map.coordinateView')}</p>
      <ol className="map-legend">
        {visible.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              aria-pressed={item.id === selectedId}
              onClick={() => onSelect(item.id)}
            >
              {t('map.alternative', { index: index + 1 })}:{' '}
              <span lang="">{item.name}</span>
            </button>
            {!item.location ? (
              <span> · {t('codes.missing_fields.location')}</span>
            ) : null}
          </li>
        ))}
      </ol>
    </>
  )
}
