import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../lib/format'
import { safeExternalUrl } from '../lib/links'
import type { Locale, Provenance, Source } from '../lib/types'

interface SourceDetailsProps {
  sources: Source[]
  locale: Locale
  provenance?: Provenance[]
}

export function SourceDetails({
  sources,
  locale,
  provenance = [],
}: SourceDetailsProps) {
  const { t } = useTranslation()
  const uniqueSources = [
    ...new Map(sources.map((source) => [source.source_id, source])).values(),
  ]
  const uniqueProvenance = [
    ...new Map(
      provenance.map((fact) => [
        JSON.stringify([
          fact.source_id,
          fact.external_id,
          [...new Set(fact.fields)].sort(),
          fact.observed_at,
        ]),
        fact,
      ]),
    ).values(),
  ]
  return (
    <details className="source-details">
      <summary>{t('source.title')}</summary>
      {uniqueSources.length === 0 ? (
        <p>{t('source.none')}</p>
      ) : (
        <ul className="source-list">
          {uniqueSources.map((source) => {
            const url = safeExternalUrl(source.url)
            const rightsUrl = safeExternalUrl(source.rights_basis_url)
            const facts = uniqueProvenance.filter(
              (entry) => entry.source_id === source.source_id,
            )
            return (
              <li key={source.source_id}>
                <div className="source-heading">
                  <strong>
                    {t(`codes.source_provider.${source.provider}`)}
                  </strong>
                  {source.is_test ? (
                    <span className="synthetic-badge">{t('card.test')}</span>
                  ) : null}
                </div>
                {url ? (
                  <a href={url} target="_blank" rel="noopener noreferrer">
                    {t('source.open')}
                  </a>
                ) : null}
                <dl className="source-meta">
                  <div>
                    <dt>{t('source.retrieved')}</dt>
                    <dd>{formatDateTime(source.retrieved_at, locale)}</dd>
                  </div>
                  <div>
                    <dt>{t('source.license')}</dt>
                    <dd lang={source.license ? '' : locale}>
                      {source.license ?? t('source.unknown')}
                    </dd>
                  </div>
                  {rightsUrl ? (
                    <div>
                      <dt>{t('source.rights')}</dt>
                      <dd>
                        <a
                          href={rightsUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {t('source.rights')}
                        </a>
                      </dd>
                    </div>
                  ) : null}
                </dl>
                {facts.length === 0 ? (
                  <p>
                    {t('source.observed')}: {t('source.unknown')}
                  </p>
                ) : (
                  facts.map((fact, index) => (
                    <div
                      className="source-fact"
                      key={`${fact.external_id}-${index}`}
                    >
                      <p>
                        {t('source.observed')}:{' '}
                        {formatDateTime(fact.observed_at, locale)}
                      </p>
                      <p>
                        {t('source.supportedFacts')}:{' '}
                        {fact.fields
                          .map((field) =>
                            t(`source.field.${field}`, {
                              defaultValue: t('source.otherFact'),
                            }),
                          )
                          .join(', ')}
                      </p>
                    </div>
                  ))
                )}
              </li>
            )
          })}
        </ul>
      )}
    </details>
  )
}
