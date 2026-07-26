import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Chart from '../Chart'
import api from '../../utils/api'

vi.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('../../utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'chart.title': 'Chart',
        'chart.error_load': 'Failed to load chart data',
        'chart.search_placeholder': 'Search ticker...',
        'chart.period': 'Period',
        'chart.indicators': 'Indicators',
        'chart.patterns': 'Patterns',
        'chart.formula': 'Custom Formula',
        'chart.formula_assist': 'AI Formula Assistant',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../hooks/usePriceChart', () => ({
  usePriceChart: vi.fn(),
}))

vi.mock('../../utils/signalTone', () => ({
  signalTone: () => 'neutral',
  TONE_DOT_CLASS: 'dot-neutral',
}))

vi.mock('../../components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: any) => children }))
vi.mock('../../components/chart/ChartSearch', () => ({
  ChartSearch: ({ tickerInput, setTickerInput, handleSearch }: any) => (
    <div>
      <div>ChartSearch</div>
      <input aria-label="ticker" value={tickerInput} onChange={e => setTickerInput(e.target.value)} />
      <button onClick={handleSearch}>Search</button>
    </div>
  ),
}))
vi.mock('../../components/chart/TechnicalControls', () => ({ TechnicalControls: () => <div>TechnicalControls</div> }))
vi.mock('../../components/chart/CustomIndicatorPane', () => ({
  CustomIndicatorPane: ({ sentimentChartData }: any) => <div>Sentiment points: {sentimentChartData.length}</div>,
}))
vi.mock('../../components/chart/AnalysisDetailSidebar', () => ({ AnalysisDetailSidebar: () => <div>AnalysisDetailSidebar</div> }))

vi.mock('lucide-react', () => ({
  RefreshCw: () => <div>RefreshCw</div>,
  BarChart2: () => <div>BarChart2</div>,
  AlertCircle: () => <div>AlertCircle</div>,
  Sparkles: () => <div>Sparkles</div>,
  ScanSearch: () => <div>ScanSearch</div>,
  TrendingUp: () => <div>TrendingUp</div>,
  TrendingDown: () => <div>TrendingDown</div>,
  Loader2: () => <div>Loader2</div>,
}))

describe('Chart', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders chart components', async () => {
    render(<Chart />)
    await waitFor(() => {
      expect(screen.getByText('ChartSearch')).toBeInTheDocument()
      expect(screen.getByText('TechnicalControls')).toBeInTheDocument()
    })
  })

  it('uses the sentiment-history object response and clears old candles on a failed symbol load', async () => {
    const get = vi.mocked(api.get)
    get.mockImplementation((url, config) => {
      const ticker = (config as any)?.params?.ticker
      if (ticker === 'AAPL' && url === '/api/market/ohlcv') {
        return Promise.resolve({ data: { candles: [{ time: '2026-07-18', open: 99, high: 101, low: 98, close: 100, volume: 1000 }] } }) as any
      }
      if (ticker === 'AAPL' && url === '/api/analysis/history') return Promise.resolve({ data: [] }) as any
      if (ticker === 'AAPL' && url === '/api/market/sentiment-history') {
        return Promise.resolve({ data: { ticker: 'AAPL', history: [{ time: '2026-07-18', value: 0.5 }] } }) as any
      }
      if (ticker === 'MSFT' && url === '/api/market/ohlcv') {
        return Promise.reject({ response: { data: { detail: 'No data found' } } })
      }
      return Promise.resolve({ data: [] }) as any
    })

    const user = userEvent.setup()
    render(<Chart />)
    const input = screen.getByLabelText('ticker')

    await user.type(input, 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => {
      expect(screen.getByText('$100.00')).toBeInTheDocument()
      expect(screen.getByText('Sentiment points: 1')).toBeInTheDocument()
    })

    await user.clear(input)
    await user.type(input, 'MSFT')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => expect(screen.getByText('No data found')).toBeInTheDocument())
    expect(screen.queryByText('$100.00')).not.toBeInTheDocument()
  })
})
