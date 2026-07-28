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

  it('identifies the tool, analyst, cause, and safe fallback for a tool failure', async () => {
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockResolvedValueOnce({
      data: [{
        id: 42,
        level: 'WARNING',
        source: 'tradingagents.run',
        message: 'run_event {"event":"tool_error","tool":"get_fundamentals","analyst":"fundamentals","error_type":"timeout","action":"continue_without_tool","error":"Timed out after 60s"}',
        details: null,
        user_id: 1,
        created_at: '2026-07-28T08:28:31Z',
      }],
    })

    render(<Logs />)

    expect(await screen.findByText('Tool Failed')).toBeInTheDocument()
    expect(screen.getByText('get_fundamentals')).toBeInTheDocument()
    expect(screen.getByText('analyst: fundamentals')).toBeInTheDocument()
    expect(screen.getByText('timeout')).toBeInTheDocument()
    expect(screen.getByText('Timed out after 60s')).toBeInTheDocument()
    expect(screen.getByText(/Continuing with remaining tools and data/)).toBeInTheDocument()
  })

  it('shows every timed-out tool when an older Python-dict log needs fallback parsing', async () => {
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockResolvedValueOnce({
      data: [{
        id: 43,
        level: 'WARNING',
        source: 'tradingagents.run',
        // The apostrophe deliberately makes the old ``replace(/'/g)`` JSON
        // conversion invalid, exercising the compatibility parser instead.
        message: "run_event {'event': 'tool_timeout', 'tools': ['get_fundamentals', 'get_cashflow'], 'analyst': 'fundamentals', 'error_type': 'timeout', 'action': 'continue_without_tool', 'error': \"provider's request timed out\", 'timeout_seconds': 60}",
        details: null,
        user_id: 1,
        created_at: '2026-07-28T08:28:31Z',
      }],
    })

    render(<Logs />)

    expect(await screen.findByText('Tool Timed Out')).toBeInTheDocument()
    expect(screen.getByText('get_fundamentals, get_cashflow')).toBeInTheDocument()
    expect(screen.getByText("provider's request timed out")).toBeInTheDocument()
  })
})
