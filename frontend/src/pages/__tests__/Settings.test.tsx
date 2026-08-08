import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import axios from 'axios'
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
        'settings.section_strategy_continuity': 'Strategy Continuity & Decision Stability',
        'settings.row_decision_stability_mode': 'Decision Stability Mode',
        'settings.decision_stability_off': 'Off',
        'settings.decision_stability_shadow': 'Shadow — record only',
        'settings.decision_stability_enforce': 'Enforce',
        'settings.row_stability_min_quality': 'Min. Change Quality',
        'settings.row_stability_min_confidence': 'Min. Calibrated Confidence',
        'settings.row_stability_min_evidence_groups': 'Min. Independent Evidence Groups',
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

  it('uses the provider model catalog while retaining a custom-model escape hatch', async () => {
    vi.mocked(axios.get).mockImplementation((url: string) => {
      if (url === '/api/settings') {
        return Promise.resolve({ data: {
          output_language: 'English', investor_persona: 'conservative', benchmark_ticker: null,
          news_article_limit: 20, global_news_article_limit: 10, global_news_lookback_days: 7,
          llm_provider: 'openai', llm_model: 'gpt-4o-mini',
          fallback_llm_chain: [],
          openai_reasoning_effort: null, anthropic_effort: null, google_thinking_level: null,
          max_recur_limit: 1000,
        } })
      }
      if (url === '/api/presets') return Promise.resolve({ data: [] })
      if (url === '/api/users/me/setting-permissions') return Promise.resolve({ data: { allowed_settings: ['general', 'llm'] } })
      if (url === '/api/cron/status') return Promise.resolve({ data: null })
      if (url === '/api/settings/llm-catalog') {
        return Promise.resolve({ data: { openai: { label: 'OpenAI', models: [{ value: 'gpt-4o-mini', label: 'GPT-4o mini' }] } } })
      }
      return Promise.resolve({ data: {} })
    })

    render(<Settings />)

    expect(await screen.findByRole('option', { name: 'GPT-4o mini' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'settings.custom_model_option' })).toBeInTheDocument()
  })

  it('exposes alert guardrails with explicit zero-value semantics', async () => {
    vi.mocked(axios.get).mockImplementation((url: string) => {
      if (url === '/api/settings') {
        return Promise.resolve({ data: {
          max_active_alerts: 30,
          max_ai_alerts_per_run: 3,
          ai_alert_cooldown_hours: 24,
          fallback_llm_chain: [],
          webhook_events: [],
        } })
      }
      if (url === '/api/presets') return Promise.resolve({ data: [] })
      if (url === '/api/users/me/setting-permissions') return Promise.resolve({ data: { allowed_settings: ['alerts'] } })
      if (url === '/api/cron/status') return Promise.resolve({ data: null })
      if (url === '/api/settings/llm-catalog') return Promise.resolve({ data: {} })
      return Promise.resolve({ data: {} })
    })

    render(<Settings />)

    expect(await screen.findByDisplayValue('30')).toBeInTheDocument()
    expect(screen.getByDisplayValue('3')).toBeInTheDocument()
    expect(screen.getByDisplayValue('24')).toBeInTheDocument()
    expect(screen.getByText('settings.alert_ai_limit_hint')).toBeInTheDocument()
    expect(screen.getByText('settings.alert_cooldown_hint')).toBeInTheDocument()
  })

  it('renders and saves strategy continuity controls from the risk settings permission', async () => {
    vi.mocked(axios.get).mockImplementation((url: string) => {
      if (url === '/api/settings') {
        return Promise.resolve({ data: {
          strategy_learning_enabled: true,
          decision_stability_mode: 'shadow',
          decision_stability_min_quality: 70,
          decision_stability_min_confidence: 0.65,
          decision_stability_min_evidence_groups: 2,
          reversal_verifier_enabled: true,
          confidence_calibration_enabled: false,
          regime_aware_weighting_enabled: false,
          fallback_llm_chain: [],
          webhook_events: [],
        } })
      }
      if (url === '/api/presets') return Promise.resolve({ data: [] })
      if (url === '/api/users/me/setting-permissions') return Promise.resolve({ data: { allowed_settings: ['risk'] } })
      if (url === '/api/cron/status') return Promise.resolve({ data: null })
      if (url === '/api/settings/llm-catalog') return Promise.resolve({ data: {} })
      return Promise.resolve({ data: {} })
    })

    render(<Settings />)

    const mode = await screen.findByRole('combobox', { name: 'Decision Stability Mode' })
    expect(mode).toHaveValue('shadow')
    expect(screen.getByLabelText('Min. Change Quality')).toHaveValue(70)
    expect(screen.getByLabelText('Min. Calibrated Confidence')).toHaveValue(0.65)
    expect(screen.getByLabelText('Min. Independent Evidence Groups')).toHaveValue(2)

    fireEvent.change(mode, { target: { value: 'enforce' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/ }))

    await waitFor(() => {
      expect(axios.put).toHaveBeenCalledWith('/api/settings', expect.objectContaining({
        decision_stability_mode: 'enforce',
        decision_stability_min_quality: 70,
        decision_stability_min_confidence: 0.65,
        decision_stability_min_evidence_groups: 2,
      }))
    })
  })
})
