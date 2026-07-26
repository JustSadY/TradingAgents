import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { NewsFeed } from '../NewsFeed'

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const news = [
  { title: 'AAPL hits all-time high', url: 'https://example.com/aapl', source: 'Yahoo Finance', published_at: '2024-01-15T14:30:00Z', ticker: 'AAPL' },
  { title: 'TSLA earnings beat estimates', url: 'https://example.com/tsla', source: 'Reuters', published_at: '2024-01-15T15:00:00Z', ticker: 'TSLA' },
]

describe('NewsFeed', () => {
  it('renders news items with ticker, title, source', () => {
    render(<NewsFeed news={news} t={(k: string) => k} />)
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('TSLA')).toBeInTheDocument()
    expect(screen.getByText('AAPL hits all-time high')).toBeInTheDocument()
    expect(screen.getByText('TSLA earnings beat estimates')).toBeInTheDocument()
    expect(screen.getByText('Yahoo Finance')).toBeInTheDocument()
  })

  it('shows empty state when no news', () => {
    render(<NewsFeed news={[]} t={(k: string) => k} />)
    expect(screen.getByText(/No news for your watchlist tickers/i)).toBeInTheDocument()
  })

  it('renders external links with target=_blank', () => {
    render(<NewsFeed news={news} t={(k: string) => k} />)
    const links = screen.getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', 'https://example.com/aapl')
    expect(links[0]).toHaveAttribute('target', '_blank')
  })
})
