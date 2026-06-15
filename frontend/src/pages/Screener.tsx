import { useState, useCallback } from 'react'
import axios from 'axios'
import { Filter, Play, TrendingUp, Loader2, ExternalLink, BarChart2 } from 'lucide-react'
import { notify } from '../utils/notify'

interface ScreenResult {
  ticker: string
  score: number
  momentum: number
  trend: number
  volume_surge: number
  rsi_position: number
  rsi: number | null
  price: number | null
  change_pct: number | null
  volume_ratio: number | null
  verdict: string
}

const VERDICT_STYLES: Record<string, string> = {
  Strong: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  Weak: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
  Neutral: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
}

const POPULAR = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSLA', 'AMD', 'JPM', 'V']

export default function Screener() {
  const [results, setResults] = useState<ScreenResult[]>([])
  const [loading, setLoading] = useState(false)
  const [tickerInput, setTickerInput] = useState('')
  const [topN, setTopN] = useState(10)
  const [mode, setMode] = useState<'custom' | 'default' | 'watchlist'>('default')
  const [analyzing, setAnalyzing] = useState<string | null>(null)

  const runScreen = useCallback(async () => {
    setLoading(true)
    setResults([])
    try {
      let data: { results: ScreenResult[] }
      if (mode === 'watchlist') {
        const r = await axios.post('/api/screener/scan-watchlist')
        data = r.data
      } else {
        const tickers = mode === 'custom'
          ? tickerInput.split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean)
          : undefined
        const r = await axios.post('/api/screener/scan', { tickers, top_n: topN })
        data = r.data
      }
      setResults(data.results || [])
      if ((data.results || []).length === 0) notify('info', 'No results found', 'Screener')
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Screener failed', 'Screener')
    } finally {
      setLoading(false)
    }
  }, [mode, tickerInput, topN])

  const runAnalysis = useCallback(async (ticker: string) => {
    setAnalyzing(ticker)
    try {
      await axios.post('/api/analysis/run', { ticker, trade_date: new Date().toISOString().slice(0, 10) })
      notify('success', `Analysis started for ${ticker}`, 'Analysis')
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Failed to start analysis', 'Analysis')
    } finally {
      setAnalyzing(null)
    }
  }, [])

  const scoreColor = (score: number) =>
    score >= 0.6 ? 'text-emerald-400' : score >= 0.4 ? 'text-amber-400' : 'text-rose-400'

  const scoreBar = (val: number) => Math.max(0, Math.min(100, val * 100))

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
          <Filter className="text-violet-400" size={20} />
          Stock Screener
        </h2>
        <p className="text-xs text-slate-500 mt-1">Score and rank tickers by momentum, trend, volume, and RSI — then launch analysis on top candidates</p>
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        {/* Mode tabs */}
        <div className="flex gap-1 bg-white/[0.02] p-0.5 rounded-xl border border-white/[0.04] w-fit">
          {([['default', 'Default Universe'], ['custom', 'Custom Tickers'], ['watchlist', 'My Watchlist']] as const).map(([m, label]) => (
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
            <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest">Tickers (comma or space separated)</label>
            <textarea
              value={tickerInput}
              onChange={e => setTickerInput(e.target.value.toUpperCase())}
              placeholder="AAPL, MSFT, NVDA, TSLA..."
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
            <label className="text-[10px] text-slate-500 font-bold uppercase tracking-widest shrink-0">Top N</label>
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
          {loading ? 'Scanning…' : 'Run Screen'}
        </button>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="glass-panel rounded-2xl overflow-hidden">
          <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart2 size={14} className="text-violet-400" />
              <span className="text-sm font-bold text-white">Results</span>
              <span className="text-[10px] text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20">{results.length}</span>
            </div>
            <p className="text-[10px] text-slate-500">Sorted by composite score ↓</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[700px]">
              <thead>
                <tr className="text-[9px] uppercase tracking-wider text-slate-500 bg-white/[0.01]">
                  <th className="px-5 py-3 text-left font-bold">#</th>
                  <th className="px-5 py-3 text-left font-bold">Ticker</th>
                  <th className="px-5 py-3 text-center font-bold">Score</th>
                  <th className="px-5 py-3 text-center font-bold">Momentum</th>
                  <th className="px-5 py-3 text-center font-bold">Trend</th>
                  <th className="px-5 py-3 text-center font-bold">Volume</th>
                  <th className="px-5 py-3 text-right font-bold">RSI</th>
                  <th className="px-5 py-3 text-center font-bold">Verdict</th>
                  <th className="px-5 py-3 text-center font-bold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {results.map((r, i) => (
                  <tr key={r.ticker} className="hover:bg-white/[0.01] transition-colors">
                    <td className="px-5 py-3 text-slate-600 font-mono font-bold">{i + 1}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white text-sm">{r.ticker}</span>
                        {typeof r.price === 'number' && <span className="text-slate-500 font-mono text-[10px]">${r.price.toFixed(2)}</span>}
                        {typeof r.change_pct === 'number' && (
                          <span className={`text-[9px] font-bold ${r.change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {r.change_pct >= 0 ? '+' : ''}{r.change_pct.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-center">
                      <div className="flex flex-col items-center gap-1">
                        <span className={`font-mono font-bold text-sm ${scoreColor(r.score)}`}>{(r.score * 100).toFixed(0)}</span>
                        <div className="w-16 h-1 rounded-full bg-white/[0.04]">
                          <div className={`h-full rounded-full ${r.score >= 0.6 ? 'bg-emerald-500' : r.score >= 0.4 ? 'bg-amber-500' : 'bg-rose-500'}`} style={{ width: `${scoreBar(r.score)}%` }} />
                        </div>
                      </div>
                    </td>
                    {[r.momentum, r.trend, r.volume_surge].map((v, j) => (
                      <td key={j} className="px-5 py-3 text-center">
                        <div className="w-12 h-1 rounded-full bg-white/[0.04] mx-auto">
                          <div className={`h-full rounded-full ${v >= 0.6 ? 'bg-emerald-500' : v >= 0.4 ? 'bg-amber-500' : 'bg-rose-500'}`} style={{ width: `${scoreBar(v)}%` }} />
                        </div>
                        <span className={`text-[9px] font-mono ${scoreColor(v)}`}>{(v * 100).toFixed(0)}</span>
                      </td>
                    ))}
                    <td className="px-5 py-3 text-right font-mono text-slate-300">
                      {typeof r.rsi === 'number' ? (
                        <span className={r.rsi < 30 ? 'text-emerald-400 font-bold' : r.rsi > 70 ? 'text-rose-400 font-bold' : 'text-slate-300'}>
                          {r.rsi.toFixed(0)}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-5 py-3 text-center">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${VERDICT_STYLES[r.verdict] || VERDICT_STYLES.Neutral}`}>
                        {r.verdict}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => runAnalysis(r.ticker)}
                          disabled={!!analyzing}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-violet-600/80 hover:bg-violet-600 text-white text-[9px] font-bold transition disabled:opacity-40 cursor-pointer"
                          title="Run AI Analysis"
                        >
                          {analyzing === r.ticker ? <Loader2 size={9} className="animate-spin" /> : <TrendingUp size={9} />}
                          Analyse
                        </button>
                        <a
                          href={`/chart?ticker=${r.ticker}`}
                          className="p-1.5 rounded-lg text-slate-600 hover:text-violet-400 hover:bg-violet-500/10 transition"
                          title="View Chart"
                        >
                          <ExternalLink size={11} />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && results.length === 0 && (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Filter size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">Select a universe and run the screener</p>
          <p className="text-[10px] text-slate-500 mt-1">Scores momentum, trend, volume surge, and RSI positioning for each ticker</p>
        </div>
      )}
    </div>
  )
}
