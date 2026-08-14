import { useCallback, useMemo } from 'react'
import { usePortfolioListPortfolios } from '../api/generated/portfolio/portfolio'

interface Portfolio {
  id: number
  mode: string
  broker: string
  initial_capital: number
  current_balance: number
  cash_available: number
  status: string
  holdings: { ticker: string; quantity: number; current_price: number; unrealized_pnl: number; avg_buy_price?: number }[]
}

export function usePortfolio() {
  const query = usePortfolioListPortfolios({ query: { refetchInterval: 15_000 } })
  const portfolios = (Array.isArray(query.data) ? query.data : []) as Portfolio[]
  const loading = query.isPending
  const fetchPortfolios = useCallback(() => query.refetch(), [query])

  const sim = useMemo(() => portfolios.find(p => p.mode === 'simulation') || portfolios[0], [portfolios])
  
  const stats = useMemo(() => {
    if (!sim) return { pnl: 0, pnlPct: 0, totalUnrealized: 0 }
    const pnl = sim.current_balance - sim.initial_capital
    const pnlPct = sim.initial_capital ? (pnl / sim.initial_capital * 100) : 0
    const totalUnrealized = (sim.holdings || []).reduce((s, h) => s + (h.unrealized_pnl || 0), 0)
    return { pnl, pnlPct, totalUnrealized }
  }, [sim])

  const allocationData = useMemo(() => {
    if (!sim || !sim.holdings) return []
    const data = sim.holdings.map(h => ({ name: h.ticker, value: h.quantity * h.current_price }))
    if (sim.cash_available > 0) data.push({ name: 'Cash', value: sim.cash_available })
    return data.sort((a, b) => b.value - a.value)
  }, [sim])

  return { portfolios, sim, stats, allocationData, loading, refreshPortfolios: fetchPortfolios }
}
