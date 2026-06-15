import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import {
  TrendingUp, TrendingDown, DollarSign, ShoppingCart, BarChart2,
  RefreshCw, RotateCcw, AlertCircle, CheckCircle, Loader2
} from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Holding {
  ticker: string
  quantity: number
  avg_buy_price: number
  current_price: number
  market_value: number
  unrealized_pnl: number
  pnl_pct: number
  side?: string
  leverage?: number
  liquidation_price?: number
  borrowed_amount?: number
  stop_loss?: number
  take_profit?: number
}

interface PortfolioData {
  id: number
  initial_capital: number
  cash_available: number
  positions_value: number
  total_value: number
  total_pnl: number
  total_pnl_pct: number
  holdings: Holding[]
  benchmark_ticker?: string
  benchmark_return_pct?: number | null
  alpha_pct?: number | null
}

interface OrderResult {
  order_id: number
  ticker: string
  action: string
  quantity: number
  price: number
  total_value: number
  commission: number
  status: string
}

function StatCard({
  icon, label, value, sub, positive,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  positive?: boolean
}) {
  const valueColor =
    positive === undefined ? 'text-white' : positive ? 'text-emerald-400' : 'text-rose-400'
  const accent =
    positive === undefined ? 'from-violet-500/10' : positive ? 'from-emerald-500/10' : 'from-rose-500/10'
  return (
    <div className={`bg-gradient-to-br ${accent} to-slate-900/40 backdrop-blur-md border border-white/[0.04] rounded-2xl p-4 flex items-start gap-3 shadow`}>
      <div className="p-2 rounded-xl bg-slate-950/60 text-violet-400 border border-white/[0.04] shrink-0">{icon}</div>
      <div className="min-w-0">
        <p className="text-slate-500 text-[10px] md:text-xs font-semibold uppercase tracking-wider mb-1.5 leading-none truncate">{label}</p>
        <p className={`text-base md:text-lg font-display font-bold leading-none ${valueColor} truncate`}>{value}</p>
        {sub && <p className={`text-[10px] mt-1.5 font-mono font-medium ${valueColor} opacity-85 truncate`}>{sub}</p>}
      </div>
    </div>
  )
}

export default function MockTrading() {
  const { t, language } = useTranslation()
  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [fetchError, setFetchError] = useState(false)

  const [ticker, setTicker] = useState('')
  const [action, setAction] = useState<'BUY' | 'SELL'>('BUY')
  const [quantity, setQuantity] = useState('')
  const [leverage, setLeverage] = useState(1)
  const [submitting, setSubmitting] = useState(false)
  const [orderResult, setOrderResult] = useState<{ ok: boolean; msg: string } | null>(null)

  const [resetting, setResetting] = useState(false)

  const fetchPortfolio = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const { data } = await axios.get<PortfolioData>('/api/trading/performance')
      setPortfolio(data)
      setFetchError(false)
    } catch {
      setFetchError(true)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { fetchPortfolio() }, [fetchPortfolio])

  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ticker.trim() || !quantity || parseFloat(quantity) <= 0) return
    setSubmitting(true)
    setOrderResult(null)
    try {
      const { data } = await axios.post<OrderResult>('/api/trading/order', {
        ticker: ticker.toUpperCase(),
        action,
        quantity: parseFloat(quantity),
        leverage,
        // A SELL with no existing long opens a short; closing a long ignores this.
        allow_short: action === 'SELL',
      })
      const levTag = leverage > 1 ? ` (${leverage}x)` : ''
      setOrderResult({
        ok: true,
        msg: `✓ ${data.action} ${data.quantity} ${data.ticker}${levTag} @ $${data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} — Total: $${data.total_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      })
      setTicker('')
      setQuantity('')
      await fetchPortfolio(true)
    } catch (err: any) {
      setOrderResult({
        ok: false,
        msg: err.response?.data?.detail || t('mocktrading.order_error_default'),
      })
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = async () => {
    if (!confirm(t('mocktrading.reset_confirm'))) return
    setResetting(true)
    try {
      await axios.post('/api/trading/reset', { initial_capital: 100000 })
      await fetchPortfolio()
    } catch (e) {
      console.error('Portfolio reset failed:', e)
    } finally {
      setResetting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500 font-semibold text-xs gap-2">
        <Loader2 className="animate-spin text-violet-400" size={16} /> {t('mocktrading.loading')}
      </div>
    )
  }

  if (fetchError || !portfolio) {
    return (
      <div className="p-4 md:p-6 space-y-4 max-w-7xl mx-auto">
        <h2 className="text-xl font-bold text-white tracking-tight">{t('mocktrading.error_title')}</h2>
        <div className="glass-panel rounded-2xl p-8 flex flex-col items-center gap-4 text-center">
          <AlertCircle size={32} className="text-rose-400" />
          <p className="text-slate-300 text-sm leading-relaxed">{t('mocktrading.error_msg')}</p>
          <button
            onClick={() => fetchPortfolio()}
            className="px-5 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-xs font-semibold shadow transition-all cursor-pointer"
          >
            {t('mocktrading.retry')}
          </button>
        </div>
      </div>
    )
  }

  const p = portfolio
  const pnlPositive = p.total_pnl >= 0
  const alphaPositive = (p.alpha_pct ?? 0) >= 0
  const locale = language === 'tr' ? 'tr-TR' : 'en-US'

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('mocktrading.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Execute manual sandbox orders and track real-time position ledger stats</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => fetchPortfolio(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-white/[0.04] text-slate-400 hover:text-white text-xs font-semibold transition disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            {t('mocktrading.refresh')}
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 hover:bg-rose-500 hover:text-white text-xs font-semibold transition disabled:opacity-50 cursor-pointer"
          >
            <RotateCcw size={12} className={resetting ? 'animate-spin' : ''} />
            {t('mocktrading.reset')}
          </button>
        </div>
      </div>

      {/* KPI Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<DollarSign size={16} />}
          label={t('mocktrading.stat_total_value')}
          value={`$${p.total_value.toLocaleString(locale, { minimumFractionDigits: 2 })}`}
        />
        <StatCard
          icon={pnlPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
          label={t('mocktrading.stat_total_pnl')}
          value={`${pnlPositive ? '+' : ''}$${p.total_pnl.toLocaleString(locale, { minimumFractionDigits: 2 })}`}
          sub={`${pnlPositive ? '+' : ''}${(p.total_pnl_pct ?? 0).toFixed(2)}%`}
          positive={pnlPositive}
        />
        <StatCard
          icon={<DollarSign size={16} />}
          label={t('mocktrading.stat_cash')}
          value={`$${p.cash_available.toLocaleString(locale, { minimumFractionDigits: 2 })}`}
        />
        <StatCard
          icon={<BarChart2 size={16} />}
          label={`${t('mocktrading.stat_alpha')} ${p.benchmark_ticker || 'SPY'}`}
          value={
            p.alpha_pct !== null && p.alpha_pct !== undefined
              ? `${alphaPositive ? '+' : ''}${p.alpha_pct.toFixed(2)}%`
              : '—'
          }
          sub={
            p.benchmark_return_pct !== null && p.benchmark_return_pct !== undefined
              ? `${p.benchmark_ticker || 'SPY'}: ${p.benchmark_return_pct >= 0 ? '+' : ''}${p.benchmark_return_pct.toFixed(2)}%`
              : undefined
          }
          positive={p.alpha_pct !== null && p.alpha_pct !== undefined ? alphaPositive : undefined}
        />
      </div>

      {/* Action Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Placed Order Card */}
        <div className="glass-panel rounded-2xl p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-display font-semibold text-slate-200 mb-4 flex items-center gap-2">
              <ShoppingCart size={15} className="text-violet-400" /> {t('mocktrading.order_title')}
            </h3>
            <form onSubmit={handleOrder} className="space-y-4">
              <div className="flex rounded-xl overflow-hidden border border-white/[0.08] p-0.5 bg-slate-950/40">
                <button
                  type="button"
                  onClick={() => setAction('BUY')}
                  className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                    action === 'BUY'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {t('mocktrading.order_buy')}
                </button>
                <button
                  type="button"
                  onClick={() => setAction('SELL')}
                  className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                    action === 'SELL'
                      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {t('mocktrading.order_sell')}
                </button>
              </div>

              <input
                type="text"
                placeholder={t('mocktrading.order_symbol_placeholder')}
                value={ticker}
                onChange={e => setTicker(e.target.value.toUpperCase())}
                className="w-full glass-input rounded-xl px-3 py-2 font-semibold uppercase text-xs outline-none"
                required
              />
              <input
                type="number"
                placeholder={t('mocktrading.order_quantity_placeholder')}
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
                min="0.0001"
                step="any"
                className="w-full glass-input rounded-xl px-3 py-2 font-mono text-xs outline-none"
                required
              />

              {(
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      {t('mocktrading.leverage_label')}
                    </label>
                    <span className={`text-xs font-mono font-bold ${leverage > 1 ? 'text-amber-400' : 'text-slate-400'}`}>
                      {leverage}x
                    </span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={10}
                    step={1}
                    value={leverage}
                    onChange={e => setLeverage(parseInt(e.target.value, 10))}
                    className="w-full accent-amber-500 cursor-pointer"
                  />
                  {leverage > 1 && (
                    <p className="text-[10px] text-amber-400/80 leading-snug">
                      {t('mocktrading.leverage_warning')}
                    </p>
                  )}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className={`w-full py-2 rounded-xl text-white text-xs font-bold transition disabled:opacity-50 flex items-center justify-center gap-2 shadow cursor-pointer ${
                  action === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/20' : 'bg-rose-600 hover:bg-rose-500 shadow-rose-500/20'
                }`}
              >
                {submitting ? (
                  <><Loader2 size={13} className="animate-spin" /> {t('mocktrading.order_processing')}</>
                ) : (
                  action === 'BUY' ? t('mocktrading.order_submit_buy') : t('mocktrading.order_submit_sell')
                )}
              </button>
            </form>
          </div>

          {orderResult && (
            <div
              className={`flex items-start gap-2 rounded-xl px-3.5 py-3 text-[11px] font-medium mt-4 border ${
                orderResult.ok
                  ? 'bg-emerald-950/20 border-emerald-500/20 text-emerald-400'
                  : 'bg-rose-950/20 border-rose-500/20 text-rose-400'
              } animate-in fade-in duration-200`}
            >
              {orderResult.ok
                ? <CheckCircle size={14} className="mt-0.5 shrink-0" />
                : <AlertCircle size={14} className="mt-0.5 shrink-0" />}
              <span className="leading-relaxed">{orderResult.msg}</span>
            </div>
          )}
        </div>

        {/* Holdings List Card */}
        <div className="lg:col-span-2 glass-panel rounded-2xl p-5">
          <h3 className="text-sm font-display font-semibold text-slate-200 mb-4">{t('mocktrading.positions_title')}</h3>
          {p.holdings.length === 0 ? (
            <p className="text-slate-500 text-xs py-8 text-center">{t('mocktrading.positions_empty')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-slate-300 min-w-[500px]">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-wider border-b border-white/[0.04] bg-white/[0.01]">
                    <th className="px-3 py-2 text-left font-bold">{t('mocktrading.col_symbol')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_quantity')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_avg_cost')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_current_price')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_leverage')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_liquidation')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_stop_loss')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_take_profit')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_market_value')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_pnl')}</th>
                    <th className="px-3 py-2 text-right font-bold">{t('mocktrading.col_pnl_pct')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.02]">
                  {p.holdings.map(h => (
                    <tr key={h.ticker} className="hover:bg-white/[0.01] transition-colors">
                      <td className="px-3 py-3 font-mono font-bold text-white text-sm">
                        <span className="inline-flex items-center gap-1.5">
                          {h.ticker}
                          {h.side === 'short' && (
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/20">
                              SHORT
                            </span>
                          )}
                        </span>
                      </td>
                       <td className="px-3 py-3 text-right font-mono text-slate-400">{(h.quantity ?? 0).toFixed(4)}</td>
                      <td className="px-3 py-3 text-right font-mono text-slate-400">${(h.avg_buy_price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className="px-3 py-3 text-right font-mono text-slate-400">${(h.current_price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className={`px-3 py-3 text-right font-mono font-semibold ${(h.leverage ?? 1) > 1 ? 'text-amber-400' : 'text-slate-500'}`}>
                        {(h.leverage ?? 1).toFixed(1)}x
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-slate-400">
                        {(h.liquidation_price ?? 0) > 0
                          ? `$${(h.liquidation_price ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : '—'}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-rose-400/80">
                        {(h.stop_loss ?? 0) > 0
                          ? `$${(h.stop_loss ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : '—'}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-emerald-400/80">
                        {(h.take_profit ?? 0) > 0
                          ? `$${(h.take_profit ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : '—'}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-slate-400">${(h.market_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className={`px-3 py-3 text-right font-mono font-semibold ${(h.unrealized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {(h.unrealized_pnl ?? 0) >= 0 ? '+' : ''}${(h.unrealized_pnl ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className={`px-3 py-3 text-right font-mono font-semibold ${h.pnl_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {h.pnl_pct >= 0 ? '+' : ''}{(h.pnl_pct ?? 0).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
