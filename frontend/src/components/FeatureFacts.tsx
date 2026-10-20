import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../lib/format'
import { safeExternalUrl } from '../lib/links'
import type { FeatureEvidence, Locale, Source } from '../lib/types'

export function FeatureFacts({
  evidence,
  sources,
  locale,
}: {
  evidence: FeatureEvidence[]
  sources: Source[]
  locale: Locale
}) {
  const { t } = useTranslation()
  if (evidence.length === 0) return null
  return (
    <section className="source-facts" aria-label={t('featureEvidence.title')}>
      <h4>{t('featureEvidence.title')}</h4>
      <p className="field-hint">{t('featureEvidence.notice')}</p>
      <ul>
        {evidence.map((fact) => {
          const source = sources.find(
            (entry) => entry.source_id === fact.source_id,
          )
          const url = safeExternalUrl(source?.url ?? null)
          if (!url) return null
          return (
            <li key={fact.field}>
              <p>
                <strong>{t(`codes.feature_fields.${fact.field}`)}:</strong>{' '}
                {t(fact.value ? 'featureEvidence.yes' : 'featureEvidence.no')}
              </p>
              <p lang="">
                {fact.source_field}={fact.source_value}
              </p>
              <p>
                {t('featureEvidence.checked')}:{' '}
                {formatDateTime(fact.checked_at, locale)}
              </p>
              <p>
                {t('featureEvidence.updated')}:{' '}
                {formatDateTime(fact.source_updated_at, locale)}
              </p>
              <p>
                {t('featureEvidence.observed')}:{' '}
                {formatDateTime(fact.observed_at, locale)}
              </p>
              <a href={url} target="_blank" rel="noopener noreferrer">
                {t('source.open')}
              </a>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
