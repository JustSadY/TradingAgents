import { isRecord } from '../utils/isRecord'
import { isFiniteNumeric } from './orderResult'

export type PortfolioDecisionPreview = {
  rating?: string
  confidenceScore?: number
  entryPrice?: number
  stopLoss?: number
  takeProfit?: number
  positionSizePct?: number
  suggestedCapital?: number
  recommendedLeverage?: number
}

/** Accept a decision that is already an object or still a JSON string. */
export function objectFromJson(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) return value
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const parsed: unknown = JSON.parse(value)
    return isRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

function decisionNumber(value: unknown): number | undefined {
  return isFiniteNumeric(value) ? value : undefined
}

/** Descend through decision wrappers until the accepted decision is reached. */
export function unwrapCanonicalPortfolioDecision(value: unknown): Record<string, unknown> | null {
  const record = objectFromJson(value)
  if (!record) return null
  if (typeof record.rating === 'string' || typeof record.action === 'string') return record
  const nested = objectFromJson(record.decision) ?? objectFromJson(record.accepted_decision)
  return nested ? unwrapCanonicalPortfolioDecision(nested) : null
}

function hasAnyValue(preview: PortfolioDecisionPreview): boolean {
  return Object.values(preview).some(value => value !== undefined)
}

export function readPortfolioDecision(
  acceptedPortfolioDecision?: unknown,
  chartAnnotations?: unknown,
  streamedPortfolioDecision?: unknown,
): PortfolioDecisionPreview | null {
  const annotations = objectFromJson(chartAnnotations)
  const decision = unwrapCanonicalPortfolioDecision(
    acceptedPortfolioDecision ?? annotations?.portfolio_decision ?? annotations?.portfolio_decision_json ?? streamedPortfolioDecision,
  )
  if (!decision) return null

  const rating = typeof decision.rating === 'string' && decision.rating.trim() ? decision.rating.trim() : undefined
  const preview: PortfolioDecisionPreview = {
    rating,
    confidenceScore: decisionNumber(decision.confidence_score),
    entryPrice: decisionNumber(decision.entry_price),
    stopLoss: decisionNumber(decision.stop_loss),
    takeProfit: decisionNumber(decision.take_profit_price ?? decision.take_profit),
    positionSizePct: decisionNumber(decision.position_size_pct),
    suggestedCapital: decisionNumber(decision.suggested_capital),
    recommendedLeverage: decisionNumber(decision.recommended_leverage),
  }
  return hasAnyValue(preview) ? preview : null
}
