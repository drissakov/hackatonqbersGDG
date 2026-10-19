import { useTranslation } from 'react-i18next'
import { safeExternalUrl } from '../lib/links'
import type { EventCitation } from '../lib/types'

/** Search evidence remains inspectable even when no event could be normalized. */
export function EventSearchSources({
  citations,
}: {
  citations: EventCitation[]
}) {
  const { t } = useTranslation()
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
