import { useMemo, useState } from 'react'
import { Loader2, Sparkles, TrendingUp } from 'lucide-react'
import {
  useOptimizationGetCatalog,
  useOptimizationRunOptimization,
} from '../../api/generated/optimization/optimization'
import { useTranslation } from '../../contexts/LanguageContext'

const Input = 'w-full glass-input rounded-xl px-3 py-2 text-xs outline-none'

interface OptimizationPanelProps {
  ticker: string
  strategy: string
  startDate: string
  endDate: string
  initialCapital: string
  /** Re-run the ordinary backtest with the parameters the search found. */
  onApply?: (params: Record<string, number>) => void
}

interface OptimizationRun {
  id: number
  objective: string
  trials_requested: number
  trials_completed: number
  best_params?: Record<string, number> | null
  best_value?: number | null
  baseline_value?: number | null
  status: string
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(3)
}

/**
 * Parameter search over the same backtest the page already runs.
 *
 * Only offered for the rule-based strategies: `consensus` replays stored
 * analyses and has nothing to tune, which is why the catalog — published by
 * the backend from the simulation's own parameter space — decides what appears
 * here rather than a list duplicated in the frontend.
 */
export default function OptimizationPanel({
  ticker,
  strategy,
  startDate,
  endDate,
  initialCapital,
  onApply,
}: OptimizationPanelProps) {
  const { t } = useTranslation()
  const [objective, setObjective] = useState('sharpe_ratio')
  const [trials, setTrials] = useState('40')
  const [error, setError] = useState<string | null>(null)

  const catalogQuery = useOptimizationGetCatalog()
  const optimize = useOptimizationRunOptimization()
  const catalog = catalogQuery.data as
    | {
        strategies?: Record<string, { label: string; params: Record<string, unknown> }>
        objectives?: Record<string, string>
        max_trials?: number
        default_trials?: number
      }
    | undefined

  const optimizable = useMemo(() => Object.keys(catalog?.strategies ?? {}), [catalog])
  const supported = optimizable.includes(strategy)
  const run = (optimize.data ?? null) as OptimizationRun | null

  const handleOptimize = () => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) {
      setError(t('backtest.optimize_needs_ticker'))
      return
    }
    setError(null)
    optimize.reset()
    optimize.mutate(
      {
        data: {
          ticker: symbol,
          strategy_type: strategy,
          start_date: startDate,
          end_date: endDate,
          objective,
          n_trials: Number.parseInt(trials, 10) || 40,
          initial_capital: Number.parseFloat(initialCapital) || 100000,
        },
      },
      {
        onError: err => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          setError(detail || t('backtest.optimize_failed'))
        },
      },
    )
  }

  if (!catalogQuery.isPending && !supported) {
    return (
      <div className="glass-panel rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-1.5">
          <Sparkles size={14} className="text-violet-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider">{t('backtest.optimize_title')}</h3>
        </div>
        <p className="text-[10px] text-slate-500 leading-relaxed">{t('backtest.optimize_unsupported')}</p>
      </div>
    )
  }

  const improvement =
    run?.best_value != null && run?.baseline_value != null ? run.best_value - run.baseline_value : null

  return (
    <div className="glass-panel rounded-2xl p-5 space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <Sparkles size={14} className="text-violet-400" />
          <h3 className="text-xs font-bold text-white uppercase tracking-wider">{t('backtest.optimize_title')}</h3>
        </div>
        <p className="text-[10px] text-slate-500 leading-relaxed">{t('backtest.optimize_hint')}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">
            {t('backtest.optimize_objective')}
          </label>
          <select className={Input} value={objective} onChange={e => setObjective(e.target.value)}>
            {Object.entries(catalog?.objectives ?? {}).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">
            {t('backtest.optimize_trials')}
          </label>
          <input
            className={Input}
            type="number"
            min={1}
            max={catalog?.max_trials ?? 200}
            value={trials}
            onChange={e => setTrials(e.target.value)}
          />
        </div>
        <div className="flex items-end">
          <button
            onClick={handleOptimize}
            disabled={optimize.isPending}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-xl px-4 py-2 text-xs font-semibold transition cursor-pointer"
          >
            {optimize.isPending ? <Loader2 size={13} className="animate-spin" /> : <TrendingUp size={13} />}
            {optimize.isPending ? t('backtest.optimize_running') : t('backtest.optimize_button')}
          </button>
        </div>
      </div>

      {optimize.isPending && (
        <p className="text-[10px] text-slate-500 leading-relaxed">{t('backtest.optimize_running_hint')}</p>
      )}
      {error && <p className="text-rose-400 text-xs font-semibold">{error}</p>}

      {run && run.status === 'completed' && (
        <div className="space-y-3 border-t border-white/[0.04] pt-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">{t('backtest.optimize_best')}</p>
              <p className="text-sm font-mono font-bold text-emerald-400">{formatValue(run.best_value)}</p>
            </div>
            <div>
              <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">{t('backtest.optimize_baseline')}</p>
              <p className="text-sm font-mono font-bold text-slate-300">{formatValue(run.baseline_value)}</p>
            </div>
            <div>
              <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">{t('backtest.optimize_improvement')}</p>
              <p className={`text-sm font-mono font-bold ${(improvement ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {improvement === null ? '—' : `${improvement >= 0 ? '+' : ''}${improvement.toFixed(3)}`}
              </p>
            </div>
            <div>
              <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">{t('backtest.optimize_trials_done')}</p>
              <p className="text-sm font-mono font-bold text-slate-300">
                {run.trials_completed}/{run.trials_requested}
              </p>
            </div>
          </div>

          <div>
            <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider mb-1.5">
              {t('backtest.optimize_best_params')}
            </p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(run.best_params ?? {}).map(([key, value]) => (
                <span
                  key={key}
                  className="rounded-lg border border-violet-500/20 bg-violet-500/[0.08] px-2 py-1 text-[10px] font-mono font-semibold text-violet-200"
                >
                  {key}={String(value)}
                </span>
              ))}
            </div>
          </div>

          {onApply && run.best_params && (
            <button
              onClick={() => onApply(run.best_params as Record<string, number>)}
              className="text-[10px] font-bold text-violet-300 hover:text-violet-200 transition cursor-pointer"
            >
              {t('backtest.optimize_apply')}
            </button>
          )}

          <p className="text-[10px] text-slate-500 leading-relaxed">{t('backtest.optimize_caveat')}</p>
        </div>
      )}
    </div>
  )
}
