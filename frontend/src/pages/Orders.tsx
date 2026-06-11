import { useEffect, useState } from 'react'
import axios from 'axios'
import { Briefcase, RefreshCw } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Order {
  id: number
  mode: string
  ticker: string
  action: string
  quantity_requested: number
  quantity_filled: number
  status: string
  price_per_share: number | null
  total_value: number | null
  ai_signal: string
  created_at: string
}

const STATUS_BADGES: Record<string, string> = {
  FILLED: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
  REJECTED: 'bg-rose-500/10 text-rose-400 border border-rose-500/20',
  PARTIALLY_FILLED: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
  PENDING: 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
}

const ACTION_BADGES: Record<string, string> = {
  BUY: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15',
  SELL: 'bg-rose-500/10 text-rose-400 border border-rose-500/15',
}

export default function Orders() {
  const { t } = useTranslation()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<string>('')

  const fetch = () => {
    setLoading(true)
    const params = mode ? `?mode=${mode}` : ''
    axios.get(`/api/portfolio/orders${params}`)
      .then(r => {
        setOrders(r.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [mode])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header Panel */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Briefcase className="text-violet-400" size={20} />
            {t('orders.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">Review ledger transactions executed by either simulated models or live accounts</p>
        </div>
        
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <select
            className="glass-input rounded-xl px-3 py-2 text-xs outline-none cursor-pointer w-40"
            value={mode}
            onChange={e => setMode(e.target.value)}
          >
            <option value="">{t('orders.filter_all')}</option>
            <option value="simulation">{t('orders.filter_simulation')}</option>
            <option value="live">{t('orders.filter_live')}</option>
          </select>
          
          <button
            onClick={fetch}
            disabled={loading}
            className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Orders Table Container */}
      {loading && orders.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-slate-400 text-sm">{t('orders.loading')}</p>
        </div>
      ) : orders.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Briefcase size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('orders.empty')}</p>
          <p className="text-[10px] text-slate-500 mt-1">No execution logs found matching your filter criteria</p>
        </div>
      ) : (
        <div className="glass-panel rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300 min-w-[700px]">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                  <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_symbol')}</th>
                  <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_direction')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_quantity')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_price')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_total')}</th>
                  <th className="px-5 py-3.5 text-center font-bold">{t('orders.col_status')}</th>
                  <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_signal')}</th>
                  <th className="px-5 py-3.5 text-center font-bold">{t('orders.col_mode')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_date')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {orders.map(o => (
                  <tr key={o.id} className="hover:bg-white/[0.01] transition-colors">
                    <td className="px-5 py-3 font-mono font-bold text-white text-sm">{o.ticker}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-md ${ACTION_BADGES[o.action] || 'text-white'}`}>
                        {o.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right font-mono font-semibold text-slate-300">{(o.quantity_filled ?? 0).toFixed(4)}</td>
                    <td className="px-5 py-3 text-right font-mono text-slate-300">
                      {o.price_per_share ? `$${(o.price_per_share ?? 0).toFixed(2)}` : '—'}
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-slate-300 font-semibold">
                      {o.total_value ? `$${(o.total_value ?? 0).toFixed(2)}` : '—'}
                    </td>
                    <td className="px-5 py-3 text-center">
                      <span className={`inline-flex items-center text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${STATUS_BADGES[o.status] || 'text-slate-300'}`}>
                        {o.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-400 font-medium truncate max-w-xs">{o.ai_signal || '—'}</td>
                    <td className="px-5 py-3 text-center">
                      <span className={`inline-flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wide ${
                        o.mode === 'live'
                          ? 'text-amber-400 bg-amber-500/10 border-amber-500/20'
                          : 'text-violet-400 bg-violet-500/10 border-violet-500/20'
                      }`}>
                        {o.mode === 'simulation' ? t('orders.filter_simulation') : o.mode === 'live' ? t('orders.filter_live') : o.mode}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right text-slate-500 font-mono text-[10px]">
                      {new Date(o.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}


