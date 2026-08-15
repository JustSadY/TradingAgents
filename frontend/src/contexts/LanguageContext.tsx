import React, { createContext, useContext, useCallback } from 'react'
import { I18nextProvider, useTranslation as useI18nextTranslation } from 'react-i18next'
import { getAccessToken } from './AuthContext'
import i18n, { LANGUAGE_STORAGE_KEY, readStoredLanguage, type Language } from '../i18n'

export type { Language }

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  /**
   * Translate a key. Accepts i18next interpolation values, so a string with a
   * `{{placeholder}}` can keep its word order in every locale instead of being
   * assembled by concatenation at the call site.
   */
  t: (key: string, options?: Record<string, unknown>) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

/**
 * App-facing language state, backed by i18next.
 *
 * The context deliberately keeps its own `{ language, setLanguage, t }` shape
 * rather than exposing react-i18next's `{ t, i18n }`: it also owns persistence
 * and the `/api/settings` write, and keeping the shape means the ~52 consuming
 * components did not have to change when i18next was introduced.
 */
const LanguageStateProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t: translate, i18n: instance } = useI18nextTranslation()
  const language = (instance.resolvedLanguage || readStoredLanguage()) as Language

  const setLanguage = useCallback((lang: Language) => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lang)
    void instance.changeLanguage(lang)
    const langMap: Record<Language, string> = { en: 'English', tr: 'Turkish' }
    const token = getAccessToken()
    if (token) {
      fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ output_language: langMap[lang] }),
      }).catch(() => {})
    }
  }, [instance])

  const t = useCallback(
    (key: string, options?: Record<string, unknown>) => translate(key, options),
    [translate],
  )

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <I18nextProvider i18n={i18n}>
    <LanguageStateProvider>{children}</LanguageStateProvider>
  </I18nextProvider>
)

export const useTranslation = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider')
  }
  return context
}
