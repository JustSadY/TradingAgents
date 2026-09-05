import { describe, expect, it } from 'vitest'
import {
  normalizedOrderOutcome,
  orderResultLogLine,
  readOrderResult,
  sameOrderResult,
  type AnalysisOrderResult,
} from '../orderResult'

const t = (key: string) => key

describe('normalizedOrderOutcome', () => {
  it.each([
    ['filled', 'filled'],
    ['executed', 'filled'],
    ['success', 'filled'],
    ['partially_filled', 'partially_filled'],
    ['partially-filled', 'partially_filled'],
    ['partially filled', 'partially_filled'],
    ['skipped', 'skipped'],
    ['no_trade', 'skipped'],
    ['no-trade', 'skipped'],
    ['rejected', 'rejected'],
    ['blocked', 'rejected'],
    ['denied', 'rejected'],
    ['reconciliation_required', 'reconciliation_required'],
    ['reconciliation-required', 'reconciliation_required'],
    ['reconciliation required', 'reconciliation_required'],
    ['error', 'error'],
    ['failed', 'error'],
    ['  FILLED  ', 'filled'],
  ])('reads %s as %s', (raw, expected) => {
    expect(normalizedOrderOutcome(raw)).toBe(expected)
  })

  it.each(['pending', '', 7, null, undefined])('refuses %s', value => {
    expect(normalizedOrderOutcome(value)).toBeNull()
  })
})

describe('readOrderResult', () => {
  it('reads the current outcome field', () => {
    expect(readOrderResult({ outcome: 'filled', action: 'buy', ticker: 'nvda', quantity: 3, price: 10 }, '')).toEqual({
      outcome: 'filled',
      action: 'BUY',
      ticker: 'NVDA',
      quantity: 3,
      price: 10,
      orderId: undefined,
      reason: undefined,
      message: undefined,
      analysisId: undefined,
    })
  })

  it('accepts the legacy status field, so a rolling deploy is harmless', () => {
    expect(readOrderResult({ status: 'no_trade', ticker: 'AAPL' }, '')?.outcome).toBe('skipped')
  })

  it('upgrades an older rejected outcome when broker status requires reconciliation', () => {
    const result = readOrderResult({
      outcome: 'rejected',
      broker_status: 'RECONCILIATION_REQUIRED',
      order_id: 'alpaca-reconcile-42',
      ticker: 'NVDA',
      reason_code: 'broker_submission_uncertain',
      message: 'Reconcile the broker account before retrying.',
    }, '')

    expect(result?.outcome).toBe('reconciliation_required')
    expect(result?.orderId).toBe('alpaca-reconcile-42')
    expect(result?.reason).toBe('broker_submission_uncertain')
    expect(result?.message).toBe('Reconcile the broker account before retrying.')
  })

  it('upgrades a terminal broker cancellation when some quantity already filled', () => {
    const result = readOrderResult({
      outcome: 'rejected',
      broker_status: 'CANCELED',
      ticker: 'NVDA',
      filled_quantity: 2,
      filled_price: 100,
    }, '')

    expect(result?.outcome).toBe('partially_filled')
    expect(result?.quantity).toBe(2)
    expect(result?.price).toBe(100)
  })

  it('keeps a zero-fill broker cancellation rejected', () => {
    const result = readOrderResult({
      outcome: 'rejected',
      broker_status: 'CANCELED',
      ticker: 'NVDA',
      filled_quantity: 0,
    }, '')

    expect(result?.outcome).toBe('rejected')
    expect(result?.quantity).toBeUndefined()
  })

  it('falls back to the filled_* fields when the plain ones are absent', () => {
    const result = readOrderResult({ outcome: 'filled', ticker: 'AAPL', filled_quantity: 5, filled_price: 99.5 }, '')
    expect(result?.quantity).toBe(5)
    expect(result?.price).toBe(99.5)
  })

  it('drops an empty broker order id instead of rendering a blank identifier', () => {
    expect(readOrderResult({ outcome: 'filled', ticker: 'AAPL', order_id: '   ' }, '')?.orderId).toBeUndefined()
  })

  it('falls back to the run ticker when the event omits one', () => {
    expect(readOrderResult({ outcome: 'filled' }, ' nvda ')?.ticker).toBe('NVDA')
  })

  it('refuses a result with no ticker at all, which would render as a blank order', () => {
    expect(readOrderResult({ outcome: 'filled' }, '   ')).toBeNull()
  })

  it('prefers a human reason over the machine reason code', () => {
    const result = readOrderResult({ outcome: 'rejected', ticker: 'A', reason: 'Cash too low', reason_code: 'CASH' }, '')
    expect(result?.reason).toBe('Cash too low')
  })

  it('uses the reason code when there is no prose reason', () => {
    expect(readOrderResult({ outcome: 'rejected', ticker: 'A', reason_code: 'CASH' }, '')?.reason).toBe('CASH')
  })

  it.each([
    ['a zero quantity', { quantity: 0 }, 'quantity'],
    ['a negative quantity', { quantity: -1 }, 'quantity'],
    ['a negative price', { price: -1 }, 'price'],
    ['a non-finite quantity', { quantity: Number.NaN }, 'quantity'],
  ])('drops %s rather than showing it', (_label, extra, field) => {
    const result = readOrderResult({ outcome: 'filled', ticker: 'A', ...extra }, '')
    expect(result?.[field as 'quantity' | 'price']).toBeUndefined()
  })

  it('keeps a zero price, which is a real fill value', () => {
    expect(readOrderResult({ outcome: 'filled', ticker: 'A', price: 0 }, '')?.price).toBe(0)
  })

  it('ignores an unusable action instead of guessing a direction', () => {
    expect(readOrderResult({ outcome: 'filled', ticker: 'A', action: 'HOLD' }, '')?.action).toBeUndefined()
  })

  it.each([null, 'string', [1], { outcome: 'pending', ticker: 'A' }])('returns null for %s', value => {
    expect(readOrderResult(value, 'A')).toBeNull()
  })
})

describe('sameOrderResult', () => {
  const base: AnalysisOrderResult = {
    outcome: 'filled',
    action: 'BUY',
    ticker: 'NVDA',
    quantity: 1,
    price: 2,
    orderId: 'broker-1',
  }

  it('treats an identical result as already shown', () => {
    expect(sameOrderResult({ ...base }, base)).toBe(true)
  })

  it('treats a missing previous result as different', () => {
    expect(sameOrderResult(null, base)).toBe(false)
  })

  it.each([
    ['outcome', { outcome: 'rejected' as const }],
    ['ticker', { ticker: 'AAPL' }],
    ['quantity', { quantity: 2 }],
    ['price', { price: 3 }],
    ['orderId', { orderId: 'broker-2' }],
  ])('notices a changed %s', (_field, change) => {
    expect(sameOrderResult({ ...base, ...change }, base)).toBe(false)
  })
})

describe('orderResultLogLine', () => {
  it('reads as one line with the marker, outcome, order and reason', () => {
    const line = orderResultLogLine(
      { outcome: 'filled', action: 'BUY', ticker: 'NVDA', quantity: 3, price: 1234.5 },
      t,
    )

    expect(line).toBe('✓ analysis.order.log_prefix — analysis.order.outcome.filled — analysis.order.action.buy 3 NVDA @ $1,234.50')
  })

  it('includes the broker order id when reconciliation needs it', () => {
    const line = orderResultLogLine(
      { outcome: 'reconciliation_required', ticker: 'NVDA', orderId: 'alpaca-42' },
      t,
    )

    expect(line).toContain('orders.col_broker_order_id: alpaca-42')
  })

  it.each([
    ['filled', '✓'],
    ['partially_filled', '⚠'],
    ['skipped', '⚠'],
    ['reconciliation_required', '⚠'],
    ['rejected', '❌'],
    ['error', '❌'],
  ] as const)('marks %s with %s', (outcome, marker) => {
    expect(orderResultLogLine({ outcome, ticker: 'A' }, t).startsWith(marker)).toBe(true)
  })

  it('prefers the message over the reason', () => {
    const line = orderResultLogLine({ outcome: 'rejected', ticker: 'A', reason: 'code', message: 'human' }, t)
    expect(line.endsWith('human')).toBe(true)
  })
})
