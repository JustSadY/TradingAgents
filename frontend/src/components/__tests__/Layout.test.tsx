import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithQuery } from '../../test/renderWithQuery'
import { MemoryRouter } from 'react-router-dom'
import Layout from '../Layout'

const mockUseAuth = vi.fn()
const mockUsePermissions = vi.fn()
const mockUseTranslation = vi.fn()
const mockUseCurrency = vi.fn()

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('../../contexts/PermissionsContext', () => ({
  usePermissions: () => mockUsePermissions(),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => mockUseTranslation(),
}))

vi.mock('../../contexts/CurrencyContext', () => ({
  useCurrency: () => mockUseCurrency(),
  CURRENCIES: ['USD', 'EUR', 'GBP', 'TRY', 'JPY', 'CAD', 'AUD', 'CHF'],
}))

vi.mock('../UpdateBanner', () => ({
  default: () => null,
}))

vi.mock('../assistant/PortfolioAssistant', () => ({
  PortfolioAssistant: () => null,
}))

const t = (key: string) => {
  const map: Record<string, string> = {
    'nav.dashboard': 'Dashboard',
    'nav.section.trading_desk': 'Trading Desk',
    'nav.section.portfolio_trading': 'Portfolio & Trading',
    'nav.section.market_tools': 'Market Tools',
    'nav.section.system_config': 'Management & Settings',
  }
  return map[key] || key
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue({
    user: 'testuser',
    role: 'admin',
    isAdmin: true,
    isOwner: false,
    isAuthenticated: true,
    logout: vi.fn(),
    loading: false,
  })
  mockUsePermissions.mockReturnValue({
    canAccess: () => true,
    loading: false,
    allowedPages: ['dashboard', 'analysis', 'chart', 'trading', 'portfolio', 'orders', 'performance', 'backtest', 'watchlist', 'alerts', 'logs', 'settings', 'profile', 'admin'],
  })
  mockUseTranslation.mockReturnValue({ t, language: 'en', setLanguage: vi.fn() })
  mockUseCurrency.mockReturnValue({
    currency: 'USD',
    setCurrency: vi.fn(),
    symbol: '$',
  })
})

describe('Layout', () => {
  it('renders brand name', () => {
    renderWithQuery(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    )
    expect(screen.getAllByText('TradingAgents')[0]).toBeInTheDocument()
  })

  it('shows user avatar and name', () => {
    renderWithQuery(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    )
    expect(screen.getByText('testuser')).toBeInTheDocument()
    expect(screen.getByText('Admin')).toBeInTheDocument()
  })

  it('renders navigation sections', () => {
    renderWithQuery(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    )
    expect(screen.getByText('Trading Desk')).toBeInTheDocument()
    expect(screen.getByText('Portfolio & Trading')).toBeInTheDocument()
    expect(screen.getByText('Market Tools')).toBeInTheDocument()
    expect(screen.getByText('Management & Settings')).toBeInTheDocument()
  })

  it('renders language and currency controls', () => {
    renderWithQuery(
      <MemoryRouter>
        <Layout />
      </MemoryRouter>
    )
    expect(screen.getByText('EN')).toBeInTheDocument()
    expect(screen.getByText('TR')).toBeInTheDocument()
  })
})
