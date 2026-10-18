import type { Locale } from './types'

const locales: Record<Locale, string> = {
  kk: 'kk-KZ',
  ru: 'ru-KZ',
  en: 'en-GB',
}
const unknown: Record<Locale, string> = {
  kk: 'Белгісіз',
  ru: 'Неизвестно',
  en: 'Unknown',
}
export const APP_TIME_ZONE = 'Asia/Almaty'

export function formatMoney(value: number | null, locale: Locale): string {
  if (value === null || !Number.isFinite(value)) return unknown[locale]
  return new Intl.NumberFormat(locales[locale], {
    style: 'currency',
    currency: 'KZT',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatMinutes(value: number | null, locale: Locale): string {
  if (value === null || !Number.isFinite(value)) return unknown[locale]
  return new Intl.NumberFormat(locales[locale], {
    style: 'unit',
    unit: 'minute',
    unitDisplay: 'short',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatDateTime(value: string | null, locale: Locale): string {
  if (value === null) return unknown[locale]
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return unknown[locale]
  return new Intl.DateTimeFormat(locales[locale], {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: APP_TIME_ZONE,
  }).format(date)
}

const wallClock = new Intl.DateTimeFormat('en-GB', {
  timeZone: APP_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
})

function localParts(date: Date): number[] {
  const parts = Object.fromEntries(
    wallClock.formatToParts(date).map(({ type, value }) => [type, value]),
  )
  return ['year', 'month', 'day', 'hour', 'minute', 'second'].map((key) =>
    Number(parts[key]),
  )
}

function utcFromParts([
  year,
  month,
  day,
  hour,
  minute,
  second,
]: number[]): number {
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day)
  date.setUTCHours(hour, minute, second, 0)
  return date.getTime()
}

/** Interpret datetime-local as Astana wall time, independently of the browser zone. */
export function astanaDateTimeToIso(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(
    value,
  )
  if (!match) return null
  const expected = match.slice(1).map((part) => Number(part ?? 0))
  const [year, month, day, hour, minute, second] = expected
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31 ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  )
    return null
  const naive = utcFromParts(expected)
  const normalized = new Date(naive)
  if (
    normalized.getUTCFullYear() !== year ||
    normalized.getUTCMonth() !== month - 1 ||
    normalized.getUTCDate() !== day
  )
    return null
  let instant = naive
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const displayed = utcFromParts(localParts(new Date(instant)))
    const correction = naive - displayed
    instant += correction
    if (correction === 0) break
  }
  if (
    localParts(new Date(instant)).some(
      (part, index) => part !== expected[index],
    )
  )
    return null
  return new Date(instant).toISOString()
}
