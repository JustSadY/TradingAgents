import type { AnalysisOrderResult } from '../../analysis/orderResult'
import { orderActionLabel } from '../../analysis/orderResult'
import { useTranslation } from '../../contexts/LanguageContext'
import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react'

export function AutomatedOrderResultCard({ result }: { result: AnalysisOrderResult | null }) {
  const { t } = useTranslation()
  const outcome = result?.outcome
  const presentation = outcome === 'filled'
    ? { Icon: CheckCircle, panel: 'border-emerald-500/25 bg-emerald-500/[0.06]', icon: 'text-emerald-400', text: 'text-emerald-200' }
    : outcome === 'skipped' || outcome === 'reconciliation_required'
      ? { Icon: AlertTriangle, panel: 'border-amber-500/25 bg-amber-500/[0.06]', icon: 'text-amber-400', text: 'text-amber-100' }
      : outcome
        ? { Icon: AlertCircle, panel: 'border-rose-500/25 bg-rose-500/[0.06]', icon: 'text-rose-400', text: 'text-rose-100' }
        : { Icon: AlertTriangle, panel: 'border-slate-600/40 bg-slate-900/35', icon: 'text-slate-400', text: 'text-slate-300' }
  const status = outcome ? t(`analysis.order.outcome.${outcome}`) : t('analysis.order.pending')
  const explanation = result?.message ?? result?.reason
  const action = orderActionLabel(result?.action, t)

  return (
    <div
      data-testid="analysis-order-result"
      data-outcome={outcome ?? 'pending'}
      className={`rounded-2xl border p-4 space-y-3 ${presentation.panel}`}
    >
      <div className="flex items-start gap-2.5">
        <presentation.Icon size={16} className={`${presentation.icon} shrink-0 mt-0.5`} />
        <div className="min-w-0 space-y-0.5">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('analysis.order.title')}</h3>
          <p className={`text-xs font-bold ${presentation.text}`}>{status}</p>
        </div>
      </div>

      {result ? (
        <>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
            <div>
              <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.symbol')}</span>
              <span className="font-mono text-slate-100">{result.ticker}</span>
            </div>
            {action && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.action')}</span>
                <span className="font-mono text-slate-100">{action}</span>
              </div>
            )}
            {result.quantity !== undefined && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.quantity')}</span>
                <span className="font-mono text-slate-100">{result.quantity.toLocaleString()}</span>
              </div>
            )}
            {result.price !== undefined && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.price')}</span>
                <span className="font-mono text-slate-100">${result.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            )}
          </div>
          {explanation && <p className="border-t border-white/[0.07] pt-2 text-[11px] leading-relaxed text-slate-300">{explanation}</p>}
        </>
      ) : (
        <p className="text-[11px] leading-relaxed text-slate-400">{t('analysis.order.pending_description')}</p>
      )}
    </div>
  )
}
