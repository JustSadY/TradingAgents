import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import axios from 'axios'
import AgentSettingsPanel from '../AgentSettingsPanel'

// Use mutable mock to avoid object-reference infinite re-render loop
const mockUseMeta = vi.fn()

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: () => mockUseMeta(),
  triggerMetaRefetch: vi.fn(),
}))

const fullAgentsMeta = [
  {
    key: 'portfolio_manager',
    label: 'Portfolio Manager',
    description: 'Makes final investment decisions.',
    category: 'main',
    default_enabled: true,
    parent_key: null,
    settings_schema: [
      { key: 'provider', type: 'select', label_key: 'LLM Provider', default: 'openai', options: [{ value: 'openai', label_key: 'OpenAI' }, { value: 'anthropic', label_key: 'Anthropic' }] },
      { key: 'model', type: 'string', label_key: 'Model', default: 'gpt-4' },
      { key: 'temperature', type: 'number', label_key: 'Temperature', default: 0.7, min: 0, max: 2, step: 0.1 },
    ],
  },
  {
    key: 'market_intelligence',
    label: 'Market Intelligence',
    description: 'Analyzes market data.',
    category: 'main',
    default_enabled: true,
    parent_key: null,
    settings_schema: [],
  },
  {
    key: 'technical_analyst',
    label: 'Technical Analyst',
    description: 'Performs technical analysis.',
    category: 'sub',
    default_enabled: true,
    parent_key: 'market_intelligence',
    settings_schema: [
      { key: 'indicator', type: 'textarea', label_key: 'Custom Indicator', default: '' },
    ],
  },
]

const defaultSettings = {
  agents: {
    portfolio_manager: { enabled: true, settings: { provider: 'openai', model: 'gpt-4', temperature: 0.7 } },
    market_intelligence: { enabled: true, settings: {} },
    technical_analyst: { enabled: true, settings: { indicator: '' } },
  },
}

describe('AgentSettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseMeta.mockReturnValue({ agents: fullAgentsMeta, signals: [] })
  })

  it('shows loading state initially', () => {
    vi.spyOn(axios, 'get').mockImplementation(() => new Promise(() => {}))
    render(<AgentSettingsPanel />)
    expect(screen.getByText('common.loading')).toBeInTheDocument()
  })

  it('renders agent settings after loading', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    await act(async () => {
      render(<AgentSettingsPanel />)
    })
    expect(screen.getByText('Portfolio Manager')).toBeInTheDocument()
    expect(screen.getByText('Market Intelligence')).toBeInTheDocument()
  })

  it('shows empty state when no agents in meta', async () => {
    mockUseMeta.mockReturnValue({ agents: [], signals: [] })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    await act(async () => {
      render(<AgentSettingsPanel />)
    })
    expect(screen.getByText(/No agent configurations found/)).toBeInTheDocument()
  })

  it('shows error state when settings is null', async () => {
    mockUseMeta.mockReturnValue({ agents: fullAgentsMeta, signals: [] })
    vi.spyOn(axios, 'get').mockRejectedValue({ response: { data: { detail: 'Failed to load.' } } })
    await act(async () => {
      render(<AgentSettingsPanel />)
    })
    expect(screen.getByText('Failed to load.')).toBeInTheDocument()
  })

  it('displays LLM settings fields for agents with schema', async () => {
    mockUseMeta.mockReturnValue({ agents: fullAgentsMeta, signals: [] })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    await act(async () => {
      render(<AgentSettingsPanel />)
    })
    // Click the expand button to show LLM settings for portfolio_manager
    const configureButtons = screen.getAllByText('Configure LLM settings')
    expect(configureButtons.length).toBeGreaterThan(0)
  })
})