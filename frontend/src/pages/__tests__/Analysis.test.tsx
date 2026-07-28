import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import Analysis from '../Analysis'

vi.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
  get: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
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

vi.mock('../../hooks/useActiveTasks', () => ({
  useActiveTasks: () => ({
    activeTasks: JSON.parse(localStorage.getItem('test_active_tasks') || '[]'),
    loading: false,
    unavailable: false,
    refreshActiveTasks: vi.fn(),
  }),
}))

vi.mock('../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'analysis.title': 'Analysis',
        'analysis.tab.single': 'Run',
        'analysis.tab.multi': 'Multi',
        'analysis.tab.history': 'History',
        'analysis.running': 'Running...',
        'analysis.ws.failed_to_start': 'Failed to start analysis',
        'analysis.btn.rerun': 'Re-run',
        'analysis.btn.cancel': 'Cancel',
        'analysis.rerun.title': 'Re-run Analysis',
        'analysis.tab.reports': 'Reports',
        'analysis.tab.debate': 'Debate',
      }
      return map[key] || key
    },
    language: 'en',
    setLanguage: vi.fn(),
  }),
}))

vi.mock('../../utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
}))

vi.mock('lucide-react', () => ({
  Loader2: () => <div>Loader2</div>,
  CheckCircle: () => <div>CheckCircle</div>,
  AlertCircle: () => <div>AlertCircle</div>,
  AlertTriangle: () => <div>AlertTriangle</div>,
  History: () => <div>HistoryIcon</div>,
  X: () => <div>X</div>,
  BarChart2: () => <div>BarChart2</div>,
  FileText: () => <div>FileText</div>,
  Zap: () => <div>Zap</div>,
  Download: () => <div>Download</div>,
  FileDown: () => <div>FileDown</div>,
  Scale: () => <div>Scale</div>,
  Share2: () => <div>Share2</div>,
  Copy: () => <div>Copy</div>,
  MessageSquare: () => <div>MessageSquare</div>,
  Bot: () => <div>Bot</div>,
  Terminal: () => <div>Terminal</div>,
  BookOpen: () => <div>BookOpen</div>,
}))

vi.mock('../../components/analysis/SignalBadge', () => ({ SignalBadge: () => <div>SignalBadge</div> }))
vi.mock('../../components/analysis/ReportCard', () => ({
  ReportCard: ({ label, defaultOpen, isStreaming }: { label: string; defaultOpen?: boolean; isStreaming?: boolean }) => (
    <div data-testid={`report-${label}`} data-default-open={String(defaultOpen)} data-streaming={String(isStreaming)}>ReportCard</div>
  ),
}))
vi.mock('../../components/analysis/AnalysisControls', () => ({
  AnalysisControls: ({ handleRun, handleStop, running, runStatus }: {
    handleRun: () => void; handleStop: () => void; running: boolean; runStatus: string
  }) => (
    <div>
      <button onClick={handleRun}>Start analysis</button>
      <button onClick={handleStop}>Stop analysis</button>
      <span data-testid="run-state">{running ? 'running' : 'idle'}</span>
      <span data-testid="run-status">{runStatus}</span>
    </div>
  ),
}))
vi.mock('../../components/analysis/DebateHistoryWidget', () => ({
  DebateHistoryWidget: () => <div>DebateHistoryWidget</div>,
  parseDebateMessage: vi.fn(),
  getSenderStyles: () => ({}),
}))
vi.mock('../../components/analysis/AnalysisChatWidget', () => ({ AnalysisChatWidget: () => <div>AnalysisChatWidget</div> }))
vi.mock('../../components/analysis/RiskMetricsCard', () => ({ RiskMetricsCard: () => <div>RiskMetricsCard</div> }))
vi.mock('../../components/analysis/MentalModelTicker', () => ({ MentalModelTicker: () => <div>MentalModelTicker</div> }))
vi.mock('../../components/analysis/KellyPositioningCard', () => ({ KellyPositioningCard: () => <div>KellyPositioningCard</div> }))
vi.mock('../../components/ErrorBoundary', () => ({ ErrorBoundary: ({ children }: any) => children }))

describe('Analysis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('renders analysis tabs', async () => {
    render(<Analysis />)
    await waitFor(() => {
      expect(screen.getByText('Run')).toBeInTheDocument()
    })
    expect(screen.getByText('Multi')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
  })

  it('ignores malformed persisted run state instead of crashing the run tab', async () => {
    localStorage.setItem('ta_last_run', JSON.stringify({
      ticker: null,
      date: 42,
      assetType: { unexpected: true },
      runStatus: 'not-a-status',
      reports: null,
      log: { line: 'not an array' },
      activeSection: ['not a string'],
      analysisId: 'not a number',
      liveDebate: { malformed: true },
    }))
    localStorage.setItem('ta_task_running', '{malformed')

    render(<Analysis />)

    await waitFor(() => expect(screen.getByText('Run')).toBeInTheDocument())
    expect(localStorage.getItem('ta_task_running')).toBeNull()
  })

  it('does not reconnect the multi-ticker WebSocket after a terminal completion event', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      url: string
      protocols: string | string[] | undefined
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string, protocols?: string | string[]) {
        this.url = url
        this.protocols = protocols
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.get).mockResolvedValue({ data: [] })
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run-portfolio') return Promise.resolve({ data: { task_id: 'portfolio-task' } })
      return Promise.resolve({ data: {} })
    })

    const user = userEvent.setup()
    localStorage.setItem('ta_access', 'test-token')
    render(<Analysis />)
    await user.click(screen.getByText('Multi').closest('button')!)

    const input = screen.getByPlaceholderText('AAPL, Enter')
    await user.type(input, 'AAPL{enter}')
    await user.type(input, 'MSFT{enter}')
    await user.click(screen.getByText('analysis.multi.btn_start').closest('button')!)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    expect(MockWebSocket.instances[0].url).toBe(`ws://${window.location.host}/ws/analysis/portfolio-task`)
    expect(MockWebSocket.instances[0].protocols).toEqual(['tradingagents.jwt.test-token'])

    vi.useFakeTimers()
    act(() => {
      MockWebSocket.instances[0].emit({ type: 'complete' })
      vi.advanceTimersByTime(10_000)
    })

    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('keeps a resumed task socket stable when streamed state causes a rerender', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      url: string
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string) {
        this.url = url
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    localStorage.setItem('ta_access', 'test-token')
    localStorage.setItem('test_active_tasks', JSON.stringify([{
      task_id: 'resume-task', ticker: 'AAPL', trade_date: '2026-07-26', asset_type: 'stock', started_at: 0, status: 'running',
    }]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: 'AAPL', taskId: 'resume-task', startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      MockWebSocket.instances[0].emit({ type: 'progress', label: 'Market data', stage: 'research' })
      await new Promise(resolve => setTimeout(resolve, 20))
    })

    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('resumes a persisted task after Strict Mode restarts its effect', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      url: string
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string) {
        this.url = url
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    localStorage.setItem('ta_access', 'test-token')
    localStorage.setItem('test_active_tasks', JSON.stringify([{
      task_id: 'strict-task', ticker: 'AAPL', trade_date: '2026-07-26', asset_type: 'stock', started_at: 0, status: 'running',
    }]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: 'AAPL', taskId: 'strict-task', startedAt: new Date().toISOString(),
    }))
    render(<StrictMode><Analysis /></StrictMode>)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
  })

  it('does not reattach a task still listed by active-tasks after the user stops it', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      url: string
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor(url: string) {
        this.url = url
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const task = {
      task_id: 'stop-task', ticker: 'AAPL', trade_date: '2026-07-26', asset_type: 'stock', started_at: 0,
    }
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockImplementation((url: string) => {
      if (url === '/api/analysis/active') return Promise.resolve({ data: [task] })
      return Promise.resolve({ data: {} })
    })

    localStorage.setItem('ta_access', 'test-token')
    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Stop analysis' }))
    await waitFor(() => expect(screen.getByTestId('run-state')).toHaveTextContent('idle'))

    await act(async () => {
      await new Promise(resolve => setTimeout(resolve, 20))
    })

    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('cancels a task returned after Stop while the start request is still pending', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    let resolveStart!: (value: { data: { task_id: string } }) => void
    const pendingStart = new Promise<{ data: { task_id: string } }>(resolve => { resolveStart = resolve })
    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return pendingStart
      if (url === '/api/analysis/late-task/cancel') return Promise.resolve({ data: {} })
      return Promise.resolve({ data: {} })
    })

    localStorage.setItem('ta_last_run', JSON.stringify({
      ticker: 'AAPL', date: '2026-07-26', assetType: 'stock', runStatus: 'idle',
      signal: null, reports: {}, log: [], activeSection: null, analysisId: null, liveDebate: [],
    }))
    render(<Analysis />)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(screen.getByTestId('run-state')).toHaveTextContent('running'))

    await user.click(screen.getByRole('button', { name: 'Stop analysis' }))
    await waitFor(() => expect(screen.getByTestId('run-state')).toHaveTextContent('idle'))

    await act(async () => {
      resolveStart({ data: { task_id: 'late-task' } })
      await Promise.resolve()
    })

    await waitFor(() => expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/late-task/cancel'))
    expect(localStorage.getItem('ta_task_running')).toBeNull()
    expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('ignores a delayed latest-analysis bootstrap response after a new run starts', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    let resolveLatest!: (value: { data: Record<string, unknown> }) => void
    const pendingLatest = new Promise<{ data: Record<string, unknown> }>(resolve => { resolveLatest = resolve })
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockImplementation((url: string) => {
      if (url === '/api/analysis/latest') return pendingLatest
      return Promise.resolve({ data: {} })
    })
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'new-task' } })
      return Promise.resolve({ data: {} })
    })
    localStorage.setItem('ta_last_run', JSON.stringify({
      ticker: 'AAPL', date: '2026-07-26', assetType: 'stock', runStatus: 'idle',
      signal: null, reports: {}, log: [], activeSection: null, analysisId: null, liveDebate: [],
    }))
    render(<Analysis />)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      resolveLatest({ data: { ticker: 'MSFT', trade_date: '2026-07-25', id: 99 } })
      await Promise.resolve()
    })

    expect(screen.getByTestId('run-state')).toHaveTextContent('running')
    expect(screen.getByTestId('run-status')).toHaveTextContent('running')
  })

  it('does not resume a persisted task that is absent from the shared active-task result', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: 'AAPL', taskId: 'probe-task', startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    expect(MockWebSocket.instances).toHaveLength(0)
    expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
    expect(localStorage.getItem('ta_task_running')).toBeNull()
  })

  it('keeps the first streamed report selected instead of jumping to every agent', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'section-task' } })
      return Promise.resolve({ data: {} })
    })
    localStorage.setItem('ta_last_run', JSON.stringify({
      ticker: 'AAPL', date: '2026-07-26', assetType: 'stock', runStatus: 'idle',
      signal: null, reports: {}, log: [], activeSection: null, analysisId: null, liveDebate: [],
    }))
    render(<Analysis />)

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      MockWebSocket.instances[0].emit({ type: 'token', agent: 'market', token: 'market update' })
      MockWebSocket.instances[0].emit({ type: 'token', agent: 'sentiment', token: 'sentiment update' })
    })
    await user.click(screen.getByRole('button', { name: /Reports/ }))

    expect(screen.getByTestId('report-market_report')).toHaveAttribute('data-default-open', 'true')
    expect(screen.getByTestId('report-sentiment_report')).toHaveAttribute('data-default-open', 'false')
  })

  it('does not reconnect a socket after Stop clears an already-scheduled retry', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close'))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    localStorage.setItem('test_active_tasks', JSON.stringify([{
      task_id: 'retry-task', ticker: 'AAPL', trade_date: '2026-07-26', asset_type: 'stock', started_at: 0, status: 'running',
    }]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: 'AAPL', taskId: 'retry-task', startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    vi.useFakeTimers()
    act(() => MockWebSocket.instances[0].close())
    await act(async () => {
      screen.getByRole('button', { name: 'Stop analysis' }).click()
      await Promise.resolve()
    })
    act(() => vi.advanceTimersByTime(10_000))

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
  })
})
