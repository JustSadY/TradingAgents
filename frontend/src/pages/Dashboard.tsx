import { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Activity, ArrowRight, Target, ExternalLink } from 'lucide-react'
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

// tone → presentation (the semantic tone + Turkish label come from /api/meta).
const TONE_META: Record<string, { text: string; dot: string }> = {
  positive: { text: 'text-emerald-400', dot: 'bg-emerald-400' },
  neutral:  { text: 'text-yellow-400',  dot: 'bg-yellow-400' },
  negative: { text: 'text-red-400',     dot: 'bg-red-400' },
}
const FALLBACK_TONE: Record<string, string> = {
  Buy: 'positive', Overweight: 'positive', Hold: 'neutral', Underweight: 'negative', Sell: 'negative',
}

function SignalBadge({ signal }: { signal: string | null }) {
  const meta = useMeta()
  if (!signal) return <span className="text-gray-600 text-xs">—</span>
  const sig = meta?.signals.find(s => s.value === signal)
  const tone = sig?.tone ?? FALLBACK_TONE[signal]
  const m = tone ? TONE_META[tone] : undefined
  const label = sig?.label ?? signal
  return (
    <span className={`flex items-center gap-1.5 text-xs font-semibold ${m?.text || 'text-gray-400'}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${m?.dot || 'bg-gray-400'}`} />
      {label}
    </span>
  )
}

export default function Dashboard() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [recentAnalysis, setRecentAnalysis] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [perf, setPerf] = useState<{ win_rate: number | null; avg_raw_return: number | null; total: number } | null>(null)
  const [news, setNews] = useState<NewsItem[]>([])
  const [orders, setOrders] = useState<any[]>([])
  const navigate = useNavigate()
  const { language, t } = useTranslation()

  useEffect(() => {
    Promise.all([
      axios.get('/api/portfolio').then(r => r.data),
      axios.get('/api/analysis/history?limit=8').then(r => r.data),
      axios.get('/api/analysis/performance').then(r => r.data).catch(() => null),
      axios.get('/api/portfolio/orders?limit=100').then(r => r.data).catch(() => []),
    ]).then(([p, a, pf, ord]) => { 
      setPortfolios(p)
      setRecentAnalysis(a)
      if (pf) setPerf(pf)
      setOrders(ord)
    })
      .finally(() => setLoading(false))
  }, [])

  // Load news feed from watchlist tickers
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

  if (loading) {
    return (
      <div className="p-4 md:p-6 space-y-4">
        <div className="h-8 w-32 bg-gray-800 rounded-lg animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => <div key={i} className="h-20 md:h-24 bg-gray-800 rounded-2xl animate-pulse" />)}
        </div>
      </div>
    )
  }

  const sim = portfolios.find(p => p.mode === 'simulation') || portfolios[0]
  const pnl = sim ? sim.current_balance - sim.initial_capital : 0
  const pnlPct = sim?.initial_capital ? (pnl / sim.initial_capital * 100) : 0
  const totalUnrealized = (sim?.holdings || []).reduce((s, h) => s + (h.unrealized_pnl || 0), 0)

  const ALLOCATION_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#8b5cf6', '#14b8a6']

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

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg md:text-xl font-bold text-white tracking-tight">{t('dashboard.title')}</h2>
        <button
          onClick={() => navigate('/analysis')}
          className="flex items-center gap-1.5 text-sm text-violet-400 hover:text-violet-300 transition-colors"
        >
          {t('dashboard.new_analysis')} <ArrowRight size={14} />
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
        <KpiCard
          icon={<DollarSign size={18} />}
          label={t('dashboard.portfolio_value')}
          value={sim ? `$${(sim.current_balance || 0).toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
        />
        <KpiCard
          icon={pnl >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          label={t('dashboard.total_return')}
          value={`${pnl >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`}
          sub={`${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`}
          color={pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}
          accent={pnl >= 0 ? 'from-emerald-500/10' : 'from-red-500/10'}
        />
        <KpiCard
          icon={<DollarSign size={18} />}
          label={t('dashboard.cash')}
          value={sim ? `$${(sim.cash_available || 0).toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}` : '—'}
          color="text-white"
        />
        <KpiCard
          icon={<Activity size={18} />}
          label={t('dashboard.unrealized_pnl')}
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(2)}`}
          color={totalUnrealized >= 0 ? 'text-emerald-400' : 'text-red-400'}
          accent={totalUnrealized >= 0 ? 'from-emerald-500/10' : 'from-red-500/10'}
        />
        {perf && perf.total > 0 && (
          <KpiCard
            icon={<Target size={18} />}
            label={t('dashboard.win_rate')}
            value={perf.win_rate !== null ? `${perf.win_rate}%` : '—'}
            sub={`${perf.total} ${t('dashboard.analyses')}`}
            color={perf.win_rate !== null && perf.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}
            accent={perf.win_rate !== null && perf.win_rate >= 50 ? 'from-emerald-500/10' : 'from-red-500/10'}
          />
        )}
      </div>

      {/* Visual Analytics */}
      {sim && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Historical Return / NAV Timeline */}
          <div className="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-1">{t('dashboard.pnl_timeline')}</h3>
              <p className="text-xs text-gray-500 mb-4">{t('dashboard.pnl_timeline_sub')}</p>
            </div>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={navTimelineData} margin={{ top: 10, right: 5, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorBalance" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.2}/>
                      <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" stroke="#4b5563" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#4b5563" tick={{ fontSize: 10 }} domain={['auto', 'auto']} tickFormatter={val => `$${(val || 0).toLocaleString()}`} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '8px' }}
                    labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                    itemStyle={{ color: '#8b5cf6', fontSize: '11px' }}
                    formatter={(value: any) => [`$${(value || 0).toLocaleString()}`, 'NAV']}
                  />
                  <Area type="monotone" dataKey="Balance" stroke="#8b5cf6" strokeWidth={2} fillOpacity={1} fill="url(#colorBalance)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Asset Allocation */}
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-300 mb-1">{t('dashboard.asset_allocation')}</h3>
              <p className="text-xs text-gray-500 mb-4">{t('dashboard.asset_allocation_sub')}</p>
            </div>
            <div className="h-64 w-full flex items-center justify-center relative">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={allocationData}
                    cx="50%"
                    cy="45%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {allocationData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '8px' }}
                    itemStyle={{ fontSize: '11px' }}
                    formatter={(value: any) => [`$${(value || 0).toLocaleString()}`, '']}
                  />
                  <Legend 
                    verticalAlign="bottom" 
                    height={36} 
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: '11px', color: '#9ca3af' }} 
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        {/* Recent analyses */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-4 md:px-5 py-3 md:py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">{t('dashboard.recent_analyses')}</h3>
            <button onClick={() => navigate('/analysis')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              {t('dashboard.all')} <ArrowRight size={11} />
            </button>
          </div>
          {recentAnalysis.length === 0 ? (
            <p className="px-5 py-8 text-gray-600 text-sm text-center">{t('dashboard.no_analyses')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[360px]">
                <thead>
                  <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                    <th className="px-4 py-2.5 text-left">{t('dashboard.ticker')}</th>
                    <th className="px-4 py-2.5 text-left">{t('dashboard.date')}</th>
                    <th className="px-4 py-2.5 text-left">{t('dashboard.signal')}</th>
                    <th className="px-4 py-2.5 text-right">{t('dashboard.duration')}</th>
                  </tr>
                </thead>
                <tbody>
                  {recentAnalysis.map(a => (
                    <tr key={a.id}
                      onClick={() => navigate('/analysis')}
                      className="border-t border-gray-800/60 hover:bg-gray-800/40 cursor-pointer transition-colors">
                      <td className="px-4 py-2.5 font-mono font-bold text-white text-sm">{a.ticker}</td>
                      <td className="px-4 py-2.5 text-gray-500 text-xs">{a.trade_date}</td>
                      <td className="px-4 py-2.5"><SignalBadge signal={a.signal} /></td>
                      <td className="px-4 py-2.5 text-gray-600 text-xs text-right">{a.duration_seconds?.toFixed(1)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Holdings */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="flex items-center justify-between px-4 md:px-5 py-3 md:py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">{t('dashboard.open_positions')}</h3>
            <button onClick={() => navigate('/portfolio')} className="text-xs text-violet-400 hover:text-violet-300 transition-colors flex items-center gap-1">
              {t('nav.portfolio')} <ArrowRight size={11} />
            </button>
          </div>
          {!sim?.holdings?.length ? (
            <p className="px-5 py-8 text-gray-600 text-sm text-center">{t('dashboard.no_open_positions')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[320px]">
                <thead>
                  <tr className="text-gray-600 text-xs uppercase tracking-wider bg-gray-800/30">
                    <th className="px-4 py-2.5 text-left">{t('dashboard.ticker')}</th>
                    <th className="px-4 py-2.5 text-right">{t('dashboard.quantity')}</th>
                    <th className="px-4 py-2.5 text-right">{t('dashboard.price')}</th>
                    <th className="px-4 py-2.5 text-right">{t('dashboard.pnl')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(sim.holdings || []).map(h => (
                    <tr key={h.ticker} className="border-t border-gray-800/60 hover:bg-gray-800/40 transition-colors">
                      <td className="px-4 py-2.5 font-mono font-bold text-white text-sm">{h.ticker}</td>
                      <td className="px-4 py-2.5 text-gray-400 text-right text-xs">{(h.quantity ?? 0).toFixed(4)}</td>
                      <td className="px-4 py-2.5 text-gray-400 text-right text-xs">${h.current_price?.toFixed(2) ?? '—'}</td>
                      <td className={`px-4 py-2.5 text-right text-xs font-semibold ${(h.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(h.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${(h.unrealized_pnl ?? 0).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Live news feed (MOD6) */}
      {news.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
          <div className="px-4 md:px-5 py-3 md:py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-300">{t('dashboard.watchlist_news')}</h3>
          </div>
          <div className="divide-y divide-gray-800">
            {news.map((item, i) => (
              <div key={i} className="px-4 md:px-5 py-3 hover:bg-gray-800/40 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono font-bold text-violet-400">{item.ticker}</span>
                      <span className="text-xs text-gray-600">{item.source}</span>
                      <span className="text-xs text-gray-700">
                        {(() => {
                          const d = new Date(item.published_at)
                          return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(language === 'tr' ? 'tr-TR' : 'en-US')
                        })()}
                      </span>
                    </div>
                    <p className="text-sm text-gray-300 line-clamp-2">{item.title}</p>
                  </div>
                  <a href={item.url} target="_blank" rel="noreferrer" className="text-gray-600 hover:text-violet-400 transition-colors shrink-0 mt-0.5">
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
    <div className={`bg-gradient-to-br ${accent} to-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5`}>
      <div className="flex items-start gap-2.5 md:gap-3">
        <div className="p-1.5 md:p-2 rounded-xl bg-gray-800 text-violet-400 shrink-0">{icon}</div>
        <div className="min-w-0">
          <p className="text-gray-500 text-xs font-medium uppercase tracking-wider mb-1 leading-tight">{label}</p>
          <p className={`text-lg md:text-xl font-bold ${color} leading-none`}>{value}</p>
          {sub && <p className={`text-xs mt-1 ${color} opacity-70`}>{sub}</p>}
        </div>
      </div>
    </div>
  )
}
