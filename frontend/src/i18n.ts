import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'
import kk from './locales/kk/common.json'
import ru from './locales/ru/common.json'
import en from './locales/en/common.json'
import type { Locale } from './lib/types'

// Storage may become unavailable after the browser detector's initial probe.
const safeStorage = {
  name: 'localStorage',
  lookup() {
    try {
      return window.localStorage.getItem('qadam.language') ?? undefined
    } catch {
      return undefined
    }
  },
  cacheUserLanguage(language: string) {
    try {
      window.localStorage.setItem('qadam.language', language)
    } catch {
      /* Language remains available for this page. */
    }
  },
}

class SafeLanguageDetector extends LanguageDetector {
  override init(...args: Parameters<LanguageDetector['init']>) {
    super.init(...args)
    this.addDetector(safeStorage)
  }
}

const detector = new SafeLanguageDetector()

export function resolvedLocale(): Locale {
  const language = i18n.resolvedLanguage
  return language === 'ru' || language === 'en' ? language : 'kk'
}

function updateDocumentLanguage() {
  if (typeof document !== 'undefined')
    document.documentElement.lang = resolvedLocale()
}

i18n.on('languageChanged', updateDocumentLanguage)

void i18n
  .use(detector)
  .use(initReactI18next)
  .init({
    resources: { kk: { common: kk }, ru: { common: ru }, en: { common: en } },
    defaultNS: 'common',
    supportedLngs: ['kk', 'ru', 'en'],
    load: 'languageOnly',
    fallbackLng: 'kk',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'qadam.language',
      caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    initAsync: false,
  })
  .then(updateDocumentLanguage)

export default i18n
