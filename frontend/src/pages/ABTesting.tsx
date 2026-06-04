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
      <div className="flex items-center justify-center h-64 text-slate-400">
        <Loader2 className="animate-spin mr-2" size={20} /> {t('common.loading')}
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 text-red-400 bg-red-950/30 border border-red-900 rounded-2xl">
        {error}
      </div>
    )
  }

  const locale = language === 'tr' ? 'tr-TR' : 'en-US'

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-violet-500/10 border border-violet-500/20 text-violet-400">
            <GitCompare size={22} />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">{t('nav.ab_testing')}</h2>
            <p className="text-xs text-gray-500 mt-0.5">LLM preset and provider infrastructure comparisons</p>
          </div>
        </div>
      </div>

      {}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.map((m, i) => (
          <div key={i} className="relative overflow-hidden bg-gradient-to-br from-gray-900 to-gray-950 border border-gray-800 hover:border-gray-700/80 rounded-2xl p-5 shadow-xl transition-all duration-300 group hover:-translate-y-1">
            <div className="absolute top-0 right-0 w-24 h-24 bg-violet-600/5 rounded-full blur-2xl group-hover:bg-violet-600/10 transition-colors" />
            <h3 className="text-sm font-bold text-white tracking-wide truncate mb-4 border-b border-gray-800/80 pb-2">{m.preset_name}</h3>

            <div className="grid grid-cols-2 gap-y-4 gap-x-2">
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-amber-400 shrink-0" />
                <div>
                  <p className="text-[10px] uppercase text-gray-500 font-medium tracking-wider">Runs</p>
                  <p className="text-sm font-bold text-white">{m.total_runs}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <DollarSign size={14} className="text-emerald-400 shrink-0" />
                <div>
                  <p className="text-[10px] uppercase text-gray-500 font-medium tracking-wider">Avg Cost</p>
                  <p className="text-sm font-bold text-white">${m.avg_cost_usd.toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Clock size={14} className="text-indigo-400 shrink-0" />
                <div>
                  <p className="text-[10px] uppercase text-gray-500 font-medium tracking-wider">Avg Speed</p>
                  <p className="text-sm font-bold text-white">{m.avg_duration.toFixed(1)}s</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Award size={14} className="text-violet-400 shrink-0" />
                <div>
                  <p className="text-[10px] uppercase text-gray-500 font-medium tracking-wider">Win Rate</p>
                  <p className="text-sm font-bold text-white">{m.win_rate !== null ? `${m.win_rate}%` : '—'}</p>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
          <h4 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">Cost Comparison ($)</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="preset_name" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', color: '#fff', fontSize: 11 }} />
                <Legend wrapperStyle={{ fontSize: 10 }} />
                <Bar name="Avg Cost (USD)" dataKey="avg_cost_usd" fill="#10b981" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 space-y-4">
          <h4 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">Speed Comparison (Seconds)</h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="preset_name" stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9ca3af" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', color: '#fff', fontSize: 11 }} />
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

