import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LanguageSwitch } from './components/LanguageSwitch'
import { SearchForm } from './components/SearchForm'
import { ResultCard } from './components/ResultCard'
import { EventCard } from './components/EventCard'
import {
  DiscoveredEventCard,
  TransientEventCard,
} from './components/DiscoveredEventCard'
import { EventSearchSources } from './components/EventSearchSources'
import { DestinationDetails } from './components/DestinationDetails'
import type { Destination } from './components/DestinationDetails'
import {
  ApiError,
  checkHealth,
  searchEvents,
  searchRecommendations,
} from './lib/api'
import { resolvedLocale } from './i18n'
import type {
  EventSearchResponse,
  DiscoveredEvent,
  RecommendationResponse,
  ResponseStatus,
  SearchRequest,
} from './lib/types'

type Kind = 'recommendations' | 'events'
function eventLocation(event: DiscoveredEvent) {
  const candidates = event.sessions.filter(
    (session) => session.recommendation_candidate,
  )
  if (candidates.length === 0) return event.venue.location
  const first = candidates[0].venue.location
  if (
    !first ||
    candidates.some(
      (session) =>
        !session.venue.location ||
        session.venue.location.latitude !== first.latitude ||
        session.venue.location.longitude !== first.longitude,
    )
  )
    return null
  if (
    event.venue.location &&
    (event.venue.location.latitude !== first.latitude ||
      event.venue.location.longitude !== first.longitude)
  )
    return null
  return first
}
type Result =
  | { kind: 'recommendations'; response: RecommendationResponse }
  | { kind: 'events'; response: EventSearchResponse }
const DevPreview = import.meta.env.DEV
  ? lazy(() => import('./dev/DevPreview'))
  : null

export default function App() {
  const { t } = useTranslation()
  const locale = resolvedLocale()
  const [kind, setKind] = useState<Kind>('recommendations')
  const [health, setHealth] = useState<'checking' | 'ok' | 'error'>('checking')
  const [phase, setPhase] = useState<'idle' | 'loading' | 'done' | 'error'>(
    'idle',
  )
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [synthetic, setSynthetic] = useState(false)
  const request = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const [previous, setPrevious] = useState<SearchRequest | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void checkHealth(controller.signal)
      .then(() => setHealth('ok'))
      .catch((failure: unknown) => {
        if (!(failure instanceof ApiError && failure.code === 'aborted'))
          setHealth('error')
      })
    return () => controller.abort()
  }, [])

  const resetSearch = useCallback(() => {
    request.current?.abort()
    generation.current += 1
    setPhase('idle')
    setResult(null)
    setSynthetic(false)
    setError(null)
    setPrevious(null)
    setSelectedId(null)
  }, [])

  useEffect(() => {
    return () => {
      request.current?.abort()
      generation.current += 1
    }
  }, [])

  function changeKind(next: Kind) {
    if (next === kind) return
    resetSearch()
    setKind(next)
  }

  async function submit(input: SearchRequest) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    const current = ++generation.current
    const body = { ...input, locale, request_id: crypto.randomUUID() }
    setPrevious(input)
    setPhase('loading')
    setResult(null)
    setError(null)
    setSynthetic(false)
    setSelectedId(null)
    try {
      const next: Result =
        kind === 'events'
          ? { kind, response: await searchEvents(body, controller.signal) }
          : {
              kind,
              response: await searchRecommendations(body, controller.signal),
            }
      if (current !== generation.current) return
      setResult(next)
      setPhase('done')
    } catch (failure) {
      if (current !== generation.current || controller.signal.aborted) return
      setError(failure instanceof ApiError ? failure : new ApiError('network'))
      setPhase('error')
    }
  }

  async function preview(status: ResponseStatus) {
    if (!import.meta.env.DEV) return
    request.current?.abort()
    const current = ++generation.current
    setResult(null)
    setSynthetic(true)
    setPhase('loading')
    setError(null)
    setPrevious(null)
    try {
      const { loadFixture } = await import('./dev/fixtures')
      const next: Result =
        kind === 'events'
          ? { kind, response: await loadFixture('events') }
          : { kind, response: await loadFixture('recommendations', status) }
      if (current !== generation.current) return
      setResult(next)
      setPhase('done')
    } catch {
      if (current !== generation.current) return
      setError(new ApiError('invalid_response'))
      setPhase('error')
    }
  }

  function live() {
    resetSearch()
  }

  const response = result?.response
  const stateKey = response?.status === 'no_match' ? 'empty' : response?.status
  const transientListings =
    result?.kind === 'events'
      ? (result.response.transient?.listings.filter(
          (event) =>
            !result.response.transient!.items.some(
              (card) => card.event.id === event.event_id,
            ),
        ) ?? [])
      : []
  const destinations: Destination[] =
    result?.kind === 'recommendations'
      ? result.response.items.slice(0, 3).map(({ poi }) => ({
          id: poi.id,
          name: poi.name,
          location: poi.location,
        }))
      : result?.kind === 'events'
        ? result.response.transient
          ? [
              ...result.response.transient.items.map((card) => ({
                id: `session:${card.session.session_id}`,
                name: card.event.title,
                location: card.session.venue.location,
              })),
              ...transientListings.map((event) => ({
                id: `listing:${event.event_id}`,
                name: event.title,
                location: eventLocation(event),
              })),
            ].slice(0, 3)
          : result.response.discovery
            ? result.response.discovery.events.slice(0, 3).map((event) => ({
                id: event.event_id,
                name: event.title,
                location: eventLocation(event),
              }))
            : result.response.items.slice(0, 3).map(({ session, event }) => ({
                id: session.id,
                name: event.title,
                location: session.location,
              }))
        : []
  return (
    <>
      <a className="skip-link" href="#search">
        {t('app.skip')}
      </a>
      <header className="site-header">
        <a className="brand" href="#search" aria-label="Qadam Astana">
          <span className="brand-mark" aria-hidden="true">
            q<span>↗</span>
          </span>
          <span>
            qadam<span className="brand-city">ASTANA</span>
          </span>
        </a>
        <span className="header-note">{t('app.tagline')}</span>
        <LanguageSwitch />
      </header>
      <main className="page-shell">
        <section className="intro">
          <div>
            <p className="eyebrow">
              <span className="location-dot" />
              {t('app.city')}
            </p>
            <h1>{t('app.title')}</h1>
            <p className="intro-copy">{t('app.description')}</p>
          </div>
          <div className="intro-stamp" aria-hidden="true">
            <span>01—03</span>
            <span>QADAM / ASTANA</span>
            <svg viewBox="0 0 120 70">
              <path d="M8 53 Q30 6 58 34 T110 15 M16 63 Q45 18 73 46 T114 32" />
              <circle cx="8" cy="53" r="4" />
              <circle cx="110" cy="15" r="6" />
            </svg>
          </div>
        </section>
        <div className="workspace">
          <section
            className="search-panel"
            id="search"
            aria-labelledby="search-title"
          >
            <div className="panel-heading">
              <span className="step-number">01</span>
              <h2 id="search-title">{t('search.title')}</h2>
            </div>
            <div
              className="mode-switch"
              role="group"
              aria-label={t('states.results')}
            >
              <button
                type="button"
                aria-pressed={kind === 'recommendations'}
                onClick={() => changeKind('recommendations')}
              >
                {t('states.places')}
              </button>
              <button
                type="button"
                aria-pressed={kind === 'events'}
                onClick={() => changeKind('events')}
              >
                {t('states.events')}
              </button>
            </div>
            <SearchForm
              onInputChange={resetSearch}
              onSubmit={(body) => {
                void submit(body)
              }}
              loading={phase === 'loading'}
              mode={kind}
            />
          </section>
          <section
            className="results-panel"
            aria-labelledby="results-title"
            aria-busy={phase === 'loading'}
          >
            <div className="results-heading">
              <div>
                <p className="eyebrow">QADAM / 02</p>
                <h2 id="results-title">{t('states.results')}</h2>
              </div>
              <span className={`health-pill health-${health}`} role="status">
                <span />
                {t(
                  health === 'ok'
                    ? 'states.healthOk'
                    : health === 'error'
                      ? 'states.healthError'
                      : 'states.healthChecking',
                )}
              </span>
            </div>
            <p className="mode-label">
              <span className={synthetic ? 'synthetic-dot' : 'live-dot'} />
              {t(synthetic ? 'dev.title' : 'states.liveMode')}
            </p>
            <div className="result-content" aria-live="polite">
              {phase === 'idle' && (
                <div className="idle-state">
                  <div className="city-art" aria-hidden="true">
                    <div className="orbit orbit-one" />
                    <div className="orbit orbit-two" />
                    <svg viewBox="0 0 320 230">
                      <path
                        className="art-road"
                        d="M-20 190 Q70 70 160 162 T350 60"
                      />
                      <path
                        className="art-road thin"
                        d="M-20 210 Q70 90 160 182 T350 80"
                      />
                      <path
                        className="art-skyline"
                        d="M48 154V109h28v45m22 0V87h28v67m24 0V65m-13 20h26m-13 0v69m36 0V109h32v45m27 0V88h27v66"
                      />
                      <circle className="art-sun" cx="150" cy="52" r="18" />
                      <path
                        className="art-window"
                        d="M55 120h14m36-21h14m75 21h16m43-20h11"
                      />
                      <circle className="art-point" cx="242" cy="178" r="12" />
                      <circle
                        className="art-point-center"
                        cx="242"
                        cy="178"
                        r="4"
                      />
                    </svg>
                    <span className="art-label">ASTANA</span>
                  </div>
                  <h3>{t('states.idle')}</h3>
                  <p>{t('app.footer')}</p>
                  <div className="idle-tags">
                    <span>kk / ru / en</span>
                    <span>1–3</span>
                    <span>KZT</span>
                  </div>
                </div>
              )}
              {phase === 'loading' && (
                <div className="loading-state" role="status">
                  <span className="spinner" />
                  <h3>{t('states.loading')}</h3>
                  <div className="skeleton" />
                  <div className="skeleton short" />
                </div>
              )}
              {phase === 'error' && (
                <div className="message-state error-state" role="alert">
                  <span className="message-icon" aria-hidden="true">
                    !
                  </span>
                  <h3>
                    {t(
                      error?.code === 'not_ready'
                        ? 'states.endpointUnavailable'
                        : 'states.error',
                    )}
                  </h3>
                  {previous && (
                    <button
                      className="secondary-button"
                      onClick={() => {
                        void submit(previous)
                      }}
                    >
                      {t('states.retry')}
                    </button>
                  )}
                </div>
              )}
              {phase === 'done' && response && (
                <div className="response-state">
                  <div
                    className={`response-notice response-${response.status}`}
                  >
                    <strong>
                      {t(`codes.response_status.${response.status}`)}
                    </strong>
                    <p>{t(`states.${stateKey}`)}</p>
                  </div>
                  {synthetic && (
                    <p className="fixture-notice">
                      {t('dev.description')} {t('dev.englishNotice')}
                    </p>
                  )}
                  {result.kind === 'events' && result.response.discovery ? (
                    <p className="event-notice">
                      {t('events.searchStatus')}:{' '}
                      {t(
                        `events.searchStates.${result.response.discovery.live_web_search}`,
                      )}
                    </p>
                  ) : null}
                  {result.kind === 'events' && result.response.transient ? (
                    <>
                      <p className="event-notice">
                        {t('events.searchStatus')}:{' '}
                        {t(
                          `events.searchStates.${result.response.transient.live_web_search}`,
                        )}
                      </p>
                      <EventSearchSources
                        sources={result.response.transient.sources}
                        locale={locale}
                      />
                    </>
                  ) : null}
                  {response.warnings.length > 0 && (
                    <ul className="warning-list">
                      {response.warnings.map((warning, index) => (
                        <li key={`${warning.code}-${index}`}>
                          {t(`codes.warning_codes.${warning.code}`)}
                          {warning.fields.length > 0
                            ? `: ${warning.fields.map((field) => t(`codes.missing_fields.${field}`)).join(', ')}`
                            : ''}
                        </li>
                      ))}
                    </ul>
                  )}
                  {result.kind === 'events' &&
                  result.response.discovery?.events.length === 0 &&
                  result.response.discovery.evidence ? (
                    <EventSearchSources
                      citations={result.response.discovery.evidence.citations}
                    />
                  ) : null}
                  <div className="result-list">
                    {result.kind === 'events' && result.response.transient ? (
                      <>
                        {result.response.transient.items.map(
                          (card, index, cards) => (
                            <TransientEventCard
                              key={card.session.session_id}
                              card={card}
                              sources={result.response.transient!.sources}
                              listing={
                                cards.findIndex(
                                  (other) => other.event.id === card.event.id,
                                ) === index
                                  ? result.response.transient!.listings.find(
                                      (event) =>
                                        event.event_id === card.event.id,
                                    )
                                  : undefined
                              }
                              representedSessionIds={cards.map(
                                (other) => other.session.session_id,
                              )}
                              locale={locale}
                              selected={
                                selectedId ===
                                `session:${card.session.session_id}`
                              }
                              onSelect={() =>
                                setSelectedId(
                                  `session:${card.session.session_id}`,
                                )
                              }
                            />
                          ),
                        )}
                        {transientListings
                          .slice(
                            0,
                            Math.max(
                              0,
                              3 - result.response.transient.items.length,
                            ),
                          )
                          .map((event) => (
                            <DiscoveredEventCard
                              key={event.event_id}
                              event={event}
                              citations={[]}
                              locale={locale}
                              selected={
                                selectedId === `listing:${event.event_id}`
                              }
                              onSelect={() =>
                                setSelectedId(`listing:${event.event_id}`)
                              }
                            />
                          ))}
                      </>
                    ) : null}
                    {result.kind === 'recommendations'
                      ? result.response.items
                          .slice(0, 3)
                          .map((card) => (
                            <ResultCard
                              key={card.poi.id}
                              card={card}
                              locale={locale}
                              sources={result.response.sources}
                              selected={selectedId === card.poi.id}
                              onSelect={() => setSelectedId(card.poi.id)}
                            />
                          ))
                      : result.response.items
                          .slice(0, 3)
                          .map((card) => (
                            <EventCard
                              key={card.session.id}
                              card={card}
                              locale={locale}
                              sources={result.response.sources}
                              selected={selectedId === card.session.id}
                              onSelect={() => setSelectedId(card.session.id)}
                            />
                          ))}
                    {result.kind === 'events' && result.response.discovery
                      ? result.response.discovery.events
                          .slice(0, 3)
                          .map((event) => (
                            <DiscoveredEventCard
                              key={event.event_id}
                              event={event}
                              citations={
                                result.response.discovery?.evidence
                                  ?.citations ?? []
                              }
                              locale={locale}
                              selected={selectedId === event.event_id}
                              onSelect={() => setSelectedId(event.event_id)}
                            />
                          ))
                      : null}
                  </div>
                  {destinations.length > 0 && (
                    <DestinationDetails
                      key={response.request_id}
                      destinations={destinations}
                      origin={previous?.origin ?? null}
                      returnToStart={previous?.return_to_start ?? false}
                      locale={locale}
                      selectedId={selectedId}
                      onSelect={setSelectedId}
                      synthetic={synthetic}
                    />
                  )}
                </div>
              )}
            </div>
            {DevPreview && (
              <Suspense fallback={null}>
                <DevPreview
                  key={kind + locale}
                  kind={kind}
                  loading={phase === 'loading'}
                  onPreview={(status) => {
                    void preview(status)
                  }}
                  onLive={live}
                />
              </Suspense>
            )}
          </section>
        </div>
      </main>
      <footer className="site-footer">
        <span>Qadam Astana</span>
        <span>{t('app.footer')}</span>
        <span>kk · ru · en</span>
      </footer>
    </>
  )
}
