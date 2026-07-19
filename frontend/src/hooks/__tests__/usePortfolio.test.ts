import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { usePortfolio } from '../usePortfolio'

const mockGet = vi.fn()

vi.mock('../../utils/api', () => ({
  default: {
    get: mockGet,
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
}))

const makePortfolios = () => [
  {
    id: 1,
    mode: 'simulation',
    broker: 'paper',
    initial_capital: 100000,
    current_balance: 105000,
    cash_available: 50000,
    status: 'active',
    holdings: [
      { ticker: 'AAPL', quantity: 10, current_price: 150, unrealized_pnl: 200, avg_buy_price: 148 },
      { ticker: 'GOOGL', quantity: 5, current_price: 180, unrealized_pnl: -50, avg_buy_price: 190 },
    ],
  },
]

describe('usePortfolio', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ data: makePortfolios() })
  })

  it('fetches portfolios on mount', async () => {
    const { result } = renderHook(() => usePortfolio())
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.portfolios).toHaveLength(1)
  })

  it('returns simulation portfolio as sim', async () => {
    const { result } = renderHook(() => usePortfolio())
    await waitFor(() => {
      expect(result.current.sim).toBeDefined()
    })
    expect(result.current.sim!.mode).toBe('simulation')
  })

  it('calculates P&L stats correctly', async () => {
    const { result } = renderHook(() => usePortfolio())
    await waitFor(() => {
      expect(result.current.stats.pnl).toBe(5000)
    })
    expect(result.current.stats.pnlPct).toBe(5)
    expect(result.current.stats.totalUnrealized).toBe(150)
  })

  it('builds allocation data with Cash', async () => {
    const { result } = renderHook(() => usePortfolio())
    await waitFor(() => {
      expect(result.current.allocationData.length).toBeGreaterThan(0)
    })
    const names = result.current.allocationData.map(d => d.name)
    expect(names).toContain('Cash')
  })

  it('handles empty portfolios gracefully', async () => {
    mockGet.mockResolvedValue({ data: null })
    const { result } = renderHook(() => usePortfolio())
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.sim).toBeUndefined()
    expect(result.current.stats.pnl).toBe(0)
  })
})
