import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClientProvider } from '@tanstack/react-query'
import { appTheme } from '../../theme/appTheme'
import { createTestQueryClient } from '../../test/renderWithQuery'
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
  external_order_id: null,
  analysis_id: null,
  ai_signal: 'Buy',
  created_at: '2024-01-01T00:00:00Z',
  executed_at: '2024-01-01T00:00:00Z',
}

const mocks = vi.hoisted(() => ({
  ordersQuery: {
    data: [] as unknown[],
    isPending: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
  saveNote: vi.fn(),
  debrief: vi.fn(),
}))

vi.mock('../../api/generated/portfolio/portfolio', () => ({
  usePortfolioListOrders: () => mocks.ordersQuery,
}))

vi.mock('../../api/generated/trading/trading', () => ({
  getTradingGetTradeNoteQueryKey: (orderId: number) => ['/api/trading/note', orderId],
  useTradingGetTradeNote: () => ({ data: null, isPending: false }),
  useTradingSaveTradeNote: () => ({ mutate: mocks.saveNote, isPending: false }),
  useTradingGenerateTradeDebrief: () => ({ mutate: mocks.debrief, isPending: false }),
}))

vi.mock('../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../test/i18nMock')).useTranslationMock,
}))

vi.mock('../../utils/notify', () => ({ notify: vi.fn() }))
vi.mock('../../utils/csvExport', () => ({ exportOrdersCSV: vi.fn() }))
vi.mock('../../components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: { children: React.ReactNode }) => children }))

function renderPage() {
  const queryClient = createTestQueryClient()
  return render(
    <ThemeProvider theme={appTheme}>
      <QueryClientProvider client={queryClient}>
        <Orders />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  mocks.ordersQuery.data = [mockOrder]
  mocks.ordersQuery.isPending = false
  mocks.ordersQuery.error = null
  mocks.ordersQuery.refetch.mockReset()
  mocks.saveNote.mockReset()
  mocks.debrief.mockReset()
})

describe('Orders', () => {
  it('renders generated order data through AppDataGrid', async () => {
    renderPage()
    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('Symbol')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
  })

  it('surfaces reconciliation state and broker order id', async () => {
    mocks.ordersQuery.data = [{
      ...mockOrder,
      broker: 'alpaca',
      status: 'RECONCILIATION_REQUIRED',
      quantity_filled: 0,
      price_per_share: null,
      total_value: null,
      external_order_id: 'alpaca-reconcile-123',
    }]

    renderPage()

    expect(await screen.findByText('RECONCILIATION_REQUIRED')).toBeInTheDocument()
    expect(screen.getByText('alpaca-reconcile-123')).toBeInTheDocument()
    expect(screen.getByText('Broker Order ID')).toBeInTheDocument()
  })

  it('does not hide a partial fill behind a terminal cancellation', async () => {
    mocks.ordersQuery.data = [{
      ...mockOrder,
      broker: 'alpaca',
      status: 'CANCELED',
      quantity_requested: 10,
      quantity_filled: 2,
      price_per_share: 150,
      total_value: 300,
      external_order_id: 'alpaca-partial-123',
    }]

    renderPage()

    expect(await screen.findByText('CANCELED · Partial fill')).toBeInTheDocument()
    expect(screen.getByText('alpaca-partial-123')).toBeInTheDocument()
  })

  it('renders the shared loading state', () => {
    mocks.ordersQuery.data = []
    mocks.ordersQuery.isPending = true
    renderPage()
    expect(screen.getByLabelText('Orders loading')).toBeInTheDocument()
  })

  it('renders the shared error state', () => {
    mocks.ordersQuery.data = []
    mocks.ordersQuery.error = new Error('orders unavailable')
    renderPage()
    expect(screen.getByText('orders unavailable')).toBeInTheDocument()
  })

  it('renders the shared empty state', () => {
    mocks.ordersQuery.data = []
    renderPage()
    expect(screen.getByText('No orders yet.')).toBeInTheDocument()
  })

  it('opens the trade journal from a row action', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'Open AAPL trade journal' }))
    expect(screen.getByText('Trade Journal')).toBeInTheDocument()
    expect(screen.getByText('#1 · AAPL')).toBeInTheDocument()
  })
})
