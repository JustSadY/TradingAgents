import React from 'react'
import { TrendingUp, DollarSign, Activity } from 'lucide-react'

interface Portfolio {
  id: number; mode: string; broker: string
  initial_capital: number; current_balance: number; cash_available: number
  status: string
  holdings: { ticker: string; quantity: number; current_price: number; unrealized_pnl: number; avg_buy_price?: number }[]
}

interface PortfolioOverviewProps {
  sim: Portfolio | undefined
  pnl: number
  pnlPct: number
  totalUnrealized: number
  t: any
}

export const PortfolioOverview: React.FC<PortfolioOverviewProps> = ({
  sim, pnl, pnlPct, totalUnrealized, t
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div className="glass-panel rounded-2xl p-5 border-white/[0.04] bg-slate-900/20">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 rounded-xl bg-violet-500/10 text-violet-400">
            <DollarSign size={18} />
          </div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('dashboard.balance')}</span>
        </div>
        <div className="flex items-baseline gap-2">
          <h3 className="text-xl font-display font-bold text-white">${sim?.current_balance?.toLocaleString() ?? '0'}</h3>
          <span className={`text-[10px] font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {pnl >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
          </span>
        </div>
      </div>

      <div className="glass-panel rounded-2xl p-5 border-white/[0.04] bg-slate-900/20">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
            <TrendingUp size={18} />
          </div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('dashboard.pnl')}</span>
        </div>
        <h3 className={`text-xl font-display font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          ${pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </h3>
      </div>

      <div className="glass-panel rounded-2xl p-5 border-white/[0.04] bg-slate-900/20">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
            <Activity size={18} />
          </div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('dashboard.unrealized')}</span>
        </div>
        <h3 className={`text-xl font-display font-bold ${totalUnrealized >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
          ${totalUnrealized.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </h3>
      </div>

      <div className="glass-panel rounded-2xl p-5 border-white/[0.04] bg-slate-900/20">
        <div className="flex items-center gap-3 mb-3">
          <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
            <Activity size={18} />
          </div>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('dashboard.holdings')}</span>
        </div>
        <h3 className="text-xl font-display font-bold text-white">{sim?.holdings?.length ?? 0} {t('dashboard.assets')}</h3>
      </div>
    </div>
  )
}
