import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import { SearchForm } from './SearchForm'
import type { Locale } from '../lib/types'

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('D05 form language and keyboard quality', () => {
  it.each(['kk', 'ru', 'en'] as Locale[])(
    'preserves every Kazakh letter and submits the localized form by keyboard in %s',
    async (locale) => {
      vi.stubEnv('VITE_TWOGIS_MAP_KEY', '')
      await i18n.changeLanguage(locale)
      const user = userEvent.setup()
      const onSubmit = vi.fn()
      render(
        <SearchForm
          onSubmit={onSubmit}
          loading={false}
          mode="recommendations"
        />,
      )
      const query = screen.getByRole('textbox', {
        name: i18n.t('search.query'),
      })
      const unicodeQuery = 'Әә Ғғ Ққ Ңң Өө Ұұ Үү Һһ Іі — café / кофе / coffee'
      expect(query).toHaveAttribute(
        'placeholder',
        i18n.t('search.queryPlaceholder'),
      )
      expect(
        screen.getAllByPlaceholderText(i18n.t('search.unknownPlaceholder')),
      ).toHaveLength(2)
      fireEvent.change(query, { target: { value: unicodeQuery } })
      await user.tab()
      expect(query).toHaveFocus()
      const submit = screen.getByRole('button', {
        name: i18n.t('search.submit'),
      })
      for (
        let steps = 0;
        document.activeElement !== submit && steps < 12;
        steps += 1
      )
        await user.tab()
      expect(submit).toHaveFocus()
      await user.keyboard('{Enter}')
      expect(onSubmit).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({
          query: unicodeQuery,
          locale,
          origin: null,
          available_minutes: null,
          budget_kzt_per_person: null,
          date_time: null,
        }),
      )
      expect(document.documentElement.lang).toBe(locale)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    },
  )
})
