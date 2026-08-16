import { isRecord } from '../utils/isRecord'

/**
 * The automated-order outcome, read off the analysis event stream.
 *
 * Analysis completion and order execution are deliberately distinct states: a
 * final model signal is a recommendation, and only the separately guarded
 * execution layer decides whether an order was actually placed. This module
 * is the boundary where that event becomes something the UI can render.
 */

export type OrderOutcome = 'filled' | 'skipped' | 'rejected' | 'error'

export type AnalysisOrderResult = {
  outcome: OrderOutcome
  action?: 'BUY' | 'SELL'
  ticker: string
  quantity?: number
  price?: number
  reason?: string
  message?: string
  analysisId?: number
}

export function isFiniteNumeric(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

export function normalizedOrderOutcome(value: unknown): OrderOutcome | null {
  if (typeof value !== 'string') return null
  switch (value.trim().toLowerCase()) {
    case 'filled':
    case 'executed':
    case 'success':
      return 'filled'
    case 'skipped':
    case 'no_trade':
    case 'no-trade':
      return 'skipped'
    case 'rejected':
    case 'blocked':
    case 'denied':
      return 'rejected'
    case 'error':
    case 'failed':
      return 'error'
    default:
      return null
  }
}

/**
 * Normalise the execution event at the UI boundary.  The execution service
 * intentionally emits a small, transport-safe payload, but old workers used
 * `status` rather than `outcome`; accepting both makes reconnect/replay and
 * rolling deployment harmless without treating arbitrary payloads as fills.
 */
export function readOrderResult(value: unknown, fallbackTicker: string): AnalysisOrderResult | null {
  if (!isRecord(value)) return null
  const outcome = normalizedOrderOutcome(value.outcome ?? value.status)
  if (!outcome) return null

  const rawAction = typeof value.action === 'string' ? value.action.trim().toUpperCase() : ''
  const action = rawAction === 'BUY' || rawAction === 'SELL' ? rawAction : undefined
  const rawTicker = typeof value.ticker === 'string' ? value.ticker.trim().toUpperCase() : ''
  const ticker = rawTicker || fallbackTicker.trim().toUpperCase()
  if (!ticker) return null

  return {
    outcome,
    action,
    ticker,
    quantity: isFiniteNumeric(value.quantity) && value.quantity > 0
      ? value.quantity
      : isFiniteNumeric(value.filled_quantity) && value.filled_quantity > 0
        ? value.filled_quantity
        : undefined,
    price: isFiniteNumeric(value.price) && value.price >= 0
      ? value.price
      : isFiniteNumeric(value.filled_price) && value.filled_price >= 0
        ? value.filled_price
        : undefined,
    reason: typeof value.reason === 'string' && value.reason.trim()
      ? value.reason.trim()
      : typeof value.reason_code === 'string' && value.reason_code.trim()
        ? value.reason_code.trim()
        : undefined,
    message: typeof value.message === 'string' && value.message.trim() ? value.message.trim() : undefined,
    analysisId: isFiniteNumeric(value.analysis_id) && value.analysis_id > 0 ? value.analysis_id : undefined,
  }
}

/** Whether a newly read result says the same thing as the one already shown. */
export function sameOrderResult(left: AnalysisOrderResult | null, right: AnalysisOrderResult): boolean {
  return !!left && left.outcome === right.outcome && left.action === right.action &&
    left.ticker === right.ticker && left.quantity === right.quantity && left.price === right.price &&
    left.reason === right.reason && left.message === right.message && left.analysisId === right.analysisId
}

export function orderActionLabel(action: AnalysisOrderResult['action'], t: (key: string) => string): string | null {
  if (!action) return null
  return t(action === 'BUY' ? 'analysis.order.action.buy' : 'analysis.order.action.sell')
}

export function orderResultLogLine(result: AnalysisOrderResult, t: (key: string) => string): string {
  const marker = result.outcome === 'filled' ? '✓' : result.outcome === 'skipped' ? '⚠' : '❌'
  const details = [
    orderActionLabel(result.action, t),
    result.quantity !== undefined ? String(result.quantity) : null,
    result.ticker,
    result.price !== undefined ? `@ $${result.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : null,
  ].filter((part): part is string => !!part)
  const reason = result.message ?? result.reason
  return [
    `${marker} ${t('analysis.order.log_prefix')}`,
    t(`analysis.order.outcome.${result.outcome}`),
    details.join(' '),
    reason,
  ].filter((part): part is string => !!part).join(' — ')
}
