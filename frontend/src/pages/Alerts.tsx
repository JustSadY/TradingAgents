import { useEffect, useState } from 'react'
import axios from 'axios'
import { Bell, BellOff, Plus, Trash2, RefreshCw } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Alert {
  id: number; ticker: string; condition: 'above' | 'below'
  target_price: number; auto_analyze: boolean; enabled: boolean
  triggered_at: string | null; created_at: string; alert_type?: string; creation_source?: string
}

const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

export default function Alerts() {
  const { t } = useTranslation()
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [ticker, setTicker] = useState('')
  const [condition, setCondition] = useState<'above' | 'below'>('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [alertType, setAlertType] = useState<'price' | 'rsi' | 'macd_cross'>('price')
  const [autoAnalyze, setAutoAnalyze] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      const { data } = await axios.get('/api/alerts')
      setAlerts(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    const sym = ticker.trim().toUpperCase()
    const needsPrice = alertType !== 'macd_cross'
    const price = needsPrice ? Number.parseFloat(targetPrice) : 0
    if (!sym || (needsPrice && (Number.isNaN(price) || price <= 0))) { setError(t('alerts.error_invalid')); return }
    setSaving(true); setError(null)
    try {
      await axios.post('/api/alerts', { ticker: sym, condition, target_price: price, auto_analyze: autoAnalyze, alert_type: alertType })
      setTicker(''); setTargetPrice(''); setAutoAnalyze(false)
      await load()
    } catch (e: any) {
      setError(e.response?.data?.detail || t('alerts.error_create'))
    } finally { setSaving(false) }
  }

  const toggleEnabled = async (a: Alert) => {
    await axios.patch(`/api/alerts/${a.id}`, { enabled: !a.enabled })
    setAlerts(prev => prev.map(x => x.id === a.id ? { ...x, enabled: !x.enabled } : x))
  }

  const deleteAlert = async (id: number) => {
    await axios.delete(`/api/alerts/${id}`)
    setAlerts(prev => prev.filter(x => x.id !== id))
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-3xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('alerts.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">Set price threshold targets to dispatch webhook triggers or auto-run graphs</p>
      </div>

      {/* New Alert Form */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="text-xs font-bold text-violet-400 uppercase tracking-widest">{t('alerts.new_alert')}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('alerts.symbol')}</label>
            <input className={Input} placeholder="AAPL" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('alerts.type')}</label>
            <select className={Input} value={alertType} onChange={e => setAlertType(e.target.value as any)}>
              <option value="price">{t('alerts.type_price')}</option>
              <option value="rsi">{t('alerts.type_rsi')}</option>
              <option value="macd_cross">{t('alerts.type_macd_cross')}</option>
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('alerts.condition')}</label>
            <select className={Input} value={condition} onChange={e => setCondition(e.target.value as any)}>
              <option value="above">{alertType === 'macd_cross' ? t('alerts.condition_bullish') : t('alerts.condition_above')}</option>
              <option value="below">{alertType === 'macd_cross' ? t('alerts.condition_bearish') : t('alerts.condition_below')}</option>
            </select>
          </div>
          {alertType !== 'macd_cross' && (
            <div>
              <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">
                {alertType === 'rsi' ? t('alerts.rsi_threshold') : t('alerts.target_price')}
              </label>
              <input className={Input} type="number" step="0.01" placeholder={alertType === 'rsi' ? '70' : '150.00'} value={targetPrice} onChange={e => setTargetPrice(e.target.value)} />
            </div>
          )}
          <div className="flex flex-col justify-end pb-1.5">
            <label className="flex items-center gap-2.5 text-xs font-semibold text-slate-400 cursor-pointer select-none">
              <input type="checkbox" checked={autoAnalyze} onChange={e => setAutoAnalyze(e.target.checked)} className="w-4.5 h-4.5 accent-violet-600 rounded cursor-pointer" />
              {t('alerts.auto_analyze')}
            </label>
          </div>
        </div>
        {error && <p className="text-rose-400 text-xs font-semibold">{error}</p>}
        <button onClick={handleCreate} disabled={saving}
          className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer">
          {saving ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />} {t('alerts.add_button')}
        </button>
      </div>

      {/* Active Alerts List */}
      <div className="glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.04]">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">{t('alerts.active_alerts')} ({alerts.filter(a => a.enabled && !a.triggered_at).length})</h3>
        </div>
        {loading ? <div className="p-8 text-slate-500 text-xs text-center font-semibold">{t('alerts.loading')}</div>
          : alerts.length === 0 ? <div className="p-8 text-slate-600 text-xs text-center font-medium">{t('alerts.empty')}</div>
          : (
            <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300 min-w-[480px]">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                  <th className="px-5 py-3 text-left font-bold">{t('alerts.col_symbol')}</th>
                  <th className="px-5 py-3 text-left hidden sm:table-cell font-bold">{t('alerts.col_condition')}</th>
                  <th className="px-5 py-3 text-right font-bold">{t('alerts.col_target')}</th>
                  <th className="px-5 py-3 text-center hidden sm:table-cell font-bold">{t('alerts.col_auto')}</th>
                  <th className="px-5 py-3 text-center font-bold">{t('alerts.col_status')}</th>
                  <th className="px-5 py-3 text-center font-bold">{t('alerts.col_action')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {alerts.map(a => (
                  <tr key={a.id} className={`transition-colors hover:bg-white/[0.01] ${a.triggered_at ? 'opacity-40' : ''}`}>
                    <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">
                      {a.ticker}
                      {a.alert_type && a.alert_type !== 'price' && (
                        <span className={`ml-2 text-[9px] font-bold px-1.5 py-0.5 rounded-md uppercase tracking-wider ${
                          a.alert_type === 'support' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                        }`}>
                          {a.alert_type}
                        </span>
                      )}
                      {a.creation_source === 'analysis' && (
                        <span className="ml-2 text-[9px] font-bold px-1.5 py-0.5 rounded-md uppercase tracking-wider bg-violet-500/10 text-violet-300 border border-violet-500/20">
                          {t('alerts.source_ai')}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 font-semibold hidden sm:table-cell">
                      {a.condition === 'above' ? `↑ ${t('alerts.condition_above')}` : `↓ ${t('alerts.condition_below')}`}
                    </td>
                    <td className="px-5 py-3.5 text-right text-white font-mono font-semibold">${a.target_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                    <td className="px-5 py-3.5 text-center hidden sm:table-cell">
                      {a.auto_analyze ? <span className="text-violet-400 font-bold">✓</span> : <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-5 py-3.5 text-center font-bold">
                      {a.triggered_at
                        ? <span className="text-amber-500 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-lg text-[10px] uppercase tracking-wide">{t('alerts.status_triggered')}</span>
                        : a.enabled
                          ? <span className="text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-lg text-[10px] uppercase tracking-wide">{t('alerts.status_active')}</span>
                          : <span className="text-slate-500 bg-slate-500/10 border border-slate-500/20 px-2 py-0.5 rounded-lg text-[10px] uppercase tracking-wide">{t('alerts.status_inactive')}</span>
                      }
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <div className="flex items-center justify-center gap-3">
                        <button onClick={() => toggleEnabled(a)} className="text-slate-500 hover:text-white transition-colors cursor-pointer" title={a.enabled ? t('alerts.btn_deactivate') : t('alerts.btn_activate')}>
                          {a.enabled ? <Bell size={13} /> : <BellOff size={13} />}
                        </button>
                        <button onClick={() => deleteAlert(a.id)} className="text-slate-500 hover:text-rose-400 transition-colors cursor-pointer">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
      </div>
    </div>
  )
}
