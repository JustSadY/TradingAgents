import { useEffect, useState } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Briefcase, Loader2, AlertCircle } from 'lucide-react'
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

  useEffect(() => {
    Promise.all([
      axios.get<PortfolioRow[]>('/api/portfolio').then(r => r.data),
      axios.get<Holding[]>('/api/portfolio/holdings').then(r => r.data),
    ]).then(([p, h]) => {
      setPortfolios(p)
      setHoldings(h)
    }).catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400">
        <Loader2 className="animate-spin mr-2" size={20} /> {t('portfolio.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 flex flex-col items-center gap-3 text-center">
        <AlertCircle size={32} className="text-red-400" />
        <p className="text-slate-300">{t('portfolio.error')}</p>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold text-white">{t('portfolio.title')}</h2>

      {/* Portfolio summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {portfolios.map(p => {
          const pnl = p.current_balance - p.initial_capital
          const pnlPct = p.initial_capital ? (pnl / p.initial_capital * 100) : 0
          const positive = pnl >= 0
          return (
            <div key={p.id} className="bg-slate-800 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-xs uppercase tracking-wider">{p.mode} / {p.broker}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${p.status === 'active' ? 'bg-emerald-900/50 text-emerald-400' : 'bg-slate-700 text-slate-400'}`}>
                  {p.status}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign size={18} className="text-indigo-400" />
                <span className="text-2xl font-bold text-white">
                  ${p.current_balance.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {positive ? <TrendingUp size={14} className="text-emerald-400" /> : <TrendingDown size={14} className="text-red-400" />}
                <span className={`text-sm font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {positive ? '+' : ''}{pnl.toFixed(2)} ({positive ? '+' : ''}{pnlPct.toFixed(2)}%)
                </span>
              </div>
              <div className="text-xs text-slate-500">
                {t('portfolio.initial')}: ${p.initial_capital.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US')} •
                {t('portfolio.cash')}: ${p.cash_available.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Holdings table */}
      <div className="bg-slate-800 rounded-xl p-5">
        <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Briefcase size={16} className="text-indigo-400" /> {t('portfolio.all_positions')}
        </h3>
        {holdings.length === 0 ? (
          <p className="text-slate-500 text-sm">{t('portfolio.no_positions')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-left text-xs border-b border-slate-700">
                  <th className="pb-2 px-1">{t('portfolio.col_symbol')}</th>
                  <th className="pb-2 px-1 text-right">{t('portfolio.col_quantity')}</th>
                  <th className="pb-2 px-1 text-right">{t('portfolio.col_avg_cost')}</th>
                  <th className="pb-2 px-1 text-right">{t('portfolio.col_current_price')}</th>
                  <th className="pb-2 px-1 text-right">{t('portfolio.col_market_value')}</th>
                  <th className="pb-2 px-1 text-right">{t('portfolio.col_unrealized_pnl')}</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map(h => {
                  const price = h.current_price ?? h.avg_buy_price
                  const marketValue = price * h.quantity
                  const pnl = h.unrealized_pnl ?? (marketValue - h.avg_buy_price * h.quantity)
                  const positive = pnl >= 0
                  return (
                    <tr key={h.id} className="border-t border-slate-700">
                      <td className="py-2 px-1 font-mono font-bold text-white">{h.ticker}</td>
                      <td className="py-2 px-1 text-right text-slate-300">{h.quantity.toFixed(4)}</td>
                      <td className="py-2 px-1 text-right text-slate-300">${h.avg_buy_price.toFixed(2)}</td>
                      <td className="py-2 px-1 text-right text-slate-300">
                        {h.current_price != null ? `$${h.current_price.toFixed(2)}` : '—'}
                      </td>
                      <td className="py-2 px-1 text-right text-slate-300">${marketValue.toFixed(2)}</td>
                      <td className={`py-2 px-1 text-right font-semibold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>
                        {positive ? '+' : ''}${pnl.toFixed(2)}
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
