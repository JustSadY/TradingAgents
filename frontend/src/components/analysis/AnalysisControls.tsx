import React from 'react'
import { Zap, Square, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { SignalBadge } from './SignalBadge'

export type TickerSuggestion = {
  symbol: string
  name?: string | null
  quote_type?: string | null
}

export type AnalysisStartError = {
  code?: string
  message: string
  ticker?: string
  suggestions: TickerSuggestion[]
}

interface AnalysisControlsProps {
  ticker: string
  setTicker: (v: string) => void
  date: string
  setDate: (v: string) => void
  assetType: string
  setAssetType: (v: string) => void
  assetTypes: any[]
  running: boolean
  stopping?: boolean
  runStatus: string
  handleRun: () => void
  handleStop: () => void
  handleClear: () => void
  signal: string | null
  costEstimate: { estimated_cost_usd: number; estimated_tokens: number; estimated_duration_min: number; analyst_count: number } | null
  existingId: number | null
  startError?: AnalysisStartError | null
  onSelectTickerSuggestion?: (ticker: string) => void
  t: any
}

export const AnalysisControls: React.FC<AnalysisControlsProps> = ({
  ticker, setTicker, date, setDate, assetType, setAssetType, assetTypes,
  running, stopping = false, runStatus, handleRun, handleStop, handleClear, signal,
  costEstimate, existingId, startError, onSelectTickerSuggestion, t
}) => {
  const startErrorMessage = startError?.code === 'unknown_ticker'
    ? t('analysis.ticker_error.unknown').replace('{ticker}', startError.ticker || ticker)
    : startError?.code === 'ticker_validation_unavailable'
      ? t('analysis.ticker_error.unavailable')
      : startError?.message

  return (
    <div className="glass-panel rounded-2xl p-4 md:p-5">
      <div className="flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[120px]">
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.label.symbol')}</label>
          <input
            className="glass-input rounded-xl px-3 py-2 w-full uppercase font-mono text-sm outline-none"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            disabled={running}
          />
        </div>
        <div className="flex-1 min-w-[140px]">
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.label.date')}</label>
          <input
            type="date"
            className="glass-input rounded-xl px-3 py-2 text-sm w-full outline-none"
            value={date}
            onChange={e => setDate(e.target.value)}
            disabled={running}
          />
        </div>
        <div className="flex-1 min-w-[110px]">
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.label.type')}</label>
          <select
            className="glass-input rounded-xl px-3 py-2 text-sm w-full outline-none"
            value={assetType}
            onChange={e => setAssetType(e.target.value)}
            disabled={running}
          >
            {assetTypes.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div className="w-full sm:w-auto flex items-center gap-2 mt-2 sm:mt-0">
          {!running ? (
            <button
              onClick={handleRun}
              disabled={!ticker.trim()}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs md:text-sm font-semibold text-white bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-violet-500/20 transition-all cursor-pointer"
            >
              <Zap size={14} /> {t('analysis.btn.start')}
            </button>
          ) : (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs md:text-sm font-semibold text-white bg-rose-600/90 hover:bg-rose-600 disabled:opacity-60 disabled:cursor-wait shadow-md shadow-rose-500/20 transition-all cursor-pointer"
            >
              {stopping ? <Loader2 size={13} className="animate-spin" /> : <Square size={12} fill="currentColor" />}
              {stopping ? t('analysis.btn.stopping') : t('analysis.btn.stop')}
            </button>
          )}

          {runStatus !== 'idle' && !running && (
            <button onClick={handleClear} className="text-slate-500 hover:text-slate-300 hover:bg-white/5 transition-colors p-2 rounded-lg shrink-0 cursor-pointer">
              <X size={15} />
            </button>
          )}
        </div>

        {runStatus === 'done' && <CheckCircle size={20} className="text-emerald-400 mb-2 hidden sm:block animate-bounce" />}
        {runStatus === 'error' && <AlertCircle size={20} className="text-rose-400 mb-2 hidden sm:block" />}
        {signal && <div className="mb-1"><SignalBadge signal={signal} large /></div>}
      </div>

      {!running && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 border-t border-white/[0.03] pt-2.5">
          {costEstimate && (
            <span className="text-[10px] text-slate-500 font-semibold">
              ~${(costEstimate.estimated_cost_usd ?? 0).toFixed(3)} · {(costEstimate.estimated_tokens ?? 0).toLocaleString()} tokens · {costEstimate.estimated_duration_min}dk
            </span>
          )}
          {existingId && (
            <span className="text-[10px] text-amber-500 font-semibold bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-lg">{t('analysis.existing_analysis')}</span>
          )}
        </div>
      )}

      {startError && (
        <div role="alert" className="mt-3 border-t border-rose-500/20 pt-3 text-xs">
          <p className="text-rose-300 font-medium">{startErrorMessage}</p>
          {startError.suggestions.length > 0 && onSelectTickerSuggestion && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-[10px] text-slate-500">{t('analysis.ticker_error.suggestions')}</span>
              {startError.suggestions.map(suggestion => (
                <button
                  key={suggestion.symbol}
                  type="button"
                  onClick={() => onSelectTickerSuggestion(suggestion.symbol)}
                  className="rounded-lg border border-amber-400/25 bg-amber-400/10 px-2 py-1 font-mono text-[11px] font-bold text-amber-200 transition hover:bg-amber-400/20"
                  title={suggestion.name || suggestion.symbol}
                >
                  {t('analysis.ticker_error.use').replace('{ticker}', suggestion.symbol)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
