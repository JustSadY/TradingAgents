import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CustomIndicatorPane } from '../CustomIndicatorPane'

const baseCandles = [
  { time: '2024-01-01', rsi: 55, macd_line: 0.5, macd_signal: 0.3, macd_hist: 0.2 },
  { time: '2024-01-02', rsi: 60, macd_line: 0.6, macd_signal: 0.4, macd_hist: 0.2 },
]

const sentimentData = [
  { time: '2024-01-01', value: 0.5 },
  { time: '2024-01-02', value: 0.3 },
]

const defaultProps = {
  showRSI: false,
  showMACD: false,
  showSentiment: false,
  candles: baseCandles,
  sentimentChartData: sentimentData,
  customIndicators: [],
  userIndicatorData: [],
  userIndicatorLabel: '',
}

describe('CustomIndicatorPane', () => {
  it('returns null when nothing is shown', () => {
    const { container } = render(<CustomIndicatorPane {...defaultProps} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders RSI panel when showRSI is true', () => {
    render(<CustomIndicatorPane {...defaultProps} showRSI={true} />)
    expect(screen.getByText('Relative Strength Index (14)')).toBeInTheDocument()
  })

  it('renders MACD panel when showMACD is true', () => {
    render(<CustomIndicatorPane {...defaultProps} showMACD={true} />)
    expect(screen.getByText('MACD (12, 26, 9)')).toBeInTheDocument()
  })

  it('renders Sentiment panel when showSentiment is true', () => {
    render(<CustomIndicatorPane {...defaultProps} showSentiment={true} />)
    expect(screen.getByText('AI Consensus Sentiment History')).toBeInTheDocument()
  })

  it('renders custom indicators', () => {
    const customIndicators = [
      { label: 'Custom SMA', formula: 'SMA(20)', data: [{ time: '2024-01-01', value: 150 }] },
    ]
    render(<CustomIndicatorPane {...defaultProps} customIndicators={customIndicators} />)
    expect(screen.getByText('Custom SMA')).toBeInTheDocument()
    expect(screen.getByText('SMA(20)')).toBeInTheDocument()
  })

  it('renders user indicator data', () => {
    const userData = [{ time: '2024-01-01', value: 1.5 }]
    render(<CustomIndicatorPane {...defaultProps} userIndicatorData={userData} userIndicatorLabel='Z-Score' />)
    expect(screen.getByText('Dynamic Indicator')).toBeInTheDocument()
    expect(screen.getByText('Z-Score')).toBeInTheDocument()
  })

  it('renders all panels simultaneously', () => {
    render(
      <CustomIndicatorPane
        {...defaultProps}
        showRSI={true}
        showMACD={true}
        showSentiment={true}
      />
    )
    expect(screen.getByText('Relative Strength Index (14)')).toBeInTheDocument()
    expect(screen.getByText('MACD (12, 26, 9)')).toBeInTheDocument()
    expect(screen.getByText('AI Consensus Sentiment History')).toBeInTheDocument()
  })
})
