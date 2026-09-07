import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, screen } from '@testing-library/react'
import { renderWithQuery } from '../../../test/renderWithQuery'
import axios from 'axios'
import AgentSettingsPanel from '../AgentSettingsPanel'

// Use mutable mock to avoid object-reference infinite re-render loop
const mockUseMeta = vi.fn()
const mockTriggerMetaRefetch = vi.fn()

vi.mock('../../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../../test/i18nMock')).useTranslationMock,
}))

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: () => mockUseMeta(),
  triggerMetaRefetch: mockTriggerMetaRefetch,
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
    renderWithQuery(<AgentSettingsPanel />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders agent settings after loading', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<AgentSettingsPanel />)
    expect(await screen.findByText('Portfolio Manager')).toBeInTheDocument()
    expect(screen.getByText('Market Intelligence')).toBeInTheDocument()
  })

  it('shows empty state when no agents in meta', async () => {
    mockUseMeta.mockReturnValue({ agents: [], signals: [] })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<AgentSettingsPanel />)
    expect(await screen.findByText(/No agent configurations found/)).toBeInTheDocument()
  })

  it('shows error state when settings is null', async () => {
    mockUseMeta.mockReturnValue({ agents: fullAgentsMeta, signals: [] })
    vi.spyOn(axios, 'get').mockRejectedValue({ response: { data: { detail: 'Failed to load.' } } })
    renderWithQuery(<AgentSettingsPanel />)
    expect(await screen.findByText('Failed to load.')).toBeInTheDocument()
  })

  it('displays LLM settings fields for agents with schema', async () => {
    mockUseMeta.mockReturnValue({ agents: fullAgentsMeta, signals: [] })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<AgentSettingsPanel />)

    const configureButtons = await screen.findAllByText('Configure LLM settings')
    expect(configureButtons.length).toBeGreaterThan(0)
  })

  it('skips mutation and metadata refresh when agent settings are unchanged', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    const put = vi.spyOn(axios, 'put').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<AgentSettingsPanel />)

    const saveButton = await screen.findByText('Save Agents')
    await act(async () => {
      saveButton.click()
    })

    expect(put).not.toHaveBeenCalled()
    expect(mockTriggerMetaRefetch).not.toHaveBeenCalled()
  })

  it('sends only the changed agent and refreshes metadata after success', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    const changedSettings = {
      agents: {
        ...defaultSettings.agents,
        market_intelligence: { ...defaultSettings.agents.market_intelligence, enabled: false },
      },
    }
    const put = vi.spyOn(axios, 'put').mockResolvedValue({ data: changedSettings })
    renderWithQuery(<AgentSettingsPanel />)

    await screen.findByText('Market Intelligence')
    const toggle = document.querySelector('input[name="market_intelligence-enabled"]')
    expect(toggle).toBeInstanceOf(HTMLInputElement)
    fireEvent.click(toggle as HTMLInputElement)

    const saveButton = screen.getByText('Save Agents')
    await act(async () => {
      saveButton.click()
    })

    expect(put).toHaveBeenCalledTimes(1)
    expect(put.mock.calls[0]?.[1]).toEqual({
      agents: { market_intelligence: changedSettings.agents.market_intelligence },
    })
    expect(mockTriggerMetaRefetch).toHaveBeenCalledTimes(1)
  })
})