from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text)


path = "backend/services/trading_orchestrator.py"
text = read(path)
text, count = re.subn(
    r"\ndef _annotations\(row\) -> dict:.*?\n    return \{\}\n(?=\ndef _as_mapping)",
    "",
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("could not remove _annotations compatibility helper")
old = '''def _portfolio_decision(row) -> dict:
    """Return the controller-accepted structured decision when available.

    ``AnalysisResult.portfolio_decision_json`` is the physical canonical field
    and is intentionally checked before the legacy chart-annotation fallback.
    Raw ``pm_proposal_json`` and historical Trader fields are never execution
    fallbacks.
    """
    annotations = _annotations(row)
    for raw in (
        getattr(row, "portfolio_decision_json", None),
        annotations.get("portfolio_decision"),
        annotations.get("portfolio_decision_json"),
    ):
        decision = _as_mapping(raw)
        if decision:
            return decision
    return {}
'''
new = '''def _portfolio_decision(row) -> dict:
    """Return the controller-accepted canonical structured decision."""
    return _as_mapping(getattr(row, "portfolio_decision_json", None))
'''
if old not in text:
    raise RuntimeError("canonical portfolio decision block did not match")
text = text.replace(old, new, 1)
write(path, text)

path = "backend/api/share.py"
text = read(path)
text = text.replace(
    '    annotations = analysis.chart_annotations if isinstance(analysis.chart_annotations, dict) else {}\n\n',
    '',
)
old = '        "portfolio_decision": annotations.get("portfolio_decision"),\n'
if old not in text:
    raise RuntimeError("share API still lacks expected annotation mapping")
text = text.replace(old, '        "portfolio_decision": analysis.portfolio_decision_json,\n', 1)
write(path, text)

write(
    "frontend/src/analysis/portfolioDecision.ts",
    '''import { isRecord } from '../utils/isRecord'
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

/** Descend through canonical decision wrappers until the accepted decision is reached. */
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
  streamedPortfolioDecision?: unknown,
): PortfolioDecisionPreview | null {
  const decision = unwrapCanonicalPortfolioDecision(acceptedPortfolioDecision ?? streamedPortfolioDecision)
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
''',
)

path = "frontend/src/components/analysis/PortfolioDecisionCard.tsx"
text = read(path)
text = text.replace("  chartAnnotations,\n", "")
text = text.replace("  chartAnnotations?: unknown\n", "")
text = text.replace(
    "  const decision = readPortfolioDecision(acceptedPortfolioDecision, chartAnnotations, streamedPortfolioDecision)\n",
    "  const decision = readPortfolioDecision(acceptedPortfolioDecision, streamedPortfolioDecision)\n",
)
if "chartAnnotations" in text:
    raise RuntimeError("PortfolioDecisionCard still exposes chart annotation decision fallback")
write(path, text)

path = "frontend/src/pages/Analysis.tsx"
text = read(path)
text = text.replace("        const activeChartAnnotations = detail?.chart_annotations ?? reports.chart_annotations;\n", "")
text = text.replace(
    "        const activePortfolioDecision = readPortfolioDecision(\n"
    "          activeAcceptedPortfolioDecision,\n"
    "          activeChartAnnotations,\n"
    "          streamedPortfolioDecision,\n"
    "        );\n",
    "        const activePortfolioDecision = readPortfolioDecision(activeAcceptedPortfolioDecision, streamedPortfolioDecision);\n",
)
text = text.replace("                            chartAnnotations={activeChartAnnotations}\n", "")
if "activeChartAnnotations" in text:
    raise RuntimeError("Analysis page still routes decisions through chart annotations")
write(path, text)

path = "frontend/src/components/analysis/tabs/HistoryTab.tsx"
text = read(path)
text = text.replace("                        chartAnnotations={detail.chart_annotations}\n", "")
if "chartAnnotations=" in text:
    raise RuntimeError("HistoryTab still routes decisions through chart annotations")
write(path, text)

path = "frontend/src/analysis/__tests__/portfolioDecision.test.ts"
text = read(path)
text = text.replace(
    "      { rating: 'Buy', entry_price: 100 },\n"
    "      { portfolio_decision: { rating: 'Sell', entry_price: 1 } },\n"
    "      { rating: 'Hold' },\n",
    "      { rating: 'Buy', entry_price: 100 },\n"
    "      { rating: 'Hold' },\n",
)
text = re.sub(
    r"\n  it\('falls back to the historical chart annotation.*?\n  \}\)\n\n  it\('accepts the portfolio_decision_json spelling.*?\n  \}\)\n",
    "\n",
    text,
    count=1,
    flags=re.S,
)
text = text.replace(
    "    const decision = readPortfolioDecision(undefined, undefined, { rating: 'Overweight', take_profit: 150 })\n",
    "    const decision = readPortfolioDecision(undefined, { rating: 'Overweight', take_profit: 150 })\n",
)
text = text.replace("readPortfolioDecision(undefined, undefined, undefined)", "readPortfolioDecision(undefined, undefined)")
write(path, text)

print("canonical portfolio decision transform complete")
