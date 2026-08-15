import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithQuery } from '../../test/renderWithQuery'
import Portfolio from '../Portfolio'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'portfolio.title': 'Portfolio',
        'portfolio.loading': 'Loading portfolio...',
        'portfolio.error': 'Error Loading Portfolio',
        'portfolio.initial': 'Initial Capital',
        'portfolio.cash': 'Cash',
        'portfolio.all_positions': 'All Positions',
        'portfolio.no_positions': 'No open positions',
        'portfolio.col_symbol': 'Symbol',
        'portfolio.col_quantity': 'Qty',
        'portfolio.risk_breach_title': 'Risk Threshold Breach',
        'portfolio.risk_breach_beta': 'Beta exceeds threshold',
        'portfolio.risk_breach_vol': 'Volatility exceeds threshold',
        'portfolio.risk_breach_conc': 'Concentration exceeds threshold',
        'orders.filter_simulation': 'Simulation',
        'orders.filter_live': 'Live',
        'common.retry': 'Retry Connection',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../utils/notify', () => ({ notify: vi.fn() }))
vi.mock('../../utils/csvExport', () => ({ exportPortfolioCSV: vi.fn() }))
vi.mock('../../components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: any) => children }))

vi.mock('lucide-react', () => ({
  TrendingUp: () => <div>TrendingUp</div>,
  TrendingDown: () => <div>TrendingDown</div>,
  DollarSign: () => <div>DollarSign</div>,
  Briefcase: () => <div>Briefcase</div>,
  Loader2: () => <div>Loader2</div>,
  AlertCircle: () => <div>AlertCircle</div>,
  RefreshCw: () => <div>RefreshCw</div>,
  PieChart: () => <div>PieChart</div>,
  Sparkles: () => <div>Sparkles</div>,
  X: () => <div>X</div>,
  CheckCircle2: () => <div>CheckCircle2</div>,
  ShieldAlert: () => <div>ShieldAlert</div>,
  Activity: () => <div>Activity</div>,
  ChevronDown: () => <div>ChevronDown</div>,
  ChevronUp: () => <div>ChevronUp</div>,
  Download: () => <div>Download</div>,
  Grid3x3: () => <div>Grid3x3</div>,
}))

describe('Portfolio', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders loading state initially', () => {
    renderWithQuery(<Portfolio />)
    expect(screen.getByText('Loading portfolio...')).toBeInTheDocument()
  })
})
