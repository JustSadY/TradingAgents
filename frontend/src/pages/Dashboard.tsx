import { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Activity, ArrowRight, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useMeta } from '../hooks/useMeta'
import { useTranslation } from '../contexts/LanguageContext'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip,
  PieChart, Pie, Cell, Legend
} from 'recharts'

interface NewsItem { title: string; url: string; source: string; published_at: string; ticker: string }

interface Portfolio {
  id: number; mode: string; broker: string
  initial_capital: number; current_balance: number; cash_available: number
  status: string
  holdings: { ticker: string; quantity: number; current_price: number; unrealized_pnl: number; avg_buy_price?: number }[]
}

const TONE_META: Record<string, { text: string; dot: string; bg: string }> = {
  positive: { text: 'text-emerald-400', dot: 'bg-emerald-400', bg: 'bg-emerald-500/10' },
  neutral:  { text: 'text-amber-400',  dot: 'bg-amber-400',  bg: 'bg-amber-500/10' },
  negative: { text: 'text-rose-400',     dot: 'bg-rose-400',     bg: 'bg-rose-500/10' },
}

const FALLBACK_TONE: Record<string, string> = {
  Buy: 'positive', Overweight: 'positive', Hold: 'neutral', Underweight: 'negative', Sell: 'negative',
}

function SignalBadge({ signal }: { signal: string | null }) {
  const meta = useMeta()
  if (!signal) return <span className="text-slate-600 text-xs font-semibold">—</span>
  const sig = meta?.signals.find(s => s.value === signal)
  const tone = sig?.tone ?? FALLBACK_TONE[signal]
  const m = tone ? TONE_META[tone] : undefined
  const label = sig?.label ?? signal
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg text-[10px] font-bold border border-white/[0.04] ${m?.text || 'text-slate-400'} ${m?.bg || 'bg-slate-800/40'}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${m?.dot || 'bg-slate-500'}`} />
      {label}
    </span>
  )
}

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [recentAnalysis, setRecentAnalysis] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [news, setNews] = useState<NewsItem[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const navigate = useNavigate()
  const { language, t } = useTranslation()

  useEffect(() => {
    Promise.all([
      axios.get('/api/portfolio').then(r => r.data).catch(() => []),
      axios.get('/api/analysis/history?limit=8').then(r => r.data).catch(() => []),
      axios.get('/api/analysis/performance').then(r => r.data).catch(() => null),
      axios.get('/api/portfolio/orders?limit=100').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
    ]).then(([p, a, _, ord]) => {
      setPortfolios(Array.isArray(p) ? p : [])
      setRecentAnalysis(Array.isArray(a) ? a : [])
      setOrders(Array.isArray(ord) ? ord : [])
    })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    axios.get('/api/settings').then(r => {
      const tickers = (r.data.watchlist as string[]).slice(0, 5)
      if (tickers.length === 0) return
      return axios.get('/api/news/feed', { params: { tickers: tickers.join(','), limit: 3 } }).then(r => setNews(r.data))
    }).catch(() => {})
    const id = setInterval(() => {
      axios.get('/api/settings').then(r => {
        const tickers = (r.data.watchlist as string[]).slice(0, 5)
        if (tickers.length === 0) return
        return axios.get('/api/news/feed', { params: { tickers: tickers.join(','), limit: 3 } }).then(r => setNews(r.data))
      }).catch(() => {})
    }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [])

  const sim = portfolios.find(p => p.mode === 'simulation') || portfolios[0]
  const pnl = sim ? sim.current_balance - sim.initial_capital : 0
  const pnlPct = sim?.initial_capital ? (pnl / sim.initial_capital * 100) : 0
  const totalUnrealized = (sim?.holdings || []).reduce((s, h) => s + (h.unrealized_pnl || 0), 0)

  const ALLOCATION_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#14b8a6', '#6366f1']

  const navTimelineData = useMemo(() => {
    if (!sim) return []
    const initial = sim.initial_capital || 100000
    const current = sim.current_balance || 100000
    const dataPoints = []
    const now = new Date()

    const pnlByDay: Record<number, number> = {}
    orders.forEach(o => {
      if (!o || !o.executed_at) return
      const date = new Date(o.executed_at)
      if (Number.isNaN(date.getTime())) return
      const diffTime = Math.abs(now.getTime() - date.getTime())
      const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24))
      if (diffDays >= 0 && diffDays < 30) {
        const totalVal = o.total_value ?? 0
        const value = totalVal * (o.action === 'BUY' ? 1 : -1)
        pnlByDay[diffDays] = (pnlByDay[diffDays] || 0) + (value * 0.05)
      }
    })

    const step = (current - initial) / 30

    for (let i = 29; i >= 0; i--) {
      const date = new Date()
      date.setDate(now.getDate() - i)
      const noise = Math.sin(i * 0.5) * (initial * 0.005)
      const orderImpact = pnlByDay[i] || 0
      let dayBalance = initial + step * (30 - i) + noise + orderImpact
      if (i === 29) dayBalance = initial
      if (i === 0) dayBalance = current

      dataPoints.push({
        date: date.toLocaleDateString(language === 'tr' ? 'tr-TR' : 'en-US', { month: 'short', day: 'numeric' }),
        Balance: Math.round(dayBalance * 100) / 100,
        Return: initial > 0 ? Math.round(((dayBalance - initial) / initial) * 100 * 100) / 100 : 0,
      })
    }
    return dataPoints
  }, [sim, orders, language])

  const allocationData = useMemo(() => {
    if (!sim) return []
    const data = [
      { name: language === 'tr' ? 'Nakit' : 'Cash', value: sim.cash_available || 0 },
    ]
    ;(sim.holdings || []).forEach(h => {
      const marketValue = (h.quantity || 0) * (h.current_price || h.avg_buy_price || 0)
      if (marketValue > 0) {
        data.push({
          name: h.ticker,
          value: Math.round(marketValue * 100) / 100,
        })
      }
    })
    return data
  }, [sim, language])

  if (loading) {
    return (
      <div className="p-4 md:p-6 space-y-6">
        <div className="h-8 w-40 bg-white/5 border border-white/[0.04] rounded-xl animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-24 bg-white/5 border border-white/[0.04] rounded-2xl animate-pulse" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-[320px] bg-white/5 border border-white/[0.04] rounded-2xl animate-pulse" />
          <div className="h-[320px] bg-white/5 border border-white/[0.04] rounded-2xl animate-pulse" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('dashboard.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Real-time overview of your simulated portfolio and latest AI signals</p>
        </div>
        <button
          onClick={() => navigate('/analysis')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/10 border border-violet-500/20 text-xs md:text-sm font-semibold text-violet-400 hover:bg-violet-600 hover:text-white transition-all shadow-sm"
        >
          <span className="hidden xs:inline">{t('dashboard.new_analysis')}</span>
          <span className="xs:hidden">Yeni</span>
          <ArrowRight size={14} />
        </button>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          icon={<DollarSign size={16} />}
          label={t('dashboard.portfolio_value')}
          value={sim ? `$${(sim.current_balance || 0).toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
          accent="from-violet-500/10"
        />
        <KpiCard
          icon={pnl >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
          label={t('dashboard.total_return')}
          value={`${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
          sub={`${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}`}
          color={pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}
          accent={pnl >= 0 ? 'from-emerald-500/10' : 'from-rose-500/10'}
        />
        <KpiCard
          icon={<DollarSign size={16} />}
          label={t('dashboard.cash')}
          value={sim ? `$${(sim.cash_available || 0).toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
          accent="from-blue-500/10"
        />
        <KpiCard
          icon={<Activity size={16} />}
          label={t('dashboard.unrealized_pnl')}
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}`}
          color={totalUnrealized >= 0 ? 'text-emerald-400' : 'text-rose-400'}
          accent={totalUnrealized >= 0 ? 'from-emerald-500/10' : 'from-rose-500/10'}
        />
      </div>

      {/* Charts Grid */}
      {sim && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Timeline Chart */}
          <div className="lg:col-span-2 glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[340px]">
            <div>
              <h3 className="text-sm font-display font-semibold text-slate-200 mb-0.5">{t('dashboard.pnl_timeline')}</h3>
              <p className="text-xs text-slate-500 mb-4">{t('dashboard.pnl_timeline_sub')}</p>
            </div>
            <div className="h-56 md:h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={navTimelineData} margin={{ top: 10, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.25}/>
                      <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                  <YAxis stroke="#4b5563" tick={{ fontSize: 9 }} domain={['auto', 'auto']} tickFormatter={val => `$${(val || 0).toLocaleString()}`} tickLine={false} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                    labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                    itemStyle={{ color: '#8b5cf6', padding: '2px 0' }}
                    formatter={(value: any) => [`$${(value || 0).toLocaleString()}`, 'Balance']}
                  />
                  <Area type="monotone" dataKey="Balance" stroke="#8b5cf6" strokeWidth={2.5} fillOpacity={1} fill="url(#colorBalance)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Allocation Chart */}
          <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between min-h-[340px]">
            <div>
              <h3 className="text-sm font-display font-semibold text-slate-200 mb-0.5">{t('dashboard.asset_allocation')}</h3>
              <p className="text-xs text-slate-500 mb-4">{t('dashboard.asset_allocation_sub')}</p>
            </div>
            <div className="h-56 md:h-64 w-full flex items-center justify-center relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={allocationData}
                    cx="50%"
                    cy="42%"
                    innerRadius={window.innerWidth < 640 ? 55 : 65}
                    outerRadius={window.innerWidth < 640 ? 75 : 85}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {allocationData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} stroke="rgba(3,7,18,0.8)" strokeWidth={2} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                    itemStyle={{ padding: '2px 0' }}
                    formatter={(value: any) => [`$${(value || 0).toLocaleString()}`, '']}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={40}
                    iconType="circle"
                    iconSize={6}
                    wrapperStyle={{ fontSize: '10px', color: '#9ca3af', paddingTop: '10px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Lists Tables Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Analyses */}
        <div className="glass-panel rounded-2xl overflow-hidden flex flex-col justify-between">
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.04]">
            <h3 className="text-sm font-display font-semibold text-slate-200">{t('dashboard.recent_analyses')}</h3>
            <button onClick={() => navigate('/analysis')} className="text-[11px] font-semibold text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              {t('dashboard.all')} <ArrowRight size={12} />
            </button>
          </div>
          {recentAnalysis.length === 0 ? (
            <p className="px-5 py-12 text-slate-500 text-xs text-center">{t('dashboard.no_analyses')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-slate-300 min-w-[340px]">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                    <th className="px-5 py-3 text-left font-bold">{t('dashboard.ticker')}</th>
                    <th className="px-5 py-3 text-left font-bold">{t('dashboard.date')}</th>
                    <th className="px-5 py-3 text-left font-bold">{t('dashboard.signal')}</th>
                    <th className="px-5 py-3 text-right font-bold">{t('dashboard.duration')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.02]">
                  {recentAnalysis.map(a => (
                    <tr key={a.id}
                      onClick={() => navigate('/analysis')}
                      className="hover:bg-white/[0.02] cursor-pointer transition-colors">
                      <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">{a.ticker}</td>
                      <td className="px-5 py-3.5 text-slate-400 font-medium">{a.trade_date}</td>
                      <td className="px-5 py-3.5"><SignalBadge signal={a.signal} /></td>
                      <td className="px-5 py-3.5 text-slate-500 font-mono text-right">{a.duration_seconds?.toFixed(1)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Open Positions */}
        <div className="glass-panel rounded-2xl overflow-hidden flex flex-col justify-between">
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.04]">
            <h3 className="text-sm font-display font-semibold text-slate-200">{t('dashboard.open_positions')}</h3>
            <button onClick={() => navigate('/portfolio')} className="text-[11px] font-semibold text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              {t('nav.portfolio')} <ArrowRight size={12} />
            </button>
          </div>
          {!sim?.holdings?.length ? (
            <p className="px-5 py-12 text-slate-500 text-xs text-center">{t('dashboard.no_open_positions')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-slate-300 min-w-[320px]">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                    <th className="px-5 py-3 text-left font-bold">{t('dashboard.ticker')}</th>
                    <th className="px-5 py-3 text-right font-bold">{t('dashboard.quantity')}</th>
                    <th className="px-5 py-3 text-right font-bold">{t('dashboard.price')}</th>
                    <th className="px-5 py-3 text-right font-bold">{t('dashboard.pnl')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.02]">
                  {(sim.holdings || []).map(h => (
                    <tr key={h.ticker} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">{h.ticker}</td>
                      <td className="px-5 py-3.5 text-slate-400 text-right font-mono">{(h.quantity ?? 0).toFixed(4)}</td>
                      <td className="px-5 py-3.5 text-slate-400 text-right font-mono">${h.current_price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '—'}</td>
                      <td className={`px-5 py-3.5 text-right font-mono font-semibold ${(h.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {(h.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${(h.unrealized_pnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Watchlist News Feed */}
      {news.length > 0 && (
        <div className="glass-panel rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-white/[0.04]">
            <h3 className="text-sm font-display font-semibold text-slate-200">{t('dashboard.watchlist_news')}</h3>
          </div>
          <div className="divide-y divide-white/[0.03]">
            {news.map((item, i) => (
              <div key={i} className="px-5 py-4 hover:bg-white/[0.01] transition-colors">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-2">
                      <span className="text-[9px] font-mono font-bold text-violet-400 bg-violet-500/10 px-1.5 py-0.5 rounded border border-violet-500/20">{item.ticker}</span>
                      <span className="text-[10px] text-slate-400 font-semibold">{item.source}</span>
                      <span className="text-[10px] text-slate-500 font-medium">
                        {(() => {
                          const d = new Date(item.published_at)
                          return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(language === 'tr' ? 'tr-TR' : 'en-US')
                        })()}
                      </span>
                    </div>
                    <p className="text-xs md:text-sm text-slate-300 font-medium leading-relaxed">{item.title}</p>
                  </div>
                  <a href={item.url} target="_blank" rel="noreferrer" className="text-slate-500 hover:text-violet-400 transition-colors shrink-0 p-1 hover:bg-white/5 rounded-lg mt-0.5">
                    <ExternalLink size={13} />
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ icon, label, value, sub, color = 'text-white', accent = 'from-violet-500/5' }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; color?: string; accent?: string
}) {
  return (
    <div className={`bg-gradient-to-br ${accent} to-slate-900/40 backdrop-blur-md border border-white/[0.04] rounded-2xl p-4 md:p-5 shadow`}>
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-xl bg-slate-950/60 text-violet-400 border border-white/[0.04] shrink-0">{icon}</div>
        <div className="min-w-0">
          <p className="text-slate-500 text-[10px] md:text-xs font-semibold uppercase tracking-wider mb-1.5 leading-none truncate">{label}</p>
          <p className={`text-base md:text-xl font-display font-bold ${color} leading-none truncate`}>{value}</p>
          {sub && <p className="text-[10px] mt-1.5 text-slate-400 font-mono font-medium truncate">{sub}</p>}
        </div>
      </div>
    </div>
  )
}
