from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text)


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {text.count(old)}")
    write(path, text.replace(old, new, 1))


def remove_matching_lines(path: str, needles: tuple[str, ...]) -> None:
    lines = read(path).splitlines(keepends=True)
    found = {needle: 0 for needle in needles}
    out: list[str] = []
    for line in lines:
        matched = False
        for needle in needles:
            if needle in line:
                found[needle] += 1
                matched = True
                break
        if not matched:
            out.append(line)
    missing = [needle for needle, count in found.items() if count == 0]
    if missing:
        raise RuntimeError(f"{path}: missing expected legacy lines: {missing}")
    write(path, "".join(out))


# Persistence/API: the Alembic revision already backfills missing final_decision
# before dropping these columns. Remove them from every current runtime schema.
remove_matching_lines(
    "backend/models/analysis.py",
    ("trader_plan: Mapped[str]", "trader_proposal_json: Mapped[str]"),
)
remove_matching_lines(
    "backend/schemas/analysis.py",
    ("trader_plan: str", "trader_proposal_json: str"),
)
remove_matching_lines(
    "backend/schemas/share.py",
    ("trader_plan: str | None", "trader_proposal_json: str | None"),
)

# Current metadata must stop advertising retired report sections.
remove_matching_lines(
    "backend/core/catalog.py",
    ('"trader_investment_plan"', '"trader_plan"'),
)

# Reviews learn only from the canonical persisted final decision after migration.
review_path = "backend/trading_agents/agents/data/review_tools.py"
review = read(review_path)
pattern = re.compile(r"def _past_decision_for_review\(analysis\) -> tuple\[str, str\]:.*?\n@tool\n", re.S)
replacement = '''def _past_decision_for_review(analysis) -> tuple[str, str]:
    """Return the prior run's canonical persisted final decision."""
    final_decision = str(getattr(analysis, "final_decision", "") or "").strip()
    if final_decision:
        return final_decision, "PAST CANONICAL FINAL DECISION"
    return "", ""

@tool
'''
review, count = pattern.subn(replacement, review, count=1)
if count != 1:
    raise RuntimeError(f"{review_path}: could not replace legacy past-decision fallback")
write(review_path, review)

# Time Travel no longer resets columns that no longer exist.
remove_matching_lines(
    "backend/services/analysis/orchestrator.py",
    ('"trader_plan": "",', '"trader_proposal_json": "{}",'),
)

# Shared/export report registry: remove retired intermediate sections.
remove_matching_lines(
    "frontend/src/report/reportSections.ts",
    ("key: 'trader_plan'", "key: 'trader_proposal_json'"),
)
remove_matching_lines(
    "frontend/src/i18n/analysis.ts",
    (
        "analysis.section.trader_investment_plan",
        "analysis.section.trader_proposal_json",
        "analysis.pm.legacy_fallback",
    ),
)
remove_matching_lines(
    "frontend/src/i18n/export_sections.ts",
    ("export.section.trader_plan",),
)

# Canonical decision reader: accepted DB value -> old chart annotation -> live
# stream. The retired Trader JSON source is no longer a runtime input.
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
''',
)

write(
    "frontend/src/analysis/__tests__/portfolioDecision.test.ts",
    '''import { describe, expect, it } from 'vitest'
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
''',
)

# The card now renders only the canonical accepted decision.
card_path = "frontend/src/components/analysis/PortfolioDecisionCard.tsx"
card = read(card_path)
card = card.replace("  legacyTraderJson,\n", "")
card = card.replace("  legacyTraderJson?: string | null\n", "")
card = card.replace(
    "  const decision = readPortfolioDecision(acceptedPortfolioDecision, chartAnnotations, legacyTraderJson, streamedPortfolioDecision)\n",
    "  const decision = readPortfolioDecision(acceptedPortfolioDecision, chartAnnotations, streamedPortfolioDecision)\n",
)
card = card.replace("{t('analysis.pm.title')}", "{t('analysis.section.final_trade_decision')}")
card = card.replace(
    "{decision.source === 'portfolio_manager' ? t('analysis.pm.single_authority') : t('analysis.pm.legacy_fallback')}",
    "{t('analysis.strategy.subtitle')}",
)
if "legacyTraderJson" in card or "decision.source" in card:
    raise RuntimeError(f"{card_path}: legacy decision branch remains")
write(card_path, card)

# Main analysis page: remove historical Trader report/decision fallback paths.
analysis_path = "frontend/src/pages/Analysis.tsx"
analysis = read(analysis_path)
analysis = analysis.replace("          trader_plan: a.trader_plan || '',\n", "")
analysis = analysis.replace(
    "        const activeLegacyTraderProposal = detail ? detail.trader_proposal_json : reports.trader_proposal_json;\n",
    "",
)
analysis = analysis.replace(
    "          activeChartAnnotations,\n          activeLegacyTraderProposal,\n          streamedPortfolioDecision,\n",
    "          activeChartAnnotations,\n          streamedPortfolioDecision,\n",
)
analysis = analysis.replace("        const hasPortfolioManagerDecision = activePortfolioDecision?.source === 'portfolio_manager';\n", "")
analysis = analysis.replace(
    "          trader_plan: hasPortfolioManagerDecision ? '' : detail.trader_plan,\n",
    "",
)
analysis = analysis.replace(
    "          trader_plan: hasPortfolioManagerDecision ? '' : reports.trader_plan || reports.trader_investment_plan || '',\n",
    "",
)
analysis = re.sub(
    r"\n\s*\{activePlans\.trader_plan && \(.*?\n\s*\)\}",
    "",
    analysis,
    count=1,
    flags=re.S,
)
if "trader_plan" in analysis or "trader_proposal_json" in analysis or "trader_investment_plan" in analysis:
    raise RuntimeError(f"{analysis_path}: retired Trader references remain")
write(analysis_path, analysis)

# History detail follows the same canonical-only contract.
history_path = "frontend/src/components/analysis/tabs/HistoryTab.tsx"
history = read(history_path)
history = history.replace(
    "    ? readPortfolioDecision(detail.portfolio_decision_json, detail.chart_annotations, detail.trader_proposal_json)\n",
    "    ? readPortfolioDecision(detail.portfolio_decision_json, detail.chart_annotations)\n",
)
history = history.replace("  const historyHasPortfolioManagerDecision = historyPortfolioDecision?.source === 'portfolio_manager'\n", "")
history = history.replace("                        legacyTraderJson={detail.trader_proposal_json}\n", "")
history = history.replace(
    "                        ...(historyHasPortfolioManagerDecision ? [] : [['trader_plan', detail.trader_plan] as [string, string]]),\n",
    "",
)
if "trader_plan" in history or "trader_proposal_json" in history or "legacyTraderJson" in history:
    raise RuntimeError(f"{history_path}: retired Trader references remain")
write(history_path, history)

# Shared reports no longer expose or hide retired sections; only canonical data exists.
shared_path = "frontend/src/pages/SharedReport.tsx"
shared = read(shared_path)
shared = shared.replace("  trader_plan: Zap,\n", "")
shared = shared.replace("  trader_proposal_json: Zap,\n", "")
shared = re.sub(
    r"\n\s*const hasCanonicalPortfolioDecision = isNonEmptyRecord\(report\.portfolio_decision\)\n"
    r"\s*// New reports have one final authority:.*?\n"
    r"\s*if \(hasCanonicalPortfolioDecision && \(def\.key === 'trader_plan' \|\| def\.key === 'trader_proposal_json'\)\) \{\n"
    r"\s*return false\n\s*\}\n",
    "\n  const hasCanonicalPortfolioDecision = isNonEmptyRecord(report.portfolio_decision)\n",
    shared,
    count=1,
    flags=re.S,
)
shared = shared.replace(
    "{label('analysis.pm.title', 'Portfolio Manager Recommendation')}",
    "{label('analysis.section.final_trade_decision', 'Canonical Portfolio Decision')}",
)
shared = shared.replace(
    "{label('analysis.pm.single_authority', 'Single AI authority for sizing and trade parameters')}",
    "{label('analysis.strategy.subtitle', 'Accepted decision after the Portfolio Manager proposal and Decision Stability policy.')}",
)
if "trader_plan" in shared or "trader_proposal_json" in shared:
    raise RuntimeError(f"{shared_path}: retired Trader references remain")
write(shared_path, shared)

print("retired Trader source transform complete")
