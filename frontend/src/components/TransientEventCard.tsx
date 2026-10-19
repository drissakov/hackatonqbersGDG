import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../lib/format'
import { safeExternalUrl } from '../lib/links'
import type {
  Locale,
  TransientEventCardData,
  TransientEventSource,
} from '../lib/types'
import { CardFacts } from './CardFacts'
import { SessionFacts } from './DiscoveredEventCard'

export function TransientEventSources({
  sources,
  locale,
}: {
  sources: TransientEventSource[]
  locale: Locale
}) {
  const { t } = useTranslation()
  if (sources.length === 0) return null
  return (
    <details className="source-details">
      <summary>{t('source.title')}</summary>
      <ul className="source-list">
        {sources.map((source) => {
          const url = safeExternalUrl(source.url)
          return (
            <li key={source.source_id}>
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {url}
                </a>
              ) : (
                t('card.unsafeLink')
              )}
              <p>
                {t('events.observed')}:{' '}
                {formatDateTime(source.retrieved_at, locale)}
              </p>
            </li>
          )
        })}
      </ul>
      <p>{t('events.observationNotice')}</p>
    </details>
  )
}

/** Runtime session facts never acquire persistent source/provenance records. */
export function TransientEventCard({
  card,
  sources,
  locale,
  selected,
  onSelect,
}: {
  card: TransientEventCardData
  sources: TransientEventSource[]
  locale: Locale
  selected: boolean
  onSelect: () => void
}) {
  const { t } = useTranslation()
  return (
    <article
      className="event-card result-card"
      aria-labelledby={`transient-${card.session.session_id}`}
    >
      <div className="card-topline">
        <span className="activity-badge">
          {t(`codes.activity_code.${card.activity_code}`)}
        </span>
        <span className={`fit-badge fit-${card.fit_status}`}>
          {t(`codes.fit_status.${card.fit_status}`)}
        </span>
      </div>
      <h3 id={`transient-${card.session.session_id}`} lang="">
        {card.event.title}
      </h3>
      <h4>{t('card.sourceFacts')}</h4>
      <SessionFacts session={card.session} locale={locale} />
      <p className="timezone-note">{t('card.timezone')}</p>
      <p className="event-notice">{t('events.ticketsUnknown')}</p>
      <CardFacts
        card={card}
        locale={locale}
        sourceUrl={card.action.url}
        ticketAction
      />
      <button
        type="button"
        className="card-select"
        onClick={onSelect}
        aria-pressed={selected}
      >
        {t(selected ? 'card.selected' : 'card.select')}
      </button>
      <TransientEventSources
        sources={sources.filter((source) =>
          card.source_ids.includes(source.source_id),
        )}
        locale={locale}
      />
    </article>
  )
}
