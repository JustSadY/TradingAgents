import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Briefcase, Loader2, AlertCircle, RefreshCw, PieChart } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Holding {
  id: number
  ticker: string
  quantity: number
  avg_buy_price: number
  current_price: number | null
  unrealized_pnl: number | null
  updated_at: string
}

interface PortfolioRow {
  id: number
  mode: string
  broker: string
  initial_capital: number
  current_balance: number
  cash_available: number
  status: string
}

export default function Portfolio() {
  const { t, language } = useTranslation()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchPortfolioData = useCallback((quiet = false) => {
    if (!quiet) setLoading(true)
    setError(false)
    Promise.all([
      axios.get<PortfolioRow[]>('/api/portfolio').then(r => r.data),
      axios.get<Holding[]>('/api/portfolio/holdings').then(r => r.data),
    ]).then(([p, h]) => {
      setPortfolios(p)
      setHoldings(h)
    }).catch(() => {
      if (!quiet) setError(true)
    }).finally(() => {
      if (!quiet) setLoading(false)
    })
  }, [])

  useEffect(() => {
    fetchPortfolioData()
    const interval = setInterval(() => {
      fetchPortfolioData(true)
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchPortfolioData])

  if (loading && portfolios.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-400 gap-3">
        <Loader2 className="animate-spin text-violet-500" size={32} />
        <p className="text-xs font-semibold uppercase tracking-wider">{t('portfolio.loading') || 'Loading portfolio...'}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 flex flex-col items-center justify-center min-h-[300px] gap-4 text-center max-w-sm mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <AlertCircle size={24} />
        </div>
        <div>
          <p className="text-sm font-bold text-white uppercase tracking-wider mb-1">{t('portfolio.error') || 'Error Loading Portfolio'}</p>
          <p className="text-xs text-slate-500 leading-relaxed">Ensure backend service is running and retry the connection request</p>
        </div>
        <button
          onClick={() => fetchPortfolioData(false)}
          className="bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition duration-200 cursor-pointer shadow-lg shadow-violet-600/25"
        >
          {t('common.retry') || 'Retry Connection'}
        </button>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header Panel */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <PieChart className="text-violet-400" size={20} />
            {t('portfolio.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">Review active assets allocations, average cost basis, and real-time ledger returns</p>
        </div>
        <button
          onClick={() => fetchPortfolioData(false)}
          disabled={loading}
          className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Account Performance Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {portfolios.map(p => {
          const pnl = p.current_balance - p.initial_capital
          const pnlPct = p.initial_capital ? (pnl / p.initial_capital * 100) : 0
          const positive = pnl >= 0
          
          return (
            <div
              key={p.id}
              className={`glass-panel rounded-2xl p-5 space-y-4 border transition-all duration-300 relative overflow-hidden ${
                positive 
                  ? 'border-emerald-500/10 hover:border-emerald-500/20 hover:shadow-[0_8px_30px_rgb(16_185_129_/_4%)]' 
                  : 'border-rose-500/10 hover:border-rose-500/20 hover:shadow-[0_8px_30px_rgb(239_68_68_/_4%)]'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest bg-white/[0.03] px-2 py-0.5 rounded-lg border border-white/[0.04]">
                  {p.mode === 'simulation' ? t('orders.filter_simulation') : p.mode === 'live' ? t('orders.filter_live') : p.mode} / {p.broker}
                </span>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border ${
                  p.status === 'active' 
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                    : 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                }`}>
                  {p.status}
                </span>
              </div>
              
              <div className="space-y-1">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Net Asset Value (NAV)</span>
                <div className="flex items-center gap-1.5">
                  <DollarSign size={20} className={positive ? 'text-emerald-400' : 'text-rose-400'} />
                  <span className="text-2xl font-display font-extrabold text-white leading-none">
                    {p.current_balance.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <div className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-bold border ${
                  positive 
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/15' 
                    : 'bg-rose-500/10 text-rose-400 border-rose-500/15'
                }`}>
                  {positive ? <TrendingUp size={12} strokeWidth={2.5} /> : <TrendingDown size={12} strokeWidth={2.5} />}
                  <span>
                    {positive ? '+' : ''}{(pnl ?? 0).toFixed(2)} ({positive ? '+' : ''}{(pnlPct ?? 0).toFixed(2)}%)
                  </span>
                </div>
              </div>

              <div className="pt-3 border-t border-white/[0.04] grid grid-cols-2 gap-2 text-[10px] font-semibold text-slate-400">
                <div>
                  <span className="text-slate-500 uppercase block tracking-wider mb-0.5">{t('portfolio.initial')}</span>
                  <span className="text-white font-mono font-bold">${p.initial_capital.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US')}</span>
                </div>
                <div>
                  <span className="text-slate-500 uppercase block tracking-wider mb-0.5">{t('portfolio.cash')}</span>
                  <span className="text-white font-mono font-bold">${p.cash_available.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Holdings Positions Table */}
      <div className="glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.04] flex items-center justify-between">
          <h3 className="text-sm font-display font-bold text-slate-200 flex items-center gap-2">
            <Briefcase size={16} className="text-violet-400" />
            {t('portfolio.all_positions')}
          </h3>
          <span className="text-[10px] font-bold text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20 uppercase tracking-wide">
            {holdings.length} Positions
          </span>
        </div>
        
        {holdings.length === 0 ? (
          <div className="p-12 text-center">
            <Briefcase size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
            <p className="text-slate-400 text-xs font-semibold">{t('portfolio.no_positions')}</p>
            <p className="text-[10px] text-slate-500 mt-1">Acquire assets via mock simulation trading or trigger autonomous strategies</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300 min-w-[650px]">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                  <th className="px-5 py-3.5 text-left font-bold">{t('portfolio.col_symbol')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_quantity')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_avg_cost')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_current_price')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_market_value')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_unrealized_pnl')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {holdings.map(h => {
                  const price = h.current_price ?? h.avg_buy_price
                  const marketValue = price * h.quantity
                  const pnl = h.unrealized_pnl ?? (marketValue - h.avg_buy_price * h.quantity)
                  const positive = pnl >= 0
                  
                  return (
                    <tr key={h.id} className="hover:bg-white/[0.01] transition-colors">
                      <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">{h.ticker}</td>
                      <td className="px-5 py-3.5 text-right font-mono font-semibold text-slate-300">{(h.quantity ?? 0).toFixed(4)}</td>
                      <td className="px-5 py-3.5 text-right font-mono text-slate-300">${(h.avg_buy_price ?? 0).toFixed(2)}</td>
                      <td className="px-5 py-3.5 text-right font-mono text-slate-300">
                        {h.current_price != null ? `$${(h.current_price ?? 0).toFixed(2)}` : '—'}
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono text-white font-bold">${(marketValue ?? 0).toFixed(2)}</td>
                      <td className="px-5 py-3.5 text-right">
                        <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-md ${
                          positive 
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15' 
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/15'
                        }`}>
                          {positive ? '+' : ''}${(pnl ?? 0).toFixed(2)}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}


