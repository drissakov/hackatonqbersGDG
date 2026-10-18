import { describe, expect, it } from 'vitest'
import {
  astanaDateTimeToIso,
  formatDateTime,
  formatMinutes,
  formatMoney,
} from './format'

describe('Astana wall-clock conversion', () => {
  it('converts datetime-local to a real instant without the browser timezone', () => {
    expect(astanaDateTimeToIso('2026-10-19T18:30')).toBe(
      '2026-10-19T13:30:00.000Z',
    )
    expect(astanaDateTimeToIso('2026-01-01T00:15:20')).toBe(
      '2025-12-31T19:15:20.000Z',
    )
  })

  it('uses timezone rules for the chosen date instead of assuming a constant offset', () => {
    expect(astanaDateTimeToIso('2023-10-19T18:30')).toBe(
      '2023-10-19T12:30:00.000Z',
    )
  })

  it.each([
    '',
    '2026-02-29T12:00',
    '2026-13-01T12:00',
    '2026-10-19T24:00',
    '2026-10-19T12:60',
    '2026-10-19',
    '2026-10-19T12:00Z',
  ])('rejects invalid or nonlocal input %s', (value) => {
    expect(astanaDateTimeToIso(value)).toBeNull()
  })
})

describe('localized formatting', () => {
  it('preserves the difference between zero and unknown price/time', () => {
    expect(formatMoney(0, 'en')).toContain('0')
    expect(formatMoney(1000, 'en')).toContain('KZT')
    expect(formatMoney(null, 'en')).toBe('Unknown')
    expect(formatMinutes(null, 'ru')).toBe('Неизвестно')
    expect(formatMinutes(0, 'en')).toContain('0')
    expect(formatMoney(Number.NaN, 'kk')).toBe('Белгісіз')
  })

  it('renders an instant in Astana time and keeps an unknown date unknown', () => {
    expect(formatDateTime('2026-10-19T13:30:00Z', 'en')).toContain('18:30')
    expect(formatDateTime(null, 'kk')).toBe('Белгісіз')
    expect(formatDateTime('invalid', 'en')).toBe('Unknown')
  })
})
