import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChartSearch } from '../ChartSearch'

const defaultProps = {
  tickerInput: '',
  setTickerInput: vi.fn(),
  period: '1y',
  handlePeriod: vi.fn(),
  periods: [
    { label: '1M', value: '1mo' },
    { label: '6M', value: '6mo' },
    { label: '1Y', value: '1y' },
    { label: '5Y', value: '5y' },
  ],
  loading: false,
  handleSearch: vi.fn(),
  t: (k: string) => k,
}

describe('ChartSearch', () => {
  it('renders search input and period buttons', () => {
    render(<ChartSearch {...defaultProps} />)
    expect(screen.getByPlaceholderText('Symbol (AAPL)')).toBeInTheDocument()
    expect(screen.getByText('1M')).toBeInTheDocument()
    expect(screen.getByText('6M')).toBeInTheDocument()
    expect(screen.getByText('1Y')).toBeInTheDocument()
    expect(screen.getByText('5Y')).toBeInTheDocument()
  })

  it('calls setTickerInput on input change', () => {
    const setTickerInput = vi.fn()
    render(<ChartSearch {...defaultProps} setTickerInput={setTickerInput} />)
    fireEvent.change(screen.getByPlaceholderText('Symbol (AAPL)'), { target: { value: 'aapl' } })
    expect(setTickerInput).toHaveBeenCalledWith('AAPL')
  })

  it('calls handleSearch on enter key', () => {
    const handleSearch = vi.fn()
    render(<ChartSearch {...defaultProps} handleSearch={handleSearch} />)
    fireEvent.keyDown(screen.getByPlaceholderText('Symbol (AAPL)'), { key: 'Enter' })
    expect(handleSearch).toHaveBeenCalled()
  })

  it('calls handlePeriod on period button click', () => {
    const handlePeriod = vi.fn()
    render(<ChartSearch {...defaultProps} handlePeriod={handlePeriod} />)
    fireEvent.click(screen.getByText('6M'))
    expect(handlePeriod).toHaveBeenCalledWith('6mo')
  })

  it('shows loading spinner when loading', () => {
    render(<ChartSearch {...defaultProps} loading={true} />)
    expect(screen.getAllByRole('button')[0].querySelector('.animate-spin')).toBeTruthy()
  })

  it('disables search button when loading', () => {
    render(<ChartSearch {...defaultProps} loading={true} />)
    expect(screen.getAllByRole('button')[0]).toBeDisabled()
  })

  it('highlights active period', () => {
    render(<ChartSearch {...defaultProps} period='1mo' />)
    const activeBtn = screen.getByText('1M')
    expect(activeBtn.className).toContain('bg-white/10')
  })
})
