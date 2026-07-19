import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LanguageProvider, useTranslation } from '../LanguageContext'

function TestConsumer() {
  const { language, setLanguage, t } = useTranslation()
  return (
    <div>
      <span data-testid="language">{language}</span>
      <span data-testid="translation">{t('nav.dashboard')}</span>
      <span data-testid="missing">{t('nonexistent.key')}</span>
      <button data-testid="set-en" onClick={() => setLanguage('en')}>EN</button>
      <button data-testid="set-tr" onClick={() => setLanguage('tr')}>TR</button>
    </div>
  )
}

function renderWithLang(children: React.ReactNode) {
  return render(<LanguageProvider>{children}</LanguageProvider>)
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  localStorage.clear()
})

describe('LanguageContext', () => {
  it('defaults to English', () => {
    renderWithLang(<TestConsumer />)
    expect(screen.getByTestId('language')).toHaveTextContent('en')
  })

  it('returns English translation for nav.dashboard', () => {
    renderWithLang(<TestConsumer />)
    expect(screen.getByTestId('translation')).toHaveTextContent('Dashboard')
  })

  it('returns the key itself for missing translations', () => {
    renderWithLang(<TestConsumer />)
    expect(screen.getByTestId('missing')).toHaveTextContent('nonexistent.key')
  })

  it('switches to Turkish', async () => {
    renderWithLang(<TestConsumer />)
    await userEvent.click(screen.getByTestId('set-tr'))
    expect(screen.getByTestId('language')).toHaveTextContent('tr')
    expect(screen.getByTestId('translation')).toHaveTextContent('Pano (Dashboard)')
  })

  it('persists language choice to localStorage', async () => {
    renderWithLang(<TestConsumer />)
    await userEvent.click(screen.getByTestId('set-tr'))
    expect(localStorage.getItem('ta_language')).toBe('tr')
  })

  it('reads persisted language from localStorage', () => {
    localStorage.setItem('ta_language', 'tr')
    renderWithLang(<TestConsumer />)
    expect(screen.getByTestId('language')).toHaveTextContent('tr')
  })

  it('falls back to English translation when key missing in Turkish', () => {
    localStorage.setItem('ta_language', 'tr')
    renderWithLang(<TestConsumer />)
    expect(screen.getByTestId('missing')).toHaveTextContent('nonexistent.key')
  })

  it('throws when used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<TestConsumer />)).toThrow('useTranslation must be used within a LanguageProvider')
    consoleError.mockRestore()
  })
})
