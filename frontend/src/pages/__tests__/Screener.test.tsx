import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axios from 'axios'
import Screener from '../Screener'

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'screener.title': 'Stock Screener',
      'screener.subtitle': 'Find candidates',
      'screener.mode_default': 'Default Universe',
      'screener.mode_custom': 'Custom Tickers',
      'screener.mode_watchlist': 'My Watchlist',
      'screener.top_n': 'Top N',
      'screener.run': 'Run Screen',
      'screener.scanning': 'Scanning',
      'screener.results': 'Results',
      'screener.sorted_by_score': 'Sorted by score',
      'screener.trend_above_sma50': 'Above SMA 50',
      'screener.trend_below_sma50': 'Below SMA 50',
      'screener.verdict_strong': 'Strong',
      'screener.verdict_weak': 'Weak',
      'screener.verdict_neutral': 'Neutral',
      'screener.analyse': 'Analyse',
    }[key] ?? key),
  }),
}))

vi.mock('../../utils/notify', () => ({ notify: vi.fn() }))

describe('Screener', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the backend screener contract without rescaling its 0–90 score', async () => {
    vi.mocked(axios.post).mockResolvedValueOnce({
      data: {
        results: [{
          ticker: 'AAPL',
          score: 35,
          momentum_1m_pct: 12.4,
          trend: 'above_sma50',
          volume_surge: 1.8,
          rsi_14: 58.2,
          signals: ['strong_momentum', 'uptrend'],
        }],
      },
    })

    const user = userEvent.setup()
    render(<Screener />)
    await user.click(screen.getByRole('button', { name: 'Run Screen' }))

    await waitFor(() => {
      expect(axios.post).toHaveBeenCalledWith('/api/screener/scan', { tickers: undefined, top_n: 10 })
    })
    expect(screen.getByText('35')).toBeInTheDocument()
    expect(screen.queryByText('3500')).not.toBeInTheDocument()
    expect(screen.getByText('+12.4%')).toBeInTheDocument()
    expect(screen.getByText('Above SMA 50')).toBeInTheDocument()
    expect(screen.getByText('1.80×')).toBeInTheDocument()
    expect(screen.getByText('58')).toBeInTheDocument()
  })
})
