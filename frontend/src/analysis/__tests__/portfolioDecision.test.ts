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
    expect(unwrapCanonicalPortfolioDecision({ accepted_decision: { rating: 'Sell' } })).toEqual({ rating: 'Sell' })
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
      { rating: 'Hold' },
    )
    expect(decision).toMatchObject({ rating: 'Buy', entryPrice: 100 })
  })

  it('falls back to the historical chart annotation for pre-migration canonical rows', () => {
    const decision = readPortfolioDecision(undefined, { portfolio_decision: { rating: 'Sell', stop_loss: 90 } })
    expect(decision).toMatchObject({ rating: 'Sell', stopLoss: 90 })
  })

  it('accepts the portfolio_decision_json spelling of the annotation', () => {
    const decision = readPortfolioDecision(undefined, { portfolio_decision_json: { rating: 'Buy' } })
    expect(decision?.rating).toBe('Buy')
  })

  it('uses the streamed decision while a run is still in progress', () => {
    const decision = readPortfolioDecision(undefined, undefined, { rating: 'Overweight', take_profit: 150 })
    expect(decision).toMatchObject({ rating: 'Overweight', takeProfit: 150 })
  })

  it('reads take_profit_price ahead of take_profit', () => {
    const decision = readPortfolioDecision({ rating: 'Buy', take_profit_price: 120, take_profit: 110 })
    expect(decision?.takeProfit).toBe(120)
  })

  it('returns nothing when no canonical source carries a decision', () => {
    expect(readPortfolioDecision(undefined, undefined, undefined)).toBeNull()
  })

  it('rejects a decision whose numbers are all unusable', () => {
    expect(readPortfolioDecision({ rating: '', entry_price: 'not a number', stop_loss: Number.NaN })).toBeNull()
  })
})
