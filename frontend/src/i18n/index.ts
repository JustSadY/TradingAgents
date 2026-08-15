import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

export type Language = 'en' | 'tr'

export const LANGUAGES: readonly Language[] = ['en', 'tr'] as const
export const DEFAULT_LANGUAGE: Language = 'en'
export const LANGUAGE_STORAGE_KEY = 'ta_language'

type TranslationModule = { default?: { en?: Record<string, string>; tr?: Record<string, string> } }

// Every sibling module is a locale bundle. Globbing rather than listing them
// means a new file is picked up by the runtime and by the parity test at the
// same moment — a hand-maintained list previously let the two drift.
const modules = import.meta.glob<TranslationModule>(['./*.ts', '!./index.ts'], { eager: true })

function load(): Record<Language, Record<string, string>> {
  const merged: Record<Language, Record<string, string>> = { en: {}, tr: {} }
  for (const module of Object.values(modules)) {
    const bundle = module.default
    if (!bundle) continue
    Object.assign(merged.en, bundle.en || {})
    Object.assign(merged.tr, bundle.tr || {})
  }
  return merged
}

/**
 * The merged translation table.
 *
 * Exported so `__tests__/i18n.test.ts` can check en/tr parity against exactly
 * what gets handed to i18next, rather than against a copy of it.
 */
export const TRANSLATIONS = load()

export function readStoredLanguage(): Language {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY)
  return LANGUAGES.includes(stored as Language) ? (stored as Language) : DEFAULT_LANGUAGE
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: TRANSLATIONS.en },
    tr: { translation: TRANSLATIONS.tr },
  },
  lng: readStoredLanguage(),
  fallbackLng: DEFAULT_LANGUAGE,
  supportedLngs: LANGUAGES,

  // Every one of our ~1000 keys is a dotted string like `analysis.strategy.bias`
  // held in a flat object. Leaving i18next's defaults on would make it read
  // those dots as a path into nested resources and resolve nothing.
  keySeparator: false,
  nsSeparator: false,

  interpolation: {
    // React escapes rendered values already; escaping here would double-encode.
    escapeValue: false,
  },

  returnNull: false,
})

export default i18n
