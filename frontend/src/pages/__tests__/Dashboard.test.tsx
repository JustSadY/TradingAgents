import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../Dashboard'

const mockPortfolioData = {
  portfolios: [],
  sim: undefined,
  stats: { pnl: 0, pnlPct: 0, totalUnrealized: 0 },
  allocationData: [],
  loading: false,
  refreshPortfolios: vi.fn(),
}

const mockNewsData = {
  news: [],
  loading: false,
  refreshNews: vi.fn(),
}

vi.mock('../../hooks/usePortfolio', () => ({
  usePortfolio: () => mockPortfolioData,
}))

vi.mock('../../hooks/useNewsFeed', () => ({
  useNewsFeed: () => mockNewsData,
}))

vi.mock('../../utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'dashboard.title': 'Dashboard',
        'dashboard.asset_allocation': 'Asset Allocation',
        'dashboard.scorecard_title': 'Performance Scorecard',
        'dashboard.scorecard_predictions': 'predictions',
        'dashboard.scorecard_accuracy': 'Accuracy',
        'dashboard.scorecard_empty': 'No Data Yet',
        'dashboard.scorecard_empty_sub': 'Run analyses to see accuracy breakdown',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  PieChart: ({ children }: any) => <div>{children}</div>,
  Pie: ({ children }: any) => <div>{children}</div>,
  Cell: () => <div>Cell</div>,
  Legend: () => <div>Legend</div>,
  Tooltip: () => <div>Tooltip</div>,
}))

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPortfolioData.portfolios = []
    mockPortfolioData.sim = undefined
    mockPortfolioData.stats = { pnl: 0, pnlPct: 0, totalUnrealized: 0 }
    mockPortfolioData.loading = false
    mockNewsData.news = []
  })

  it('renders dashboard title', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })
  })

  it('renders AI Morning Brief section', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('AI Morning Brief')).toBeInTheDocument()
    })
  })

  it('renders Asset Allocation section', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Asset Allocation')).toBeInTheDocument()
    })
  })

  it('shows loading state initially', () => {
    mockPortfolioData.loading = true
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    expect(screen.getByText('Synchronizing Engine...')).toBeInTheDocument()
  })
})
