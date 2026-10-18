import { useTranslation } from 'react-i18next'
import { formatMoney } from '../lib/format'
import type { Locale, RecommendationCard, Source } from '../lib/types'
import { CardFacts } from './CardFacts'
import { SourceDetails } from './SourceDetails'

interface ResultCardProps {
  card: RecommendationCard
  locale: Locale
  sources?: Source[]
}

export function ResultCard({ card, locale, sources = [] }: ResultCardProps) {
  const { t } = useTranslation()
  const { poi } = card
  const citedIds = new Set(card.provenance.map((fact) => fact.source_id))
  return (
    <article className="result-card" aria-labelledby={`poi-${poi.id}`}>
      <div className="card-topline">
        <span className="activity-badge">
          {t(`codes.activity_code.${card.activity_code}`)}
        </span>
        <span className={`fit-badge fit-${card.fit_status}`}>
          {t(`codes.fit_status.${card.fit_status}`)}
        </span>
      </div>
      {poi.is_test ? (
        <span className="synthetic-badge">{t('card.test')}</span>
      ) : null}
      <h3 id={`poi-${poi.id}`}>{poi.name}</h3>
      {poi.description ? (
        <p className="card-description">{poi.description}</p>
      ) : null}
      <dl className="card-facts">
        <div>
          <dt>{t('card.price')}</dt>
          <dd>{formatMoney(poi.price_kzt_per_person, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.environment')}</dt>
          <dd>
            {poi.indoor === null
              ? t('card.unknown')
              : t(poi.indoor ? 'card.indoor' : 'card.outdoor')}
          </dd>
        </div>
        <div>
          <dt>{t('card.address')}</dt>
          <dd>{poi.address ?? t('card.unknown')}</dd>
        </div>
      </dl>
      {poi.opening_hours_text ? (
        <p className="source-hours">
          <strong>{t('card.hours')}:</strong> {poi.opening_hours_text}
        </p>
      ) : null}
      <CardFacts card={card} locale={locale} />
      <SourceDetails
        sources={[
          ...poi.sources,
          ...sources.filter((source) => citedIds.has(source.source_id)),
        ]}
        provenance={card.provenance}
        locale={locale}
      />
    </article>
  )
}
