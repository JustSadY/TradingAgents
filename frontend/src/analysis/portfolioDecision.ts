import { isRecord } from '../utils/isRecord'
import { isFiniteNumeric } from './orderResult'

/**
 * The Portfolio Manager's decision, read from whichever field a given run
 * happened to persist it in.
 *
 * The Portfolio Manager is the only agent with final decision authority, so
 * there is exactly one decision to show — but where it lives on the row has
 * changed over time. New runs persist the controller-accepted canonical
 * decision directly; the chart annotation is a backwards-compatible fallback
 * for older rows; and the Trader JSON is read only for historical legacy
 * analyses, which is why it is the last resort and labelled as such.
 */

export type PortfolioDecisionPreview = {
  source: 'portfolio_manager' | 'legacy_trader'
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

/** Descend through decision wrappers until the decision itself is reached. */
export function unwrapCanonicalPortfolioDecision(value: unknown): Record<string, unknown> | null {
  const record = objectFromJson(value)
  if (!record) return null
  if (typeof record.rating === 'string' || typeof record.action === 'string') return record
  const nested = objectFromJson(record.decision) ?? objectFromJson(record.accepted_decision)
  return nested ? unwrapCanonicalPortfolioDecision(nested) : null
}

/** True once the preview carries at least one value worth rendering. */
function hasAnyValue(preview: PortfolioDecisionPreview): boolean {
  return Object.entries(preview).some(([key, value]) => key !== 'source' && value !== undefined)
}

export function readPortfolioDecision(
  acceptedPortfolioDecision?: unknown,
  chartAnnotations?: unknown,
  legacyTraderJson?: string | null,
  streamedPortfolioDecision?: unknown,
): PortfolioDecisionPreview | null {
  const annotations = objectFromJson(chartAnnotations)
  const decision = unwrapCanonicalPortfolioDecision(
    acceptedPortfolioDecision ?? annotations?.portfolio_decision ?? annotations?.portfolio_decision_json ?? streamedPortfolioDecision,
  )
  if (decision) {
    const rating = typeof decision.rating === 'string' && decision.rating.trim() ? decision.rating.trim() : undefined
    const preview: PortfolioDecisionPreview = {
      source: 'portfolio_manager',
      rating,
      confidenceScore: decisionNumber(decision.confidence_score),
      entryPrice: decisionNumber(decision.entry_price),
      stopLoss: decisionNumber(decision.stop_loss),
      takeProfit: decisionNumber(decision.take_profit_price ?? decision.take_profit),
      positionSizePct: decisionNumber(decision.position_size_pct),
      suggestedCapital: decisionNumber(decision.suggested_capital),
      recommendedLeverage: decisionNumber(decision.recommended_leverage),
    }
    if (hasAnyValue(preview)) return preview
  }

  const legacy = objectFromJson(legacyTraderJson)
  if (!legacy) return null
  const kellySize = decisionNumber(legacy.kelly_size)
  const preview: PortfolioDecisionPreview = {
    source: 'legacy_trader',
    rating: typeof legacy.action === 'string' && legacy.action.trim() ? legacy.action.trim() : undefined,
    confidenceScore: decisionNumber(legacy.confidence_score),
    entryPrice: decisionNumber(legacy.entry_price),
    stopLoss: decisionNumber(legacy.stop_loss),
    takeProfit: decisionNumber(legacy.take_profit_price ?? legacy.take_profit),
    // Kelly is a fraction on old rows and a percentage on newer ones.
    positionSizePct: kellySize === undefined ? decisionNumber(legacy.position_size_pct) : (kellySize <= 1 ? kellySize * 100 : kellySize),
    suggestedCapital: decisionNumber(legacy.suggested_capital),
    recommendedLeverage: decisionNumber(legacy.recommended_leverage),
  }
  return hasAnyValue(preview) ? preview : null
}
