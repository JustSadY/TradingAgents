import { useEffect, useState } from 'react'
import axios from 'axios'
import { GitCompare, Loader2, DollarSign, Clock, Award, Zap } from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  Tooltip, Legend, CartesianGrid
} from 'recharts'
import { useTranslation } from '../contexts/LanguageContext'

interface ABMetric {
  preset_name: string
  total_runs: number
  avg_duration: number
  avg_tokens: number
  avg_cost_usd: number
  win_rate: number | null
  total_graded: number
}

export default function ABTesting() {
  const { t, language } = useTranslation()
  const [data, setData] = useState<ABMetric[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    axios.get('/api/analysis/ab-comparison')
      .then(r => setData(r.data))
      .catch(() => setError(t('common.error')))
      .finally(() => setLoading(false))
  }, [t])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500 font-semibold text-xs gap-2">
        <Loader2 className="animate-spin text-violet-400" size={16} /> {t('common.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
        <div className="bg-rose-950/20 border border-rose-500/20 text-rose-300 text-xs rounded-xl px-4 py-3">
          {error}
        </div>
      </div>
    )
  }

  const locale = language === 'tr' ? 'tr-TR' : 'en-US'

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-400 shadow shadow-violet-500/10">
            <GitCompare size={20} />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('nav.ab_testing')}</h2>
            <p className="text-xs text-slate-500 mt-1">Audit execution runtime speeds and total tokens costs across models presets</p>
          </div>
        </div>
      </div>

      {/* Cards List */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.map((m, i) => (
          <div key={i} className="relative overflow-hidden glass-panel glass-panel-hover rounded-2xl p-5 shadow">
            <div className="absolute top-0 right-0 w-24 h-24 bg-violet-600/5 rounded-full blur-2xl pointer-events-none" />
            <h3 className="text-sm font-bold text-white tracking-wide truncate mb-4 border-b border-white/[0.04] pb-2">{m.preset_name}</h3>

            <div className="grid grid-cols-2 gap-y-4 gap-x-2">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/25 shrink-0"><Zap size={12} /></div>
                <div>
                  <p className="text-[9px] uppercase text-slate-500 font-bold tracking-wider leading-none mb-1">Runs</p>
                  <p className="text-xs font-bold text-white font-mono leading-none">{m.total_runs}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 shrink-0"><DollarSign size={12} /></div>
                <div>
                  <p className="text-[9px] uppercase text-slate-500 font-bold tracking-wider leading-none mb-1">Avg Cost</p>
                  <p className="text-xs font-bold text-white font-mono leading-none">${m.avg_cost_usd.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/25 shrink-0"><Clock size={12} /></div>
                <div>
                  <p className="text-[9px] uppercase text-slate-500 font-bold tracking-wider leading-none mb-1">Avg Speed</p>
                  <p className="text-xs font-bold text-white font-mono leading-none">{m.avg_duration.toFixed(1)}s</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-violet-500/10 text-violet-400 border border-violet-500/25 shrink-0"><Award size={12} /></div>
                <div>
                  <p className="text-[9px] uppercase text-slate-500 font-bold tracking-wider leading-none mb-1">Win Rate</p>
                  <p className="text-xs font-bold text-white font-mono leading-none">{m.win_rate !== null ? `${m.win_rate}%` : '—'}</p>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Comparisons Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost Comparison */}
        <div className="glass-panel rounded-2xl p-5 space-y-4">
          <h4 className="text-xs font-bold text-violet-400 uppercase tracking-widest">Cost Comparison ($)</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                <XAxis dataKey="preset_name" stroke="#9ca3af" tick={{ fontSize: 9 }} tickLine={false} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 9 }} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: 12, color: '#fff', fontSize: 10 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar name="Avg Cost (USD)" dataKey="avg_cost_usd" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Speed Comparison */}
        <div className="glass-panel rounded-2xl p-5 space-y-4">
          <h4 className="text-xs font-bold text-violet-400 uppercase tracking-widest">Speed Comparison (Seconds)</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                <XAxis dataKey="preset_name" stroke="#9ca3af" tick={{ fontSize: 9 }} tickLine={false} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 9 }} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: 12, color: '#fff', fontSize: 10 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar name="Avg Duration (seconds)" dataKey="avg_duration" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
