import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n, { resolvedLocale } from './i18n'
import { LanguageSwitch } from './components/LanguageSwitch'
import kk from './locales/kk/common.json'
import ru from './locales/ru/common.json'
import en from './locales/en/common.json'
import codes from '../../contracts/codes.json'

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

  it('has matching dictionary keys and labels for every display code in contract v1', () => {
    function leaves(value: object, prefix = ''): string[] {
      return Object.entries(value).flatMap(([key, entry]) =>
        typeof entry === 'object'
          ? leaves(entry, `${prefix}${key}.`)
          : `${prefix}${key}`,
      )
    }
    expect(leaves(kk).sort()).toEqual(leaves(en).sort())
    expect(leaves(ru).sort()).toEqual(leaves(en).sort())
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
})
