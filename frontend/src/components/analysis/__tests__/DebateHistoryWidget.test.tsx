import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DebateHistoryWidget, parseDebateMessage, getSenderStyles } from '../DebateHistoryWidget'

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (k: string) => {
    const map: Record<string, string> = {
      'analysis.section.risk_debate_history': 'Risk Debate',
      'analysis.reports.empty': 'No debate messages yet.',
    }
    return map[k] || k
  }}),
}))

describe('parseDebateMessage', () => {
  it('parses sender: content format', () => {
    const result = parseDebateMessage('Bull Analyst: The stock looks strong.')
    expect(result.sender).toBe('Bull Analyst')
    expect(result.content).toBe('The stock looks strong.')
  })

  it('falls back to System for messages without colon', () => {
    const result = parseDebateMessage('Plain message without colon')
    expect(result.sender).toBe('System')
    expect(result.content).toBe('Plain message without colon')
  })

  it('handles multiple colons', () => {
    const result = parseDebateMessage('Bear Analyst: Price: $150, Target: $145')
    expect(result.sender).toBe('Bear Analyst')
    expect(result.content).toBe('Price: $150, Target: $145')
  })
})

describe('getSenderStyles', () => {
  it('returns bull styles for Bull Analyst', () => {
    const styles = getSenderStyles('Bull Analyst')
    expect(styles.side).toBe('justify-start')
  })

  it('returns bear styles for Bear Analyst', () => {
    const styles = getSenderStyles('Bear Analyst')
    expect(styles.side).toBe('justify-end')
  })

  it('returns default styles for unknown sender', () => {
    const styles = getSenderStyles('Unknown')
    expect(styles.side).toBe('justify-center mx-auto')
  })
})

describe('DebateHistoryWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders tab headers', () => {
    render(<DebateHistoryWidget investmentHistory={null} riskHistory={null} />)
    expect(screen.getByText('Consensus Debate')).toBeInTheDocument()
    expect(screen.getByText('Risk Debate')).toBeInTheDocument()
  })

  it('shows empty state when no messages', () => {
    render(<DebateHistoryWidget investmentHistory={null} riskHistory={null} />)
    expect(screen.getByText('No debate messages yet.')).toBeInTheDocument()
  })

  it('renders investment debate messages', () => {
    const history = 'Bull Analyst: Strong buy signal\nBear Analyst: Overvalued at current price'
    render(<DebateHistoryWidget investmentHistory={history} riskHistory={null} />)
    expect(screen.getByText('Strong buy signal')).toBeInTheDocument()
    expect(screen.getByText('Overvalued at current price')).toBeInTheDocument()
  })

  it('switches to risk debate tab', () => {
    const riskHistory = 'Aggressive Analyst: High risk tolerance\nConservative Analyst: Reduce position'
    render(<DebateHistoryWidget investmentHistory={null} riskHistory={riskHistory} />)
    fireEvent.click(screen.getByText('Risk Debate'))
    expect(screen.getByText('High risk tolerance')).toBeInTheDocument()
    expect(screen.getByText('Reduce position')).toBeInTheDocument()
  })

  it('parses JSON array history', () => {
    const history = JSON.stringify(['Bull Analyst: Price target met', 'Bear Analyst: Resistance at $200'])
    render(<DebateHistoryWidget investmentHistory={history} riskHistory={null} />)
    expect(screen.getByText('Price target met')).toBeInTheDocument()
  })

  it('parses array of objects history', () => {
    const history = ['Bull Analyst: New high confirmed', 'Bear Analyst: Watch for reversal']
    render(<DebateHistoryWidget investmentHistory={history} riskHistory={null} />)
    expect(screen.getByText('New high confirmed')).toBeInTheDocument()
    expect(screen.getByText('Watch for reversal')).toBeInTheDocument()
  })
})
