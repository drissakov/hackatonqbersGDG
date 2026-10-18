import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface MapPickerProps {
  publicKey: string
  latitude: string
  longitude: string
  onSelect: (latitude: number, longitude: number) => void
}

type MapApi = Awaited<ReturnType<(typeof import('@2gis/mapgl'))['load']>>
type MapInstance = InstanceType<MapApi['Map']>
type MarkerInstance = InstanceType<MapApi['Marker']>

function validPoint(
  latitude: string,
  longitude: string,
): [number, number] | null {
  if (!latitude.trim() || !longitude.trim()) return null
  const lat = Number(latitude)
  const lon = Number(longitude)
  return Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= -90 &&
    lat <= 90 &&
    lon >= -180 &&
    lon <= 180
    ? [lon, lat]
    : null
}

export function MapPicker({
  publicKey,
  latitude,
  longitude,
  onSelect,
}: MapPickerProps) {
  const { t } = useTranslation()
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MapInstance | null>(null)
  const marker = useRef<MarkerInstance | null>(null)
  const api = useRef<MapApi | null>(null)
  const selectRef = useRef(onSelect)
  const [state, setState] = useState<'loading' | 'ready' | 'failed'>('loading')

  useEffect(() => {
    selectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    let active = true
    let cleanup: () => void = () => undefined
    // A map center is only the initial viewport, never an inferred starting point.
    void import('@2gis/mapgl')
      .then(({ load }) => load())
      .then((loadedApi) => {
        if (!active || !container.current) return
        api.current = loadedApi
        const instance = new loadedApi.Map(container.current, {
          key: publicKey,
          center: [71.43, 51.13],
          zoom: 11,
        })
        map.current = instance
        instance.on('click', ({ lngLat }) => {
          if (
            active &&
            Number.isFinite(lngLat[0]) &&
            Number.isFinite(lngLat[1])
          )
            selectRef.current(lngLat[1], lngLat[0])
        })
        instance.on('error', () => {
          if (active) setState('failed')
        })
        setState('ready')
        cleanup = () => {
          marker.current?.destroy()
          marker.current = null
          instance.destroy()
          map.current = null
          api.current = null
        }
      })
      .catch(() => {
        if (active) setState('failed')
      })
    return () => {
      active = false
      cleanup()
    }
  }, [publicKey])

  useEffect(() => {
    if (state !== 'ready' || !map.current || !api.current) return
    marker.current?.destroy()
    marker.current = null
    const coordinates = validPoint(latitude, longitude)
    if (coordinates)
      marker.current = new api.current.Marker(map.current, { coordinates })
  }, [latitude, longitude, state])

  return (
    <div className="optional-map">
      <p className="field-hint">{t('location.mapHint')}</p>
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label={t('location.mapLabel')}
        hidden={state === 'failed'}
      />
      {state !== 'ready' && (
        <p className="field-hint" role="status">
          {t(
            state === 'loading'
              ? 'location.mapLoading'
              : 'location.mapUnavailable',
          )}
        </p>
      )}
      <p className="field-hint">{t('location.mapPrivacy')}</p>
    </div>
  )
}
