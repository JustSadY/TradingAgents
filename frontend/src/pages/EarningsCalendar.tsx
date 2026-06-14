import { useState, useCallback, useEffect } from 'react'
import { CalendarDays, Loader2, Search, Play, AlertTriangle } from 'lucide-react'
import axios from '../utils/api'
import { notify } from '../utils/notify'

interface EarningsEntry {
  ticker: string
  earnings_date: string | null
  eps_estimate: number | null
  reported_eps: number | null
  surprise_pct: number | null
  days_until: number | null
  status: 'upcoming' | 'reported' | 'unknown'
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'upcoming') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-violet-500/10 text-violet-400 border-violet-500/20">
        Upcoming
      </span>
    )
  }
  if (status === 'reported') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-500/10 text-slate-400 border-slate-500/20">
        Reported
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-700/30 text-slate-500 border-slate-600/20">
      Unknown
    </span>
  )
}

function SurpriseBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-slate-600 font-mono">—</span>
  const positive = pct >= 0
  return (
    <span
      className={`font-mono font-bold ${positive ? 'text-emerald-400' : 'text-rose-400'}`}
    >
      {positive ? '+' : ''}{pct.toFixed(2)}%
    </span>
  )
}

function EarningsSoonBadge({ days_until }: { days_until: number | null }) {
  if (days_until === null || days_until < 0 || days_until > 7) return null
  return (
    <span className="inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full border bg-amber-500/10 text-amber-400 border-amber-500/20">
      <AlertTriangle size={9} />
      Earnings Soon!
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
  const [results, setResults] = useState<EarningsEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [tickerInput, setTickerInput] = useState('')
  const [analyzing, setAnalyzing] = useState<string | null>(null)
  const [hasLoaded, setHasLoaded] = useState(false)

  const fetchEarnings = useCallback(async (overrideTickers?: string) => {
    setLoading(true)
    setResults([])
    try {
      const params: Record<string, string> = {}
      const query = overrideTickers ?? tickerInput
      if (query.trim()) {
        params.tickers = query
          .split(/[\s,]+/)
          .map(t => t.trim().toUpperCase())
          .filter(Boolean)
          .join(',')
      }
      const r = await axios.get('/api/market/earnings-calendar', { params })
      setResults(r.data.results || [])
      setHasLoaded(true)
      if ((r.data.results || []).length === 0) {
        notify('info', 'No earnings data found for the selected tickers.', 'Earnings Calendar')
      }
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Failed to load earnings data.', 'Earnings Calendar')
    } finally {
      setLoading(false)
    }
  }, [tickerInput])

  // Auto-load watchlist on mount
  useEffect(() => {
    fetchEarnings('')
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const runAnalysis = useCallback(async (ticker: string) => {
    setAnalyzing(ticker)
    try {
      await axios.post('/api/analysis/run', {
        ticker,
        trade_date: new Date().toISOString().slice(0, 10),
      })
      notify('success', `Analysis started for ${ticker}`, 'Analysis')
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Failed to start analysis.', 'Analysis')
    } finally {
      setAnalyzing(null)
    }
  }, [])

  const handleSearch = useCallback(() => {
    fetchEarnings()
  }, [fetchEarnings])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
          <CalendarDays className="text-violet-400" size={20} />
          Earnings Calendar
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Upcoming and recent earnings for your watchlist — EPS estimates, reported results, and surprise percentages
        </p>
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
              Tickers (leave blank to use your watchlist)
            </label>
            <input
              type="text"
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="e.g. AAPL, MSFT, NVDA"
              className="w-full bg-white/[0.02] border border-white/[0.06] focus:border-violet-500/40 outline-none rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-600 transition-colors"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl px-4 py-2.5 shadow shadow-violet-600/25 transition-all cursor-pointer"
          >
            {loading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Search size={13} />
            )}
            {loading ? 'Loading...' : 'Search'}
          </button>
        </div>
      </div>

      {/* Results Table */}
      {loading ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Loader2 size={24} className="animate-spin text-violet-400 mx-auto mb-3" />
          <p className="text-xs text-slate-500">Fetching earnings data...</p>
        </div>
      ) : hasLoaded && results.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <CalendarDays size={32} className="text-slate-600 opacity-30 mx-auto mb-3" />
          <p className="text-sm font-semibold text-slate-400">No earnings data found</p>
          <p className="text-xs text-slate-600 mt-1">
            Add tickers to your watchlist or enter them above
          </p>
        </div>
      ) : results.length > 0 ? (
        <div className="glass-panel rounded-2xl overflow-hidden">
          {/* Table header */}
          <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              {results.length} ticker{results.length !== 1 ? 's' : ''}
            </p>
            <p className="text-[9px] text-slate-600 font-medium">
              Sorted by earnings date — soonest first
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.04]">
                  <th className="px-4 py-2.5 text-left text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Ticker
                  </th>
                  <th className="px-4 py-2.5 text-left text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Earnings Date
                  </th>
                  <th className="px-4 py-2.5 text-right text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Days Until
                  </th>
                  <th className="px-4 py-2.5 text-right text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    EPS Estimate
                  </th>
                  <th className="px-4 py-2.5 text-right text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Reported EPS
                  </th>
                  <th className="px-4 py-2.5 text-right text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Surprise %
                  </th>
                  <th className="px-4 py-2.5 text-center text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Status
                  </th>
                  <th className="px-4 py-2.5 text-center text-[9px] uppercase tracking-wider text-slate-500 font-bold">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {results.map(row => {
                  const isPositiveSurprise = row.surprise_pct !== null && row.surprise_pct >= 0
                  const rowHighlight =
                    row.status === 'reported' && row.surprise_pct !== null
                      ? isPositiveSurprise
                        ? 'hover:bg-emerald-500/[0.03]'
                        : 'hover:bg-rose-500/[0.03]'
                      : 'hover:bg-white/[0.01]'

                  return (
                    <tr
                      key={row.ticker}
                      className={`transition-colors ${rowHighlight}`}
                    >
                      {/* Ticker */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-white text-[11px]">
                            {row.ticker}
                          </span>
                          <EarningsSoonBadge days_until={row.days_until} />
                        </div>
                      </td>

                      {/* Earnings Date */}
                      <td className="px-4 py-3 text-slate-300 font-mono text-[11px]">
                        {fmtDate(row.earnings_date)}
                      </td>

                      {/* Days Until */}
                      <td className="px-4 py-3 text-right">
                        <span
                          className={`font-mono font-bold text-[11px] ${
                            row.days_until !== null && row.days_until >= 0 && row.days_until <= 7
                              ? 'text-amber-400'
                              : row.days_until !== null && row.days_until >= 0
                              ? 'text-violet-400'
                              : 'text-slate-500'
                          }`}
                        >
                          {fmtDaysUntil(row.days_until)}
                        </span>
                      </td>

                      {/* EPS Estimate */}
                      <td className="px-4 py-3 text-right font-mono text-slate-300 text-[11px]">
                        {row.eps_estimate !== null ? `$${fmt(row.eps_estimate)}` : <span className="text-slate-600">—</span>}
                      </td>

                      {/* Reported EPS */}
                      <td className="px-4 py-3 text-right font-mono text-[11px]">
                        {row.reported_eps !== null ? (
                          <span
                            className={
                              row.eps_estimate !== null
                                ? row.reported_eps >= row.eps_estimate
                                  ? 'text-emerald-400 font-bold'
                                  : 'text-rose-400 font-bold'
                                : 'text-slate-300'
                            }
                          >
                            ${fmt(row.reported_eps)}
                          </span>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>

                      {/* Surprise % */}
                      <td className="px-4 py-3 text-right text-[11px]">
                        <SurpriseBadge pct={row.surprise_pct} />
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3 text-center">
                        <StatusBadge status={row.status} />
                      </td>

                      {/* Analyse button */}
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => runAnalysis(row.ticker)}
                          disabled={analyzing === row.ticker}
                          title={`Run AI analysis for ${row.ticker}`}
                          className="inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-lg bg-violet-600/10 hover:bg-violet-600/20 text-violet-400 border border-violet-500/20 hover:border-violet-500/40 disabled:opacity-40 transition-all cursor-pointer"
                        >
                          {analyzing === row.ticker ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <Play size={10} />
                          )}
                          Analyse
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  )
}
