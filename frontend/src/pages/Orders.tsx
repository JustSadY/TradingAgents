import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { Briefcase, RefreshCw, NotebookPen, X, Save, Sparkles, Loader2, Bot, Download } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { notify } from '../utils/notify'
import { exportOrdersCSV } from '../utils/csvExport'
import { ErrorBoundary } from '../components/ErrorBoundary'
import type { OrderRead, JournalNoteReadResponse } from '../api/types'

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

// ── Trade Journal Modal ────────────────────────────────────────────────────────
function JournalModal({ order, onClose }: { order: OrderRead; onClose: () => void }) {
  const [entry, setEntry] = useState<JournalNoteReadResponse | null>(null)
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [debriefing, setDebriefing] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    axios.get<JournalNoteReadResponse>(`/api/trading/journal/${order.id}`)
      .then(r => {
        setEntry(r.data)
        setNote(r.data.note || '')
      })
      .catch(() => setNote(''))
      .finally(() => {
        setLoading(false)
        setTimeout(() => textareaRef.current?.focus(), 50)
      })
  }, [order.id])

  const saveNote = async () => {
    setSaving(true)
    try {
      const { data } = await axios.post<{ order_id: number; note: string; has_debrief: boolean }>(
        `/api/trading/journal/${order.id}/note`,
        { note }
      )
      setEntry(prev => prev ? { ...prev, note: data.note, has_debrief: data.has_debrief } : null)
      notify('success', 'Note saved', 'Journal')
    } catch {
      notify('error', 'Failed to save note', 'Journal')
    } finally {
      setSaving(false)
    }
  }

  const generateDebrief = async () => {
    setDebriefing(true)
    try {
      const { data } = await axios.post<{ order_id: number; ai_debrief: string }>(
        `/api/trading/journal/${order.id}/debrief`
      )
      setEntry(prev => prev ? { ...prev, ai_debrief: data.ai_debrief, has_debrief: true } : null)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Debrief generation failed', 'AI Debrief')
    } finally {
      setDebriefing(false)
    }
  }

  const pnl = order.realized_pnl ?? 0
  const pnlPct = order.total_value && order.total_value !== pnl
    ? (pnl / (order.total_value - pnl)) * 100
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-slate-950 border border-white/[0.08] rounded-2xl shadow-2xl flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <NotebookPen size={15} className="text-violet-400" />
            <span className="text-sm font-bold text-white">Trade Journal</span>
            <span className="text-[10px] font-mono font-bold text-slate-400 bg-white/[0.04] px-2 py-0.5 rounded-md border border-white/[0.05]">
              #{order.id} · {order.ticker}
            </span>
          </div>
          <button onClick={onClose} className="p-1.5 text-slate-500 hover:text-white rounded-lg hover:bg-white/5 transition cursor-pointer">
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Trade summary row */}
          <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-xs flex-wrap">
            <span className={`font-bold px-2 py-0.5 rounded-md ${ACTION_BADGES[order.action] || 'text-white'}`}>{order.action}</span>
            <span className="text-slate-300 font-mono font-semibold">{order.quantity_filled?.toFixed(4)} shares</span>
            {order.price_per_share && <span className="text-slate-400">@ ${order.price_per_share.toFixed(2)}</span>}
            {order.action === 'SELL' && order.realized_pnl !== null && (
              <span className={`ml-auto font-bold font-mono ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                {pnlPct !== null && ` (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)`}
              </span>
            )}
          </div>

          {/* Note area */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Your Notes</label>
            {loading ? (
              <div className="h-24 rounded-xl bg-white/[0.02] border border-white/[0.04] animate-pulse" />
            ) : (
              <textarea
                ref={textareaRef}
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="What happened? Why did you enter this trade? What did you learn?"
                rows={4}
                className="w-full bg-white/[0.02] border border-white/[0.06] focus:border-violet-500/40 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-600 outline-none resize-none transition-colors"
              />
            )}
            <button
              onClick={saveNote}
              disabled={saving || loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/80 hover:bg-violet-600 text-white text-[10px] font-bold transition disabled:opacity-40 cursor-pointer"
            >
              {saving ? <Loader2 size={10} className="animate-spin" /> : <Save size={10} />}
              {saving ? 'Saving…' : 'Save Note'}
            </button>
          </div>

          {/* AI Debrief section */}
          <div className="space-y-3 border-t border-white/[0.04] pt-4">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                <Bot size={11} className="text-violet-400" />
                AI Coach Debrief
              </p>
              {order.action === 'SELL' && (
                <button
                  onClick={generateDebrief}
                  disabled={debriefing || loading}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 text-violet-400 text-[10px] font-bold transition disabled:opacity-40 cursor-pointer"
                >
                  {debriefing ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                  {debriefing ? 'Analysing…' : entry?.has_debrief ? 'Re-generate' : 'Generate'}
                </button>
              )}
            </div>
            {order.action !== 'SELL' && (
              <p className="text-[11px] text-slate-500 italic">AI debrief is available for closed (SELL) positions only.</p>
            )}
            {entry?.ai_debrief ? (
              <div className="p-3.5 rounded-xl bg-violet-500/5 border border-violet-500/10 text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">
                {entry.ai_debrief}
              </div>
            ) : !debriefing && order.action === 'SELL' && (
              <p className="text-[11px] text-slate-600 italic">No debrief yet — click Generate to get AI coaching feedback on this trade.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Orders Page ───────────────────────────────────────────────────────────
export default function Orders() {
  const { t } = useTranslation()
  const [orders, setOrders] = useState<OrderRead[]>([])
  const [loading, setLoading] = useState(true)
  const [journalOrder, setJournalOrder] = useState<OrderRead | null>(null)

  const loadOrders = useCallback(() => {
    setLoading(true)
    axios.get('/api/portfolio/orders')
      .then(r => setOrders(r.data))
      .catch(e => console.error('Failed to load orders', e))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadOrders() }, [loadOrders])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {journalOrder && <ErrorBoundary name="TradeJournal"><JournalModal order={journalOrder} onClose={() => setJournalOrder(null)} /></ErrorBoundary>}

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
          <button
            onClick={() => exportOrdersCSV(orders)}
            disabled={orders.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-40"
            title="Export CSV"
          >
            <Download size={13} /> CSV
          </button>
          <button
            onClick={loadOrders}
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
        <ErrorBoundary name="OrdersTable">
          <div className="glass-panel rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-slate-300 min-w-[760px]">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                    <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_symbol')}</th>
                    <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_direction')}</th>
                    <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_quantity')}</th>
                    <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_price')}</th>
                    <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_total')}</th>
                    <th className="px-5 py-3.5 text-right font-bold">P&amp;L</th>
                    <th className="px-5 py-3.5 text-center font-bold">{t('orders.col_status')}</th>
                    <th className="px-5 py-3.5 text-left font-bold">{t('orders.col_signal')}</th>
                    <th className="px-5 py-3.5 text-right font-bold">{t('orders.col_date')}</th>
                    <th className="px-5 py-3.5 text-center font-bold">Journal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.02]">
                  {orders.map(o => {
                    const pnl = o.realized_pnl ?? 0
                    return (
                      <tr key={o.id} className="hover:bg-white/[0.01] transition-colors">
                        <td className="px-5 py-3 font-mono font-bold text-white text-sm">{o.ticker}</td>
                        <td className="px-5 py-3">
                          <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-md ${ACTION_BADGES[o.action] || 'text-white'}`}>
                            {o.action}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-right font-mono font-semibold text-slate-300">{(o.quantity_filled ?? 0).toFixed(4)}</td>
                        <td className="px-5 py-3 text-right font-mono text-slate-300">
                          {o.price_per_share ? `$${(o.price_per_share).toFixed(2)}` : '—'}
                        </td>
                        <td className="px-5 py-3 text-right font-mono text-slate-300 font-semibold">
                          {o.total_value ? `$${(o.total_value).toFixed(2)}` : '—'}
                        </td>
                        <td className="px-5 py-3 text-right font-mono">
                          {o.action === 'SELL' && o.realized_pnl !== null ? (
                            <span className={pnl >= 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                            </span>
                          ) : <span className="text-slate-600">—</span>}
                        </td>
                        <td className="px-5 py-3 text-center">
                          <span className={`inline-flex items-center text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${STATUS_BADGES[o.status] || 'text-slate-300'}`}>
                            {o.status}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-slate-400 font-medium truncate max-w-[160px]">{o.ai_signal || '—'}</td>
                        <td className="px-5 py-3 text-right text-slate-500 font-mono text-[10px]">
                          {new Date(o.created_at).toLocaleString()}
                        </td>
                        <td className="px-5 py-3 text-center">
                          <button
                            onClick={() => setJournalOrder(o)}
                            className="p-1.5 rounded-lg text-slate-600 hover:text-violet-400 hover:bg-violet-500/10 transition cursor-pointer"
                            title="Open Trade Journal"
                          >
                            <NotebookPen size={13} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </ErrorBoundary>
      )}
    </div>
  )
}
