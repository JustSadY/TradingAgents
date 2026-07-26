import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  useActiveTasks: () => ({ activeTasks: [], loading: false, refreshActiveTasks: vi.fn() }),
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
vi.mock('../../components/analysis/ReportCard', () => ({ ReportCard: () => <div>ReportCard</div> }))
vi.mock('../../components/analysis/AnalysisControls', () => ({ AnalysisControls: () => <div>AnalysisControls</div> }))
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
    expect(MockWebSocket.instances[0].url).toBe(`ws://${window.location.host}/ws/analysis/portfolio-task?token=test-token`)

    vi.useFakeTimers()
    act(() => {
      MockWebSocket.instances[0].emit({ type: 'complete' })
      vi.advanceTimersByTime(10_000)
    })

    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
