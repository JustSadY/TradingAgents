import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClientProvider } from '@tanstack/react-query'
import { appTheme } from '../../theme/appTheme'
import { createTestQueryClient } from '../../test/renderWithQuery'
import EarningsCalendar from '../EarningsCalendar'

const earningsRow = {
  ticker: 'AAPL',
  earnings_date: '2026-08-20',
  eps_estimate: 2.1,
  reported_eps: null,
  surprise_pct: null,
  days_until: 6,
  status: 'upcoming',
}

const mocks = vi.hoisted(() => ({
  earningsQuery: {
    data: { results: [] as unknown[] },
    isFetching: false,
    isSuccess: true,
    dataUpdatedAt: 1,
    error: null as unknown,
  },
  earningsHook: vi.fn(),
  analyse: vi.fn(),
  notify: vi.fn(),
}))

vi.mock('../../api/generated/earnings/earnings', () => ({
  useEarningsEarningsCalendar: (params: unknown) => {
    mocks.earningsHook(params)
    return mocks.earningsQuery
  },
}))

vi.mock('../../api/generated/analysis/analysis', () => ({
  useAnalysisRunAnalysis: () => ({ mutate: mocks.analyse }),
}))

vi.mock('../../api/useQueryErrorToast', () => ({ useQueryErrorToast: vi.fn() }))
vi.mock('../../utils/notify', () => ({ notify: (...args: unknown[]) => mocks.notify(...args) }))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'earnings.title': 'Earnings Calendar',
        'earnings.subtitle': 'Upcoming earnings',
        'earnings.ticker_label': 'Tickers',
        'earnings.ticker_placeholder': 'AAPL, MSFT',
        'earnings.loading': 'Loading',
        'earnings.search': 'Search',
        'earnings.no_data': 'No earnings data',
        'earnings.sorted_by_date': 'Sorted by date',
        'earnings.col_ticker': 'Ticker',
        'earnings.col_date': 'Date',
        'earnings.col_days_until': 'Days',
        'earnings.col_eps_estimate': 'Estimate',
        'earnings.col_reported_eps': 'Reported',
        'earnings.col_surprise': 'Surprise',
        'earnings.col_status': 'Status',
        'earnings.col_action': 'Action',
        'earnings.status_upcoming': 'Upcoming',
        'earnings.status_reported': 'Reported',
        'earnings.status_unknown': 'Unknown',
        'earnings.soon_badge': 'Soon',
        'earnings.analyse': 'Analyse',
        'earnings.run_analysis_title': 'Analyse {ticker}',
      }
      return map[key] || key
    },
  }),
}))

function renderPage() {
  const queryClient = createTestQueryClient()
  return render(
    <ThemeProvider theme={appTheme}>
      <QueryClientProvider client={queryClient}>
        <EarningsCalendar />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  mocks.earningsQuery.data = { results: [earningsRow] }
  mocks.earningsQuery.isFetching = false
  mocks.earningsQuery.isSuccess = true
  mocks.earningsQuery.dataUpdatedAt += 1
  mocks.earningsQuery.error = null
  mocks.earningsHook.mockReset()
  mocks.analyse.mockReset()
  mocks.notify.mockReset()
})

describe('EarningsCalendar', () => {
  it('renders earnings data through AppDataGrid', async () => {
    renderPage()
    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('Upcoming')).toBeInTheDocument()
    expect(screen.getByText('Estimate')).toBeInTheDocument()
  })

  it('renders the shared loading state', () => {
    mocks.earningsQuery.data = { results: [] }
    mocks.earningsQuery.isFetching = true
    mocks.earningsQuery.isSuccess = false
    renderPage()
    expect(screen.getByLabelText('Earnings Calendar loading')).toBeInTheDocument()
  })

  it('renders the shared error state', () => {
    mocks.earningsQuery.data = { results: [] }
    mocks.earningsQuery.isSuccess = false
    mocks.earningsQuery.error = new Error('earnings unavailable')
    renderPage()
    expect(screen.getByText('earnings unavailable')).toBeInTheDocument()
  })

  it('renders the shared empty state', () => {
    mocks.earningsQuery.data = { results: [] }
    renderPage()
    expect(screen.getByText('No earnings data')).toBeInTheDocument()
  })

  it('preserves ticker search and row analysis actions', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.clear(screen.getByRole('textbox', { name: 'Tickers' }))
    await user.type(screen.getByRole('textbox', { name: 'Tickers' }), 'msft')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(mocks.earningsHook).toHaveBeenLastCalledWith({ tickers: 'MSFT' })

    await user.click(screen.getByRole('button', { name: 'Analyse AAPL' }))
    expect(mocks.analyse).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ ticker: 'AAPL' }) }),
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function), onSettled: expect.any(Function) }),
    )
  })
})
