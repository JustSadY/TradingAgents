import { useEffect, useState } from 'react'
import axios from 'axios'
import { BarChart2, TrendingUp, TrendingDown, Target, Search } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { useTranslation } from '../contexts/LanguageContext'

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
  const [ticker, setTicker] = useState('')
  const [filterTicker, setFilterTicker] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async (ti?: string) => {
    setLoading(true)
    try {
      const [p, h, attr] = await Promise.all([
        axios.get('/api/analysis/performance', { params: ti ? { ticker: ti } : {} }).then(r => r.data),
        axios.get('/api/analysis/history', { params: { limit: 100, ...(ti ? { ticker: ti } : {}) } }).then(r => r.data),
        axios.get('/api/analysis/performance-attribution').then(r => r.data).catch(() => ({ attribution: [] })),
      ])
      setPerf(p)
      setHistory(h.filter((x: HistoryItem) => x.raw_return !== null))
      setAttribution(attr.attribution || [])
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

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
                        <td className="px-5 py-3.5 font-bold text-white text-xs md:text-sm">{item.label}</td>
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
                          <span className={`text-[11px] font-bold ${
                            ['Buy','Overweight'].includes(item.signal||'') ? 'text-emerald-400' :
                            ['Sell','Underweight'].includes(item.signal||'') ? 'text-rose-400' : 'text-amber-400'
                          }`}>{item.signal ?? '—'}</span>
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
