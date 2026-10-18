import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ResponseStatus } from '../lib/types'

interface Props {
  kind: 'recommendations' | 'events'
  loading: boolean
  onPreview: (status: ResponseStatus) => void
  onLive: () => void
}

export default function DevPreview({
  kind,
  loading,
  onPreview,
  onLive,
}: Props) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<ResponseStatus>('partial')
  if (!import.meta.env.DEV) return null
  return (
    <details className="dev-preview">
      <summary>{t('dev.title')}</summary>
      <p>{t('dev.description')}</p>
      {kind === 'recommendations' && (
        <label>
          {t('states.results')}
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as ResponseStatus)
            }
          >
            {(
              ['ok', 'partial', 'unknown', 'unavailable', 'no_match'] as const
            ).map((value) => (
              <option key={value} value={value}>
                {t(`codes.response_status.${value}`)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="dev-actions">
        <button
          className="secondary-button"
          type="button"
          disabled={loading}
          onClick={() => onPreview(status)}
        >
          {t('dev.preview')}
        </button>
        <button className="text-button" type="button" onClick={onLive}>
          {t('dev.live')}
        </button>
      </div>
    </details>
  )
}
