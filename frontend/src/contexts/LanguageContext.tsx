import React, { createContext, useContext, useState, useCallback } from 'react'
import { getAccessToken } from './AuthContext'
import { TRANSLATIONS, type Language } from '../i18n'

export type { Language }

interface LanguageContextType {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<Language>(() => {
    return (localStorage.getItem('ta_language') as Language) || 'en'
  })

  const setLanguage = useCallback((lang: Language) => {
    localStorage.setItem('ta_language', lang)
    setLanguageState(lang)
    const langMap: Record<Language, string> = { en: 'English', tr: 'Turkish' }
    const token = getAccessToken()
    if (token) {
      fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ output_language: langMap[lang] }),
      }).catch(() => {})
    }
  }, [])

  const t = useCallback((key: string): string => {
    return TRANSLATIONS[language]?.[key] || TRANSLATIONS['en']?.[key] || key
  }, [language])

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export const useTranslation = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider')
  }
  return context
}

