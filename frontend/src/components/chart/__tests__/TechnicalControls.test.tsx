import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TechnicalControls } from '../TechnicalControls'

const defaultProps = {
  showSMA: false, setShowSMA: vi.fn(),
  showEMA: false, setShowEMA: vi.fn(),
  showRSI: false, setShowRSI: vi.fn(),
  showMACD: false, setShowMACD: vi.fn(),
  showSentiment: false, setShowSentiment: vi.fn(),
  t: (k: string) => k,
}

describe('TechnicalControls', () => {
  it('renders all indicator buttons', () => {
    render(<TechnicalControls {...defaultProps} />)
    expect(screen.getByText('SMA (20)')).toBeInTheDocument()
    expect(screen.getByText('EMA (20)')).toBeInTheDocument()
    expect(screen.getByText('RSI (14)')).toBeInTheDocument()
    expect(screen.getByText('MACD')).toBeInTheDocument()
    expect(screen.getByText('Sentiment')).toBeInTheDocument()
  })

  it('toggles SMA on click', () => {
    const setShowSMA = vi.fn()
    render(<TechnicalControls {...defaultProps} setShowSMA={setShowSMA} />)
    fireEvent.click(screen.getByText('SMA (20)'))
    expect(setShowSMA).toHaveBeenCalledWith(true)
  })

  it('shows active state for enabled indicators', () => {
    render(<TechnicalControls {...defaultProps} showSMA={true} showRSI={true} />)
    const smaBtn = screen.getByText('SMA (20)')
    const rsiBtn = screen.getByText('RSI (14)')
    expect(smaBtn.className).toContain('bg-amber-500/20')
    expect(rsiBtn.className).toContain('bg-blue-500/20')
  })

  it('shows inactive state for disabled indicators', () => {
    render(<TechnicalControls {...defaultProps} />)
    const smaBtn = screen.getByText('SMA (20)')
    expect(smaBtn.className).toContain('bg-white/5')
  })

  it('calls correct setter for each indicator', () => {
    const setters = {
      setShowSMA: vi.fn(),
      setShowEMA: vi.fn(),
      setShowRSI: vi.fn(),
      setShowMACD: vi.fn(),
      setShowSentiment: vi.fn(),
    }
    render(<TechnicalControls {...defaultProps} {...setters} />)

    fireEvent.click(screen.getByText('SMA (20)'))
    expect(setters.setShowSMA).toHaveBeenCalledWith(true)

    fireEvent.click(screen.getByText('EMA (20)'))
    expect(setters.setShowEMA).toHaveBeenCalledWith(true)

    fireEvent.click(screen.getByText('RSI (14)'))
    expect(setters.setShowRSI).toHaveBeenCalledWith(true)

    fireEvent.click(screen.getByText('MACD'))
    expect(setters.setShowMACD).toHaveBeenCalledWith(true)

    fireEvent.click(screen.getByText('Sentiment'))
    expect(setters.setShowSentiment).toHaveBeenCalledWith(true)
  })
})
