import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, act, waitFor } from '@testing-library/react'
import { renderWithQuery } from '../../../test/renderWithQuery'
import { AnalysisChatWidget } from '../AnalysisChatWidget'

const mockAxiosGet = vi.fn()
const mockAxiosPost = vi.fn()

vi.mock('axios', () => {
  const get = (...args: any[]) => mockAxiosGet(...args)
  const post = (...args: any[]) => mockAxiosPost(...args)
  // The generated client calls axios(config); dispatch to the same spies.
  const instance = Object.assign(
    vi.fn((config: { url?: string; method?: string; data?: unknown } = {}) =>
      String(config.method ?? 'get').toLowerCase() === 'get'
        ? get(config.url, config)
        : post(config.url, config.data, config),
    ),
    {
      get,
      post,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  )
  return { default: instance, get, post, interceptors: instance.interceptors }
})

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => {
    const map: Record<string, string> = {
      'analysis.chat.welcome_title': 'Ask questions about this analysis',
      'analysis.chat.welcome_desc': 'The AI can explain reports, compare tickers, etc.',
      'analysis.chat.placeholder': 'Type your question...',
      'analysis.chat.send': 'Send',
      'analysis.chat.thinking': 'Thinking...',
      'analysis.chat.error': 'Chat error',
    }
    return map[k] || k
  }}),
}))

describe('AnalysisChatWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders welcome state when no messages', async () => {
    mockAxiosGet.mockResolvedValue({ data: [] })
    await act(async () => {
      renderWithQuery(<AnalysisChatWidget analysisId={1} />)
    })
    expect(screen.getByText('Ask questions about this analysis')).toBeInTheDocument()
  })

  it('loads existing chat messages on mount', async () => {
    const messages = [
      { id: 1, role: 'user', content: 'What is the signal?' },
      { id: 2, role: 'assistant', content: 'The signal is Buy.' },
    ]
    mockAxiosGet.mockResolvedValue({ data: messages })
    renderWithQuery(<AnalysisChatWidget analysisId={1} />)

    // History lands through the query cache, so wait for the commit rather
    // than asserting synchronously after render.
    expect(await screen.findByText('What is the signal?')).toBeInTheDocument()
    expect(screen.getByText('The signal is Buy.')).toBeInTheDocument()
  })

  it('sends a message and shows response', async () => {
    mockAxiosGet.mockResolvedValue({ data: [] })
    mockAxiosPost.mockResolvedValue({
      data: { id: 3, role: 'assistant', content: 'Based on the data, I recommend a Buy.' },
    })

    await act(async () => {
      renderWithQuery(<AnalysisChatWidget analysisId={1} />)
    })

    const input = screen.getByPlaceholderText('Type your question...')
    const sendBtn = screen.getByText('Send')

    await act(async () => {
      fireEvent.change(input, { target: { value: 'What do you recommend?' } })
    })
    await act(async () => {
      fireEvent.click(sendBtn)
    })

    await waitFor(() => {
      expect(screen.getByText('What do you recommend?')).toBeInTheDocument()
    })
    expect(screen.getByText('Based on the data, I recommend a Buy.')).toBeInTheDocument()
  })

  it('shows thinking indicator while waiting for response', async () => {
    mockAxiosGet.mockResolvedValue({ data: [] })
    mockAxiosPost.mockImplementation(() => new Promise(() => {}))

    await act(async () => {
      renderWithQuery(<AnalysisChatWidget analysisId={1} />)
    })

    const input = screen.getByPlaceholderText('Type your question...')
    const sendBtn = screen.getByText('Send')

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Analyze this' } })
    })
    await act(async () => {
      fireEvent.click(sendBtn)
    })

    expect(screen.getByText('Thinking...')).toBeInTheDocument()
  })
})
