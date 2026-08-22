import { useCallback, useEffect, useState, useMemo } from 'react'
import { useAnalysisListAnalysis, useAnalysisGetPerformanceAttribution } from '../api/generated/analysis/analysis'
import { useWatchlistGetWatchlist } from '../api/generated/watchlist/watchlist'
import { useDailySummaryFetchDailySummary, useDailySummaryTriggerDailySummary } from '../api/generated/daily-summary/daily-summary'
import { Activity, Sparkles, Loader2, RefreshCw, Newspaper } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { ErrorBoundary } from '../components/ErrorBoundary'
import {
  PieChart, Pie, Cell, Legend, Tooltip
} from 'recharts'
import { ResponsiveChart } from '../components/ui/ResponsiveChart'
import { usePortfolio } from '../hooks/usePortfolio'
import { useNewsFeed } from '../hooks/useNewsFeed'
import { PortfolioOverview } from '../components/dashboard/PortfolioOverview'
import { RecentAnalysisTable } from '../components/dashboard/RecentAnalysisTable'
import { NewsFeed } from '../components/dashboard/NewsFeed'

interface DailySummary { id: number; date: string; summary: string; tickers: string[]; generated_at: string | null }

const ALLOCATION_COLORS = ['#8b5cf6', '#10b981', '#f59e0b', '#3b82f6', '#ec4899', '#14b8a6', '#6366f1']

export default function Dashboard() {
  const { t } = useTranslation()
  const { sim, stats, allocationData, loading: portfolioLoading } = usePortfolio()
  const [watchlist, setWatchlist] = useState<string[]>([])
  
  const watchlistSlice = useMemo(() => watchlist.slice(0, 5), [watchlist])
  const { news } = useNewsFeed(watchlistSlice)
  
  const historyQuery = useAnalysisListAnalysis({ limit: 8 })
  const watchlistQuery = useWatchlistGetWatchlist()
  const attributionQuery = useAnalysisGetPerformanceAttribution()
  const summaryQuery = useDailySummaryFetchDailySummary()

  const recentAnalysis = (Array.isArray(historyQuery.data) ? historyQuery.data : []) as any[]
  const attribution = ((attributionQuery.data as { attribution?: any[] } | undefined)?.attribution ?? []) as any[]
  // Each panel degrades on its own: a failed section renders empty rather than
  // blocking the whole dashboard, which is what the previous per-request
  // .catch() fallbacks did.
  const loading = historyQuery.isPending || watchlistQuery.isPending || attributionQuery.isPending

  const generateMutation = useDailySummaryTriggerDailySummary()
  const summaryLoading = generateMutation.isPending
  // Only a payload carrying an id is a real summary; the endpoint returns an
  // empty body when none has been generated yet.
  const rawSummary = generateMutation.data ?? summaryQuery.data ?? null
  const summary = ((rawSummary as { id?: number } | null)?.id ? (rawSummary as DailySummary) : null)
  const generateSummary = useCallback(() => generateMutation.mutate(undefined), [generateMutation])
  const loadSummary = useCallback(() => { generateMutation.reset(); void summaryQuery.refetch() }, [generateMutation, summaryQuery])

  useEffect(() => {
    // Guard the shape: a malformed payload must not turn `watchlist` into a
    // non-array and crash every consumer that reads .length.
    if (Array.isArray(watchlistQuery.data)) setWatchlist(watchlistQuery.data as string[])
  }, [watchlistQuery.data, setWatchlist])

  if (loading || portfolioLoading) return (
    <div className="h-[80vh] flex flex-col items-center justify-center space-y-4 opacity-50">
        <Activity className="text-violet-500 animate-pulse" size={32} />
        <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">{t('dashboard.synchronizing')}</p>
    </div>
  )

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('dashboard.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">{t('dashboard.subtitle')}</p>
        </div>
      </div>

      <PortfolioOverview sim={sim} pnl={stats.pnl} pnlPct={stats.pnlPct} totalUnrealized={stats.totalUnrealized} t={t} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <RecentAnalysisTable recentAnalysis={recentAnalysis} t={t} />
        <NewsFeed news={news} t={t} />
      </div>

      {/* Daily AI Market Summary */}
      <div className="glass-panel rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Newspaper size={14} className="text-violet-400" />
            <span className="text-xs font-bold text-white uppercase tracking-widest">{t('dashboard.morning_brief')}</span>
            {summary && <span className="text-[10px] text-slate-600 font-mono">{summary.date}</span>}
          </div>
          <button
            onClick={generateSummary}
            disabled={summaryLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/20 text-violet-300 text-[10px] font-bold transition cursor-pointer disabled:opacity-40"
          >
            {summaryLoading ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
            {summaryLoading ? 'Generating…' : summary ? 'Regenerate' : 'Generate'}
          </button>
        </div>

        {!summary && !summaryLoading && (
          <p className="text-[11px] text-slate-600 italic">
            Click <strong className="text-slate-500">{t('dashboard.generate')}</strong> to create today's AI market brief — covers watchlist movers and sector rotation.
          </p>
        )}

        {summaryLoading && (
          <div className="flex items-center gap-2 text-[11px] text-slate-500">
            <Loader2 size={11} className="animate-spin text-violet-400" />
            Analysing markets, this takes ~10 seconds…
          </div>
        )}

        {summary && !summaryLoading && (
          <div className="space-y-2">
            <p className="text-xs text-slate-300 leading-relaxed">{summary.summary}</p>
            {summary.tickers.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {summary.tickers.map(t => (
                  <span key={t} className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border border-white/[0.06] text-slate-500">{t}</span>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between pt-1">
              <span className="text-[9px] text-slate-700">
                {summary.generated_at ? `Generated at ${new Date(summary.generated_at).toLocaleTimeString()}` : ''}
              </span>
              <button onClick={loadSummary} className="text-[9px] text-slate-600 hover:text-slate-400 cursor-pointer flex items-center gap-1">
                <RefreshCw size={9} /> refresh
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-2xl p-6 border-white/[0.04] bg-slate-900/20">
          <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-6">{t('dashboard.asset_allocation')}</h3>
          <div className="h-64 w-full">
            <ErrorBoundary name="Allocation Chart">
                <ResponsiveChart width="100%" height="100%">
                <PieChart>
                    <Pie
                    data={allocationData}
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                    stroke="none"
                    >
                    {allocationData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                    ))}

                    </Pie>
                    <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '12px', fontSize: '10px' }}
                    />
                    <Legend verticalAlign="middle" align="right" layout="vertical" iconType="circle" />
                </PieChart>
                </ResponsiveChart>
            </ErrorBoundary>
          </div>
        </div>

        <div className="glass-panel rounded-2xl p-6 border-white/[0.04] bg-slate-900/20">
          <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-6">{t('dashboard.scorecard_title')}</h3>
          {attribution.length > 0 ? (
            <div className="space-y-4 overflow-y-auto max-h-64 pr-1">
              {attribution.map(item => (
                <div key={item.key} className="flex items-center justify-between p-3 rounded-xl bg-slate-950/40 border border-white/[0.02] hover:border-white/[0.06] transition-all">
                  <div className="min-w-0">
                    <p className="text-xs font-bold text-white truncate">{item.label}</p>
                    <p className="text-[10px] text-slate-500 font-mono mt-0.5">{item.total_predictions} {t('dashboard.scorecard_predictions')}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono font-bold text-emerald-400">{item.win_rate}% {t('dashboard.scorecard_accuracy')}</span>
                    <div className="w-16 bg-slate-800 rounded-full h-1 overflow-hidden shrink-0">
                      <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${item.win_rate}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-64 flex flex-col justify-center items-center opacity-40">
                 <Activity size={32} className="text-slate-600 mb-3" />
                 <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 text-center">
                     {t('dashboard.scorecard_empty')}
                 </p>
                 <p className="text-[9px] text-slate-600 text-center mt-1">{t('dashboard.scorecard_empty_sub')}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
