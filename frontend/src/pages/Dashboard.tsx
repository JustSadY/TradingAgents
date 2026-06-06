import { useEffect, useState, useMemo } from 'react'
import api from '../utils/api'
import { Activity } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { ErrorBoundary } from '../components/ErrorBoundary'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { usePortfolio } from '../hooks/usePortfolio'
import { useNewsFeed } from '../hooks/useNewsFeed'

// Components
import { PortfolioOverview } from '../components/dashboard/PortfolioOverview'
import { RecentAnalysisTable } from '../components/dashboard/RecentAnalysisTable'
import { NewsFeed } from '../components/dashboard/NewsFeed'

const ALLOCATION_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#14b8a6', '#6366f1']

export default function Dashboard() {
  const { t } = useTranslation()
  const { sim, stats, allocationData, loading: portfolioLoading } = usePortfolio()
  const [watchlist, setWatchlist] = useState<string[]>([])
  
  const watchlistSlice = useMemo(() => watchlist.slice(0, 5), [watchlist])
  const { news, loading: newsLoading } = useNewsFeed(watchlistSlice)
  
  const [recentAnalysis, setRecentAnalysis] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch only what's not covered by hooks
    Promise.all([
      api.get('/api/analysis/history?limit=8').then(r => r.data).catch(() => []),
      api.get('/api/settings').then(r => r.data.watchlist || []).catch(() => []),
    ]).then(([a, w]) => {
      setRecentAnalysis(Array.isArray(a) ? a : [])
      setWatchlist(w)
    })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading || portfolioLoading) return (
    <div className="h-[80vh] flex flex-col items-center justify-center space-y-4 opacity-50">
        <Activity className="text-violet-500 animate-pulse" size={32} />
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Synchronizing Engine...</p>
    </div>
  )

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('dashboard.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Multi-agent portfolio summary and live market intelligence</p>
        </div>
      </div>

      <PortfolioOverview sim={sim} pnl={stats.pnl} pnlPct={stats.pnlPct} totalUnrealized={stats.totalUnrealized} t={t} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <RecentAnalysisTable recentAnalysis={recentAnalysis} t={t} />
        <NewsFeed news={news} t={t} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-2xl p-6 border-white/[0.04] bg-slate-900/20">
          <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-6">{t('dashboard.asset_allocation')}</h3>
          <div className="h-64 w-full">
            <ErrorBoundary name="Allocation Chart">
                <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                    data={allocationData}
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                    >
                    {allocationData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                    ))}
                    </Pie>
                    <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '12px', fontSize: '10px' }}
                    />
                    <Legend verticalAlign="middle" align="right" layout="vertical" iconType="circle" />
                </PieChart>
                </ResponsiveContainer>
            </ErrorBoundary>
          </div>
        </div>

        <div className="glass-panel rounded-2xl p-6 border-white/[0.04] bg-slate-900/20 flex flex-col justify-center items-center opacity-40">
             <Activity size={48} className="text-slate-600 mb-4" />
             <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 text-center">
                 Advanced Risk Analytics Coming Soon
             </p>
        </div>
      </div>
    </div>
  )
}
