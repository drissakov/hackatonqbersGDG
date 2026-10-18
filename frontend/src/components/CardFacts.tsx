import { useTranslation } from 'react-i18next'
import { formatMinutes } from '../lib/format'
import type { CardDetails, Locale } from '../lib/types'
import { safeExternalUrl } from '../lib/links'

export function CardFacts({
  card,
  locale,
}: {
  card: CardDetails
  locale: Locale
}) {
  const { t } = useTranslation()
  const actionUrl = safeExternalUrl(card.action.url)
  return (
    <>
      <dl className="card-facts">
        <div>
          <dt>{t('card.visit')}</dt>
          <dd>{formatMinutes(card.visit_minutes_estimate, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.travel')}</dt>
          <dd>{formatMinutes(card.travel_minutes_estimate, locale)}</dd>
        </div>
        <div>
          <dt>{t('card.route')}</dt>
          <dd>{t(`codes.route_status.${card.route_status}`)}</dd>
        </div>
      </dl>
      <div className="card-reasons">
        <h4>{t('card.why')}</h4>
        <ul className="reason-list">
          {card.reason_codes.map((reason) => (
            <li key={reason}>{t(`codes.reason_codes.${reason}`)}</li>
          ))}
        </ul>
      </div>
      <div className="card-explanation">
        <h4>
          {t('card.explanation')}{' '}
          <span lang={card.generated_locale}>
            ({card.generated_locale.toUpperCase()})
          </span>
        </h4>
        <p lang={card.generated_locale}>{card.explanation}</p>
      </div>
      {card.missing_fields.length > 0 ? (
        <div className="missing-details">
          <h4>{t('card.missing')}</h4>
          <ul>
            {card.missing_fields.map((field) => (
              <li key={field}>{t(`codes.missing_fields.${field}`)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="estimate-notice">{t('card.estimateNotice')}</p>
      {actionUrl ? (
        <a
          className="card-action"
          href={actionUrl}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t(`codes.action_code.${card.action.code}`)}{' '}
          <span aria-hidden="true">↗</span>
        </a>
      ) : (
        <p>{t('card.unsafeLink')}</p>
      )}
    </>
  )
}
