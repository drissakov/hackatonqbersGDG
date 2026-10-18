import { useTranslation } from 'react-i18next'
import { formatDateTime, formatMoney } from '../lib/format'
import type { EventCardData, Locale, Source } from '../lib/types'
import { CardFacts } from './CardFacts'
import { SourceDetails } from './SourceDetails'

interface EventCardProps {
  card: EventCardData
  locale: Locale
  sources?: Source[]
}

export function EventCard({ card, locale, sources = [] }: EventCardProps) {
  const { t } = useTranslation()
  const { event, session } = card
  const citedIds = new Set(card.provenance.map((fact) => fact.source_id))
  return (
    <article
      className="event-card result-card"
      aria-labelledby={`event-${session.id}`}
    >
      <div className="card-topline">
        <span className="activity-badge">
          {t(`codes.activity_code.${card.activity_code}`)}
        </span>
        <span className={`fit-badge fit-${card.fit_status}`}>
          {t(`codes.fit_status.${card.fit_status}`)}
        </span>
      </div>
      {event.is_test || session.is_test ? (
        <span className="synthetic-badge">{t('card.test')}</span>
      ) : null}
      <h3 id={`event-${session.id}`}>{event.title}</h3>
      {event.description ? (
        <p className="card-description">{event.description}</p>
      ) : null}
      <dl className="card-facts">
        <div>
          <dt>{t('card.start')}</dt>
          <dd>{formatDateTime(session.starts_at, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.end')}</dt>
          <dd>{formatDateTime(session.ends_at, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.price')}</dt>
          <dd>{formatMoney(session.price_kzt_per_person, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.session')}</dt>
          <dd>{t(`codes.session_status.${session.status}`)}</dd>
        </div>
      </dl>
      <p className="timezone-note">{t('card.timezone')}</p>
      <CardFacts card={card} locale={locale} />
      <SourceDetails
        sources={[
          ...event.sources,
          ...session.sources,
          ...sources.filter((source) => citedIds.has(source.source_id)),
        ]}
        provenance={card.provenance}
        locale={locale}
      />
    </article>
  )
}
