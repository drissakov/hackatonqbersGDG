import { useTranslation } from 'react-i18next'
import { formatDateTime, formatMoney } from '../lib/format'
import type { EventCardData, Locale, Source } from '../lib/types'
import { safeExternalUrl } from '../lib/links'
import { CardFacts } from './CardFacts'
import { SourceDetails } from './SourceDetails'

interface EventCardProps {
  card: EventCardData
  locale: Locale
  sources?: Source[]
  selected?: boolean
  onSelect?: () => void
}

export function EventCard({
  card,
  locale,
  sources = [],
  selected = false,
  onSelect,
}: EventCardProps) {
  const { t } = useTranslation()
  const { event, session } = card
  const description = event.provenance.some(
    (fact) =>
      event.sources.some((source) => source.source_id === fact.source_id) &&
      fact.fields.includes('description'),
  )
    ? event.description
    : null
  const citedIds = new Set(card.provenance.map((fact) => fact.source_id))
  const cardSources = [
    ...event.sources,
    ...session.sources,
    ...sources.filter((source) => citedIds.has(source.source_id)),
  ]
  const confirmedBooking = session.provenance.some(
    (fact) =>
      fact.fields.includes('booking_url') &&
      session.sources.some((source) => source.source_id === fact.source_id),
  )
  const sourceUrl =
    (confirmedBooking ? safeExternalUrl(session.booking_url) : null) ??
    [...session.sources, ...event.sources]
      .map((source) => safeExternalUrl(source.url))
      .find((url) => url !== null) ??
    null
  return (
    <article
      className="event-card result-card"
      aria-labelledby={`event-${session.id}`}
    >
      <div className="card-topline">
        <span
          className="activity-badge"
          aria-label={`${t('card.category')}: ${t(`codes.activity_code.${event.activity_code}`)}`}
        >
          {t(`codes.activity_code.${event.activity_code}`)}
        </span>
        <span className={`fit-badge fit-${card.fit_status}`}>
          {t(`codes.fit_status.${card.fit_status}`)}
        </span>
      </div>
      {event.is_test || session.is_test ? (
        <span className="synthetic-badge">{t('card.test')}</span>
      ) : null}
      <h3 id={`event-${session.id}`} lang="">
        {event.title}
      </h3>
      <h4>{t('card.sourceFacts')}</h4>
      {description ? (
        <p className="card-description">
          <strong>{t('card.sourceText')}:</strong>{' '}
          <span lang="">{description}</span>
        </p>
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
        <div>
          <dt>{t('card.availability')}</dt>
          <dd>{t('card.unknown')}</dd>
        </div>
      </dl>
      <p className="timezone-note">{t('card.timezone')}</p>
      <CardFacts
        card={card}
        locale={locale}
        sourceUrl={sourceUrl}
        ticketAction
      />
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
      <SourceDetails
        sources={cardSources}
        provenance={[
          ...event.provenance,
          ...session.provenance,
          ...card.provenance,
        ]}
        locale={locale}
      />
    </article>
  )
}
