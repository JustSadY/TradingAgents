import { REPORT_SECTIONS } from '../../report/reportSections'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axios from 'axios'
import { renderWithQuery } from '../../test/renderWithQuery'
import SharedReport from '../SharedReport'
import { formatSharedReportValue } from '../../utils/sharedReport'

vi.mock('react-router-dom', () => ({
  useParams: () => ({ token: 'public-token' }),
}))

vi.mock('../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../test/i18nMock')).useTranslationMock,
}))

vi.mock('../../components/analysis/DebateHistoryWidget', () => ({
  DebateHistoryWidget: ({ investmentHistory, riskHistory }: { investmentHistory: unknown; riskHistory: unknown }) => (
    <div data-testid="shared-debates">
      {JSON.stringify({ investmentHistory, riskHistory })}
    </div>
  ),
}))

const fullSharedReport = {
  ticker: 'NVDA',
  trade_date: '2026-08-01',
  signal: 'Buy',
  market_report: 'Market report body',
  sentiment_report: 'Sentiment report body',
  news_report: 'News report body',
  fundamentals_report: 'Fundamentals report body',
  macro_report: 'Macro report body',
  options_report: 'Options report body',
  quant_report: 'Quant report body',
  earnings_report: 'Earnings report body',
  insider_report: 'Insider report body',
  ownership_report: 'Ownership report body',
  ratings_report: 'Ratings report body',
  short_interest_report: 'Short interest report body',
  valuation_report: 'Valuation report body',
  catalyst_report: 'Catalyst report body',
  review_report: 'Review report body',
  synthesis_report: 'Synthesis report body',
  audit_report: 'Audit report body',
  agent_qa_report: 'Q&A report body',
  investment_plan: 'Investment plan body',
  trader_plan: 'Trader plan body',
  final_decision: 'Final decision body',
  bull_history: ['Bull Analyst: Trend is constructive'],
  bear_history: [{ sender: 'Bear Analyst', content: 'Valuation is demanding' }],
  investment_debate_history: ['Bull Analyst: Consensus argument'],
  risk_debate_history: ['Aggressive Analyst: Risk argument'],
  judge_decision: 'Judge decision body',
  trader_proposal_json: JSON.stringify({ action: 'BUY', quantity: 2 }),
  chart_annotations: null,
  risk_metrics: { max_drawdown: 0.12 },
  quality: null,
  degraded: false,
  failed_agents: [],
  duration_seconds: 12.5,
  llm_provider: 'test',
  llm_model: 'test-model',
  expires_at: '2026-08-03T00:00:00+00:00',
  created_at: '2026-08-01T00:00:00+00:00',
}

describe('SharedReport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(axios.get).mockResolvedValue({ data: fullSharedReport })
  })

  it('renders every non-empty public report section instead of only final decisions', async () => {
    renderWithQuery(<SharedReport />)

    // Wait for rendered content rather than the request itself: the fetch fires
    // one tick before the data is committed to the DOM.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Final Decision (Portfolio Manager)' })).toBeInTheDocument())
    expect(axios.get).toHaveBeenCalledWith('/api/share/public-token', expect.anything())

    for (const label of [
      'Final Decision (Portfolio Manager)',
      'Market Analysis',
      'Fundamental Analysis',
      'Short Interest',
      'Cross-Examination',
      'Bull Arguments',
      'Debate',
      'Risk Metrics',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }

    await userEvent.click(screen.getByRole('button', { name: 'Market Analysis' }))
    expect(screen.getByText('Market report body')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Debate' }))
    expect(screen.getByTestId('shared-debates')).toHaveTextContent('Consensus argument')
    expect(screen.getByTestId('shared-debates')).toHaveTextContent('Risk argument')
  })

  it('shows the canonical Portfolio Manager decision and hides competing legacy Trader proposals', async () => {
    vi.mocked(axios.get).mockResolvedValue({
      data: {
        ...fullSharedReport,
        portfolio_decision: {
          rating: 'Buy',
          executive_summary: 'Enter only with a defined stop.',
          investment_thesis: 'The analyst evidence supports a measured long.',
          confidence_score: 0.72,
          entry_price: 180,
          stop_loss: 165,
          take_profit_price: 210,
          position_size_pct: 12.5,
          suggested_capital: 2500,
        },
      },
    })

    renderWithQuery(<SharedReport />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Portfolio Manager Recommendation' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Legacy Trader Proposal' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Legacy Trade Proposal Details' })).not.toBeInTheDocument()

    expect(screen.getByTestId('shared-portfolio-decision')).toHaveTextContent('Enter only with a defined stop.')
    expect(screen.getByTestId('shared-portfolio-decision')).toHaveTextContent('$2,500.00')
    expect(screen.getByTestId('shared-portfolio-decision')).toHaveTextContent('12.5%')
  })
})

describe('formatSharedReportValue', () => {
  it('formats persisted JSON history without object-object output', () => {
    expect(formatSharedReportValue([{ sender: 'Aggressive Analyst', content: 'Use a tight stop' }]))
      .toBe('Aggressive Analyst: Use a tight stop')
    expect(formatSharedReportValue('{}')).toBe('')
  })
})

describe('shared report section registry', () => {
  it('renders exactly the sections marked shareable, in registry order', () => {
    // The share page used to hold its own copy of this list. Pinning the derived
    // list keeps a registry edit from silently adding or dropping a section from
    // a public link.
    const shareable = REPORT_SECTIONS.filter(section => section.shareable).map(s => s.key)

    expect(shareable.slice(0, 6)).toEqual([
      'portfolio_decision', 'final_decision', 'investment_plan',
      'trader_plan', 'judge_decision', 'trader_proposal_json',
    ])
    expect(shareable.at(-1)).toBe('risk_metrics')
    expect(shareable).toHaveLength(28)
  })

  it('gives every shareable section a label key and a category', () => {
    for (const section of REPORT_SECTIONS.filter(s => s.shareable)) {
      expect(section.labelKey).toBeTruthy()
      expect(['decision', 'analyst', 'research']).toContain(section.category)
    }
  })
})
