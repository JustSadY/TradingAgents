import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AnalysisControls } from '../AnalysisControls'

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: vi.fn(() => ({
    signals: [
      { value: 'Buy', label: 'Buy', tone: 'positive' },
      { value: 'Sell', label: 'Sell', tone: 'negative' },
      { value: 'Hold', label: 'Hold', tone: 'neutral' },
    ],
  })),
}))

const t = (k: string) => {
  const map: Record<string, string> = {
    'analysis.label.symbol': 'Symbol',
    'analysis.label.date': 'Date',
    'analysis.label.type': 'Type',
    'analysis.btn.start': 'Start',
    'analysis.btn.stop': 'Stop',
    'analysis.existing_analysis': 'Existing analysis found',
  }
  return map[k] || k
}

const assetTypes = [
  { value: 'stock', label: 'Stock' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'etf', label: 'ETF' },
]

describe('AnalysisControls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders ticker, date, type inputs and start button', () => {
    render(
      <AnalysisControls
        ticker=""
        setTicker={vi.fn()}
        date="2024-01-15"
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={false}
        runStatus="idle"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={null}
        existingId={null}
        t={t}
      />
    )
    expect(screen.getByPlaceholderText('AAPL')).toBeInTheDocument()
    expect(screen.getByDisplayValue('2024-01-15')).toBeInTheDocument()
    expect(screen.getByText('Start')).toBeInTheDocument()
  })

  it('calls setTicker on input change', () => {
    const setTicker = vi.fn()
    render(
      <AnalysisControls
        ticker=""
        setTicker={setTicker}
        date=""
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={false}
        runStatus="idle"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={null}
        existingId={null}
        t={t}
      />
    )
    fireEvent.change(screen.getByPlaceholderText('AAPL'), { target: { value: 'aapl' } })
    expect(setTicker).toHaveBeenCalledWith('AAPL')
  })

  it('shows stop button when running', () => {
    render(
      <AnalysisControls
        ticker="AAPL"
        setTicker={vi.fn()}
        date=""
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={true}
        runStatus="running"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={null}
        existingId={null}
        t={t}
      />
    )
    expect(screen.getByText('Stop')).toBeInTheDocument()
  })

  it('disables start when ticker is empty', () => {
    render(
      <AnalysisControls
        ticker=""
        setTicker={vi.fn()}
        date=""
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={false}
        runStatus="idle"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={null}
        existingId={null}
        t={t}
      />
    )
    expect(screen.getByText('Start')).toBeDisabled()
  })

  it('shows cost estimate when provided', () => {
    const costEstimate = {
      estimated_cost_usd: 0.042,
      estimated_tokens: 15000,
      estimated_duration_min: 2.5,
      analyst_count: 12,
    }
    render(
      <AnalysisControls
        ticker="AAPL"
        setTicker={vi.fn()}
        date=""
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={false}
        runStatus="idle"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={costEstimate}
        existingId={null}
        t={t}
      />
    )
    expect(screen.getByText(/0.042/)).toBeInTheDocument()
    expect(screen.getByText(/15,000/)).toBeInTheDocument()
  })

  it('shows existing analysis badge', () => {
    render(
      <AnalysisControls
        ticker="AAPL"
        setTicker={vi.fn()}
        date=""
        setDate={vi.fn()}
        assetType="stock"
        setAssetType={vi.fn()}
        assetTypes={assetTypes}
        running={false}
        runStatus="idle"
        handleRun={vi.fn()}
        handleStop={vi.fn()}
        handleClear={vi.fn()}
        signal={null}
        costEstimate={null}
        existingId={42}
        t={t}
      />
    )
    expect(screen.getByText('Existing analysis found')).toBeInTheDocument()
  })
})
