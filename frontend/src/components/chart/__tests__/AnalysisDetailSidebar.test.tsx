import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AnalysisDetailSidebar } from '../AnalysisDetailSidebar'

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: vi.fn(() => ({
    signals: [
      { value: 'Buy', label: 'Buy', tone: 'positive' },
      { value: 'Sell', label: 'Sell', tone: 'negative' },
      { value: 'Hold', label: 'Hold', tone: 'neutral' },
    ],
  })),
}))

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: vi.fn(() => ({
    signals: [
      { value: 'Buy', label: 'Buy', tone: 'positive' },
      { value: 'Sell', label: 'Sell', tone: 'negative' },
    ],
  }) as any),
}))

const t = (k: string) => {
  const map: Record<string, string> = {
    'chart.analysis_detail': 'Analysis Detail',
    'chart.trade_date': 'Trade Date',
    'chart.signal': 'Signal',
    'chart.executive_summary': 'Executive Summary',
    'chart.technical_levels': 'Technical Levels',
    'chart.target_price': 'Target Price',
    'chart.stop_loss': 'Stop Loss',
    'chart.recommended_leverage': 'Leverage',
    'chart.liquidation': 'Liquidation',
    'chart.support_label': 'Support',
    'chart.resistance_label': 'Resistance',
    'chart.view_full_report': 'View Full Report',
  }
  return map[k] || k
}

const baseSelected = {
  id: 1,
  trade_date: '2024-01-15',
  signal: 'Buy',
  final_decision: 'Strong buy based on momentum.',
}

describe('AnalysisDetailSidebar', () => {
  it('returns null when no analysis selected', () => {
    const { container } = render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={null} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders trade date and signal', () => {
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={baseSelected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('2024-01-15')).toBeInTheDocument()
    expect(screen.getByText('Buy')).toBeInTheDocument()
  })

  it('renders executive summary when present', () => {
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={baseSelected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('Strong buy based on momentum.')).toBeInTheDocument()
  })

  it('renders View Full Report button', () => {
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={baseSelected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('View Full Report')).toBeInTheDocument()
  })

  it('renders technical levels from annotations', () => {
    const selected = {
      ...baseSelected,
      chart_annotations: JSON.stringify({
        target_price: 200,
        stop_loss: 180,
        leverage: 3,
        liquidation_price: 150,
      }),
    }
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={selected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('$200.00')).toBeInTheDocument()
    expect(screen.getByText('$180.00')).toBeInTheDocument()
    expect(screen.getByText('3x')).toBeInTheDocument()
    expect(screen.getByText('$150.00')).toBeInTheDocument()
  })

  it('renders support and resistance levels', () => {
    const selected = {
      ...baseSelected,
      chart_annotations: JSON.stringify({
        support_levels: [175, 170],
        resistance_levels: [210, 220],
      }),
    }
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={selected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('$175.00, $170.00')).toBeInTheDocument()
    expect(screen.getByText('$210.00, $220.00')).toBeInTheDocument()
  })

  it('handles non-JSON annotations gracefully', () => {
    const selected = {
      ...baseSelected,
      chart_annotations: 'not-json-string',
    }
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={selected} setSelected={vi.fn()} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('View Full Report')).toBeInTheDocument()
  })

  it('calls setSelected(null) on close', () => {
    const setSelected = vi.fn()
    render(
      <MemoryRouter>
        <AnalysisDetailSidebar selected={baseSelected} setSelected={setSelected} t={t} />
      </MemoryRouter>
    )
    const closeBtn = screen.getByRole('button', { name: '' })
    fireEvent.click(closeBtn)
    expect(setSelected).toHaveBeenCalledWith(null)
  })
})
