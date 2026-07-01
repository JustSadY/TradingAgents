import { useEffect, useState } from 'react'
import axios from 'axios'
import { BarChart2, TrendingUp, TrendingDown, Target, Search, Activity, Trophy, Skull, ShieldAlert, Zap, DollarSign } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts'
import { useTranslation } from '../contexts/LanguageContext'
import { signalTone, TONE_TEXT_CLASS } from '../utils/signalTone'

interface TradingStats {
  total_trades: number
  winning_trades: number
  win_rate: number
  avg_return_pct: number | null
  best_trade: { ticker: string; pnl_pct: number; date: string } | null
  worst_trade: { ticker: string; pnl_pct: number; date: string } | null
  total_realized_pnl: number
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
  by_ticker: { ticker: string; trades: number; wins: number; win_rate: number; total_pnl: number }[]
}

interface PerfData {
  total: number
  win_rate: number | null
  avg_raw_return: number | null
  avg_alpha_return: number | null
  by_signal: Record<string, { count: number; wins: number; win_rate: number; avg_return: number }>
}

interface HistoryItem {
  id: number; ticker: string; trade_date: string; signal: string | null
  raw_return: number | null; alpha_return: number | null; holding_days: number | null
  duration_seconds: number; created_at: string
}

interface AttributionItem {
  key: string
  label: string
  total_predictions: number
  correct_predictions: number
  win_rate: number
  weight: number
  chronic_underperformer?: boolean
}

interface TokenBreakdown {
  provider: string
  model: string
  tokens_in: number
  tokens_out: number
  analyses: number
  estimated_cost_usd: number
}

interface TokenUsage {
  total_tokens_in: number
  total_tokens_out: number
  total_tokens: number
  total_cost_usd: number
  breakdown: TokenBreakdown[]
  daily: { day: string; tokens_in: number; tokens_out: number; analyses: number }[]
}

function ReturnCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-slate-600 font-semibold">—</span>
  const pct = (value * 100).toFixed(2)
  return <span className={value >= 0 ? 'text-emerald-400 font-mono font-semibold' : 'text-rose-400 font-mono font-semibold'}>{value >= 0 ? '+' : ''}{pct}%</span>
}

export default function Performance() {
  const { t } = useTranslation()
  const [perf, setPerf] = useState<PerfData | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [attribution, setAttribution] = useState<AttributionItem[]>([])
  const [tradingStats, setTradingStats] = useState<TradingStats | null>(null)
  const [ticker, setTicker] = useState('')
  const [filterTicker, setFilterTicker] = useState('')
  const [loading, setLoading] = useState(true)
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null)

  const load = async (ti?: string) => {
    setLoading(true)
    try {
      const [p, h, attr, ts] = await Promise.all([
        axios.get('/api/analysis/performance', { params: ti ? { ticker: ti } : {} }).then(r => r.data),
        axios.get('/api/analysis/history', { params: { limit: 100, ...(ti ? { ticker: ti } : {}) } }).then(r => r.data),
        axios.get('/api/analysis/performance-attribution').then(r => r.data).catch(() => ({ attribution: [] })),
        axios.get('/api/trading/portfolio-stats').then(r => r.data).catch(() => null),
      ])
      setPerf(p)
      setHistory(h.filter((x: HistoryItem) => x.raw_return !== null))
      setAttribution(attr.attribution || [])
      setTradingStats(ts)
    } finally { setLoading(false) }
  }

  useEffect(() => {
    load()
    axios.get('/api/analytics/token-usage').then(r => setTokenUsage(r.data)).catch(() => {})
  }, [])

  const handleFilter = () => { setFilterTicker(ticker); load(ticker || undefined) }

  const bySignalData = perf ? Object.entries(perf.by_signal).map(([sig, d]) => ({
    signal: sig, win_rate: d.win_rate, avg_return: d.avg_return, count: d.count,
  })) : []

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header & Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('performance.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Audit analyst correctness rates, historical signal gains, and weights allocation</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 bg-slate-900 border border-white/[0.08] rounded-xl px-3 py-1.5 focus-within:border-violet-500/50 transition-colors">
            <Search size={14} className="text-slate-500" />
            <input className="bg-transparent text-white text-xs outline-none w-20 md:w-24 uppercase font-mono font-semibold"
              placeholder="AAPL" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} onKeyDown={e => e.key === 'Enter' && handleFilter()} />
          </div>
          <button onClick={handleFilter} className="bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold px-4 py-2 rounded-xl transition cursor-pointer">{t('performance.filter_btn')}</button>
          {filterTicker && <button onClick={() => { setTicker(''); setFilterTicker(''); load() }} className="text-slate-500 hover:text-white text-xs font-medium cursor-pointer">{t('performance.filter_clear')}</button>}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-white/5 border border-white/[0.04] rounded-2xl animate-pulse" />)}
        </div>
      ) : perf && perf.total > 0 ? (
        <>
          {/* ── Paper Trading Stats ──────────────────────────────────────── */}
          {tradingStats && tradingStats.total_trades > 0 && (
            <div className="glass-panel rounded-2xl overflow-hidden border border-white/[0.04]">
              <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center gap-2">
                <Activity size={14} className="text-violet-400" />
                <span className="text-sm font-bold text-white">Paper Trading Performance</span>
                <span className="text-[10px] text-slate-500 ml-1">— closed positions</span>
              </div>
              <div className="p-5 space-y-5">
                {/* KPI row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Trades Closed', value: String(tradingStats.total_trades), icon: <Activity size={13} />, color: 'text-white' },
                    {
                      label: 'Trade Win Rate',
                      value: `${tradingStats.win_rate.toFixed(1)}%`,
                      icon: <Target size={13} />,
                      color: tradingStats.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400',
                    },
                    {
                      label: 'Sharpe Ratio',
                      value: tradingStats.sharpe_ratio !== null ? tradingStats.sharpe_ratio.toFixed(2) : '—',
                      icon: <TrendingUp size={13} />,
                      color: tradingStats.sharpe_ratio !== null && tradingStats.sharpe_ratio >= 1 ? 'text-emerald-400' : tradingStats.sharpe_ratio !== null && tradingStats.sharpe_ratio < 0 ? 'text-rose-400' : 'text-amber-400',
                    },
                    {
                      label: 'Max Drawdown',
                      value: tradingStats.max_drawdown_pct !== null ? `${tradingStats.max_drawdown_pct.toFixed(1)}%` : '—',
                      icon: <ShieldAlert size={13} />,
                      color: tradingStats.max_drawdown_pct !== null && tradingStats.max_drawdown_pct < -20 ? 'text-rose-400' : 'text-amber-400',
                    },
                  ].map(k => (
                    <div key={k.label} className="bg-white/[0.02] border border-white/[0.04] rounded-xl p-3 flex items-center gap-2.5">
                      <div className="text-violet-400 shrink-0">{k.icon}</div>
                      <div className="min-w-0">
                        <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider truncate">{k.label}</p>
                        <p className={`text-base font-display font-bold leading-tight ${k.color}`}>{k.value}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Best / Worst trade */}
                {(tradingStats.best_trade || tradingStats.worst_trade) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {tradingStats.best_trade && (
                      <div className="flex items-center gap-3 p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10">
                        <Trophy size={14} className="text-emerald-400 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Best Trade</p>
                          <p className="text-xs font-mono font-bold text-white">{tradingStats.best_trade.ticker}
                            <span className="text-emerald-400 ml-2">{tradingStats.best_trade.pnl_pct >= 0 ? '+' : ''}{tradingStats.best_trade.pnl_pct.toFixed(1)}%</span>
                          </p>
                          <p className="text-[9px] text-slate-500">{tradingStats.best_trade.date}</p>
                        </div>
                      </div>
                    )}
                    {tradingStats.worst_trade && (
                      <div className="flex items-center gap-3 p-3 rounded-xl bg-rose-500/5 border border-rose-500/10">
                        <Skull size={14} className="text-rose-400 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">Worst Trade</p>
                          <p className="text-xs font-mono font-bold text-white">{tradingStats.worst_trade.ticker}
                            <span className="text-rose-400 ml-2">{tradingStats.worst_trade.pnl_pct.toFixed(1)}%</span>
                          </p>
                          <p className="text-[9px] text-slate-500">{tradingStats.worst_trade.date}</p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* By-ticker table */}
                {tradingStats.by_ticker.length > 0 && (
                  <div className="overflow-x-auto rounded-xl border border-white/[0.04]">
                    <table className="w-full text-xs min-w-[380px]">
                      <thead>
                        <tr className="text-[9px] uppercase tracking-wider text-slate-500 bg-white/[0.01]">
                          <th className="px-4 py-2.5 text-left font-bold">Ticker</th>
                          <th className="px-4 py-2.5 text-center font-bold">Trades</th>
                          <th className="px-4 py-2.5 text-center font-bold">Win Rate</th>
                          <th className="px-4 py-2.5 text-right font-bold">Total P&L</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.02]">
                        {tradingStats.by_ticker.map(r => (
                          <tr key={r.ticker} className="hover:bg-white/[0.01] transition-colors">
                            <td className="px-4 py-2.5 font-mono font-bold text-white">{r.ticker}</td>
                            <td className="px-4 py-2.5 text-center text-slate-400">{r.trades}</td>
                            <td className="px-4 py-2.5 text-center">
                              <span className={`font-mono font-semibold ${r.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {r.win_rate.toFixed(0)}%
                              </span>
                            </td>
                            <td className="px-4 py-2.5 text-right font-mono font-semibold">
                              <span className={r.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                {r.total_pnl >= 0 ? '+' : ''}${r.total_pnl.toFixed(2)}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={<BarChart2 size={16} />} label={t('performance.stat_total')} value={String(perf.total)} accent="from-violet-500/10" />
            <StatCard icon={<Target size={16} />} label={t('performance.stat_win_rate')}
              value={perf.win_rate !== null ? `${perf.win_rate}%` : '—'}
              color={perf.win_rate !== null && perf.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'}
              accent={perf.win_rate !== null && perf.win_rate >= 50 ? 'from-emerald-500/10' : 'from-rose-500/10'} />
            <StatCard icon={<TrendingUp size={16} />} label={t('performance.stat_avg_raw_return')}
              value={perf.avg_raw_return !== null ? `${perf.avg_raw_return >= 0 ? '+' : ''}${perf.avg_raw_return}%` : '—'}
              color={perf.avg_raw_return !== null && perf.avg_raw_return >= 0 ? 'text-emerald-400' : 'text-rose-400'}
              accent={perf.avg_raw_return !== null && perf.avg_raw_return >= 0 ? 'from-emerald-500/10' : 'from-rose-500/10'} />
            <StatCard icon={<TrendingDown size={16} />} label={t('performance.stat_avg_alpha')}
              value={perf.avg_alpha_return !== null ? `${perf.avg_alpha_return >= 0 ? '+' : ''}${perf.avg_alpha_return}%` : '—'}
              color={perf.avg_alpha_return !== null && perf.avg_alpha_return >= 0 ? 'text-emerald-400' : 'text-rose-400'}
              accent={perf.avg_alpha_return !== null && perf.avg_alpha_return >= 0 ? 'from-emerald-500/10' : 'from-rose-500/10'} />
          </div>

          {/* Subplots Grid */}
          {bySignalData.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="glass-panel rounded-2xl p-5">
                <h3 className="text-xs font-display font-semibold text-slate-200 mb-4">{t('performance.chart_win_rate_title')}</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={bySignalData}>
                    <XAxis dataKey="signal" stroke="#6b7280" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis stroke="#6b7280" tick={{ fontSize: 9 }} domain={[0, 100]} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: 12, fontSize: 10 }} labelStyle={{ color: '#fff', fontWeight: 'bold' }} />
                    <Bar dataKey="win_rate" radius={[4, 4, 0, 0]}>
                      {bySignalData.map(d => (
                        <Cell key={d.signal} fill={d.win_rate >= 50 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="glass-panel rounded-2xl p-5">
                <h3 className="text-xs font-display font-semibold text-slate-200 mb-4">{t('performance.chart_avg_return_title')}</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={bySignalData}>
                    <XAxis dataKey="signal" stroke="#6b7280" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis stroke="#6b7280" tick={{ fontSize: 9 }} tickLine={false} />
                    <Tooltip contentStyle={{ background: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: 12, fontSize: 10 }} labelStyle={{ color: '#fff', fontWeight: 'bold' }} />
                    <Bar dataKey="avg_return" radius={[4, 4, 0, 0]}>
                      {bySignalData.map(d => (
                        <Cell key={d.signal} fill={d.avg_return >= 0 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Analyst Scorecard Panel */}
          {attribution.length > 0 && (
            <div className="glass-panel rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-white/[0.04]">
                <h3 className="text-sm font-display font-semibold text-slate-200">{t('performance.analyst_title')}</h3>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">{t('performance.analyst_subtitle')}</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-slate-300 min-w-[500px]">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                      <th className="px-5 py-3 text-left font-bold">{t('performance.col_analyst')}</th>
                      <th className="px-5 py-3 text-center font-bold">{t('performance.col_predictions')}</th>
                      <th className="px-5 py-3 text-left font-bold">{t('performance.col_accuracy')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('performance.col_weight')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.02]">
                    {attribution.map(item => (
                      <tr key={item.key} className="hover:bg-white/[0.01] transition-colors">
                        <td className="px-5 py-3.5 font-bold text-white text-xs md:text-sm">
                          <span className="flex items-center gap-1.5">
                            {item.label}
                            {item.chronic_underperformer && (
                              <span title={t('performance.chronic_underperformer_hint')} className="text-[9px] font-bold text-rose-300 bg-rose-500/15 border border-rose-500/30 px-1.5 py-0.5 rounded-full">
                                {t('performance.chronic_underperformer')}
                              </span>
                            )}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-center text-slate-400 font-mono">{item.total_predictions}</td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <span className="text-emerald-400 font-mono font-semibold w-10 text-right">{item.win_rate}%</span>
                            <div className="hidden sm:block w-24 bg-slate-800 rounded-full h-1 overflow-hidden shrink-0">
                              <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${item.win_rate}%` }} />
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <span className="inline-flex items-center text-[10px] font-bold text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20">
                            {item.weight}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Historical Returns List */}
          {history.length > 0 && (
            <div className="glass-panel rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-white/[0.04]">
                <h3 className="text-sm font-display font-semibold text-slate-200">{t('performance.history_title')}</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-slate-300 min-w-[400px]">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                      <th className="px-5 py-3 text-left font-bold">{t('performance.col_symbol')}</th>
                      <th className="px-5 py-3 text-left font-bold">{t('performance.col_date')}</th>
                      <th className="px-5 py-3 text-left font-bold">{t('performance.col_signal')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('performance.col_raw_return')}</th>
                      <th className="px-5 py-3 text-right hidden sm:table-cell font-bold">{t('performance.col_alpha')}</th>
                      <th className="px-5 py-3 text-right hidden sm:table-cell font-bold">{t('performance.col_days')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.02]">
                    {history.slice(0, 50).map(item => (
                      <tr key={item.id} className="hover:bg-white/[0.01] transition-colors">
                        <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">{item.ticker}</td>
                        <td className="px-5 py-3.5 text-slate-400 font-semibold">{item.trade_date}</td>
                        <td className="px-5 py-3.5">
                          <span className={`text-[11px] font-bold ${TONE_TEXT_CLASS[signalTone(item.signal)]}`}>{item.signal ?? '—'}</span>
                        </td>
                        <td className="px-5 py-3.5 text-right font-medium"><ReturnCell value={item.raw_return} /></td>
                        <td className="px-5 py-3.5 text-right hidden sm:table-cell font-medium"><ReturnCell value={item.alpha_return} /></td>
                        <td className="px-5 py-3.5 text-right text-slate-500 hidden sm:table-cell font-mono">{item.holding_days ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="glass-panel rounded-2xl p-12 md:p-16 text-center">
          <BarChart2 size={36} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('performance.empty_title')}</p>
          <p className="text-[10px] text-slate-500 mt-1">{t('performance.empty_subtitle')}</p>
        </div>
      )}

      {/* ── LLM Token & Cost Usage ──────────────────────────────────────── */}
      {tokenUsage && tokenUsage.total_tokens > 0 && (
        <div className="glass-panel rounded-2xl overflow-hidden border border-white/[0.04]">
          <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center gap-2">
            <Zap size={14} className="text-amber-400" />
            <span className="text-sm font-bold text-white">LLM Token & Cost Usage</span>
            <span className="text-[10px] text-slate-500 ml-1">— estimated based on public pricing</span>
          </div>
          <div className="p-5 space-y-5">
            {/* KPI row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Total Tokens', value: tokenUsage.total_tokens.toLocaleString(), icon: <Zap size={13} />, color: 'text-amber-400' },
                { label: 'Input Tokens', value: tokenUsage.total_tokens_in.toLocaleString(), icon: <TrendingUp size={13} />, color: 'text-sky-400' },
                { label: 'Output Tokens', value: tokenUsage.total_tokens_out.toLocaleString(), icon: <TrendingDown size={13} />, color: 'text-violet-400' },
                { label: 'Est. Cost (USD)', value: `$${tokenUsage.total_cost_usd.toFixed(4)}`, icon: <DollarSign size={13} />, color: 'text-emerald-400' },
              ].map(k => (
                <div key={k.label} className="bg-white/[0.02] border border-white/[0.04] rounded-xl p-3 flex items-center gap-2.5">
                  <div className="text-amber-400 shrink-0">{k.icon}</div>
                  <div className="min-w-0">
                    <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider truncate">{k.label}</p>
                    <p className={`text-base font-display font-bold leading-tight ${k.color}`}>{k.value}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Provider cost pie */}
              {tokenUsage.breakdown.length > 1 && (
                <div>
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Cost by Provider</p>
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={tokenUsage.breakdown.map(b => ({ name: b.provider, value: b.estimated_cost_usd }))}
                          innerRadius={40}
                          outerRadius={65}
                          paddingAngle={4}
                          dataKey="value"
                          stroke="none"
                        >
                          {tokenUsage.breakdown.map((_, i) => (
                            <Cell key={i} fill={['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ec4899'][i % 5]} />
                          ))}
                        </Pie>
                        <Tooltip
                          formatter={((v: unknown) => [`$${Number(v ?? 0).toFixed(4)}`, 'Est. Cost']) as unknown as undefined}
                          contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '10px', fontSize: '10px' }}
                        />
                        <Legend iconType="circle" wrapperStyle={{ fontSize: '10px' }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Daily token trend */}
              {tokenUsage.daily.length > 1 && (
                <div>
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Daily Token Usage (last 30 days)</p>
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={tokenUsage.daily} barCategoryGap="30%">
                        <XAxis dataKey="day" tick={{ fontSize: 8, fill: '#64748b' }} tickLine={false} axisLine={false}
                          tickFormatter={d => d.slice(5)} interval="preserveStartEnd" />
                        <YAxis tick={{ fontSize: 8, fill: '#64748b' }} tickLine={false} axisLine={false}
                          tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '10px', fontSize: '10px' }}
                          formatter={((v: unknown, name: unknown) => [Number(v ?? 0).toLocaleString(), name === 'tokens_in' ? 'Input' : 'Output']) as unknown as undefined}
                        />
                        <Bar dataKey="tokens_in" fill="#38bdf8" stackId="a" radius={[0, 0, 0, 0]} />
                        <Bar dataKey="tokens_out" fill="#8b5cf6" stackId="a" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>

            {/* Provider / model breakdown table */}
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">Model Breakdown</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-slate-300 min-w-[480px]">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                      <th className="px-4 py-2.5 text-left font-bold">Provider</th>
                      <th className="px-4 py-2.5 text-left font-bold">Model</th>
                      <th className="px-4 py-2.5 text-right font-bold">Analyses</th>
                      <th className="px-4 py-2.5 text-right font-bold">Input Tokens</th>
                      <th className="px-4 py-2.5 text-right font-bold">Output Tokens</th>
                      <th className="px-4 py-2.5 text-right font-bold">Est. Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.02]">
                    {tokenUsage.breakdown.map((b, i) => (
                      <tr key={i} className="hover:bg-white/[0.01] transition-colors">
                        <td className="px-4 py-3 text-slate-300 font-semibold capitalize">{b.provider}</td>
                        <td className="px-4 py-3 text-slate-400 font-mono text-[10px]">{b.model}</td>
                        <td className="px-4 py-3 text-right text-slate-400">{b.analyses}</td>
                        <td className="px-4 py-3 text-right text-sky-400 font-mono">{b.tokens_in.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-violet-400 font-mono">{b.tokens_out.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right text-emerald-400 font-mono font-bold">${b.estimated_cost_usd.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, color = 'text-white', accent = 'from-violet-500/5' }: { icon: React.ReactNode; label: string; value: string; color?: string; accent?: string }) {
  return (
    <div className={`bg-gradient-to-br ${accent} to-slate-900/40 backdrop-blur-md border border-white/[0.04] rounded-2xl p-4 flex items-start gap-3 shadow`}>
      <div className="p-2 rounded-xl bg-slate-950/60 text-violet-400 border border-white/[0.04] shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-slate-500 text-[10px] md:text-xs font-semibold uppercase tracking-wider mb-1.5 leading-none truncate">{label}</p>
        <p className={`text-base md:text-lg font-display font-bold ${color} leading-none truncate`}>{value}</p>
      </div>
    </div>
  )
}
