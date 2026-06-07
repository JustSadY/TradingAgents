import { Shield, TrendingUp, BarChart, Activity, Target } from 'lucide-react'

interface RiskMetrics {
  sharpe_ratio: number
  max_drawdown: number
  annualized_volatility: number
  beta?: number
  market_correlation?: number
}

interface RiskMetricsCardProps {
  metrics: RiskMetrics
}

export function RiskMetricsCard({ metrics }: RiskMetricsCardProps) {
  if (!metrics) return null

  const items = [
    { label: 'Sharpe Ratio', value: metrics.sharpe_ratio, icon: <TrendingUp size={14} />, color: 'text-emerald-400' },
    { label: 'Max Drawdown', value: `${(metrics.max_drawdown * 100).toFixed(2)}%`, icon: <Shield size={14} />, color: 'text-rose-400' },
    { label: 'Volatility', value: `${(metrics.annualized_volatility * 100).toFixed(2)}%`, icon: <Activity size={14} />, color: 'text-amber-400' },
    { label: 'Beta', value: metrics.beta?.toFixed(2) ?? 'N/A', icon: <BarChart size={14} />, color: 'text-violet-400' },
    { label: 'Market Corr.', value: metrics.market_correlation?.toFixed(2) ?? 'N/A', icon: <Target size={14} />, color: 'text-indigo-400' },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      {items.map((item) => (
        <div key={item.label} className="glass-panel p-3 rounded-xl border border-white/[0.04] bg-slate-900/40">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={item.color}>{item.icon}</span>
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{item.label}</span>
          </div>
          <div className="text-sm font-mono font-bold text-white">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  )
}
