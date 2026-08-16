import { readPortfolioDecision } from '../../analysis/portfolioDecision'
import { useTranslation } from '../../contexts/LanguageContext'
import { SignalBadge } from './SignalBadge'

export function PortfolioDecisionCard({
  acceptedPortfolioDecision,
  chartAnnotations,
  legacyTraderJson,
  streamedPortfolioDecision,
}: {
  acceptedPortfolioDecision?: unknown
  chartAnnotations?: unknown
  legacyTraderJson?: string | null
  streamedPortfolioDecision?: unknown
}) {
  const { t } = useTranslation()
  const decision = readPortfolioDecision(acceptedPortfolioDecision, chartAnnotations, legacyTraderJson, streamedPortfolioDecision)
  if (!decision) return null

  const confidence = decision.confidenceScore === undefined
    ? null
    : decision.confidenceScore <= 1 ? decision.confidenceScore * 100 : decision.confidenceScore
  const money = (value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const values = [
    decision.entryPrice === undefined ? null : [t('analysis.pm.entry'), money(decision.entryPrice)],
    decision.stopLoss === undefined ? null : [t('analysis.pm.stop'), money(decision.stopLoss)],
    decision.takeProfit === undefined ? null : [t('analysis.pm.target'), money(decision.takeProfit)],
    decision.positionSizePct === undefined ? null : [t('analysis.pm.allocation'), `${decision.positionSizePct.toFixed(1)}%`],
    decision.suggestedCapital === undefined ? null : [t('analysis.pm.capital'), money(decision.suggestedCapital)],
    decision.recommendedLeverage === undefined ? null : [t('analysis.pm.leverage'), `${decision.recommendedLeverage.toFixed(1)}x`],
  ].filter((entry): entry is [string, string] => entry !== null)

  return (
    <div data-testid="portfolio-decision-card" className="rounded-2xl border border-violet-500/20 bg-violet-500/[0.06] p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h4 className="text-[10px] font-bold text-violet-300 uppercase tracking-widest">{t('analysis.pm.title')}</h4>
          <p className="text-[10px] text-slate-400">
            {decision.source === 'portfolio_manager' ? t('analysis.pm.single_authority') : t('analysis.pm.legacy_fallback')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {decision.rating && <SignalBadge signal={decision.rating} />}
          {confidence !== null && <span className="rounded-md border border-violet-400/20 bg-violet-400/10 px-2 py-0.5 text-[10px] font-mono font-bold text-violet-200">{confidence.toFixed(0)}%</span>}
        </div>
      </div>
      {values.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-2 text-[10px]">
          {values.map(([label, value]) => (
            <div key={label}>
              <span className="block text-slate-500 uppercase tracking-wide font-semibold">{label}</span>
              <span className="font-mono text-slate-100">{value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Analysis completion and order execution are deliberately distinct states.
 * A final model signal is a recommendation; this card only confirms whether
 * the separately guarded execution layer actually placed a sandbox order.
 */
