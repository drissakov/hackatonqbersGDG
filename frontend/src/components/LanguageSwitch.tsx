import { useTranslation } from 'react-i18next'
import { resolvedLocale } from '../i18n'
import type { Locale } from '../lib/types'

const languages: { locale: Locale; label: string }[] = [
  { locale: 'kk', label: 'Қазақша' },
  { locale: 'ru', label: 'Русский' },
  { locale: 'en', label: 'English' },
]

export function LanguageSwitch() {
  const { t, i18n } = useTranslation()
  const locale = resolvedLocale()
  return (
    <div
      className="language-switch"
      role="group"
      aria-label={t('language.label')}
    >
      {languages.map((language) => (
        <button
          type="button"
          key={language.locale}
          lang={language.locale}
          aria-pressed={locale === language.locale}
          onClick={() => {
            void i18n.changeLanguage(language.locale)
          }}
        >
          {language.label}
        </button>
      ))}
    </div>
  )
}
