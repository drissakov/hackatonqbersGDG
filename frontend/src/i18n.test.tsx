import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n, { resolvedLocale } from './i18n'
import { LanguageSwitch } from './components/LanguageSwitch'
import kk from './locales/kk/common.json'
import ru from './locales/ru/common.json'
import en from './locales/en/common.json'
import codes from '../../contracts/codes.json'
import { auditDictionaries } from './test/i18nAudit'

beforeEach(async () => {
  localStorage.clear()
  await i18n.changeLanguage('kk')
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('bundled interface languages', () => {
  it('switches kk/ru/en, marks the active language, persists preference and updates html.lang', async () => {
    const user = userEvent.setup()
    render(<LanguageSwitch />)
    expect(screen.getByRole('button', { name: 'Қазақша' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    for (const [locale, label] of [
      ['ru', 'Русский'],
      ['en', 'English'],
      ['kk', 'Қазақша'],
    ]) {
      await user.click(screen.getByRole('button', { name: label }))
      expect(resolvedLocale()).toBe(locale)
      expect(document.documentElement.lang).toBe(locale)
      expect(localStorage.getItem('qadam.language')).toBe(locale)
      expect(screen.getByRole('button', { name: label })).toHaveAttribute(
        'aria-pressed',
        'true',
      )
    }
  })

  it('detects the saved preference before navigator and reduces regional language tags', async () => {
    localStorage.setItem('qadam.language', 'ru-KZ')
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['en-GB'])
    await act(async () => {
      await i18n.changeLanguage()
    })
    expect(resolvedLocale()).toBe('ru')
    expect(document.documentElement.lang).toBe('ru')
  })

  it('falls back to kk for unsupported browser languages', async () => {
    localStorage.clear()
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-DE'])
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('de-DE')
    await act(async () => {
      await i18n.changeLanguage()
    })
    expect(resolvedLocale()).toBe('kk')
    expect(document.documentElement.lang).toBe('kk')
  })

  it('keeps switching usable when browser storage is blocked', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Blocked', 'SecurityError')
    })
    await expect(i18n.changeLanguage('en')).resolves.toBeDefined()
    expect(resolvedLocale()).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })

  it('has matching base keys, placeholders and locale-specific plurals with every contract display code', () => {
    expect(auditDictionaries({ kk, ru, en })).toEqual([])
    for (const dictionary of [kk, ru, en]) {
      for (const [kind, entries] of Object.entries(dictionary.codes)) {
        expect(Object.keys(entries).sort()).toEqual(
          (codes[kind as keyof typeof codes] as string[]).toSorted(),
        )
        expect(
          Object.values(entries).every(
            (entry) => typeof entry === 'string' && entry.length > 0,
          ),
        ).toBe(true)
      }
    }
  })

  it('accepts different plural suffix sets when each locale covers Intl.PluralRules', () => {
    expect(
      auditDictionaries({
        kk: { items_one: '{{count}} орын', items_other: '{{count}} орын' },
        ru: {
          items_one: '{{count}} место',
          items_few: '{{count}} места',
          items_many: '{{count}} мест',
          items_other: '{{count}} места',
        },
        en: { items_one: '{{count}} place', items_other: '{{count}} places' },
      }),
    ).toEqual([])
  })

  it('rejects missing plural categories, unsupported forms and changed interpolation names', () => {
    const problems = auditDictionaries({
      kk: { items_one: '{{count}} орын', items_other: '{{count}} орын' },
      ru: {
        items_one: '{{count}} место',
        items_many: '{{count}} мест',
        items_other: '{{total}} места',
      },
      en: {
        items_one: '{{count}} place',
        items_other: '{{count}} places',
        items_two: '{{count}} places',
      },
    })
    expect(problems).toEqual(
      expect.arrayContaining([
        'ru:items: missing plural few',
        'ru:items: interpolation placeholders differ',
        'en:items: invalid plural two',
      ]),
    )
  })

  it('rejects losing every plural form in one locale even when the base key survives', () => {
    const problems = auditDictionaries({
      kk: { items_one: '{{count}} орын', items_other: '{{count}} орын' },
      ru: { items: '{{count}} место' },
      en: { items_one: '{{count}} place', items_other: '{{count}} places' },
    })
    for (const category of new Intl.PluralRules('ru').resolvedOptions()
      .pluralCategories)
      expect(problems).toContain(`ru:items: missing plural ${category}`)
  })

  it('checks every bundled string directly in its locale without relying on fallback', () => {
    function verify(value: object, locale: 'kk' | 'ru' | 'en', prefix = '') {
      for (const [key, entry] of Object.entries(value)) {
        const path = `${prefix}${key}`
        if (typeof entry === 'object') verify(entry, locale, `${path}.`)
        else {
          expect(String(entry).trim()).not.toBe('')
          expect(String(entry)).not.toContain('\uFFFD')
          expect(String(entry)).not.toContain('\u0000')
          const translated = i18n.getFixedT(locale)(path, {
            activity: 'TEST activity',
            reasons: 'TEST reasons',
            index: 2,
            name: 'TEST name',
            amount: 'TEST amount',
          })
          expect(translated).not.toBe(path)
          expect(translated).not.toMatch(/\{\{|\}\}/u)
        }
      }
    }
    for (const [locale, dictionary] of Object.entries({ kk, ru, en }))
      verify(dictionary, locale as 'kk' | 'ru' | 'en')
    expect(JSON.stringify(kk)).toMatch(/[ӘәҒғҚқҢңӨөҰұҮүІі]/u)
  })
})
