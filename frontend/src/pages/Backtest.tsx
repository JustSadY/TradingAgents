import { useState } from 'react'
import { useTradingRunBacktest } from '../api/generated/trading/trading'
import {
  Play, BarChart2, TrendingUp, TrendingDown, Target, Search,
  Landmark, AlertCircle, Sparkles, Loader2
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useTranslation } from '../contexts/LanguageContext'

interface Trade {
  entry_date: string
  exit_date: string
  side: 'long' | 'short'
  entry_price: number
  exit_price: number
  return_pct: number
  pnl: number
  reason: string
}

interface EquityPoint {
  date: string
  value: number
  cash: number
  holdings_value: number
}

interface BacktestResults {
  initial_capital: number
  final_value: number
  total_return: number
  win_rate: number
  max_drawdown: number
  sharpe_ratio: number
  trades_count: number
  trades: Trade[]
  equity_curve: EquityPoint[]
  slippage_bps?: number
  benchmark?: { ticker: string; return_pct: number } | null
  alpha_pct?: number | null
}

const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

export default function Backtest() {
  const { t } = useTranslation()
  const [ticker, setTicker] = useState('')
  const [strategy, setStrategy] = useState('consensus')
  const [startDate, setStartDate] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 1)
    return d.toISOString().split('T')[0]
  })
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0])
  const [initialCapital, setInitialCapital] = useState('100000')

  const [error, setError] = useState<string | null>(null)

  const backtest = useTradingRunBacktest()
  const loading = backtest.isPending
  const results = (backtest.data ?? null) as BacktestResults | null

  const handleRun = async () => {
    const sym = ticker.trim().toUpperCase()
    const cap = Number.parseFloat(initialCapital)
    if (!sym) {
      setError(t('common.error') + ': Please specify a symbol')
      return
    }
    if (!startDate || !endDate) {
      setError(t('backtest.error_dates'))
      return
    }
    if (Number.isNaN(cap) || cap <= 0) {
      setError(t('common.error') + ': Initial capital must be positive')
      return
    }

    setError(null)
    // Clear the previous run first: useMutation keeps `data` until the next
    // success, which would leave stale numbers on screen while pending.
    backtest.reset()
    backtest.mutate(
      {
        data: {
          ticker: sym,
          strategy_type: strategy,
          start_date: startDate,
          end_date: endDate,
          initial_capital: cap,
        },
      },
      {
        onError: (err) => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          setError(detail || t('backtest.error_load'))
        },
      },
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('backtest.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">Run simulations of indicators or agent decisions over a historical window to optimize risk strategies.</p>
      </div>

      {/* Setup Form */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('backtest.ticker')}</label>
            <div className="flex items-center gap-2 bg-slate-900 border border-white/[0.08] rounded-xl px-3 py-1.5 focus-within:border-violet-500/50 transition-colors">
              <Search size={14} className="text-slate-500" />
              <input className="bg-transparent text-white text-xs outline-none w-full uppercase font-mono font-semibold"
                placeholder="AAPL" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} />
            </div>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('backtest.strategy')}</label>
            <select className={Input} value={strategy} onChange={e => setStrategy(e.target.value)}>
              <option value="consensus">{t('backtest.consensus')}</option>
              <option value="macd_crossover">{t('backtest.macd')}</option>
              <option value="rsi_oversold">{t('backtest.rsi')}</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('backtest.start_date')}</label>
            <input className={Input} type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('backtest.end_date')}</label>
            <input className={Input} type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('backtest.initial_capital')}</label>
            <input className={Input} type="number" value={initialCapital} onChange={e => setInitialCapital(e.target.value)} />
          </div>
        </div>

        {error && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-center gap-2 text-rose-400 text-xs font-semibold">
            <AlertCircle size={14} /> {error}
          </div>
        )}

        <button onClick={handleRun} disabled={loading}
          className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 text-white text-xs font-bold px-5 py-2.5 rounded-xl transition cursor-pointer">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} fill="currentColor" />}
          {loading ? t('backtest.running') : t('backtest.run_btn')}
        </button>
      </div>

      {loading && (
        <div className="glass-panel rounded-2xl p-16 text-center space-y-4">
          <Loader2 size={36} className="mx-auto text-violet-500 animate-spin" />
          <p className="text-slate-400 text-xs font-semibold">{t('backtest.running')}</p>
        </div>
      )}

      {!loading && !results && (
        <div className="glass-panel rounded-2xl p-16 text-center">
          <BarChart2 size={36} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('backtest.empty')}</p>
        </div>
      )}

      {results && (
        <div className="space-y-6 animate-in fade-in duration-300">
          {/* Stats Dashboard */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <StatCard icon={<Landmark size={16} />} label="Final Balance" value={`$${results.final_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}`} />
            <StatCard icon={<TrendingUp size={16} />} label={t('backtest.stats_total_return')} value={`${results.total_return >= 0 ? '+' : ''}${results.total_return}%`} color={results.total_return >= 0 ? 'text-emerald-400' : 'text-rose-400'} accent={results.total_return >= 0 ? 'from-emerald-500/10' : 'from-rose-500/10'} />
            <StatCard icon={<Target size={16} />} label={t('backtest.stats_win_rate')} value={`${results.win_rate}%`} color={results.win_rate >= 50 ? 'text-emerald-400' : 'text-rose-400'} accent={results.win_rate >= 50 ? 'from-emerald-500/10' : 'from-rose-500/10'} />
            <StatCard icon={<TrendingDown size={16} />} label={t('backtest.stats_max_dd')} value={`${results.max_drawdown}%`} color="text-rose-400" accent="from-rose-500/10" />
            <StatCard icon={<Sparkles size={16} />} label={t('backtest.stats_sharpe')} value={String(results.sharpe_ratio)} color={results.sharpe_ratio >= 1.5 ? 'text-emerald-400' : results.sharpe_ratio >= 0 ? 'text-slate-200' : 'text-rose-400'} />
          </div>

          {results.benchmark && results.alpha_pct != null && (
            <div className="glass-panel rounded-2xl p-4 flex items-center justify-between text-xs">
              <span className="text-slate-400 font-semibold">
                {t('backtest.vs_benchmark').replace('{ticker}', results.benchmark.ticker)}: <span className={results.benchmark.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{results.benchmark.return_pct >= 0 ? '+' : ''}{results.benchmark.return_pct}%</span>
              </span>
              <span className="font-bold">
                {t('backtest.alpha')}: <span className={results.alpha_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{results.alpha_pct >= 0 ? '+' : ''}{results.alpha_pct}%</span>
              </span>
              {results.slippage_bps != null && (
                <span className="text-slate-500">{t('backtest.slippage_applied').replace('{bps}', String(results.slippage_bps))}</span>
              )}
            </div>
          )}

          {/* Chart Section */}
          <div className="glass-panel rounded-2xl p-5 space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">{t('backtest.curve_title')}</h3>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={results.equity_curve}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#7c3aed" stopOpacity={0.2}/>
                      <stop offset="95%" stopColor="#7c3aed" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                  <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 9 }} tickLine={false} />
                  <YAxis stroke="#6b7280" tick={{ fontSize: 9 }} tickLine={false} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ background: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: 12, fontSize: 10 }} labelStyle={{ color: '#fff', fontWeight: 'bold' }} />
                  <Area type="monotone" dataKey="value" stroke="#8b5cf6" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" name="Account Value" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Executed Trades Log */}
          <div className="glass-panel rounded-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-white/[0.04]">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">{t('backtest.trades_title')} ({results.trades_count})</h3>
            </div>
            {results.trades.length === 0 ? (
              <div className="p-8 text-slate-600 text-xs text-center font-medium">No trades executed during this simulation period.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-slate-300 min-w-[500px]">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                      <th className="px-5 py-3 text-left font-bold">{t('backtest.col_entry')}</th>
                      <th className="px-5 py-3 text-left font-bold">{t('backtest.col_exit')}</th>
                      <th className="px-5 py-3 text-center font-bold">{t('backtest.col_side')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('backtest.col_entry_price')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('backtest.col_exit_price')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('backtest.col_pnl')}</th>
                      <th className="px-5 py-3 text-right font-bold">{t('backtest.col_return')}</th>
                      <th className="px-5 py-3 text-center font-bold">{t('backtest.col_reason')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.02]">
                    {results.trades.map((trade, i) => (
                      <tr key={i} className="hover:bg-white/[0.01] transition-colors">
                        <td className="px-5 py-3.5 font-mono text-slate-400">{trade.entry_date}</td>
                        <td className="px-5 py-3.5 font-mono text-slate-400">{trade.exit_date}</td>
                        <td className="px-5 py-3.5 text-center">
                          <span className={`px-2 py-0.5 rounded-lg text-[10px] uppercase font-bold tracking-wide ${trade.side === 'long' ? 'text-emerald-400 bg-emerald-500/10' : 'text-amber-400 bg-amber-500/10'}`}>
                            {trade.side}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-right font-mono font-semibold">${trade.entry_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className="px-5 py-3.5 text-right font-mono font-semibold">${trade.exit_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                        <td className={`px-5 py-3.5 text-right font-mono font-bold ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                        </td>
                        <td className={`px-5 py-3.5 text-right font-mono font-bold ${trade.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {trade.return_pct >= 0 ? '+' : ''}{trade.return_pct.toFixed(2)}%
                        </td>
                        <td className="px-5 py-3.5 text-center">
                          <span className="text-[10px] font-bold text-slate-500 bg-white/5 border border-white/[0.04] px-2 py-0.5 rounded-lg uppercase tracking-wide">
                            {trade.reason}
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
