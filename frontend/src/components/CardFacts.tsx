import { useTranslation } from 'react-i18next'
import { formatMinutes } from '../lib/format'
import type { CardDetails, Locale } from '../lib/types'
import { safeExternalUrl } from '../lib/links'

export function CardFacts({
  card,
  locale,
  sourceUrl,
  ticketAction = false,
}: {
  card: Omit<CardDetails, 'provenance' | 'missing_fields'> & {
    missing_fields: string[]
  }
  locale: Locale
  sourceUrl: string | null
  ticketAction?: boolean
}) {
  const { t } = useTranslation()
  const actionUrl = safeExternalUrl(sourceUrl)
  const activity = t(`activityAction.${card.activity_code}`)
  const hasExplanation =
    card.generated_locale === locale && card.explanation.trim().length > 0
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
      <p className="field-hint">{t('card.searchSnapshot')}</p>
      <div className="card-idea">
        <h4>{t('card.idea')}</h4>
        <p>{activity}</p>
      </div>
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
          {t(hasExplanation ? 'card.explanation' : 'card.localizedSummary')}
        </h4>
        <p lang={locale}>
          {hasExplanation
            ? card.explanation
            : t('card.explanationFallback', {
                activity: t(`codes.activity_code.${card.activity_code}`),
                reasons:
                  card.reason_codes.length > 0
                    ? card.reason_codes
                        .map((reason) => t(`codes.reason_codes.${reason}`))
                        .join('; ')
                    : t('card.reasonUnknown'),
              })}
        </p>
      </div>
      {card.missing_fields.length > 0 ? (
        <div className="missing-details">
          <h4>{t('card.missing')}</h4>
          <ul>
            {card.missing_fields.map((field) => (
              <li key={field}>
                {t(`codes.missing_fields.${field}`, {
                  defaultValue: t(`events.fields.${field}`, {
                    defaultValue: t('source.otherFact'),
                  }),
                })}
              </li>
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
          {t(
            ticketAction
              ? 'events.checkTickets'
              : 'codes.action_code.open_source',
          )}{' '}
          <span aria-hidden="true">↗</span>
        </a>
      ) : (
        <p>{t('card.unsafeLink')}</p>
      )}
    </>
  )
}
