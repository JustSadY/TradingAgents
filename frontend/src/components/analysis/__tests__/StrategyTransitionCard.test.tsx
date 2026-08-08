import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StrategyTransitionCard } from '../StrategyTransitionCard'

vi.mock('../../../contexts/LanguageContext', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'analysis.strategy.title': 'Strategy Continuity',
      'analysis.strategy.subtitle': 'Neutral research plan, persistent thesis, and controller-approved decision.',
      'analysis.strategy.subtitle_counterfactual': 'The PM decision remains canonical.',
      'analysis.strategy.analysis_plan': 'Investigation Plan',
      'analysis.strategy.before': 'Strategy Before',
      'analysis.strategy.after': 'Strategy After',
      'analysis.strategy.version': 'Version',
      'analysis.strategy.bias': 'Bias',
      'analysis.strategy.conviction': 'Conviction',
      'analysis.strategy.rating': 'Rating',
      'analysis.strategy.status': 'Status',
      'analysis.strategy.revision': 'Revision',
      'analysis.strategy.change_strength': 'Change Strength',
      'analysis.strategy.pm_proposal': 'PM Proposal',
      'analysis.strategy.pm_canonical_decision': 'PM Canonical Decision',
      'analysis.strategy.accepted_decision': 'Accepted Decision',
      'analysis.strategy.controller': 'Stability Controller',
      'analysis.strategy.counterfactual': 'Counterfactual',
      'analysis.strategy.counterfactual_hint': 'The physical portfolio decision remains the PM canonical output.',
      'analysis.strategy.confidence': 'Calibrated Confidence',
      'analysis.strategy.allocation': 'Allocation',
      'analysis.strategy.execution': 'Execution',
      'analysis.strategy.tactical': 'Tactical Action',
      'analysis.strategy.no_order': 'No new order: the accepted tactical state is hold/freeze.',
      'analysis.strategy.counterfactual_no_order': 'Controller counterfactual: it would issue no new order; the PM canonical decision remains unchanged.',
      'analysis.strategy.none': 'No strategy state recorded for this run.',
    }[key] || key),
  }),
}))

describe('StrategyTransitionCard', () => {
  it('does not render for analyses that predate strategy continuity', () => {
    const { container } = render(<StrategyTransitionCard />)
    expect(container.innerHTML).toBe('')
  })

  it('shows the neutral plan, strategy transition, and blocked no-order decision', () => {
    render(
      <StrategyTransitionCard
        analysisPlan={{
          objective: 'Re-test demand and margin assumptions.',
          horizon: '3-6 months',
          unresolved_questions: ['Has guidance deteriorated?'],
          analyst_questions: { fundamentals: ['Is margin deterioration structural?'] },
        }}
        strategyBefore={{
          version: 7,
          strategic_bias: 'BULLISH',
          conviction: 0.73,
          accepted_rating: 'Overweight',
          status: 'ACTIVE',
        }}
        strategyAfter={{
          version: 8,
          strategic_bias: 'BULLISH',
          conviction: 0.64,
          accepted_rating: 'Overweight',
          status: 'ACTIVE',
        }}
        strategyCandidate={{
          revision_action: 'WEAKEN',
          change_strength: 'MATERIAL',
          revision_reason: 'Valuation risk rose while the core thesis remains intact.',
        }}
        pmProposal={{ proposed_decision: { rating: 'Sell', confidence_score: 0.89, position_size_pct: 12 } }}
        acceptedDecision={{ rating: 'Hold', confidence_score: 0.67 }}
        transition={{
          outcome: 'BLOCKED_CHANGE',
          reason_codes: ['reversal_invalidation_missing', 'independent_evidence_missing'],
          accepted_decision: { execution_action: 'NO_NEW_ORDER', tactical_action: 'HOLD', decision: { rating: 'Hold' } },
        }}
        calibratedConfidence={0.67}
        strategyUpdateStatus="updated"
      />,
    )

    expect(screen.getByTestId('strategy-transition-card')).toBeInTheDocument()
    expect(screen.getByText('Re-test demand and margin assumptions.')).toBeInTheDocument()
    expect(screen.getByText('Has guidance deteriorated?')).toBeInTheDocument()
    expect(screen.getByText('v7')).toBeInTheDocument()
    expect(screen.getByText('v8')).toBeInTheDocument()
    expect(screen.getAllByText('WEAKEN')).toHaveLength(2)
    expect(screen.getAllByText('Sell')).toHaveLength(2)
    expect(screen.getAllByText('Hold')).toHaveLength(2)
    expect(screen.getByTestId('strategy-controller-outcome')).toHaveTextContent('BLOCKED CHANGE')
    expect(screen.getByTestId('strategy-no-order')).toHaveTextContent('No new order')
    expect(screen.getByText('reversal invalidation missing')).toBeInTheDocument()
    expect(screen.getByText('independent evidence missing')).toBeInTheDocument()
  })

  it('labels a shadow controller result as counterfactual while retaining the physical PM decision', () => {
    render(
      <StrategyTransitionCard
        pmProposal={{ proposed_decision: { rating: 'Buy', confidence_score: 0.89, position_size_pct: 10 } }}
        acceptedDecision={{ rating: 'Buy', confidence_score: 0.89, position_size_pct: 10 }}
        transition={{
          mode: 'shadow',
          canonical_enforced: false,
          outcome: 'BLOCKED_CHANGE',
          accepted_decision: {
            execution_action: 'NO_NEW_ORDER',
            tactical_action: 'HOLD',
            decision: { rating: 'Hold', confidence_score: 0.67 },
          },
        }}
        calibratedConfidence={0.67}
      />,
    )

    expect(screen.getByTestId('strategy-controller-counterfactual')).toHaveTextContent('shadow · Counterfactual')
    expect(screen.getByText('PM Canonical Decision')).toBeInTheDocument()
    expect(screen.queryByText('Accepted Decision')).not.toBeInTheDocument()
    expect(screen.getByTestId('strategy-counterfactual-note')).toHaveTextContent('physical portfolio decision remains')
    expect(screen.getByTestId('strategy-no-order')).toHaveTextContent('would issue no new order')
  })
})
