import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PortfolioOverview } from '../PortfolioOverview'

const t = (k: string) => {
  const map: Record<string, string> = {
    'dashboard.balance': 'Balance',
    'dashboard.pnl': 'P&L',
    'dashboard.unrealized': 'Unrealized',
    'dashboard.holdings': 'Holdings',
    'dashboard.assets': 'Assets',
  }
  return map[k] || k
}

const mockSim = {
  id: 1,
  mode: 'paper',
  broker: 'demo',
  initial_capital: 100000,
  current_balance: 105000,
  cash_available: 30000,
  status: 'active',
  holdings: [
    { ticker: 'AAPL', quantity: 100, current_price: 200, unrealized_pnl: 1000, avg_buy_price: 190 },
    { ticker: 'TSLA', quantity: 50, current_price: 700, unrealized_pnl: 2500, avg_buy_price: 650 },
  ],
}

describe('PortfolioOverview', () => {
  it('renders balance, P&L, unrealized, and holdings', () => {
    render(<PortfolioOverview sim={mockSim} pnl={5000} pnlPct={5.25} totalUnrealized={3500} t={t} />)
    expect(screen.getByText('Balance')).toBeInTheDocument()
    expect(screen.getByText('P&L')).toBeInTheDocument()
    expect(screen.getByText('Unrealized')).toBeInTheDocument()
    expect(screen.getByText('Holdings')).toBeInTheDocument()
  })

  it('formats balance with locale string', () => {
    render(<PortfolioOverview sim={mockSim} pnl={5000} pnlPct={5.25} totalUnrealized={3500} t={t} />)
    expect(screen.getByText((content) => content.includes('105,000'))).toBeInTheDocument()
  })

  it('shows positive P&L percentage with + prefix', () => {
    render(<PortfolioOverview sim={mockSim} pnl={5000} pnlPct={5.25} totalUnrealized={3500} t={t} />)
    expect(screen.getByText('+5.25%')).toBeInTheDocument()
  })

  it('shows negative P&L without + prefix', () => {
    render(<PortfolioOverview sim={mockSim} pnl={-2000} pnlPct={-2.0} totalUnrealized={-500} t={t} />)
    expect(screen.getByText('-2.00%')).toBeInTheDocument()
  })

  it('shows zero values when sim is undefined', () => {
    render(<PortfolioOverview sim={undefined} pnl={0} pnlPct={0} totalUnrealized={0} t={t} />)
    expect(screen.getByText('$0')).toBeInTheDocument()
  })

  it('shows holding count', () => {
    render(<PortfolioOverview sim={mockSim} pnl={5000} pnlPct={5.25} totalUnrealized={3500} t={t} />)
    expect(screen.getByText('2 Assets')).toBeInTheDocument()
  })
})
