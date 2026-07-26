import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axios from 'axios'
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
  const validPortfolio = {
    cash_available: 100_000,
    total_value: 100_000,
    total_pnl: 0,
    total_pnl_pct: 0,
    holdings: [],
    benchmark_ticker: null,
    benchmark_return_pct: null,
    alpha_pct: null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(axios.get).mockResolvedValue({ data: validPortfolio })
  })

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

  it('shows a recoverable error instead of rendering a malformed portfolio payload', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: {} })

    render(<MockTrading />)

    await waitFor(() => {
      expect(screen.getByText('Error Loading Portfolio')).toBeInTheDocument()
    })
    expect(screen.getByText('Unable to connect to trading engine')).toBeInTheDocument()
  })

  it('handles a malformed order response without crashing the page', async () => {
    vi.mocked(axios.post).mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    render(<MockTrading />)

    await screen.findByText('Paper Trading')
    await user.type(screen.getByPlaceholderText('mocktrading.order_symbol_placeholder'), 'AAPL')
    await user.type(screen.getByPlaceholderText('mocktrading.order_quantity_placeholder'), '1')
    await user.click(screen.getByRole('button', { name: 'mocktrading.order_submit_buy' }))

    await waitFor(() => expect(screen.getByText('Order failed')).toBeInTheDocument())
    expect(screen.getByText('Paper Trading')).toBeInTheDocument()
  })
})
