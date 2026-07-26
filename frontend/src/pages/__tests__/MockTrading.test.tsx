import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import MockTrading from '../MockTrading'

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
        'mocktrading.title': 'Paper Trading',
        'mocktrading.loading': 'Loading portfolio...',
        'mocktrading.error_title': 'Error Loading Portfolio',
        'mocktrading.error_msg': 'Unable to connect to trading engine',
        'mocktrading.retry': 'Retry',
        'mocktrading.refresh': 'Refresh',
        'mocktrading.reset': 'Reset Portfolio',
        'mocktrading.reset_confirm': 'Are you sure?',
        'mocktrading.stat_total_value': 'Total Value',
        'mocktrading.stat_total_pnl': 'Total P&L',
        'mocktrading.stat_cash': 'Cash',
        'mocktrading.order_error_default': 'Order failed',
        'mocktrading.buy': 'BUY',
        'mocktrading.sell': 'SELL',
        'mocktrading.place_order': 'Place Order',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('lucide-react', () => ({
  TrendingUp: () => <div>TrendingUp</div>,
  TrendingDown: () => <div>TrendingDown</div>,
  DollarSign: () => <div>DollarSign</div>,
  ShoppingCart: () => <div>ShoppingCart</div>,
  BarChart2: () => <div>BarChart2</div>,
  RefreshCw: () => <div>RefreshCw</div>,
  RotateCcw: () => <div>RotateCcw</div>,
  AlertCircle: () => <div>AlertCircle</div>,
  CheckCircle: () => <div>CheckCircle</div>,
  Loader2: () => <div>Loader2</div>,
}))

describe('MockTrading', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders loading state initially', () => {
    render(<MockTrading />)
    expect(screen.getByText('Loading portfolio...')).toBeInTheDocument()
  })

  it('renders paper trading title after loading', async () => {
    render(<MockTrading />)
    await waitFor(() => {
      expect(screen.getByText('Paper Trading')).toBeInTheDocument()
    })
  })
})
