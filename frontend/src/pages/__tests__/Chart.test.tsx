import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Chart from '../Chart'

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
vi.mock('../../components/chart/ChartSearch', () => ({ ChartSearch: () => <div>ChartSearch</div> }))
vi.mock('../../components/chart/TechnicalControls', () => ({ TechnicalControls: () => <div>TechnicalControls</div> }))
vi.mock('../../components/chart/CustomIndicatorPane', () => ({ CustomIndicatorPane: () => <div>CustomIndicatorPane</div> }))
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
})
