import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecentAnalysisTable } from '../RecentAnalysisTable'

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
    'dashboard.recent_analysis': 'Recent Analysis',
    'dashboard.view_all': 'View All',
  }
  return map[k] || k
}

const recentAnalysis = [
  { id: 1, ticker: 'AAPL', trade_date: '2024-01-15', signal: 'Buy', duration_seconds: 42.5 },
  { id: 2, ticker: 'TSLA', trade_date: '2024-01-14', signal: 'Sell', duration_seconds: 38.1 },
  { id: 3, ticker: 'GOOGL', trade_date: '2024-01-13', signal: 'Hold', duration_seconds: 0 },
]

describe('RecentAnalysisTable', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders table with analysis rows', () => {
    render(
      <MemoryRouter>
        <RecentAnalysisTable recentAnalysis={recentAnalysis} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('TSLA')).toBeInTheDocument()
    expect(screen.getByText('GOOGL')).toBeInTheDocument()
    expect(screen.getByText('Buy')).toBeInTheDocument()
    expect(screen.getByText('Sell')).toBeInTheDocument()
  })

  it('shows empty state when no analysis', () => {
    render(
      <MemoryRouter>
        <RecentAnalysisTable recentAnalysis={[]} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText(/No recent analysis found/i)).toBeInTheDocument()
  })

  it('shows duration in seconds', () => {
    render(
      <MemoryRouter>
        <RecentAnalysisTable recentAnalysis={recentAnalysis} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('42.5s')).toBeInTheDocument()
    expect(screen.getByText('38.1s')).toBeInTheDocument()
  })

  it('shows View All button linking to /analysis', () => {
    render(
      <MemoryRouter>
        <RecentAnalysisTable recentAnalysis={recentAnalysis} t={t} />
      </MemoryRouter>
    )
    expect(screen.getByText('View All')).toBeInTheDocument()
  })
})
