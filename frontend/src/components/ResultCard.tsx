import { useTranslation } from 'react-i18next'
import { formatMoney } from '../lib/format'
import type { Locale, RecommendationCard, Source } from '../lib/types'
import { safeExternalUrl } from '../lib/links'
import { CardFacts } from './CardFacts'
import { SourceDetails } from './SourceDetails'
import { FeatureFacts } from './FeatureFacts'

interface ResultCardProps {
  card: RecommendationCard
  locale: Locale
  sources?: Source[]
  selected?: boolean
  onSelect?: () => void
}

export function ResultCard({
  card,
  locale,
  sources = [],
  selected = false,
  onSelect,
}: ResultCardProps) {
  const { t } = useTranslation()
  const { poi } = card
  const sourceIds = new Set(poi.sources.map((source) => source.source_id))
  const description =
    poi.provenance.some(
      (fact) =>
        sourceIds.has(fact.source_id) && fact.fields.includes('description'),
    ) && !poi.description?.startsWith('Derived summary from OSM tags:')
      ? poi.description
      : null
  const citedIds = new Set(card.provenance.map((fact) => fact.source_id))
  const cardSources = [
    ...poi.sources,
    ...sources.filter((source) => citedIds.has(source.source_id)),
  ]
  const sourceUrl =
    cardSources
      .map((source) => safeExternalUrl(source.url))
      .find((url) => url !== null) ?? null
  return (
    <article className="result-card" aria-labelledby={`poi-${poi.id}`}>
      <div className="card-topline">
        <span
          className="activity-badge"
          aria-label={`${t('card.category')}: ${t(`codes.activity_code.${poi.activity_code}`)}`}
        >
          {t(`codes.activity_code.${poi.activity_code}`)}
        </span>
        <span className={`fit-badge fit-${card.fit_status}`}>
          {t(`codes.fit_status.${card.fit_status}`)}
        </span>
      </div>
      {poi.is_test ? (
        <span className="synthetic-badge">{t('card.test')}</span>
      ) : null}
      <h3 id={`poi-${poi.id}`} lang="">
        {poi.name}
      </h3>
      {card.name_is_derived ? (
        <p className="field-hint">{t('featureEvidence.derivedName')}</p>
      ) : null}
      <h4>{t('card.sourceFacts')}</h4>
      {description ? (
        <p className="card-description">
          <strong>{t('card.sourceText')}:</strong>{' '}
          <span lang="">{description}</span>
        </p>
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
          <dd>
            <span lang={poi.address ? '' : locale}>
              {poi.address ?? t('card.unknown')}
            </span>
          </dd>
        </div>
      </dl>
      <p className="source-hours">
        <strong>{t('card.hours')}:</strong>{' '}
        <span lang={poi.opening_hours_text ? '' : locale}>
          {poi.opening_hours_text ?? t('card.unknown')}
        </span>
      </p>
      <p>
        <strong>{t('card.availability')}:</strong> {t('card.unknown')}
      </p>
      <FeatureFacts
        evidence={card.feature_evidence ?? []}
        sources={poi.sources}
        locale={locale}
      />
      <CardFacts card={card} locale={locale} sourceUrl={sourceUrl} />
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
        provenance={[...poi.provenance, ...card.provenance]}
        locale={locale}
      />
    </article>
  )
}
