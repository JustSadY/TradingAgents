import { describe, expect, it } from 'vitest'
import { readPortfolioDecision, unwrapCanonicalPortfolioDecision } from '../portfolioDecision'

describe('unwrapCanonicalPortfolioDecision', () => {
  it('accepts a decision that is still a JSON string', () => {
    expect(unwrapCanonicalPortfolioDecision('{"rating":"Buy"}')).toEqual({ rating: 'Buy' })
  })

  it('descends through the decision wrapper', () => {
    expect(unwrapCanonicalPortfolioDecision({ decision: { rating: 'Hold' } })).toEqual({ rating: 'Hold' })
  })

  it('descends through the accepted_decision wrapper', () => {
    expect(unwrapCanonicalPortfolioDecision({ accepted_decision: { action: 'SELL' } })).toEqual({ action: 'SELL' })
  })

  it('descends more than one level', () => {
    expect(unwrapCanonicalPortfolioDecision({ decision: { accepted_decision: { rating: 'Buy' } } }))
      .toEqual({ rating: 'Buy' })
  })

  it.each([null, 'not json', '', {}, { decision: 'nothing useful' }])('gives up on %s', value => {
    expect(unwrapCanonicalPortfolioDecision(value)).toBeNull()
  })
})

describe('readPortfolioDecision', () => {
  it('prefers the accepted canonical decision that new runs persist', () => {
    const decision = readPortfolioDecision(
      { rating: 'Buy', entry_price: 100 },
      { portfolio_decision: { rating: 'Sell', entry_price: 1 } },
      JSON.stringify({ action: 'HOLD' }),
    )

    expect(decision).toMatchObject({ source: 'portfolio_manager', rating: 'Buy', entryPrice: 100 })
  })

  it('falls back to the chart annotation for older rows', () => {
    const decision = readPortfolioDecision(
      undefined,
      { portfolio_decision: { rating: 'Sell', stop_loss: 90 } },
    )

    expect(decision).toMatchObject({ source: 'portfolio_manager', rating: 'Sell', stopLoss: 90 })
  })

  it('accepts the portfolio_decision_json spelling of the annotation', () => {
    const decision = readPortfolioDecision(undefined, { portfolio_decision_json: { rating: 'Buy' } })
    expect(decision?.rating).toBe('Buy')
  })

  it('uses the streamed decision while a run is still in progress', () => {
    const decision = readPortfolioDecision(undefined, undefined, null, { rating: 'Overweight', take_profit: 150 })
    expect(decision).toMatchObject({ source: 'portfolio_manager', rating: 'Overweight', takeProfit: 150 })
  })

  it('reads take_profit_price ahead of take_profit', () => {
    const decision = readPortfolioDecision({ rating: 'Buy', take_profit_price: 120, take_profit: 110 })
    expect(decision?.takeProfit).toBe(120)
  })

  it('marks a legacy trader payload as such so the UI can say so', () => {
    const decision = readPortfolioDecision(undefined, undefined, JSON.stringify({ action: 'BUY', entry_price: 50 }))
    expect(decision).toMatchObject({ source: 'legacy_trader', rating: 'BUY', entryPrice: 50 })
  })

  it('reads a legacy Kelly fraction as a percentage', () => {
    const decision = readPortfolioDecision(undefined, undefined, JSON.stringify({ action: 'BUY', kelly_size: 0.25 }))
    expect(decision?.positionSizePct).toBe(25)
  })

  it('leaves a legacy Kelly value that is already a percentage alone', () => {
    const decision = readPortfolioDecision(undefined, undefined, JSON.stringify({ action: 'BUY', kelly_size: 25 }))
    expect(decision?.positionSizePct).toBe(25)
  })

  it('falls through to the legacy payload when the canonical one carries no values', () => {
    const decision = readPortfolioDecision(
      { rating: '   ' },
      undefined,
      JSON.stringify({ action: 'SELL', stop_loss: 10 }),
    )

    expect(decision).toMatchObject({ source: 'legacy_trader', rating: 'SELL' })
  })

  it('returns nothing when no source carries a decision', () => {
    expect(readPortfolioDecision(undefined, undefined, null, undefined)).toBeNull()
  })

  it('rejects a decision whose numbers are all unusable', () => {
    // A card with a heading and no values is worse than no card.
    expect(readPortfolioDecision({ rating: '', entry_price: 'not a number', stop_loss: Number.NaN })).toBeNull()
  })
})
