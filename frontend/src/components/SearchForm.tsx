import { useState } from 'react'
import type { FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import type { ConstraintField, Locale, SearchRequest } from '../lib/types'
import { astanaDateTimeToIso } from '../lib/format'
import { GeoPointPicker } from './GeoPointPicker'
import type { PointSource } from './GeoPointPicker'

interface SearchFormProps {
  onSubmit: (request: SearchRequest) => void
  onInputChange?: () => void
  loading: boolean
  mode: 'recommendations' | 'events'
}

type FormError =
  | 'query'
  | 'origin'
  | 'available_minutes'
  | 'budget_kzt_per_person'
  | 'date_time'

function optionalInteger(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

export function SearchForm({
  onSubmit,
  onInputChange,
  loading,
  mode,
}: SearchFormProps) {
  const { t, i18n } = useTranslation()
  const [query, setQuery] = useState('')
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')
  const [pointSource, setPointSource] = useState<PointSource>('unknown')
  const [minutes, setMinutes] = useState('')
  const [budget, setBudget] = useState('')
  const [returnToStart, setReturnToStart] = useState(false)
  const [indoor, setIndoor] = useState(false)
  const [dateTime, setDateTime] = useState('')
  const [explicitFields, setExplicitFields] = useState<ConstraintField[]>([])
  const [errors, setErrors] = useState<Partial<Record<FormError, string>>>({})

  function markExplicit(field: ConstraintField) {
    onInputChange?.()
    setExplicitFields((current) =>
      current.includes(field) ? current : [...current, field],
    )
    setErrors((current) => ({ ...current, [field]: undefined }))
  }

  function changePoint(
    nextLatitude: string,
    nextLongitude: string,
    source: PointSource,
  ) {
    setLatitude(nextLatitude)
    setLongitude(nextLongitude)
    setPointSource(source)
    markExplicit('origin')
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return

    const nextErrors: Partial<Record<FormError, string>> = {}
    const form = event.currentTarget
    const badInput = (name: string) => {
      const control = form.elements.namedItem(name)
      return control instanceof HTMLInputElement && control.validity.badInput
    }
    const trimmedQuery = query.trim()
    const availableMinutes = optionalInteger(minutes)
    const budgetKzt = optionalInteger(budget)
    const hasLatitude = latitude.trim() !== ''
    const hasLongitude = longitude.trim() !== ''
    const lat = Number(latitude)
    const lon = Number(longitude)

    if (!trimmedQuery) nextErrors.query = 'search.queryRequired'
    else if (trimmedQuery.length > 2000)
      nextErrors.query = 'search.queryTooLong'
    if (
      badInput('latitude') ||
      badInput('longitude') ||
      hasLatitude !== hasLongitude ||
      (hasLatitude &&
        (!Number.isFinite(lat) ||
          !Number.isFinite(lon) ||
          lat < -90 ||
          lat > 90 ||
          lon < -180 ||
          lon > 180))
    )
      nextErrors.origin = 'location.coordinatesInvalid'
    if (
      badInput('available_minutes') ||
      (availableMinutes !== null &&
        (!Number.isInteger(availableMinutes) ||
          availableMinutes < 1 ||
          availableMinutes > 1440))
    ) {
      nextErrors.available_minutes = 'search.minutesInvalid'
    }
    if (
      badInput('budget_kzt_per_person') ||
      (budgetKzt !== null &&
        (!Number.isSafeInteger(budgetKzt) || budgetKzt < 0))
    ) {
      nextErrors.budget_kzt_per_person = 'search.budgetInvalid'
    }
    const awareDateTime = dateTime ? astanaDateTimeToIso(dateTime) : null
    if (badInput('date_time') || (dateTime && !awareDateTime))
      nextErrors.date_time = 'search.dateTimeInvalid'

    setErrors(nextErrors)
    const firstError = Object.keys(nextErrors)[0] as FormError | undefined
    if (firstError) {
      const originField = badInput('latitude')
        ? 'latitude'
        : badInput('longitude')
          ? 'longitude'
          : !hasLatitude || !Number.isFinite(lat) || lat < -90 || lat > 90
            ? 'latitude'
            : 'longitude'
      const names: Record<FormError, string> = {
        query: 'query',
        origin: originField,
        available_minutes: 'available_minutes',
        budget_kzt_per_person: 'budget_kzt_per_person',
        date_time: 'date_time',
      }
      const control = form.elements.namedItem(names[firstError])
      if (control instanceof HTMLElement) control.focus()
      return
    }

    const locale: Locale =
      i18n.resolvedLanguage === 'ru' || i18n.resolvedLanguage === 'en'
        ? i18n.resolvedLanguage
        : 'kk'
    onSubmit({
      query: trimmedQuery,
      locale,
      origin: hasLatitude ? { latitude: lat, longitude: lon } : null,
      available_minutes: availableMinutes,
      return_to_start: returnToStart,
      budget_kzt_per_person: budgetKzt,
      indoor_only: indoor,
      date_time: awareDateTime,
      explicit_fields: explicitFields,
    })
  }

  return (
    <form
      className="search-form"
      onSubmit={submit}
      noValidate
      autoComplete="off"
      onInputCapture={(event) => {
        const control = event.target
        if (
          !(control instanceof HTMLInputElement) ||
          !control.validity.badInput
        )
          return
        if (
          control.name === 'available_minutes' ||
          control.name === 'budget_kzt_per_person' ||
          control.name === 'date_time'
        )
          markExplicit(control.name)
      }}
      aria-busy={loading}
    >
      <label className="field query-field" htmlFor="search-query">
        <span>{t('search.query')}</span>
        <textarea
          id="search-query"
          name="query"
          value={query}
          maxLength={2000}
          placeholder={t('search.queryPlaceholder')}
          aria-invalid={Boolean(errors.query)}
          aria-describedby={errors.query ? 'query-error' : undefined}
          onChange={(event) => {
            onInputChange?.()
            setQuery(event.target.value)
            setErrors((current) => ({ ...current, query: undefined }))
          }}
          rows={3}
          required
        />
      </label>
      {errors.query && (
        <p className="field-error" id="query-error">
          {t(errors.query)}
        </p>
      )}

      <GeoPointPicker
        latitude={latitude}
        longitude={longitude}
        source={pointSource}
        onChange={changePoint}
        error={errors.origin ? t(errors.origin) : undefined}
      />

      <fieldset className="constraint-fields">
        <legend>{t('search.constraints')}</legend>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="available-minutes">{t('search.minutes')}</label>
            <input
              id="available-minutes"
              name="available_minutes"
              type="number"
              min={1}
              max={1440}
              step={1}
              value={minutes}
              placeholder={t('search.unknownPlaceholder')}
              aria-invalid={Boolean(errors.available_minutes)}
              aria-describedby={
                errors.available_minutes ? 'minutes-error' : undefined
              }
              onChange={(event) => {
                setMinutes(event.target.value)
                markExplicit('available_minutes')
              }}
            />
            {errors.available_minutes && (
              <span className="field-error" id="minutes-error">
                {t(errors.available_minutes)}
              </span>
            )}
          </div>
          <div className="field">
            <label htmlFor="budget-kzt">{t('search.budget')}</label>
            <input
              id="budget-kzt"
              name="budget_kzt_per_person"
              type="number"
              min={0}
              step={1}
              value={budget}
              placeholder={t('search.unknownPlaceholder')}
              aria-invalid={Boolean(errors.budget_kzt_per_person)}
              aria-describedby={
                errors.budget_kzt_per_person ? 'budget-error' : undefined
              }
              onChange={(event) => {
                setBudget(event.target.value)
                markExplicit('budget_kzt_per_person')
              }}
            />
            {errors.budget_kzt_per_person && (
              <span className="field-error" id="budget-error">
                {t(errors.budget_kzt_per_person)}
              </span>
            )}
          </div>
        </div>

        <div className="field">
          <label htmlFor="search-date-time">{t('search.dateTime')}</label>
          <input
            id="search-date-time"
            name="date_time"
            type="datetime-local"
            value={dateTime}
            aria-invalid={Boolean(errors.date_time)}
            aria-describedby={`date-time-hint${errors.date_time ? ' date-time-error' : ''}`}
            onChange={(event) => {
              setDateTime(event.target.value)
              markExplicit('date_time')
            }}
          />
          <span className="field-hint" id="date-time-hint">
            {t('search.dateTimeHint')}
          </span>
          {errors.date_time && (
            <span className="field-error" id="date-time-error">
              {t(errors.date_time)}
            </span>
          )}
        </div>
        <div className="checkbox-fields">
          <label className="checkbox-field">
            <input
              type="checkbox"
              name="return_to_start"
              checked={returnToStart}
              onChange={(event) => {
                setReturnToStart(event.target.checked)
                markExplicit('return_to_start')
              }}
            />
            <span>{t('search.returnToStart')}</span>
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              name="indoor_only"
              checked={indoor}
              onChange={(event) => {
                setIndoor(event.target.checked)
                markExplicit('indoor_only')
              }}
            />
            <span>{t('search.indoor')}</span>
          </label>
        </div>
      </fieldset>
      {Object.values(errors).some(Boolean) && (
        <p className="field-error" role="alert">
          {t('search.validationSummary')}
        </p>
      )}
      <button
        className="primary-button search-submit"
        type="submit"
        disabled={loading}
      >
        {t(
          loading
            ? 'search.searching'
            : mode === 'events'
              ? 'search.submitEvents'
              : 'search.submit',
        )}
        <span aria-hidden="true">↗</span>
      </button>
    </form>
  )
}
