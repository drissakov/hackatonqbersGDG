import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MapPicker } from './MapPicker'

export type PointSource = 'unknown' | 'manual' | 'gps' | 'map'

interface GeoPointPickerProps {
  latitude: string
  longitude: string
  source: PointSource
  onChange: (latitude: string, longitude: string, source: PointSource) => void
  error?: string
}

export function GeoPointPicker({
  latitude,
  longitude,
  source,
  onChange,
  error,
}: GeoPointPickerProps) {
  const { t } = useTranslation()
  const [gpsPending, setGpsPending] = useState(false)
  const [gpsAttempted, setGpsAttempted] = useState(false)
  const [gpsError, setGpsError] = useState<string | null>(null)
  const mounted = useRef(false)
  const attemptStarted = useRef(false)
  const pointRevision = useRef(0)
  const changeRef = useRef(onChange)

  useEffect(() => {
    changeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  function requestLocation() {
    if (attemptStarted.current) return
    attemptStarted.current = true
    setGpsAttempted(true)
    setGpsError(null)
    if (!navigator.geolocation) {
      setGpsError('location.gpsUnsupported')
      return
    }
    setGpsPending(true)
    const requestedRevision = pointRevision.current
    try {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          if (!mounted.current || requestedRevision !== pointRevision.current)
            return
          setGpsPending(false)
          const { latitude: lat, longitude: lon } = position.coords
          if (
            !Number.isFinite(lat) ||
            !Number.isFinite(lon) ||
            lat < -90 ||
            lat > 90 ||
            lon < -180 ||
            lon > 180
          ) {
            setGpsError('location.gpsUnavailable')
            return
          }
          changeRef.current(String(lat), String(lon), 'gps')
        },
        (failure) => {
          if (!mounted.current || requestedRevision !== pointRevision.current)
            return
          setGpsPending(false)
          setGpsError(
            failure.code === 1
              ? 'location.gpsDenied'
              : failure.code === 3
                ? 'location.gpsTimeout'
                : 'location.gpsUnavailable',
          )
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 },
      )
    } catch {
      setGpsPending(false)
      setGpsError('location.gpsUnavailable')
    }
  }

  function changeManual(nextLatitude: string, nextLongitude: string) {
    // Ignore a late GPS result after the person deliberately switches to manual input.
    pointRevision.current += 1
    setGpsPending(false)
    setGpsError(null)
    onChange(
      nextLatitude,
      nextLongitude,
      nextLatitude.trim() || nextLongitude.trim() ? 'manual' : 'unknown',
    )
  }

  const sourceKey =
    source === 'gps' ? 'gpsSource' : source === 'map' ? 'mapSource' : source

  return (
    <fieldset className="location-picker" aria-describedby="location-hint">
      <legend>{t('location.title')}</legend>
      <p className="field-hint" id="location-hint">
        {t('location.hint')}
      </p>
      {import.meta.env.VITE_TWOGIS_MAP_KEY && (
        <MapPicker
          publicKey={import.meta.env.VITE_TWOGIS_MAP_KEY}
          latitude={latitude}
          longitude={longitude}
          onSelect={(lat, lon) => {
            pointRevision.current += 1
            setGpsPending(false)
            setGpsError(null)
            onChange(String(lat), String(lon), 'map')
          }}
        />
      )}
      <div className="field-grid coordinate-fields">
        <label className="field" htmlFor="origin-latitude">
          <span>{t('location.latitude')}</span>
          <input
            id="origin-latitude"
            name="latitude"
            type="number"
            inputMode="decimal"
            min={-90}
            max={90}
            step="any"
            value={latitude}
            onChange={(event) => changeManual(event.target.value, longitude)}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'origin-error' : undefined}
          />
        </label>
        <label className="field" htmlFor="origin-longitude">
          <span>{t('location.longitude')}</span>
          <input
            id="origin-longitude"
            name="longitude"
            type="number"
            inputMode="decimal"
            min={-180}
            max={180}
            step="any"
            value={longitude}
            onChange={(event) => changeManual(latitude, event.target.value)}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'origin-error' : undefined}
          />
        </label>
      </div>
      {error && (
        <p className="field-error" id="origin-error">
          {error}
        </p>
      )}
      <div className="location-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={requestLocation}
          disabled={gpsAttempted}
        >
          <span aria-hidden="true">⌖</span>{' '}
          {t(
            gpsPending
              ? 'location.gpsLoading'
              : gpsAttempted
                ? 'location.gpsUsed'
                : 'location.gps',
          )}
        </button>
        <button
          className="text-button"
          type="button"
          onClick={() => changeManual('', '')}
          disabled={!latitude && !longitude}
        >
          {t('location.clear')}
        </button>
      </div>
      <p className="point-source">
        <span>{t('location.sourceLabel')}:</span> {t(`location.${sourceKey}`)}
      </p>
      {gpsError && (
        <p className="field-hint location-message" role="status">
          {t(gpsError)}
        </p>
      )}
      {gpsPending && (
        <span className="sr-only" role="status">
          {t('location.gpsLoading')}
        </span>
      )}
    </fieldset>
  )
}
