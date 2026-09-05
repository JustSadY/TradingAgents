import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { GridColDef } from '@mui/x-data-grid'
import {
  useTradingGetTradeNote,
  useTradingSaveTradeNote,
  useTradingGenerateTradeDebrief,
  getTradingGetTradeNoteQueryKey,
} from '../api/generated/trading/trading'
import { usePortfolioListOrders } from '../api/generated/portfolio/portfolio'
import { Briefcase, RefreshCw, NotebookPen, X, Save, Sparkles, Loader2, Bot, Download } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { notify } from '../utils/notify'
import { exportOrdersCSV } from '../utils/csvExport'
import { ErrorBoundary } from '../components/ErrorBoundary'
import AppDataGrid from '../components/ui/AppDataGrid'
import type { OrderRead } from '../api/generated/model'

const STATUS_BADGES: Record<string, string> = {
  FILLED: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20',
  REJECTED: 'bg-rose-500/10 text-rose-400 border border-rose-500/20',
  PARTIALLY_FILLED: 'bg-amber-500/10 text-amber-400 border border-amber-500/20',
  RECONCILIATION_REQUIRED: 'bg-amber-500/10 text-amber-300 border border-amber-500/30',
  CANCELED: 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
  EXPIRED: 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
  PENDING: 'bg-slate-500/10 text-slate-400 border border-slate-500/20',
}

const ACTION_BADGES: Record<string, string> = {
  BUY: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15',
  SELL: 'bg-rose-500/10 text-rose-400 border border-rose-500/15',
}

function displayOrderStatus(order: OrderRead): { label: string; badgeKey: string } {
  if ((order.status === 'CANCELED' || order.status === 'EXPIRED') && order.quantity_filled > 0) {
    return { label: `${order.status} · PARTIAL FILL`, badgeKey: 'PARTIALLY_FILLED' }
  }
  return { label: order.status, badgeKey: order.status }
}

// ── Trade Journal Modal ────────────────────────────────────────────────────────
function JournalModal({ order, onClose }: { order: OrderRead; onClose: () => void }) {
  const { t } = useTranslation()
  const [note, setNote] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const queryClient = useQueryClient()

  const noteQuery = useTradingGetTradeNote(order.id)
  const entry = noteQuery.data ?? null
  const loading = noteQuery.isPending

  // Seed the editable draft once the saved note arrives, without clobbering
  // whatever the user has typed since.
  useEffect(() => {
    if (noteQuery.data) setNote(noteQuery.data.note || '')
  }, [noteQuery.data])

  useEffect(() => {
    if (!loading) setTimeout(() => textareaRef.current?.focus(), 50)
  }, [loading])

  const refreshNote = () =>
    queryClient.invalidateQueries({ queryKey: getTradingGetTradeNoteQueryKey(order.id) })

  const saveMutation = useTradingSaveTradeNote({
    mutation: {
      onSuccess: () => { refreshNote(); notify('success', 'Note saved', 'Journal') },
      onError: () => notify('error', 'Failed to save note', 'Journal'),
    },
  })
  const debriefMutation = useTradingGenerateTradeDebrief({
    mutation: {
      onSuccess: refreshNote,
      onError: (err) => {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        notify('error', detail || 'Debrief generation failed', 'AI Debrief')
      },
    },
  })
  const saving = saveMutation.isPending
  const debriefing = debriefMutation.isPending

  const saveNote = () => saveMutation.mutate({ orderId: order.id, data: { note } })
  const generateDebrief = () => debriefMutation.mutate({ orderId: order.id })

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
            <span className="text-sm font-bold text-white">{t('orders.journal_title')}</span>
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
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('orders.your_notes')}</label>
            {loading ? (
              <div className="h-24 rounded-xl bg-white/[0.02] border border-white/[0.04] animate-pulse" />
            ) : (
              <textarea
                ref={textareaRef}
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder={t('orders.notes_placeholder')}
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
              <p className="text-[11px] text-slate-500 italic">{t('orders.debrief_sell_only')}</p>
            )}
            {entry?.ai_debrief ? (
              <div className="p-3.5 rounded-xl bg-violet-500/5 border border-violet-500/10 text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap">
                {entry.ai_debrief}
              </div>
            ) : !debriefing && order.action === 'SELL' && (
              <p className="text-[11px] text-slate-600 italic">{t('orders.debrief_empty')}</p>
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
  const [journalOrder, setJournalOrder] = useState<OrderRead | null>(null)

  const ordersQuery = usePortfolioListOrders()
  const orders = (ordersQuery.data ?? []) as OrderRead[]
  const loading = ordersQuery.isPending
  const loadOrders = () => ordersQuery.refetch()

  const columns = useMemo<GridColDef<OrderRead>[]>(() => [
    {
      field: 'ticker',
      headerName: t('orders.col_symbol'),
      minWidth: 88,
      flex: 0.8,
      renderCell: ({ value }) => <span className="font-mono font-bold text-white text-sm">{String(value ?? '')}</span>,
    },
    {
      field: 'action',
      headerName: t('orders.col_direction'),
      minWidth: 84,
      renderCell: ({ value }) => {
        const action = String(value ?? '')
        return <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-md ${ACTION_BADGES[action] || 'text-white'}`}>{action}</span>
      },
    },
    {
      field: 'quantity_filled',
      headerName: t('orders.col_quantity'),
      type: 'number',
      minWidth: 92,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => <span className="font-mono font-semibold text-slate-300">{Number(value ?? 0).toFixed(4)}</span>,
    },
    {
      field: 'price_per_share',
      headerName: t('orders.col_price'),
      type: 'number',
      minWidth: 88,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => <span className="font-mono text-slate-300">{value == null ? '—' : `$${Number(value).toFixed(2)}`}</span>,
    },
    {
      field: 'total_value',
      headerName: t('orders.col_total'),
      type: 'number',
      minWidth: 96,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ value }) => <span className="font-mono font-semibold text-slate-300">{value == null ? '—' : `$${Number(value).toFixed(2)}`}</span>,
    },
    {
      field: 'realized_pnl',
      headerName: 'P&L',
      type: 'number',
      minWidth: 92,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => {
        if (row.action !== 'SELL' || row.realized_pnl == null) return <span className="text-slate-600">—</span>
        const pnl = row.realized_pnl
        return <span className={`font-mono font-semibold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
      },
    },
    {
      field: 'status',
      headerName: t('orders.col_status'),
      minWidth: 150,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => {
        const status = displayOrderStatus(row)
        return <span className={`inline-flex items-center text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${STATUS_BADGES[status.badgeKey] || 'text-slate-300'}`}>{status.label}</span>
      },
    },
    {
      field: 'external_order_id',
      headerName: t('orders.col_broker_order_id'),
      minWidth: 150,
      flex: 1,
      renderCell: ({ value }) => {
        const orderId = String(value || '')
        return orderId
          ? <span title={orderId} className="font-mono text-[10px] text-amber-200 truncate max-w-full">{orderId}</span>
          : <span className="text-slate-600">—</span>
      },
    },
    {
      field: 'ai_signal',
      headerName: t('orders.col_signal'),
      minWidth: 110,
      flex: 1,
      renderCell: ({ value }) => <span className="text-slate-400 font-medium truncate">{String(value || '—')}</span>,
    },
    {
      field: 'created_at',
      headerName: t('orders.col_date'),
      minWidth: 116,
      renderCell: ({ value }) => (
        <span className="text-slate-500 font-mono text-[10px]">
          {new Date(String(value)).toLocaleString(undefined, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    },
    {
      field: 'journal',
      headerName: 'Journal',
      minWidth: 72,
      sortable: false,
      filterable: false,
      align: 'center',
      headerAlign: 'center',
      renderCell: ({ row }) => (
        <button
          onClick={() => setJournalOrder(row)}
          className="p-1.5 rounded-lg text-slate-600 hover:text-violet-400 hover:bg-violet-500/10 transition cursor-pointer"
          title={t('orders.open_journal')}
          aria-label={`Open ${row.ticker} trade journal`}
        >
          <NotebookPen size={13} />
        </button>
      ),
    },
  ], [t])

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
          <p className="text-xs text-slate-500 mt-1">{t('orders.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            onClick={() => exportOrdersCSV(orders)}
            disabled={orders.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-40"
            title={t('orders.export_csv')}
          >
            <Download size={13} /> CSV
          </button>
          <button
            onClick={loadOrders}
            disabled={loading}
            className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
            title={t('orders.refresh')}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <ErrorBoundary name="OrdersTable">
        <div className="glass-panel rounded-2xl p-2">
          <AppDataGrid<OrderRead>
            rows={orders}
            columns={columns}
            loading={loading}
            error={ordersQuery.error}
            emptyMessage={t('orders.empty')}
            ariaLabel="Orders"
            minHeight={320}
            density="compact"
          />
        </div>
      </ErrorBoundary>
    </div>
  )
}
