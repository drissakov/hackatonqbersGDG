import { useTranslation } from 'react-i18next'
import { formatDateTime, formatMoney } from '../lib/format'
import { safeExternalUrl } from '../lib/links'
import type {
  DiscoveredEvent,
  DiscoveredSession,
  EventCitation,
  EventVenue,
  Locale,
} from '../lib/types'

function SourceLink({
  url,
  ticketAction = false,
  label,
}: {
  url: string
  ticketAction?: boolean
  label?: string
}) {
  const { t } = useTranslation()
  const safeUrl = safeExternalUrl(url)
  return safeUrl ? (
    <a href={safeUrl} target="_blank" rel="noopener noreferrer">
      {label ?? t(ticketAction ? 'events.checkTickets' : 'source.open')}
    </a>
  ) : (
    <span>{t('card.unsafeLink')}</span>
  )
}

function VenueSources({ venue }: { venue: EventVenue }) {
  const { t } = useTranslation()
  if (venue.basis !== 'name_address_astana_permitted_poi' || !venue.location)
    return null
  return (
    <div className="source-fact">
      <h4>{t('events.venueSources')}</h4>
      <p>{t('events.venueNotice')}</p>
      {venue.source_urls.length > 0 ? (
        <ul className="source-list">
          {[...new Set(venue.source_urls)].map((url) => (
            <li key={url}>
              <SourceLink url={url} label={url} />
            </li>
          ))}
        </ul>
      ) : (
        <p>{t('source.none')}</p>
      )}
    </div>
  )
}

export function SessionFacts({
  session,
  locale,
}: {
  session: DiscoveredSession
  locale: Locale
}) {
  const { t } = useTranslation()
  const amount =
    session.price_from === null
      ? t('card.unknown')
      : session.currency === 'KZT'
        ? formatMoney(session.price_from, locale)
        : `${new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(session.price_from)} (${t('events.currencyUnknown')})`
  return (
    <section className="event-session" aria-label={t('events.sessionFacts')}>
      <dl className="card-facts">
        <div>
          <dt>{t('events.fields.venue_name')}</dt>
          <dd lang="">{session.venue_name ?? t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('card.address')}</dt>
          <dd lang="">{session.venue_address ?? t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('card.start')}</dt>
          <dd>{formatDateTime(session.starts_at, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.end')}</dt>
          <dd>{formatDateTime(session.ends_at, locale)}</dd>
        </div>
        <div>
          <dt>{t('events.price')}</dt>
          <dd>
            {session.price_from !== null ? `${t('events.from')} ` : ''}
            {amount}
            {session.price_from !== null && session.price_kind === 'promotion'
              ? ` · ${t('events.promotion')}`
              : ''}
          </dd>
        </div>
        <div>
          <dt>{t('card.session')}</dt>
          <dd>{t(`codes.session_status.${session.status}`)}</dd>
        </div>
        <div>
          <dt>{t('card.availability')}</dt>
          <dd>{t('card.unknown')}</dd>
        </div>
      </dl>
      {session.price_conditions ? (
        <p>
          <strong>
            {t('events.fields.price_conditions')} ({t('card.sourceText')}):
          </strong>{' '}
          <span lang="">{session.price_conditions}</span>
        </p>
      ) : null}
      {session.missing_fields.length > 0 ? (
        <p>
          {t('card.missing')}:{' '}
          {session.missing_fields
            .map((field) =>
              t(`events.fields.${field}`, {
                defaultValue: t('source.otherFact'),
              }),
            )
            .join(', ')}
        </p>
      ) : null}
      <p>
        {session.verified_fields.length > 0
          ? `${t('events.checkedFields')}: ${session.verified_fields
              .map((check) =>
                t(`events.fields.${check.field}`, {
                  defaultValue: t('source.otherFact'),
                }),
              )
              .join(', ')}`
          : t('events.discoveredOnly')}
      </p>
      <SourceLink url={session.source_url} />
      <VenueSources venue={session.venue} />
    </section>
  )
}

export function DiscoveredEventCard({
  event,
  citations,
  locale,
  selected = false,
  onSelect,
  includeWithheldSessions = false,
}: {
  event: DiscoveredEvent
  citations: EventCitation[]
  locale: Locale
  selected?: boolean
  onSelect?: () => void
  includeWithheldSessions?: boolean
}) {
  const { t } = useTranslation()
  const sessions = event.sessions.filter(
    (session) =>
      includeWithheldSessions ||
      (session.recommendation_candidate &&
        session.status === 'scheduled' &&
        session.starts_at !== null &&
        session.exclusion_reasons.length === 0),
  )
  const sourceUrls = new Set([
    event.source_url,
    ...sessions.map((session) => session.source_url),
  ])
  const relevantCitations = citations.filter((citation) =>
    sourceUrls.has(citation.url),
  )
  return (
    <article
      className="event-card result-card"
      aria-labelledby={`discovered-${event.event_id}`}
    >
      <div className="card-topline">
        <span className="activity-badge">
          {t(
            event.status === 'listing' ? 'events.listing' : 'events.discovered',
          )}
        </span>
        <span className="fit-badge fit-unknown">
          {t('codes.fit_status.unknown')}
        </span>
      </div>
      <h3 id={`discovered-${event.event_id}`} lang="">
        {event.title}
      </h3>
      <h4>{t('card.sourceFacts')}</h4>
      <dl className="card-facts">
        <div>
          <dt>{t('card.category')}</dt>
          <dd>{t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('events.fields.city')}</dt>
          <dd lang="">{event.city ?? t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('events.fields.venue_name')}</dt>
          <dd lang="">{event.venue_name ?? t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('card.address')}</dt>
          <dd lang="">{event.venue_address ?? t('card.unknown')}</dd>
        </div>
      </dl>
      {event.schedule_hints.length > 0 ? (
        <p className="source-hours">
          {t('events.scheduleHint')}:{' '}
          <span lang="">{event.schedule_hints.join('; ')}</span>
        </p>
      ) : null}
      {sessions.length > 0 ? (
        sessions.map((session) => (
          <div key={session.session_id}>
            <SessionFacts session={session} locale={locale} />
            {!session.recommendation_candidate ? (
              <p className="event-notice">{t('events.notAlternative')}</p>
            ) : null}
          </div>
        ))
      ) : (
        <>
          <p className="event-notice">{t('events.noSession')}</p>
          <dl className="card-facts">
            <div>
              <dt>{t('events.price')}</dt>
              <dd>{t('card.unknown')}</dd>
            </div>
            <div>
              <dt>{t('card.session')}</dt>
              <dd>{t('codes.session_status.unknown')}</dd>
            </div>
            <div>
              <dt>{t('card.availability')}</dt>
              <dd>{t('card.unknown')}</dd>
            </div>
          </dl>
        </>
      )}
      <p className="timezone-note">{t('card.timezone')}</p>
      <p className="event-notice">{t('events.ticketsUnknown')}</p>
      <p className="estimate-notice">{t('events.fitUnknown')}</p>
      <dl className="card-facts">
        <div>
          <dt>{t('card.visit')}</dt>
          <dd>{t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('card.travel')}</dt>
          <dd>{t('card.unknown')}</dd>
        </div>
        <div>
          <dt>{t('card.route')}</dt>
          <dd>{t('codes.route_status.not_requested')}</dd>
        </div>
      </dl>
      <p className="field-hint">{t('card.searchSnapshot')}</p>
      <div className="card-idea">
        <h4>{t('card.idea')}</h4>
        <p>{t('events.activity')}</p>
      </div>
      <div className="card-reasons">
        <h4>{t('card.why')}</h4>
        <p>{t('events.reason')}</p>
      </div>
      {event.missing_fields.length > 0 ? (
        <div className="missing-details">
          <h4>{t('card.missing')}</h4>
          <ul>
            {event.missing_fields.map((field) => (
              <li key={field}>
                {t(`events.fields.${field}`, {
                  defaultValue: t('source.otherFact'),
                })}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <SourceLink url={event.source_url} ticketAction />
      {onSelect ? (
        <button
          type="button"
          className="card-select"
          onClick={onSelect}
          aria-pressed={selected}
        >
          {t(selected ? 'card.selected' : 'card.select')}
        </button>
      ) : null}
      <details className="source-details">
        <summary>{t('source.title')}</summary>
        <SourceLink url={event.source_url} />
        <p>
          {t('events.observed')}:{' '}
          {formatDateTime(event.source_fetched_at, locale)}
        </p>
        <p>{t('events.observationNotice')}</p>
        <VenueSources venue={event.venue} />
        {relevantCitations.length > 0 ? (
          <>
            <h4>{t('events.citations')}</h4>
            <p>{t('events.citationNotice')}</p>
            <ul className="source-list">
              {relevantCitations.map((citation, index) => (
                <li key={`${citation.url}-${citation.start_index}-${index}`}>
                  <SourceLink url={citation.url} />
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </details>
    </article>
  )
}
