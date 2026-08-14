import { useState, useCallback, useEffect, useMemo } from 'react'
import type { GridColDef } from '@mui/x-data-grid'
import { CalendarDays, Loader2, Search, Play, AlertTriangle } from 'lucide-react'
import { useEarningsEarningsCalendar } from '../api/generated/earnings/earnings'
import { useAnalysisRunAnalysis } from '../api/generated/analysis/analysis'
import { useQueryErrorToast } from '../api/useQueryErrorToast'
import AppDataGrid from '../components/ui/AppDataGrid'
import { notify } from '../utils/notify'
import { useTranslation } from '../contexts/LanguageContext'

interface EarningsEntry {
  ticker: string
  earnings_date: string | null
  eps_estimate: number | null
  reported_eps: number | null
  surprise_pct: number | null
  days_until: number | null
  status: 'upcoming' | 'reported' | 'unknown'
}

function StatusBadge({ status, t }: { status: string; t: (key: string) => string }) {
  if (status === 'upcoming') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-violet-500/10 text-violet-400 border-violet-500/20">
        {t('earnings.status_upcoming')}
      </span>
    )
  }
  if (status === 'reported') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-500/10 text-slate-400 border-slate-500/20">
        {t('earnings.status_reported')}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-700/30 text-slate-500 border-slate-600/20">
      {t('earnings.status_unknown')}
    </span>
  )
}

function SurpriseBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-600 font-mono">—</span>
  const positive = pct >= 0
  return (
    <span className={`font-mono font-bold ${positive ? 'text-emerald-400' : 'text-rose-400'}`}>
      {positive ? '+' : ''}{pct.toFixed(2)}%
    </span>
  )
}

function EarningsSoonBadge({ days_until, t }: { days_until: number | null; t: (key: string) => string }) {
  if (days_until === null || days_until < 0 || days_until > 7) return null
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full border bg-amber-500/10 text-amber-400 border-amber-500/20">
      <AlertTriangle size={9} />
      {t('earnings.soon_badge')}
    </span>
  )
}

function fmt(val: number | null, decimals = 2): string {
  if (val === null) return '—'
  return val.toFixed(decimals)
}

function fmtDate(dateStr: string | null): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtDaysUntil(days: number | null): string {
  if (days === null) return '—'
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days < 0) return `${Math.abs(days)}d ago`
  return `${days}d`
}

export default function EarningsCalendar() {
  const { t } = useTranslation()
  const [tickerInput, setTickerInput] = useState('')
  const [analyzing, setAnalyzing] = useState<string | null>(null)

  // The submitted tickers, not the live input: typing must not refetch.
  const [submitted, setSubmitted] = useState('')

  const normalize = (query: string) =>
    query
      .split(/[\s,]+/)
      .map(ticker => ticker.trim().toUpperCase())
      .filter(Boolean)
      .join(',')

  const params = submitted.trim() ? { tickers: normalize(submitted) } : {}
  const earningsQuery = useEarningsEarningsCalendar(params)
  const loading = earningsQuery.isFetching
  const results = ((earningsQuery.data as { results?: EarningsEntry[] } | undefined)?.results ?? []) as EarningsEntry[]

  useEffect(() => {
    if (!earningsQuery.isSuccess) return
    if (results.length === 0) {
      notify('info', 'No earnings data found for the selected tickers.', 'Earnings Calendar')
    }
  }, [earningsQuery.isSuccess, earningsQuery.dataUpdatedAt, results.length])

  useQueryErrorToast(earningsQuery.error, 'Failed to load earnings data.', 'Earnings Calendar')

  const fetchEarnings = useCallback((overrideTickers?: string) => {
    setSubmitted(overrideTickers ?? tickerInput)
  }, [tickerInput])

  const analysisMutation = useAnalysisRunAnalysis()
  const runAnalysis = useCallback((ticker: string) => {
    setAnalyzing(ticker)
    analysisMutation.mutate(
      { data: { ticker, trade_date: new Date().toISOString().slice(0, 10) } },
      {
        onSuccess: () => notify('success', `Analysis started for ${ticker}`, 'Analysis'),
        onError: (err) => {
          const detail = (err as unknown as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          notify('error', detail || 'Failed to start analysis.', 'Analysis')
        },
        onSettled: () => setAnalyzing(null),
      },
    )
  }, [analysisMutation])

  const columns = useMemo<GridColDef<EarningsEntry>[]>(() => [
    {
      field: 'ticker',
      headerName: t('earnings.col_ticker'),
      minWidth: 135,
      flex: 0.8,
      renderCell: ({ row }) => (
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-white text-[11px]">{row.ticker}</span>
          <EarningsSoonBadge days_until={row.days_until} t={t} />
        </div>
      ),
    },
    {
      field: 'earnings_date',
      headerName: t('earnings.col_date'),
      minWidth: 145,
      renderCell: ({ value }) => <span className="text-slate-300 font-mono text-[11px]">{fmtDate((value as string | null) ?? null)}</span>,
    },
    {
      field: 'days_until',
      headerName: t('earnings.col_days_until'),
      type: 'number',
      minWidth: 115,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => {
        const days = value == null ? null : Number(value)
        const tone = days !== null && days >= 0 && days <= 7
          ? 'text-amber-400'
          : days !== null && days >= 0
            ? 'text-violet-400'
            : 'text-slate-500'
        return <span className={`font-mono font-bold text-[11px] ${tone}`}>{fmtDaysUntil(days)}</span>
      },
    },
    {
      field: 'eps_estimate',
      headerName: t('earnings.col_eps_estimate'),
      type: 'number',
      minWidth: 120,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => <span className="font-mono text-slate-300 text-[11px]">{value == null ? '—' : `$${fmt(Number(value))}`}</span>,
    },
    {
      field: 'reported_eps',
      headerName: t('earnings.col_reported_eps'),
      type: 'number',
      minWidth: 125,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => {
        if (row.reported_eps === null) return <span className="text-slate-600">—</span>
        const tone = row.eps_estimate === null
          ? 'text-slate-300'
          : row.reported_eps >= row.eps_estimate
            ? 'text-emerald-400 font-bold'
            : 'text-rose-400 font-bold'
        return <span className={`font-mono text-[11px] ${tone}`}>${fmt(row.reported_eps)}</span>
      },
    },
    {
      field: 'surprise_pct',
      headerName: t('earnings.col_surprise'),
      type: 'number',
      minWidth: 115,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => <SurpriseBadge pct={value == null ? null : Number(value)} />,
    },
    {
      field: 'status',
      headerName: t('earnings.col_status'),
      minWidth: 115,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ value }) => <StatusBadge status={String(value ?? 'unknown')} t={t} />,
    },
    {
      field: 'action',
      headerName: t('earnings.col_action'),
      minWidth: 115,
      sortable: false,
      filterable: false,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <button
          onClick={() => runAnalysis(row.ticker)}
          disabled={analyzing === row.ticker}
          title={t('earnings.run_analysis_title').replace('{ticker}', row.ticker)}
          aria-label={`Analyse ${row.ticker}`}
          className="inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-lg bg-violet-600/10 hover:bg-violet-600/20 text-violet-400 border border-violet-500/20 hover:border-violet-500/40 disabled:opacity-40 transition-all cursor-pointer"
        >
          {analyzing === row.ticker ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
          {t('earnings.analyse')}
        </button>
      ),
    },
  ], [analyzing, runAnalysis, t])

  const handleSearch = useCallback(() => {
    fetchEarnings()
  }, [fetchEarnings])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
          <CalendarDays className="text-violet-400" size={20} />
          {t('earnings.title')}
        </h2>
        <p className="text-xs text-slate-500 mt-1">{t('earnings.subtitle')}</p>
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label htmlFor="earnings-tickers" className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
              {t('earnings.ticker_label')}
            </label>
            <input
              id="earnings-tickers"
              type="text"
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder={t('earnings.ticker_placeholder')}
              className="w-full bg-white/[0.02] border border-white/[0.06] focus:border-violet-500/40 outline-none rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-600 transition-colors"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl px-4 py-2.5 shadow shadow-violet-600/25 transition-all cursor-pointer"
          >
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {loading ? t('earnings.loading') : t('earnings.search')}
          </button>
        </div>
      </div>

      {results.length > 0 && (
        <div className="flex items-center justify-between px-1">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            {results.length} {t('earnings.col_ticker')}{results.length !== 1 ? 's' : ''}
          </p>
          <p className="text-[9px] text-slate-600 font-medium">{t('earnings.sorted_by_date')}</p>
        </div>
      )}

      <AppDataGrid<EarningsEntry>
        rows={results}
        columns={columns}
        getRowId={row => row.ticker}
        loading={loading}
        error={earningsQuery.error}
        emptyMessage={t('earnings.no_data')}
        ariaLabel="Earnings Calendar"
        minHeight={320}
        density="compact"
        sx={{
          minWidth: 900,
          '& .earnings-positive:hover': { backgroundColor: 'rgba(16,185,129,.035)' },
          '& .earnings-negative:hover': { backgroundColor: 'rgba(244,63,94,.035)' },
        }}
        getRowClassName={({ row }) => {
          if (row.status !== 'reported' || row.surprise_pct === null) return ''
          return row.surprise_pct >= 0 ? 'earnings-positive' : 'earnings-negative'
        }}
      />
    </div>
  )
}
