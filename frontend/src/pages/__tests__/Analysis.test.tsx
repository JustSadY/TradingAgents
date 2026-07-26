import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
  })

  it('renders analysis tabs', async () => {
    render(<Analysis />)
    await waitFor(() => {
      expect(screen.getByText('Run')).toBeInTheDocument()
    })
    expect(screen.getByText('Multi')).toBeInTheDocument()
    expect(screen.getByText('History')).toBeInTheDocument()
  })
})
