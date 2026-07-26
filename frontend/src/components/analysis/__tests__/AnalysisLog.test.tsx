import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AnalysisLog } from '../AnalysisLog'

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const t = (k: string) => {
  const map: Record<string, string> = {
    'analysis.tabs.progress': 'Progress',
    'analysis.tabs.live_debate': 'Live Debate',
    'analysis.log.empty': 'Waiting for progress logs...',
    'analysis.debate.waiting': 'Waiting for debate messages...',
    'analysis.debate.typing': 'typing...',
  }
  return map[k] || k
}

describe('AnalysisLog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tab headers', () => {
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={vi.fn()}
        log={[]}
        liveDebate={[]}
        t={t}
      />
    )
    expect(screen.getByText('Progress')).toBeInTheDocument()
    expect(screen.getByText('Live Debate')).toBeInTheDocument()
  })

  it('shows log messages', () => {
    const log = ['Progress: Starting analysis...', 'Completed: Market Intelligence', 'Progress: Running research...']
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={vi.fn()}
        log={log}
        liveDebate={[]}
        t={t}
      />
    )
    expect(screen.getByText(/Starting analysis/)).toBeInTheDocument()
    expect(screen.getByText(/Completed: Market Intelligence/)).toBeInTheDocument()
    expect(screen.getByText(/Running research/)).toBeInTheDocument()
  })

  it('shows empty log state when log is empty', () => {
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={vi.fn()}
        log={[]}
        liveDebate={[]}
        t={t}
      />
    )
    expect(screen.getByText('Waiting for progress logs...')).toBeInTheDocument()
  })

  it('applies color classes based on log line prefixes', () => {
    const log = ['Completed: Done', 'Error: Failed', 'Progress: Running', 'Other message']
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={vi.fn()}
        log={log}
        liveDebate={[]}
        currentStep={null}
        t={t}
      />
    )
    expect(screen.getByText(/Completed: Done/)).toBeInTheDocument()
    expect(screen.getByText(/Error: Failed/)).toBeInTheDocument()
    expect(screen.getByText(/Progress: Running/)).toBeInTheDocument()
    expect(screen.getByText(/Other message/)).toBeInTheDocument()
  })

  it('shows live debate tab content when active', () => {
    const liveDebate = [
      { sender: 'Bull Analyst', content: 'I see upside potential.' },
      { sender: 'Bear Analyst', content: 'Resistance is too strong.' },
    ]
    render(
      <AnalysisLog
        leftTab="debate"
        setLeftTab={vi.fn()}
        log={[]}
        liveDebate={liveDebate}
        t={t}
      />
    )
    expect(screen.getByText('I see upside potential.')).toBeInTheDocument()
    expect(screen.getByText('Resistance is too strong.')).toBeInTheDocument()
  })

  it('switches tabs when clicked', () => {
    const setLeftTab = vi.fn()
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={setLeftTab}
        log={[]}
        liveDebate={[]}
        t={t}
      />
    )
    fireEvent.click(screen.getByText('Live Debate'))
    expect(setLeftTab).toHaveBeenCalledWith('debate')
  })

  it('shows stats bar when stats are provided', () => {
    const stats = { llmCalls: 12, tokensIn: 5000, tokensOut: 3000 }
    render(
      <AnalysisLog
        leftTab="log"
        setLeftTab={vi.fn()}
        log={[]}
        liveDebate={[]}
        stats={stats}
        t={t}
      />
    )
    expect(screen.getByText(/LLM Calls/)).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })
})
