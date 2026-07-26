import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Watchlist from '../Watchlist'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: vi.fn().mockResolvedValue({ data: [] }),
  post: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'watchlist.title': 'Watchlist',
        'watchlist.add': 'Add',
        'watchlist.add_title': 'Add New Asset',
        'watchlist.loading': 'Loading...',
        'watchlist.empty': 'No assets tracked yet',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('lucide-react', () => ({
  Plus: () => <div>Plus</div>,
  Trash2: () => <div>Trash2</div>,
  RefreshCw: () => <div>RefreshCw</div>,
  Star: () => <div>Star</div>,
  TrendingUp: () => <div>TrendingUp</div>,
}))

describe('Watchlist', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders watchlist title', async () => {
    render(<Watchlist />)
    await waitFor(() => {
      expect(screen.getByText('Watchlist')).toBeInTheDocument()
    })
  })

  it('renders add new asset section', async () => {
    render(<Watchlist />)
    await waitFor(() => {
      expect(screen.getByText('Add New Asset')).toBeInTheDocument()
    })
  })
})
