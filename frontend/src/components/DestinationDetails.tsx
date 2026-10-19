import { useEffect, useEffectEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getRoute } from '../lib/api'
import { formatDateTime, formatMinutes } from '../lib/format'
import type { Coordinates, Locale, RouteResponse } from '../lib/types'
import { DestinationMap } from './DestinationMap'

export interface Destination {
  id: string
  name: string
  location: Coordinates | null
}

interface Props {
  destinations: Destination[]
  origin: Coordinates | null
  returnToStart: boolean
  locale: Locale
  selectedId: string | null
  onSelect: (id: string) => void
  synthetic: boolean
}

export function DestinationDetails({
  destinations,
  origin,
  returnToStart,
  locale,
  selectedId,
  onSelect,
  synthetic,
}: Props) {
  const { t } = useTranslation()
  const selected = destinations.find((item) => item.id === selectedId)
  const [cache] = useState(() => new Map<string, RouteResponse>())
  return (
    <section
      className="destination-details"
      aria-labelledby="destination-map-title"
    >
      <h3 id="destination-map-title">{t('map.title')}</h3>
      <DestinationMap
        origin={origin}
        destinations={destinations}
        selectedId={selectedId}
        onSelect={onSelect}
      />
      <RouteDetails
        key={selectedId ?? 'none'}
        selected={selected}
        origin={origin}
        returnToStart={returnToStart}
        locale={locale}
        synthetic={synthetic}
        cache={cache}
      />
    </section>
  )
}

function RouteDetails({
  selected,
  origin,
  returnToStart,
  locale,
  synthetic,
  cache,
}: {
  selected: Destination | undefined
  origin: Coordinates | null
  returnToStart: boolean
  locale: Locale
  synthetic: boolean
  cache: Map<string, RouteResponse>
}) {
  const { t } = useTranslation()
  const selectedId = selected?.id
  const [route, setRoute] = useState<RouteResponse | null>(() =>
    selectedId ? (cache.get(selectedId) ?? null) : null,
  )
  const [phase, setPhase] = useState<'idle' | 'loading' | 'done' | 'error'>(
    () =>
      route
        ? 'done'
        : selected?.location && origin && !synthetic
          ? 'loading'
          : 'idle',
  )
  const [attempt, setAttempt] = useState(0)
  const currentLocale = useEffectEvent(() => locale)
  const latitude = selected?.location?.latitude
  const longitude = selected?.location?.longitude

  useEffect(() => {
    if (
      !selectedId ||
      latitude === undefined ||
      longitude === undefined ||
      !origin ||
      synthetic
    )
      return
    if (cache.has(selectedId)) return
    const controller = new AbortController()
    let active = true
    void getRoute(
      {
        request_id: crypto.randomUUID(),
        origin,
        destination: { latitude, longitude },
        return_to_start: returnToStart,
        locale: currentLocale(),
      },
      controller.signal,
    )
      .then((response) => {
        if (!active) return
        cache.set(selectedId, response)
        setRoute(response)
        setPhase('done')
      })
      .catch(() => {
        if (active && !controller.signal.aborted) setPhase('error')
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [
    selectedId,
    latitude,
    longitude,
    origin,
    returnToStart,
    synthetic,
    cache,
    attempt,
  ])

  return (
    <div
      className="route-details"
      aria-live="polite"
      aria-busy={phase === 'loading'}
    >
      {selected ? <h4 lang="">{selected.name}</h4> : null}
      {!selected ? (
        <p>{t('route.notSelected')}</p>
      ) : !selected.location ? (
        <p>{t('map.noPoints')}</p>
      ) : !origin ? (
        <p>{t('route.missingOrigin')}</p>
      ) : synthetic ? (
        <p>{t('dev.description')}</p>
      ) : phase === 'loading' ? (
        <p role="status">{t('route.loading')}</p>
      ) : phase === 'error' ? (
        <>
          <p role="status">{t('route.error')}</p>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setPhase('loading')
              setAttempt((value) => value + 1)
            }}
          >
            {t('states.retry')}
          </button>
        </>
      ) : route ? (
        <>
          <p>{t(`codes.route_status.${route.status}`)}</p>
          <dl className="card-facts">
            <div>
              <dt>{t('route.walking')}</dt>
              <dd>
                {formatMinutes(
                  route.outbound.duration_seconds === null
                    ? null
                    : Math.ceil(route.outbound.duration_seconds / 60),
                  locale,
                )}{' '}
                · {t(`codes.route_status.${route.outbound.status}`)}
              </dd>
            </div>
            {returnToStart ? (
              <div>
                <dt>{t('route.return')}</dt>
                <dd>
                  {formatMinutes(
                    route.return_route.duration_seconds === null
                      ? null
                      : Math.ceil(route.return_route.duration_seconds / 60),
                    locale,
                  )}{' '}
                  · {t(`codes.route_status.${route.return_route.status}`)}
                </dd>
              </div>
            ) : null}
          </dl>
          <p className="field-hint">{t('route.approximateDestination')}</p>
          {[route.outbound, ...(returnToStart ? [route.return_route] : [])].map(
            (leg, index) =>
              leg.provenance ? (
                <p className="field-hint" key={index}>
                  {t(index === 0 ? 'route.walking' : 'route.return')}:{' '}
                  <a
                    href="https://dev.2gis.ru"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    2ГИС
                  </a>{' '}
                  · {t('source.retrieved')}:{' '}
                  {formatDateTime(leg.provenance.retrieved_at, locale)}
                </p>
              ) : null,
          )}
          {route.warnings.length > 0 ? (
            <ul className="warning-list">
              {route.warnings.map((warning, index) => (
                <li key={`${warning.code}-${index}`}>
                  {t(`codes.warning_codes.${warning.code}`)}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
      <p className="field-hint">{t('route.noGeometry')}</p>
    </div>
  )
}
