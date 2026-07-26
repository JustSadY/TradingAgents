import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Orders from '../Orders'

const mockOrder = {
  id: 1,
  portfolio_id: 1,
  broker: 'simulation',
  ticker: 'AAPL',
  action: 'BUY',
  quantity_requested: 10,
  quantity_filled: 10,
  status: 'FILLED',
  price_per_share: 150,
  total_value: 1500,
  commission: 1,
  leverage: 1,
  side: 'long',
  realized_pnl: 0,
  analysis_id: null,
  ai_signal: 'Buy',
  created_at: '2024-01-01T00:00:00Z',
  executed_at: '2024-01-01T00:00:00Z',
}

const mockGet = vi.fn((url: string) => {
  if (url === '/api/portfolio/orders') return Promise.resolve({ data: [mockOrder] })
  return Promise.resolve({ data: [] })
})

vi.mock('axios', () => ({
  default: {
    get: (...args: [string]) => mockGet(...args),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: (...args: [string]) => mockGet(...args),
  post: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'orders.title': 'Orders',
        'orders.loading': 'Loading orders...',
        'orders.empty': 'No orders yet',
        'orders.col_symbol': 'Symbol',
        'orders.col_direction': 'Direction',
        'orders.col_quantity': 'Qty',
        'orders.col_price': 'Price',
        'orders.col_total': 'Total',
        'orders.col_status': 'Status',
        'orders.col_signal': 'Signal',
        'orders.col_date': 'Date',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../utils/notify', () => ({ notify: vi.fn() }))
vi.mock('../../utils/csvExport', () => ({ exportOrdersCSV: vi.fn() }))
vi.mock('../../components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: any) => children }))

vi.mock('lucide-react', () => ({
  Briefcase: () => <div>Briefcase</div>,
  RefreshCw: () => <div>RefreshCw</div>,
  NotebookPen: () => <div>NotebookPen</div>,
  X: () => <div>X</div>,
  Save: () => <div>Save</div>,
  Sparkles: () => <div>Sparkles</div>,
  Loader2: () => <div>Loader2</div>,
  Bot: () => <div>Bot</div>,
  Download: () => <div>Download</div>,
}))

describe('Orders', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders orders title', async () => {
    render(<Orders />)
    await waitFor(() => {
      expect(screen.getByText('Orders')).toBeInTheDocument()
    })
  })

  it('renders order table columns', async () => {
    render(<Orders />)
    await waitFor(() => {
      expect(screen.getByText('Symbol')).toBeInTheDocument()
      expect(screen.getByText('Direction')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })
  })
})
