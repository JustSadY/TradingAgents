import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, act } from '@testing-library/react'
import { renderWithQuery } from '../../../test/renderWithQuery'
import axios from 'axios'
import ToolSettingsPanel from '../ToolSettingsPanel'

// Use mutable mock that can be changed per test via mockReturnValue
const mockUseMeta = vi.fn()

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => {
    const map: Record<string, string> = {
      'tools.category.market': 'MARKET',
      'tools.category.analysis': 'ANALYSIS',
    }
    return map[k] || k
  }}),
}))

vi.mock('../../../hooks/useMeta', () => ({
  useMeta: () => mockUseMeta(),
}))

const fullToolsMeta = [
  {
    key: 'yfinance',
    category: 'market',
    default_enabled: true,
    allowed_analysts: ['market'],
    label_key: 'Yahoo Finance',
    description_key: 'Fetch market data from Yahoo Finance.',
    settings_schema: [
      { key: 'max_results', type: 'number', label_key: 'Max Results', default: 10, min: 1, max: 100, scope: 'both' },
      { key: 'api_key', type: 'secret', label_key: 'API Key', default: '', scope: 'user' },
    ],
  },
  {
    key: 'technical_indicator',
    category: 'analysis',
    default_enabled: false,
    allowed_analysts: ['technical'],
    label_key: 'Technical Indicators',
    description_key: 'Compute technical indicators.',
    settings_schema: [
      { key: 'enabled_indicators', type: 'string_list', label_key: 'Indicators', default: ['RSI', 'MACD'], scope: 'both' },
    ],
  },
]

const defaultSettings = {
  tools: {
    yfinance: { enabled: true, settings: { max_results: 20, api_key: '' } },
    technical_indicator: { enabled: false, settings: { enabled_indicators: ['RSI'] } },
  },
}

describe('ToolSettingsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock: return full tools list
    mockUseMeta.mockReturnValue({ tools: fullToolsMeta })
  })

  it('shows loading state initially', () => {
    vi.spyOn(axios, 'get').mockImplementation(() => new Promise(() => {}))
    renderWithQuery(<ToolSettingsPanel />)
    expect(screen.getByText('common.loading')).toBeInTheDocument()
  })

  it('renders tool settings after loading', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<ToolSettingsPanel />)
    expect(await screen.findByText('Yahoo Finance')).toBeInTheDocument()
    expect(screen.getByText('Technical Indicators')).toBeInTheDocument()
  })

  it('renders category headers', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<ToolSettingsPanel />)
    expect(await screen.findByText('MARKET')).toBeInTheDocument()
    expect(screen.getByText('ANALYSIS')).toBeInTheDocument()
  })

  it('shows empty state when no tools in meta', async () => {
    mockUseMeta.mockReturnValue({ tools: [] })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<ToolSettingsPanel />)
    expect(await screen.findByText(/No tool configurations found/)).toBeInTheDocument()
  })

  it('renders Save Tools button by default', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    renderWithQuery(<ToolSettingsPanel />)
    expect(await screen.findByText('Save Tools')).toBeInTheDocument()
  })

  it('hides save button when hideSaveButton is true', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultSettings })
    await act(async () => {
      renderWithQuery(<ToolSettingsPanel hideSaveButton={true} />)
    })
    expect(screen.queryByText('Save Tools')).not.toBeInTheDocument()
  })
})