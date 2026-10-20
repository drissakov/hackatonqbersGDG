import { useTranslation } from 'react-i18next'
import type {
  ConstraintClarification,
  MissingField,
  SearchWarning,
} from '../lib/types'

const unknownReasonKeys = {
  child_suitability: 'unknownReasons.child_suitability',
  age_restrictions: 'unknownReasons.age_restrictions',
  power_outlets: 'unknownReasons.power_outlets',
} as const

function isUnknownReason(
  field: MissingField,
): field is keyof typeof unknownReasonKeys {
  return Object.hasOwn(unknownReasonKeys, field)
}

export function ConstraintClarificationMessages({
  clarifications,
}: {
  clarifications: ConstraintClarification[]
}) {
  const { t } = useTranslation()
  const unique = clarifications.filter(
    (clarification, position, all) =>
      all.findIndex(
        (other) =>
          other.field === clarification.field &&
          other.reason === clarification.reason,
      ) === position,
  )
  return (
    <>
      {unique.map(({ field, reason }) => (
        <p key={`${field}-${reason}`}>
          {t(`constraintClarifications.${reason}.${field}`)}
        </p>
      ))}
    </>
  )
}

/** Stable API fields are translated on every render, including language changes. */
export function SearchWarnings({ warnings }: { warnings: SearchWarning[] }) {
  const { t } = useTranslation()
  if (warnings.length === 0) return null
  const hasUnknownReason = warnings.some((warning) =>
    warning.fields.some(isUnknownReason),
  )
  const hasClarification = warnings.some(
    (warning) => warning.clarifications.length > 0,
  )

  return (
    <>
      <ul className="warning-list">
        {warnings.map((warning, index) => {
          const fields = [...new Set(warning.fields)]
          const ordinaryFields = fields.filter(
            (field) => !isUnknownReason(field),
          )
          const reasons = fields.filter(isUnknownReason)
          return (
            <li key={`${warning.code}-${index}`}>
              {t(`codes.warning_codes.${warning.code}`)}
              {ordinaryFields.length > 0
                ? `: ${ordinaryFields.map((field) => t(`codes.missing_fields.${field}`)).join(', ')}`
                : ''}
              {reasons.map((reason) => (
                <p key={reason}>{t(unknownReasonKeys[reason])}</p>
              ))}
              <ConstraintClarificationMessages
                clarifications={warning.clarifications}
              />
            </li>
          )
        })}
      </ul>
      {hasClarification ? (
        <p className="event-notice">{t('constraintClarifications.resubmit')}</p>
      ) : null}
      {hasUnknownReason ? (
        <p className="event-notice">{t('unknownReasons.checkWithVenue')}</p>
      ) : null}
    </>
  )
}
