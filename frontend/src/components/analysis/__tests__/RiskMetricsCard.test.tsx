import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RiskMetricsCard } from '../RiskMetricsCard'

describe('RiskMetricsCard', () => {
  it('returns null when metrics is null', () => {
    const { container } = render(<RiskMetricsCard metrics={null as any} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders all risk metrics', () => {
    const metrics = {
      sharpe_ratio: 1.5,
      max_drawdown: -0.15,
      annualized_volatility: 0.25,
      beta: 1.2,
      market_correlation: 0.75,
    }
    render(<RiskMetricsCard metrics={metrics} />)
    expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
    expect(screen.getByText('Max Drawdown')).toBeInTheDocument()
    expect(screen.getByText('Volatility')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
    expect(screen.getByText('Market Corr.')).toBeInTheDocument()
  })

  it('formats percentage values correctly', () => {
    const metrics = {
      sharpe_ratio: 1.5,
      max_drawdown: -0.1523,
      annualized_volatility: 0.2534,
      beta: 1.2,
      market_correlation: 0.75,
    }
    render(<RiskMetricsCard metrics={metrics} />)
    expect(screen.getByText('-15.23%')).toBeInTheDocument()
    expect(screen.getByText('25.34%')).toBeInTheDocument()
  })

  it('shows N/A for missing beta and correlation', () => {
    const metrics = {
      sharpe_ratio: 1.0,
      max_drawdown: -0.1,
      annualized_volatility: 0.2,
    }
    render(<RiskMetricsCard metrics={metrics} />)
    const naElements = screen.getAllByText('N/A')
    expect(naElements.length).toBe(2)
  })
})
