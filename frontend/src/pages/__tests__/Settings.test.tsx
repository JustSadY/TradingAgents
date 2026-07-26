import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import Settings from '../Settings'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
  put: vi.fn().mockResolvedValue({ data: {} }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'settings.loading': 'Loading settings...',
        'settings.save_error_default': 'Save failed',
        'settings.webhook_success': 'Webhook test successful',
        'settings.webhook_failed': 'Webhook test failed',
        'settings.general': 'General',
        'settings.llm': 'AI Configuration',
        'settings.risk': 'Risk & Safety',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../hooks/useMeta', () => ({
  useMeta: () => ({
    analysts: [],
    signals: [],
    tools: [],
    choices: [],
    agent_settings: [],
    tool_settings: [],
  }),
  triggerMetaRefetch: vi.fn(),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, role: 'user', isAdmin: false, isOwner: false, isAuthenticated: true, loading: false, login: vi.fn(), logout: vi.fn() }),
}))

vi.mock('lucide-react', () => ({
  Save: () => <div>Save</div>,
  BookmarkPlus: () => <div>BookmarkPlus</div>,
  Trash2: () => <div>Trash2</div>,
  Play: () => <div>Play</div>,
  Bell: () => <div>Bell</div>,
  Settings: () => <div>Settings</div>,
  Brain: () => <div>Brain</div>,
  ShieldAlert: () => <div>ShieldAlert</div>,
  Clock: () => <div>Clock</div>,
  Wrench: () => <div>Wrench</div>,
  Database: () => <div>Database</div>,
  CheckCircle2: () => <div>CheckCircle2</div>,
  XCircle: () => <div>XCircle</div>,
  RefreshCw: () => <div>RefreshCw</div>,
  UserCircle: () => <div>UserCircle</div>,
  Plus: () => <div>Plus</div>,
  Pencil: () => <div>Pencil</div>,
}))

describe('Settings', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders loading state initially', () => {
    render(<Settings />)
    expect(screen.getByText('Loading settings...')).toBeInTheDocument()
  })
})
