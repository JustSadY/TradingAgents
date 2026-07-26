import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Logs from '../Logs'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: vi.fn().mockResolvedValue({ data: [] }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'logs.title': 'System Logs',
        'logs.all_sources': 'All Sources',
        'logs.all_levels': 'All Levels',
        'logs.no_logs': 'No logs found',
        'common.loading': 'Loading Logs...',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'admin' }, role: 'admin', isAdmin: true, isOwner: false, isAuthenticated: true, loading: false, login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('lucide-react', () => ({
  RefreshCw: () => <div>RefreshCw</div>,
  Terminal: () => <div>Terminal</div>,
  Clock: () => <div>Clock</div>,
  ChevronDown: () => <div>ChevronDown</div>,
  ChevronRight: () => <div>ChevronRight</div>,
}))

describe('Logs', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders system logs title', async () => {
    render(<Logs />)
    await waitFor(() => {
      expect(screen.getByText('System Logs')).toBeInTheDocument()
    })
  })

  it('renders level filter', async () => {
    render(<Logs />)
    await waitFor(() => {
      expect(screen.getByText('All Levels')).toBeInTheDocument()
    })
  })
})
