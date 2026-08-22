import { useState, useMemo } from 'react'
import type { GridColDef } from '@mui/x-data-grid'
import { useScreenerScan, useScreenerScanWatchlist } from '../api/generated/screener/screener'
import { useAnalysisRunAnalysis } from '../api/generated/analysis/analysis'
import { Filter, Play, TrendingUp, Loader2, ExternalLink, BarChart2 } from 'lucide-react'
import { notify } from '../utils/notify'
import { useTranslation } from '../contexts/LanguageContext'
import { errorDetail } from '../utils/errorDetail'
import AppDataGrid from '../components/ui/AppDataGrid'

interface ScreenResult {
  ticker: string
  score: number
  momentum_1m_pct: number
  trend: 'above_sma50' | 'below_sma50' | string
  volume_surge: number
  rsi_14: number
  signals: string[]
}

const VERDICT_STYLES: Record<string, string> = {
  Strong: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  Weak: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  Neutral: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
}

const POPULAR = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'JPM', 'V']
const MAX_SCORE = 90

export default function Screener() {
  const { t } = useTranslation()
  const [results, setResults] = useState<ScreenResult[]>([])
  const [tickerInput, setTickerInput] = useState('')
  const [topN, setTopN] = useState(10)
  const [mode, setMode] = useState<'custom' | 'default' | 'watchlist'>('default')
  const [analyzing, setAnalyzing] = useState<string | null>(null)

  const onScanError = (err: unknown) => {
    const detail = errorDetail(err)
    notify('error', detail || 'Screener failed', 'Screener')
  }
  const onScanSuccess = (data: unknown) => {
    const rows = ((data as { results?: ScreenResult[] } | undefined)?.results ?? []) as ScreenResult[]
    setResults(rows)
    if (rows.length === 0) notify('info', 'No results found', 'Screener')
  }

  const scanMutation = useScreenerScan({ mutation: { onSuccess: onScanSuccess, onError: onScanError } })
  const watchlistScanMutation = useScreenerScanWatchlist({
    mutation: { onSuccess: onScanSuccess, onError: onScanError },
  })
  const analysisMutation = useAnalysisRunAnalysis()
  const loading = scanMutation.isPending || watchlistScanMutation.isPending

  const runScreen = () => {
    setResults([])
    if (mode === 'watchlist') {
      watchlistScanMutation.mutate()
      return
    }
    const tickers = mode === 'custom'
      ? tickerInput.split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
      : undefined
    scanMutation.mutate({ data: { tickers, top_n: topN } })
  }

  const runAnalysis = (ticker: string) => {
    setAnalyzing(ticker)
    analysisMutation.mutate(
      { data: { ticker, trade_date: new Date().toISOString().slice(0, 10) } },
      {
        onSuccess: () => notify('success', `Analysis started for ${ticker}`, 'Analysis'),
        onError: (err) => {
          const detail = errorDetail(err)
          notify('error', detail || 'Failed to start analysis', 'Analysis')
        },
        onSettled: () => setAnalyzing(null),
      },
    )
  }

  const scoreColor = (score: number | null | undefined) => {
    const s = score ?? 0
    return s >= 60 ? 'text-emerald-400' : s >= 30 ? 'text-amber-400' : 'text-rose-400'
  }

  const scoreBar = (score: number | null | undefined) => Math.max(0, Math.min(100, ((score ?? 0) / MAX_SCORE) * 100))
  const scoreVerdict = (score: number) => score >= 60 ? 'Strong' : score < 20 ? 'Weak' : 'Neutral'
  const momentumBar = (momentum: number) => Math.min(100, Math.abs(momentum) / 25 * 100)
  const volumeBar = (ratio: number) => Math.min(100, Math.max(0, ratio / 3 * 100))

  const columns = useMemo<GridColDef<ScreenResult>[]>(() => [
    {
      field: 'rank',
      headerName: t('screener.col_rank'),
      minWidth: 64,
      sortable: false,
      renderCell: ({ api, id }) => (
        <span className="text-slate-600 font-mono font-bold">
          {api.getSortedRowIds().indexOf(id) + 1}
        </span>
      ),
    },
    {
      field: 'ticker',
      headerName: t('screener.col_ticker'),
      minWidth: 96,
      flex: 0.6,
      renderCell: ({ row }) => <span className="font-mono font-bold text-white text-sm">{row.ticker}</span>,
    },
    {
      field: 'score',
      headerName: t('screener.col_score'),
      type: 'number',
      minWidth: 96,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <div className="flex flex-col items-center gap-1 w-full">
          <span className={`font-mono font-bold text-sm ${scoreColor(row.score)}`}>{row.score.toFixed(0)}</span>
          <div className="w-16 h-1 rounded-full bg-white/[0.04]">
            <div
              className={`h-full rounded-full ${row.score >= 60 ? 'bg-emerald-500' : row.score >= 30 ? 'bg-amber-500' : 'bg-rose-500'}`}
              style={{ width: `${scoreBar(row.score)}%` }}
            />
          </div>
        </div>
      ),
    },
    {
      field: 'momentum_1m_pct',
      headerName: t('screener.col_momentum'),
      type: 'number',
      minWidth: 104,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <div className="flex flex-col items-center gap-1 w-full">
          <div className="w-12 h-1 rounded-full bg-white/[0.04]">
            <div
              className={`h-full rounded-full ${row.momentum_1m_pct >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}
              style={{ width: `${momentumBar(row.momentum_1m_pct)}%` }}
            />
          </div>
          <span className={`text-[9px] font-mono ${row.momentum_1m_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {row.momentum_1m_pct >= 0 ? '+' : ''}{row.momentum_1m_pct.toFixed(1)}%
          </span>
        </div>
      ),
    },
    {
      field: 'trend',
      headerName: t('screener.col_trend'),
      minWidth: 104,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${
          row.trend === 'above_sma50'
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
        }`}>
          {t(row.trend === 'above_sma50' ? 'screener.trend_above_sma50' : 'screener.trend_below_sma50')}
        </span>
      ),
    },
    {
      field: 'volume_surge',
      headerName: t('screener.col_volume'),
      type: 'number',
      minWidth: 96,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <div className="flex flex-col items-center gap-1 w-full">
          <div className="w-12 h-1 rounded-full bg-white/[0.04]">
            <div
              className={`h-full rounded-full ${row.volume_surge >= 1.5 ? 'bg-emerald-500' : 'bg-slate-500'}`}
              style={{ width: `${volumeBar(row.volume_surge)}%` }}
            />
          </div>
          <span className="text-[9px] font-mono text-slate-300">{row.volume_surge.toFixed(2)}×</span>
        </div>
      ),
    },
    {
      field: 'rsi_14',
      headerName: t('screener.col_rsi'),
      type: 'number',
      minWidth: 76,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => (
        <span className={`font-mono ${row.rsi_14 < 30 ? 'text-emerald-400 font-bold' : row.rsi_14 > 70 ? 'text-rose-400 font-bold' : 'text-slate-300'}`}>
          {row.rsi_14.toFixed(0)}
        </span>
      ),
    },
    {
      field: 'verdict',
      headerName: t('screener.col_verdict'),
      minWidth: 96,
      align: 'center',
      headerAlign: 'center',
      valueGetter: (_value, row) => scoreVerdict(row.score),
      renderCell: ({ row }) => {
        const verdict = scoreVerdict(row.score)
        return (
          <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${VERDICT_STYLES[verdict]}`}>
            {t(`screener.verdict_${verdict.toLowerCase()}`)}
          </span>
        )
      },
    },
    {
      field: 'action',
      headerName: t('screener.col_action'),
      minWidth: 132,
      sortable: false,
      filterable: false,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <div className="flex items-center justify-center gap-1.5">
          <button
            onClick={() => runAnalysis(row.ticker)}
            disabled={!!analyzing}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-violet-600/80 hover:bg-violet-600 text-white text-[9px] font-bold transition disabled:opacity-40 cursor-pointer"
            title={t('screener.run_analysis_title')}
          >
            {analyzing === row.ticker ? <Loader2 size={9} className="animate-spin" /> : <TrendingUp size={9} />}
            {t('screener.analyse')}
          </button>
          <a
            href={`/chart?ticker=${row.ticker}`}
            className="p-1.5 rounded-lg text-slate-600 hover:text-violet-400 hover:bg-violet-500/10 transition"
            title={t('screener.view_chart_title')}
          >
            <ExternalLink size={11} />
          </a>
        </div>
      ),
    },
  ], [t, analyzing])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Filter className="text-violet-400" size={20} />
            {t('screener.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">{t('screener.subtitle')}</p>
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        {/* Mode tabs */}
        <div className="flex gap-1 bg-white/[0.02] p-0.5 rounded-xl border border-white/[0.04] w-fit">
          {([['default', t('screener.mode_default')], ['custom', t('screener.mode_custom')], ['watchlist', t('screener.mode_watchlist')]] as const).map(([m, label]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition cursor-pointer ${
                mode === m ? 'bg-violet-600 text-white shadow' : 'text-slate-400 hover:text-white'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === 'custom' && (
          <div className="space-y-2">
            <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">{t('screener.ticker_label')}</label>
            <textarea
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value.toUpperCase())}
              placeholder={t('screener.ticker_placeholder')}
              rows={2}
              className="w-full bg-white/[0.02] border border-white/[0.06] focus:border-violet-500/40 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-600 outline-none resize-none font-mono transition-colors"
            />
            <div className="flex flex-wrap gap-1.5">
              {POPULAR.map(t => (
                <button
                  key={t}
                  onClick={() => setTickerInput(prev => {
                    const existing = prev.split(/[\s,]+/).map(x => x.trim().toUpperCase()).filter(Boolean)
                    return existing.includes(t) ? prev : [...existing, t].join(', ')
                  })}
                  className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border border-white/[0.06] text-slate-500 hover:text-violet-400 hover:border-violet-500/30 transition cursor-pointer"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}

        {mode !== 'watchlist' && (
          <div className="flex items-center gap-3">
            <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest shrink-0">{t('screener.top_n')}</label>
            <input
              type="number"
              min={1} max={50}
              value={topN}
              onChange={e => setTopN(Math.min(50, Math.max(1, Number(e.target.value))))}
              className="w-20 bg-white/[0.02] border border-white/[0.06] rounded-lg px-2 py-1 text-xs text-white outline-none font-mono"
            />
          </div>
        )}

        <button
          onClick={runScreen}
          disabled={loading || (mode === 'custom' && !tickerInput.trim())}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold transition cursor-pointer shadow shadow-violet-600/25"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          {loading ? t('screener.scanning') : t('screener.run')}
        </button>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="glass-panel rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart2 size={14} className="text-violet-400" />
              <span className="text-sm font-bold text-white">{t('screener.results')}</span>
              <span className="text-[10px] text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20">{results.length}</span>
            </div>
            <p className="text-[10px] text-slate-500">{t('screener.sorted_by_score')}</p>
          </div>
          <div className="p-2">
            <AppDataGrid<ScreenResult>
              rows={results}
              columns={columns}
              getRowId={row => row.ticker}
              ariaLabel={t('screener.col_ticker')}
              minHeight={280}
              density="comfortable"
              hideFooter
            />
          </div>
        </div>
      )}

      {!loading && results.length === 0 && (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Filter size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('screener.empty_title')}</p>
          <p className="text-[10px] text-slate-500 mt-1">{t('screener.empty_subtitle')}</p>
        </div>
      )}
    </div>
  )
}
