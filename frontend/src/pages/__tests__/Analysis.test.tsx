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
        'analysis.order.title': 'Automated Order Result',
        'analysis.order.analysis_complete_status': 'Analysis complete',
        'analysis.order.analysis_complete': 'Analysis complete. This does not confirm that a trade was placed.',
        'analysis.order.pending': 'Order result pending',
        'analysis.order.pending_description': 'No execution outcome has been received. Check Orders before assuming an order was placed.',
        'analysis.order.log_prefix': 'Order result',
        'analysis.order.outcome.filled': 'Order filled',
        'analysis.order.outcome.skipped': 'Order skipped',
        'analysis.order.outcome.rejected': 'Order rejected',
        'analysis.order.outcome.error': 'Order execution failed',
        'analysis.order.action': 'Action',
        'analysis.order.action.buy': 'Buy',
        'analysis.order.action.sell': 'Sell',
        'analysis.order.symbol': 'Symbol',
        'analysis.order.quantity': 'Quantity',
        'analysis.order.price': 'Price',
        'analysis.pm.title': 'Portfolio Manager Recommendation',
        'analysis.pm.single_authority': 'Single AI authority for sizing and trade parameters',
        'analysis.pm.legacy_fallback': 'Legacy Trader proposal retained for this historical analysis',
        'analysis.pm.entry': 'Entry',
        'analysis.pm.stop': 'Stop Loss',
        'analysis.pm.target': 'Take Profit',
        'analysis.pm.allocation': 'Allocation',
        'analysis.pm.capital': 'Suggested Capital',
        'analysis.pm.leverage': 'Leverage',
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
  AnalysisControls: ({ handleRun, handleStop, running, runStatus, ticker, setTicker, startError, onSelectTickerSuggestion }: {
    handleRun: () => void; handleStop: () => void; running: boolean; runStatus: string
    ticker: string; setTicker: (ticker: string) => void
    startError?: { message: string; suggestions: { symbol: string }[] } | null
    onSelectTickerSuggestion?: (ticker: string) => void
  }) => (
    <div>
      <input aria-label="Ticker" value={ticker} onChange={event => setTicker(event.target.value)} />
      <button onClick={handleRun}>Start analysis</button>
      <button onClick={handleStop}>Stop analysis</button>
      <span data-testid="run-state">{running ? 'running' : 'idle'}</span>
      <span data-testid="run-status">{runStatus}</span>
      {startError && (
        <div role="alert">
          {startError.message}
          {startError.suggestions.map(suggestion => (
            <button key={suggestion.symbol} onClick={() => onSelectTickerSuggestion?.(suggestion.symbol)}>
              Use {suggestion.symbol}
            </button>
          ))}
        </div>
      )}
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

  it('renders a status message instead of falling back to its technical agent key', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'status-task' } })
      return Promise.resolve({ data: {} })
    })

    render(<Analysis />)
    const user = userEvent.setup()
    await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      MockWebSocket.instances[0].emit({
        type: 'status',
        agent: 'portfolio_manager',
        status: 'running',
        message: 'Preparing engine',
      })
    })

    expect(screen.getAllByText('Preparing engine')).not.toHaveLength(0)
    expect(screen.queryByText('portfolio_manager')).not.toBeInTheDocument()
  })

  it('shows the separate filled order outcome after analysis completion', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'order-result-task' } })
      return Promise.resolve({ data: {} })
    })

    render(<Analysis />)
    const user = userEvent.setup()
    await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      // `complete` only closes the analysis lifecycle. The execution result
      // arrives as its own event, so it can never be mistaken for a fill.
      MockWebSocket.instances[0].emit({ type: 'complete', duration_seconds: 5, llm_calls: 2, signal: 'Buy' })
      MockWebSocket.instances[0].emit({
        type: 'order_result', outcome: 'filled', action: 'BUY', ticker: 'AAPL',
        filled_quantity: 2, filled_price: 123.45, reason_code: 'risk_checks_passed',
      })
    })

    const card = await screen.findByTestId('analysis-order-result')
    expect(card).toHaveAttribute('data-outcome', 'filled')
    expect(card).toHaveTextContent('Order filled')
    expect(card).toHaveTextContent('Buy')
    expect(card).toHaveTextContent('AAPL')
    expect(card).toHaveTextContent('2')
    expect(card).toHaveTextContent('$123.45')
    expect(card).toHaveTextContent('risk_checks_passed')
    expect(screen.getByText('Analysis complete. This does not confirm that a trade was placed.')).toBeInTheDocument()
  })

  it('renders a skipped order result from the legacy status field', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'skipped-order-task' } })
      return Promise.resolve({ data: {} })
    })

    render(<Analysis />)
    const user = userEvent.setup()
    await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'NVDA')
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      MockWebSocket.instances[0].emit({
        type: 'order_result', status: 'skipped', ticker: 'NVDA',
        message: 'Signal is HOLD, so no order was sent.',
      })
    })

    const card = await screen.findByTestId('analysis-order-result')
    expect(card).toHaveAttribute('data-outcome', 'skipped')
    expect(card).toHaveTextContent('Order skipped')
    expect(card).toHaveTextContent('Signal is HOLD, so no order was sent.')
  })

  it('uses the streamed Portfolio Manager decision as the only live sizing recommendation', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {}

      emit(event: Record<string, unknown>) {
        this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent)
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'pm-decision-task' } })
      return Promise.resolve({ data: {} })
    })

    render(<Analysis />)
    const user = userEvent.setup()
    await user.type(screen.getByRole('textbox', { name: 'Ticker' }), 'NVDA')
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await act(async () => {
      MockWebSocket.instances[0].emit({ type: 'report', section: 'trader_plan', content: 'Legacy-looking trader text' })
      MockWebSocket.instances[0].emit({
        type: 'report',
        section: 'portfolio_decision_json',
        content: JSON.stringify({
          rating: 'Buy', confidence_score: 0.82, entry_price: 120, stop_loss: 112,
          take_profit_price: 140, position_size_pct: 8, suggested_capital: 8000,
          recommended_leverage: 1,
        }),
      })
    })

    const card = await screen.findByTestId('portfolio-decision-card')
    expect(card).toHaveTextContent('Portfolio Manager Recommendation')
    expect(card).toHaveTextContent('Single AI authority for sizing and trade parameters')
    expect(card).toHaveTextContent('82%')
    expect(card).toHaveTextContent('$120.00')
    expect(card).toHaveTextContent('8.0%')
    expect(screen.queryByText('Trader Proposal')).not.toBeInTheDocument()
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
    expect(MockWebSocket.instances[0].protocols).toEqual([
      'tradingagents.v1',
      'tradingagents.jwt.test-token',
    ])

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

  it('defers a connecting socket close until it can send an explicit normal close code', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      static CONNECTING = 0
      static OPEN = 1
      static CLOSING = 2
      static CLOSED = 3
      readyState = MockWebSocket.CONNECTING
      closeCalls: Array<[number | undefined, string | undefined]> = []
      onopen: ((event: Event) => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close(code?: number, reason?: string) {
        this.closeCalls.push([code, reason])
        this.readyState = MockWebSocket.CLOSING
        this.onclose?.(new CloseEvent('close', { code }))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const task = {
      task_id: 'connecting-stop-task', ticker: 'AAPL', trade_date: '2026-07-28', asset_type: 'stock', started_at: 0, status: 'running',
    }
    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Stop analysis' }))
    await waitFor(() => expect(screen.getByTestId('run-state')).toHaveTextContent('idle'))

    // Calling close while CONNECTING cancels the handshake and yields an
    // abnormal 1005/1006 pair. The implementation waits for the handshake.
    expect(MockWebSocket.instances[0].closeCalls).toEqual([])
    act(() => {
      MockWebSocket.instances[0].readyState = MockWebSocket.OPEN
      MockWebSocket.instances[0].onopen?.(new Event('open'))
    })
    expect(MockWebSocket.instances[0].closeCalls).toEqual([[1000, 'Analysis stopped by user']])
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

  it('keeps a known analysis running when the server rejects Stop', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      readyState = 1
      onclose: ((event: CloseEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close', { code: 1000 }))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'cannot-stop-task' } })
      if (url === '/api/analysis/cannot-stop-task/cancel') return Promise.reject(new Error('backend unavailable'))
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
    await user.click(screen.getByRole('button', { name: 'Stop analysis' }))

    await waitFor(() => expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/cannot-stop-task/cancel'))
    expect(screen.getByTestId('run-state')).toHaveTextContent('running')
  })

  it('cancels a multi-analysis and does not reconnect its socket afterwards', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      readyState = 1
      onclose: ((event: CloseEvent) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close', { code: 1000 }))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const axios = await import('axios')
    vi.mocked(axios.default.get).mockResolvedValue({ data: [] })
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run-portfolio') return Promise.resolve({ data: { task_id: 'portfolio-stop-task' } })
      if (url === '/api/analysis/portfolio-stop-task/cancel') return Promise.resolve({ data: { cancelled: true } })
      return Promise.resolve({ data: {} })
    })
    render(<Analysis />)

    const user = userEvent.setup()
    await user.click(screen.getByText('Multi').closest('button')!)
    const input = screen.getByPlaceholderText('AAPL, Enter')
    await user.type(input, 'AAPL{enter}')
    await user.type(input, 'MSFT{enter}')
    await user.click(screen.getByText('analysis.multi.btn_start').closest('button')!)
    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))

    await user.click(screen.getByRole('button', { name: /analysis\.btn\.stop/ }))

    await waitFor(() => expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/portfolio-stop-task/cancel'))
    expect(screen.getByText('analysis.ws.stopped')).toBeInTheDocument()
    expect(MockWebSocket.instances).toHaveLength(1)
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

  it('normalizes analyst stream aliases and keeps dynamically added reports visible', async () => {
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
      if (url === '/api/analysis/run') return Promise.resolve({ data: { task_id: 'dynamic-report-task' } })
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
      MockWebSocket.instances[0].emit({ type: 'token', agent: 'social', token: 'sentiment update' })
      MockWebSocket.instances[0].emit({ type: 'report', section: 'sector_rotation_report', content: 'Sector result' })
    })
    await user.click(screen.getByRole('button', { name: /Reports/ }))

    expect(screen.getByTestId('report-sentiment_report')).toBeInTheDocument()
    expect(screen.queryByTestId('report-social_report')).not.toBeInTheDocument()
    expect(screen.getByTestId('report-Sector Rotation')).toBeInTheDocument()
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

  it('marks a closed task as failed instead of retrying or reviving it from a stale active-task snapshot', async () => {
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

    const task = {
      task_id: 'terminal-task', ticker: 'NVDA', trade_date: '2026-07-28', asset_type: 'stock', started_at: 0,
      status: 'running',
    }
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockImplementation((url: string) => {
      // The hook deliberately still has this stale snapshot. The close-time
      // probe is authoritative and says the worker already removed the task.
      if (url === '/api/analysis/active') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: {} })
    })

    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    act(() => MockWebSocket.instances[0].close())

    await waitFor(() => {
      expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
      expect(screen.getByTestId('run-status')).toHaveTextContent('error')
    })
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(localStorage.getItem('ta_task_running')).toBeNull()
  })

  it('does not retry an explicitly unauthorized WebSocket close', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close(code = 1000) {
        this.onclose?.(new CloseEvent('close', { code }))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const task = {
      task_id: 'unauthorized-task', ticker: 'NVDA', trade_date: '2026-07-28', asset_type: 'stock', started_at: 0,
      status: 'running',
    }
    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    act(() => MockWebSocket.instances[0].close(4001))

    await waitFor(() => {
      expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
      expect(screen.getByTestId('run-status')).toHaveTextContent('error')
      expect(screen.getByText('analysis.ws.auth_required')).toBeInTheDocument()
    })
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('stops reconnecting when the close-time task probe confirms authentication failed', async () => {
    class MockWebSocket {
      static instances: MockWebSocket[] = []
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: ((event: CloseEvent) => void) | null = null
      onerror: ((event: Event) => void) | null = null

      constructor() {
        MockWebSocket.instances.push(this)
      }

      close() {
        this.onclose?.(new CloseEvent('close', { code: 1000 }))
      }
    }
    vi.stubGlobal('WebSocket', MockWebSocket)

    const task = {
      task_id: 'expired-probe-task', ticker: 'NVDA', trade_date: '2026-07-28', asset_type: 'stock', started_at: 0,
      status: 'running',
    }
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockImplementation((url: string) => {
      if (url === '/api/analysis/active') return Promise.reject({ response: { status: 401 } })
      return Promise.resolve({ data: {} })
    })
    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    act(() => MockWebSocket.instances[0].close())

    await waitFor(() => {
      expect(screen.getByTestId('run-state')).toHaveTextContent('idle')
      expect(screen.getByTestId('run-status')).toHaveTextContent('error')
      expect(screen.getByText('analysis.ws.auth_required')).toBeInTheDocument()
    })
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('keeps reconnecting when the close-time task probe confirms the analysis is still active', async () => {
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

    const task = {
      task_id: 'active-task', ticker: 'NVDA', trade_date: '2026-07-28', asset_type: 'stock', started_at: 0,
      status: 'running',
    }
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockImplementation((url: string) => {
      if (url === '/api/analysis/active') return Promise.resolve({ data: [task] })
      return Promise.resolve({ data: {} })
    })

    localStorage.setItem('test_active_tasks', JSON.stringify([task]))
    localStorage.setItem('ta_task_running', JSON.stringify({
      ticker: task.ticker, taskId: task.task_id, startedAt: new Date().toISOString(),
    }))
    render(<Analysis />)

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    vi.useFakeTimers()
    act(() => MockWebSocket.instances[0].close())
    await act(async () => {
      // Flush the async close-time `/active` probe before advancing its
      // reconnect delay.  The mock resolves on a Promise microtask rather
      // than a fake timer.
      for (let index = 0; index < 6; index += 1) await Promise.resolve()
    })
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/active', { timeout: 2_000 })
    await act(async () => {
      // Resumed tasks begin at reconnect attempt 1, so the next exponential
      // delay is two seconds.
      await vi.advanceTimersByTimeAsync(2_000)
    })

    expect(MockWebSocket.instances).toHaveLength(2)
    expect(screen.getByTestId('run-state')).toHaveTextContent('running')
  })

  it('shows structured unknown-symbol API errors and only applies a suggestion after an explicit click', async () => {
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockResolvedValue({ data: {} })
    vi.mocked(axios.default.post).mockImplementation((url: string) => {
      if (url === '/api/analysis/run') {
        return Promise.reject({
          response: {
            data: {
              detail: {
                code: 'unknown_ticker',
                message: "'NVDIA' is not a recognized Yahoo Finance symbol.",
                ticker: 'NVDIA',
                suggestions: [{ symbol: 'NVDA', name: 'NVIDIA Corporation', quote_type: 'EQUITY' }],
              },
            },
          },
        })
      }
      return Promise.resolve({ data: {} })
    })
    render(<Analysis />)

    const user = userEvent.setup()
    const tickerInput = screen.getByRole('textbox', { name: 'Ticker' })
    await user.clear(tickerInput)
    await user.type(tickerInput, 'NVDIA')
    await user.click(screen.getByRole('button', { name: 'Start analysis' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("'NVDIA' is not a recognized Yahoo Finance symbol."))
    expect(screen.getByRole('alert')).not.toHaveTextContent('[object Object]')
    expect(tickerInput).toHaveValue('NVDIA')

    await user.click(screen.getByRole('button', { name: 'Use NVDA' }))
    expect(tickerInput).toHaveValue('NVDA')
  })
})
