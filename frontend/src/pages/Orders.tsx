import { useEffect, useState } from 'react'
import axios from 'axios'
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

const STATUS_COLORS: Record<string, string> = {
  FILLED: 'text-emerald-400',
  REJECTED: 'text-red-400',
  PARTIALLY_FILLED: 'text-yellow-400',
  PENDING: 'text-slate-400',
}

const ACTION_COLORS: Record<string, string> = {
  BUY: 'text-emerald-400',
  SELL: 'text-red-400',
}

export default function Orders() {
  const { t } = useTranslation()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<string>('')

  const fetch = () => {
    const params = mode ? `?mode=${mode}` : ''
    axios.get(`/api/portfolio/orders${params}`).then(r => { setOrders(r.data); setLoading(false) })
  }

  useEffect(() => { fetch() }, [mode])

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">{t('orders.title')}</h2>
        <select className="bg-slate-700 text-white rounded-lg px-3 py-1.5 text-sm outline-none" value={mode} onChange={e => setMode(e.target.value)}>
          <option value="">{t('orders.filter_all')}</option>
          <option value="simulation">{t('orders.filter_simulation')}</option>
          <option value="live">{t('orders.filter_live')}</option>
        </select>
      </div>

      {loading ? <p className="text-slate-400">{t('orders.loading')}</p> : (
        orders.length === 0 ? <p className="text-slate-500">{t('orders.empty')}</p> : (
          <div className="bg-slate-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-700">
                <tr className="text-slate-300 text-left">
                  <th className="px-4 py-3">{t('orders.col_symbol')}</th>
                  <th className="px-4 py-3">{t('orders.col_direction')}</th>
                  <th className="px-4 py-3">{t('orders.col_quantity')}</th>
                  <th className="px-4 py-3">{t('orders.col_price')}</th>
                  <th className="px-4 py-3">{t('orders.col_total')}</th>
                  <th className="px-4 py-3">{t('orders.col_status')}</th>
                  <th className="px-4 py-3">{t('orders.col_signal')}</th>
                  <th className="px-4 py-3">{t('orders.col_mode')}</th>
                  <th className="px-4 py-3">{t('orders.col_date')}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => (
                  <tr key={o.id} className="border-t border-slate-700 hover:bg-slate-750">
                    <td className="px-4 py-2 font-mono font-bold text-white">{o.ticker}</td>
                    <td className={`px-4 py-2 font-semibold ${ACTION_COLORS[o.action] || 'text-white'}`}>{o.action}</td>
                    <td className="px-4 py-2 text-slate-300">{o.quantity_filled.toFixed(4)}</td>
                    <td className="px-4 py-2 text-slate-300">{o.price_per_share ? `$${o.price_per_share.toFixed(2)}` : '—'}</td>
                    <td className="px-4 py-2 text-slate-300">{o.total_value ? `$${o.total_value.toFixed(2)}` : '—'}</td>
                    <td className={`px-4 py-2 font-semibold ${STATUS_COLORS[o.status] || 'text-slate-300'}`}>{o.status}</td>
                    <td className="px-4 py-2 text-slate-400 text-xs">{o.ai_signal}</td>
                    <td className="px-4 py-2 text-slate-500 text-xs">{o.mode}</td>
                    <td className="px-4 py-2 text-slate-500 text-xs">{new Date(o.created_at).toLocaleString('tr-TR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

