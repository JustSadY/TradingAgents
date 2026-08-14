import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithQuery } from '../../test/renderWithQuery'
import Backtest from '../Backtest'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  post: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'backtest.title': 'Backtest',
        'backtest.ticker': 'Ticker',
        'backtest.strategy': 'Strategy',
        'backtest.consensus': 'Consensus',
        'backtest.macd': 'MACD Crossover',
        'backtest.rsi': 'RSI Oversold',
        'backtest.start_date': 'Start Date',
        'backtest.end_date': 'End Date',
        'backtest.initial_capital': 'Initial Capital',
        'backtest.run_btn': 'Run Backtest',
        'backtest.running': 'Running...',
        'backtest.error_load': 'Failed to run backtest',
        'backtest.error_dates': 'Start date must be before end date',
        'common.error': 'Error',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  AreaChart: ({ children }: any) => <div>{children}</div>,
  Area: () => <div>Area</div>,
  XAxis: () => <div>XAxis</div>,
  YAxis: () => <div>YAxis</div>,
  Tooltip: () => <div>Tooltip</div>,
  CartesianGrid: () => <div>CartesianGrid</div>,
}))

vi.mock('lucide-react', () => ({
  Play: () => <div>Play</div>,
  BarChart2: () => <div>BarChart2</div>,
  TrendingUp: () => <div>TrendingUp</div>,
  TrendingDown: () => <div>TrendingDown</div>,
  Target: () => <div>Target</div>,
  Search: () => <div>Search</div>,
  Landmark: () => <div>Landmark</div>,
  AlertCircle: () => <div>AlertCircle</div>,
  Sparkles: () => <div>Sparkles</div>,
  Loader2: () => <div>Loader2</div>,
}))

describe('Backtest', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders backtest form', async () => {
    renderWithQuery(<Backtest />)
    await waitFor(() => {
      expect(screen.getByText('Backtest')).toBeInTheDocument()
    })
  })

  it('renders strategy options', async () => {
    renderWithQuery(<Backtest />)
    await waitFor(() => {
      expect(screen.getByText('Consensus')).toBeInTheDocument()
      expect(screen.getByText('MACD Crossover')).toBeInTheDocument()
      expect(screen.getByText('RSI Oversold')).toBeInTheDocument()
    })
  })
})
