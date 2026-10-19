import { useTranslation } from 'react-i18next'
import { safeExternalUrl } from '../lib/links'
import { formatDateTime } from '../lib/format'
import type { EventCitation, Locale, TransientEventSource } from '../lib/types'

/** Search evidence remains inspectable even when no event could be normalized. */
export function EventSearchSources({
  citations = [],
  sources,
  locale = 'kk',
}: {
  citations?: EventCitation[]
  sources?: TransientEventSource[]
  locale?: Locale
}) {
  const { t } = useTranslation()
  if (sources)
    return sources.length > 0 ? (
      <details className="source-details">
        <summary>{t('source.title')}</summary>
        <p>{t('events.observationNotice')}</p>
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.source_id}>
              {safeExternalUrl(source.url) ? (
                <a
                  href={safeExternalUrl(source.url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {source.url}
                </a>
              ) : (
                <span>{t('card.unsafeLink')}</span>
              )}
              <p>
                {t('events.observed')}:{' '}
                {formatDateTime(source.retrieved_at, locale)}
              </p>
            </li>
          ))}
        </ul>
      </details>
    ) : null
  if (citations.length === 0) return null
  return (
    <details className="source-details">
      <summary>{t('events.citations')}</summary>
      <p>{t('events.citationNotice')}</p>
      <ul className="source-list">
        {citations.map((citation, index) => {
          const url = safeExternalUrl(citation.url)
          return (
            <li key={`${citation.url}-${citation.start_index}-${index}`}>
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {t('source.open')}
                </a>
              ) : (
                <span>{t('card.unsafeLink')}</span>
              )}
            </li>
          )
        })}
      </ul>
    </details>
  )
}
