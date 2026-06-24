import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { LanguageProvider, useTranslation } from './LanguageContext'

function Probe({ translationKey }: { translationKey: string }) {
  const { t, language, setLanguage } = useTranslation()
  return (
    <div>
      <span data-testid="value">{t(translationKey)}</span>
      <span data-testid="language">{language}</span>
      <button onClick={() => setLanguage('tr')}>switch</button>
    </div>
  )
}

function renderKey(translationKey: string) {
  render(
    <LanguageProvider>
      <Probe translationKey={translationKey} />
    </LanguageProvider>
  )
}

describe('LanguageProvider', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => cleanup())

  it('defaults to English', () => {
    renderKey('nav.dashboard')
    expect(screen.getByTestId('language').textContent).toBe('en')
    expect(screen.getByTestId('value').textContent).toBe('Dashboard')
  })

  it('returns the key itself for unknown translations', () => {
    renderKey('nope.missing')
    expect(screen.getByTestId('value').textContent).toBe('nope.missing')
  })

  it('merges page translation modules from src/i18n at load time', () => {
    renderKey('login.subtitle')
    expect(screen.getByTestId('value').textContent).toBe('Dashboard Login')
  })

  it('honours the persisted language on startup', () => {
    localStorage.setItem('ta_language', 'tr')
    renderKey('login.subtitle')
    expect(screen.getByTestId('value').textContent).toBe('Dashboard Girişi')
  })

  it('switches language and persists the choice', () => {
    renderKey('nav.dashboard')
    fireEvent.click(screen.getByText('switch'))
    expect(screen.getByTestId('value').textContent).toBe('Pano (Dashboard)')
    expect(localStorage.getItem('ta_language')).toBe('tr')
  })
})
