import { useState, useCallback, useMemo } from 'react'
import type { GridColDef } from '@mui/x-data-grid'
import { usePortfolioListPortfolios, usePortfolioListHoldings } from '../api/generated/portfolio/portfolio'
import { useTradingRebalancePortfolio, useTradingGetRiskDashboard, useTradingCreateOrder, useTradingGetCorrelation } from '../api/generated/trading/trading'
import { useQueryErrorToast } from '../api/useQueryErrorToast'
import type { APIOrderRequestAction } from '../api/generated/model'
import { TrendingUp, TrendingDown, DollarSign, Briefcase, Loader2, AlertCircle, RefreshCw, PieChart, Sparkles, X, CheckCircle2, ShieldAlert, Activity, ChevronDown, ChevronUp, Download, Grid3x3 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { notify } from '../utils/notify'
import { exportPortfolioCSV } from '../utils/csvExport'
import { ErrorBoundary } from '../components/ErrorBoundary'
import AppDataGrid from '../components/ui/AppDataGrid'
import type { HoldingRead, HoldingRisk, PortfolioRead, RiskDashboardResponse, RebalanceResponse } from '../api/generated/model'
import { errorDetail } from '../utils/errorDetail'

const LONG_HOLD_DAYS = 30

function holdingDays(openedAt?: string | null): number | null {
  if (!openedAt) return null
  const opened = new Date(openedAt).getTime()
  if (Number.isNaN(opened)) return null
  return Math.max(0, Math.floor((Date.now() - opened) / 86_400_000))
}

interface RebalanceSuggestion {
  action: string
  ticker: string
  quantity: number
  rationale: string
  urgency: string
}

function HealthBadge({ score }: { score: number }) {
  const { bg, text, border, label } =
    score >= 80
      ? { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20', label: 'Healthy' }
      : score >= 60
        ? { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20', label: 'Fair' }
        : { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/20', label: 'Critical' }
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${bg} ${text} ${border}`}>
      {score}/100 · {label}
    </span>
  )
}

function UrgencyBadge({ urgency }: { urgency: string }) {
  const styles: Record<string, string> = {
    high: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    medium: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  }
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border capitalize ${styles[urgency] ?? styles.low}`}>
      {urgency}
    </span>
  )
}

export default function Portfolio() {
  const { t, language } = useTranslation()
  const [rebalanceResult, setRebalanceResult] = useState<RebalanceResponse | null>(null)
  const [applyingIdx, setApplyingIdx] = useState<number | null>(null)
  const orderMutation = useTradingCreateOrder()
  const [showRisk, setShowRisk] = useState(false)

  const portfoliosQuery = usePortfolioListPortfolios({ query: { refetchInterval: 15_000 } })
  const holdingsQuery = usePortfolioListHoldings(undefined, { query: { refetchInterval: 15_000 } })
  const portfolios = (portfoliosQuery.data ?? []) as PortfolioRead[]
  const holdings = (holdingsQuery.data ?? []) as HoldingRead[]
  const loading = portfoliosQuery.isPending || holdingsQuery.isPending
  const error = Boolean(portfoliosQuery.error || holdingsQuery.error)
  const fetchPortfolioData = useCallback(
    () => Promise.all([portfoliosQuery.refetch(), holdingsQuery.refetch()]),
    [portfoliosQuery, holdingsQuery],
  )

  const rebalanceMutation = useTradingRebalancePortfolio()
  const rebalancing = rebalanceMutation.isPending
  const runRebalance = useCallback(() => {
    rebalanceMutation.mutate(undefined, {
      onSuccess: setRebalanceResult,
      onError: (err) => {
        const detail = errorDetail(err)
        notify('error', detail || 'Rebalance failed', 'AI Rebalance')
      },
    })
  }, [rebalanceMutation])

  // Only fetched on demand: the risk dashboard is an expensive panel behind a
  // toggle, not part of the page's initial load.
  const riskQuery = useTradingGetRiskDashboard({ query: { enabled: showRisk } })
  const riskData = (riskQuery.data ?? null) as RiskDashboardResponse | null

  const riskColumns = useMemo<GridColDef<HoldingRisk>[]>(() => [
    {
      field: 'ticker',
      headerName: t('portfolio.col_ticker'),
      minWidth: 96,
      flex: 0.6,
      renderCell: ({ row }) => <span className="font-mono font-bold text-white">{row.ticker}</span>,
    },
    {
      field: 'sector',
      headerName: t('portfolio.col_sector'),
      minWidth: 120,
      flex: 1,
      renderCell: ({ row }) => <span className="text-slate-400 text-[10px]">{row.sector}</span>,
    },
    {
      field: 'weight_pct',
      headerName: t('portfolio.col_weight'),
      type: 'number',
      minWidth: 88,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => <span className="font-mono text-slate-300">{row.weight_pct.toFixed(1)}%</span>,
    },
    {
      field: 'beta',
      headerName: t('portfolio.col_beta'),
      type: 'number',
      minWidth: 80,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => row.beta == null
        ? <span className="text-slate-600">—</span>
        : <span className={`font-mono ${row.beta > 1.5 ? 'text-rose-400' : row.beta < 0 ? 'text-amber-400' : 'text-slate-300'}`}>{row.beta.toFixed(2)}</span>,
    },
    {
      field: 'volatility_annual',
      headerName: t('portfolio.col_volatility'),
      type: 'number',
      minWidth: 96,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => row.volatility_annual == null
        ? <span className="text-slate-600">—</span>
        : <span className={`font-mono ${row.volatility_annual > 0.5 ? 'text-rose-400' : 'text-slate-300'}`}>{(row.volatility_annual * 100).toFixed(1)}%</span>,
    },
  ], [t])

  const holdingColumns = useMemo<GridColDef<HoldingRead>[]>(() => {
    const marketValueOf = (row: HoldingRead) => (row.current_price ?? row.avg_buy_price) * row.quantity
    const pnlOf = (row: HoldingRead) =>
      row.unrealized_pnl ?? (marketValueOf(row) - row.avg_buy_price * row.quantity)

    return [
      {
        field: 'ticker',
        headerName: t('portfolio.col_symbol'),
        minWidth: 104,
        flex: 0.7,
        renderCell: ({ row }) => {
          const days = holdingDays(row.opened_at)
          const longHeld = days !== null && days >= LONG_HOLD_DAYS
          return (
            <span className="flex items-center gap-1.5 font-mono font-bold text-white text-sm">
              {row.ticker}
              {longHeld && (
                <span
                  title={t('portfolio.long_held_hint', { days })}
                  className="text-[9px] font-bold text-amber-300 bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 rounded-full normal-case"
                >
                  {days}d
                </span>
              )}
            </span>
          )
        },
      },
      {
        field: 'quantity',
        headerName: t('portfolio.col_quantity'),
        type: 'number',
        minWidth: 92,
        align: 'right',
        headerAlign: 'right',
        renderCell: ({ row }) => <span className="font-mono font-semibold text-slate-300">{(row.quantity ?? 0).toFixed(4)}</span>,
      },
      {
        field: 'avg_buy_price',
        headerName: t('portfolio.col_avg_cost'),
        type: 'number',
        minWidth: 96,
        align: 'right',
        headerAlign: 'right',
        renderCell: ({ row }) => <span className="font-mono text-slate-300">${(row.avg_buy_price ?? 0).toFixed(2)}</span>,
      },
      {
        field: 'current_price',
        headerName: t('portfolio.col_current_price'),
        type: 'number',
        minWidth: 104,
        align: 'right',
        headerAlign: 'right',
        renderCell: ({ row }) => <span className="font-mono text-slate-300">{row.current_price != null ? `$${row.current_price.toFixed(2)}` : '—'}</span>,
      },
      {
        field: 'market_value',
        headerName: t('portfolio.col_market_value'),
        type: 'number',
        minWidth: 104,
        align: 'right',
        headerAlign: 'right',
        valueGetter: (_value, row) => marketValueOf(row),
        renderCell: ({ row }) => <span className="font-mono text-white font-bold">${marketValueOf(row).toFixed(2)}</span>,
      },
      {
        field: 'unrealized_pnl',
        headerName: t('portfolio.col_unrealized_pnl'),
        type: 'number',
        minWidth: 112,
        align: 'right',
        headerAlign: 'right',
        valueGetter: (_value, row) => pnlOf(row),
        renderCell: ({ row }) => {
          const pnl = pnlOf(row)
          const positive = pnl >= 0
          return (
            <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-md ${
              positive
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15'
                : 'bg-rose-500/10 text-rose-400 border border-rose-500/15'
            }`}>
              {positive ? '+' : ''}${pnl.toFixed(2)}
            </span>
          )
        },
      },
    ]
  }, [t])
  const loadingRisk = showRisk && riskQuery.isFetching
  useQueryErrorToast(riskQuery.error, 'Risk dashboard failed', 'Risk')
  const loadRiskDashboard = useCallback(() => setShowRisk(true), [])

  const applySuggestion = useCallback(async (s: RebalanceSuggestion, idx: number) => {
    setApplyingIdx(idx)
    try {
      await orderMutation.mutateAsync({
        data: { ticker: s.ticker, action: s.action as APIOrderRequestAction, quantity: s.quantity },
      })
      notify('success', `${s.action} ${s.quantity} ${s.ticker} order placed`, 'Trade Executed')
      void fetchPortfolioData()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      notify('error', detail || 'Order failed', 'Trade Error')
    } finally {
      setApplyingIdx(null)
    }
  }, [fetchPortfolioData])

  if (loading && portfolios.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-400 gap-3">
        <Loader2 className="animate-spin text-violet-500" size={32} />
        <p className="text-xs font-semibold uppercase tracking-wider">{t('portfolio.loading')}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 md:p-6 flex flex-col items-center justify-center min-h-[300px] gap-4 text-center max-w-sm mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <AlertCircle size={24} />
        </div>
        <div>
          <p className="text-sm font-bold text-white uppercase tracking-wider mb-1">{t('portfolio.error')}</p>
          <p className="text-xs text-slate-500 leading-relaxed">{t('portfolio.error_hint')}</p>
        </div>
        <button
          onClick={() => fetchPortfolioData()}
          className="bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition duration-200 cursor-pointer shadow-lg shadow-violet-600/25"
        >
          {t('common.retry')}
        </button>
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header Panel */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <PieChart className="text-violet-400" size={20} />
            {t('portfolio.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">{t('portfolio.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportPortfolioCSV(
              holdings.map(h => ({ ...h, current_price: h.current_price ?? 0, unrealized_pnl: h.unrealized_pnl ?? 0 })),
              portfolios[0]?.cash_available ?? 0
            )}
            disabled={holdings.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white text-xs font-bold transition-all cursor-pointer disabled:opacity-40"
            title={t('portfolio.export_csv')}
          >
            <Download size={13} /> CSV
          </button>
          <button
            onClick={loadRiskDashboard}
            disabled={loadingRisk || holdings.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-500/10 hover:bg-slate-500/20 border border-slate-500/20 text-slate-400 hover:text-slate-300 text-xs font-bold transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loadingRisk ? <Loader2 size={13} className="animate-spin" /> : <Activity size={13} />}
            {loadingRisk ? 'Loading…' : 'Risk Dashboard'}
          </button>
          <button
            onClick={runRebalance}
            disabled={rebalancing || holdings.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 text-violet-400 hover:text-violet-300 text-xs font-bold transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {rebalancing
              ? <Loader2 size={13} className="animate-spin" />
              : <Sparkles size={13} />}
            {rebalancing ? 'Analysing…' : 'AI Rebalance'}
          </button>
          <button
            onClick={() => fetchPortfolioData()}
            disabled={loading}
            className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
            title={t('portfolio.refresh')}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* ── AI Rebalance Panel ─────────────────────────────────────────── */}
      {rebalanceResult && (
        <div className="glass-panel rounded-2xl overflow-hidden border border-violet-500/15">
          {/* Panel header */}
          <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between bg-violet-500/5">
            <div className="flex items-center gap-2.5">
              <Sparkles size={15} className="text-violet-400" />
              <span className="text-sm font-bold text-white">{t('portfolio.ai_analysis')}</span>
              <HealthBadge score={rebalanceResult.score} />
            </div>
            <button
              onClick={() => setRebalanceResult(null)}
              className="p-1.5 text-slate-500 hover:text-white rounded-lg hover:bg-white/5 transition cursor-pointer"
            >
              <X size={14} />
            </button>
          </div>

          <div className="p-5 space-y-5">
            {/* Summary */}
            <p className="text-xs text-slate-300 leading-relaxed">{rebalanceResult.summary}</p>

            {/* Issues */}
            {rebalanceResult.issues.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('portfolio.issues_detected')}</p>
                <div className="space-y-1.5">
                  {rebalanceResult.issues.map((issue, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs text-amber-300">
                      <ShieldAlert size={12} className="shrink-0 mt-0.5 text-amber-400" />
                      {issue}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suggestions */}
            {rebalanceResult.suggestions.length > 0 ? (
              <div className="space-y-2">
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('portfolio.suggested_actions')}</p>
                <div className="space-y-2">
                  {rebalanceResult.suggestions.map((s, i) => (
                    <div key={i} className="flex items-start gap-3 p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.04] hover:border-white/[0.07] transition">
                      <div className="shrink-0 mt-0.5">
                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${
                          s.action === 'SELL'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/20'
                            : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
                        }`}>{s.action}</span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-mono font-bold text-white">{s.ticker}</span>
                          <span className="text-xs text-slate-400">{s.quantity} shares</span>
                          <UrgencyBadge urgency={s.urgency} />
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">{s.rationale}</p>
                      </div>
                      <button
                        onClick={() => applySuggestion(s, i)}
                        disabled={applyingIdx !== null}
                        className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/80 hover:bg-violet-600 text-white text-[10px] font-bold transition disabled:opacity-40 cursor-pointer"
                      >
                        {applyingIdx === i
                          ? <Loader2 size={10} className="animate-spin" />
                          : <CheckCircle2 size={10} />}
                        Apply
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-emerald-400 flex items-center gap-2">
                <CheckCircle2 size={14} /> Portfolio looks well-balanced. No immediate actions needed.
              </p>
            )}

            <div className="pt-1 border-t border-white/[0.04] flex justify-end">
              <button
                onClick={runRebalance}
                disabled={rebalancing}
                className="text-[10px] text-slate-500 hover:text-violet-400 transition cursor-pointer font-semibold"
              >
                {rebalancing ? 'Analysing…' : 'Re-analyse'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Risk Dashboard Panel ────────────────────────────────────────── */}
      <ErrorBoundary name="RiskDashboard">
      {riskData && (
        <div className="glass-panel rounded-2xl overflow-hidden border border-slate-500/15">
          <button
            className="w-full px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between bg-slate-500/5 hover:bg-slate-500/10 transition cursor-pointer"
            onClick={() => setShowRisk(v => !v)}
          >
            <div className="flex items-center gap-2.5">
              <Activity size={15} className="text-slate-400" />
              <span className="text-sm font-bold text-white">{t('portfolio.risk_dashboard')}</span>
              {riskData.beta != null && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-500/10 text-slate-400 border-slate-500/20">
                  β {riskData.beta.toFixed(2)} · σ {riskData.volatility != null ? `${(riskData.volatility * 100).toFixed(1)}%` : '—'}
                </span>
              )}
            </div>
            {showRisk ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
          </button>

          {showRisk && (
            <div className="p-5 space-y-5">
              {riskData.message ? (
                <p className="text-xs text-slate-400">{riskData.message}</p>
              ) : (
                <>
                  {riskData.breaches && riskData.breaches.length > 0 && (
                    <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 space-y-1">
                      <p className="text-[11px] font-bold text-rose-300 uppercase tracking-wide">⚠ {t('portfolio.risk_breach_title')}</p>
                      {riskData.breaches.map((b, i) => (
                        <p key={i} className="text-xs text-rose-200/90">
                          {b.type === 'beta' && `${t('portfolio.risk_breach_beta')}: ${b.value?.toFixed(2)} > ${b.threshold}`}
                          {b.type === 'volatility' && `${t('portfolio.risk_breach_vol')}: ${((b.value ?? 0) * 100).toFixed(1)}% > ${((b.threshold ?? 0) * 100).toFixed(0)}%`}
                          {b.type === 'concentration' && `${t('portfolio.risk_breach_conc')}: ${b.sector} ${b.value?.toFixed(1)}% > ${b.threshold}%`}
                        </p>
                      ))}
                    </div>
                  )}
                  {/* Portfolio-level KPIs */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {[
                      { label: 'Portfolio Beta', value: riskData.beta != null ? riskData.beta.toFixed(2) : '—', hint: 'vs SPY', color: riskData.beta != null && riskData.beta > 1.5 ? 'text-rose-400' : 'text-white' },
                      { label: 'Annualized Vol', value: riskData.volatility != null ? `${(riskData.volatility * 100).toFixed(1)}%` : '—', hint: 'weighted avg', color: riskData.volatility != null && riskData.volatility > 0.4 ? 'text-rose-400' : 'text-amber-400' },
                      { label: 'Sectors', value: String(riskData.sector_weights.length), hint: 'diversification', color: 'text-white' },
                    ].map(k => (
                      <div key={k.label} className="bg-white/[0.02] border border-white/[0.04] rounded-xl p-3">
                        <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider">{k.label}</p>
                        <p className={`text-xl font-display font-bold leading-tight mt-0.5 ${k.color}`}>{k.value}</p>
                        <p className="text-[9px] text-slate-600 mt-0.5">{k.hint}</p>
                      </div>
                    ))}
                  </div>

                  {/* Sector concentration */}
                  {riskData.sector_weights.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('portfolio.sector_concentration')}</p>
                      <div className="space-y-2">
                        {riskData.sector_weights.map(s => (
                          <div key={s.sector} className="space-y-1">
                            <div className="flex items-center justify-between text-[10px]">
                              <span className="text-slate-300 font-semibold">{s.sector}</span>
                              <span className={`font-mono font-bold ${s.weight_pct > 40 ? 'text-rose-400' : s.weight_pct > 25 ? 'text-amber-400' : 'text-slate-400'}`}>
                                {s.weight_pct.toFixed(1)}%
                              </span>
                            </div>
                            <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all ${s.weight_pct > 40 ? 'bg-rose-500' : s.weight_pct > 25 ? 'bg-amber-500' : 'bg-violet-500'}`}
                                style={{ width: `${Math.min(s.weight_pct, 100)}%` }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Holdings risk table */}
                  {riskData.holdings_risk.length > 0 && (
                    <AppDataGrid<HoldingRisk>
                      rows={riskData.holdings_risk}
                      columns={riskColumns}
                      getRowId={row => row.ticker}
                      ariaLabel={t('portfolio.col_ticker')}
                      minHeight={200}
                      density="compact"
                      hideFooter
                    />
                  )}

                  {/* Top correlations */}
                  {riskData.correlation.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('portfolio.high_correlations')}</p>
                      <div className="flex flex-wrap gap-2">
                        {riskData.correlation
                          .filter(c => c.ticker_a < c.ticker_b && Math.abs(c.correlation) >= 0.6)
                          .sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation))
                          .slice(0, 8)
                          .map(c => (
                            <span key={`${c.ticker_a}-${c.ticker_b}`} className={`text-[10px] font-mono font-semibold px-2.5 py-1 rounded-lg border ${Math.abs(c.correlation) >= 0.85 ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>
                              {c.ticker_a}↔{c.ticker_b} {c.correlation > 0 ? '+' : ''}{c.correlation.toFixed(2)}
                            </span>
                          ))}
                        {riskData.correlation.filter(c => c.ticker_a < c.ticker_b && Math.abs(c.correlation) >= 0.6).length === 0 && (
                          <p className="text-[11px] text-slate-500 italic">{t('portfolio.no_high_correlations')}</p>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
      </ErrorBoundary>

      {/* Account Performance Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {portfolios.map(p => {
          const pnl = p.current_balance - p.initial_capital
          const pnlPct = p.initial_capital ? (pnl / p.initial_capital * 100) : 0
          const positive = pnl >= 0
          
          return (
            <div
              key={p.id}
              className={`glass-panel rounded-2xl p-5 space-y-4 border transition-all duration-300 relative overflow-hidden ${
                positive 
                  ? 'border-emerald-500/10 hover:border-emerald-500/20 hover:shadow-[0_8px_30px_rgb(16_185_129_/_4%)]' 
                  : 'border-rose-500/10 hover:border-rose-500/20 hover:shadow-[0_8px_30px_rgb(239_68_68_/_4%)]'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest bg-white/[0.03] px-2 py-0.5 rounded-lg border border-white/[0.04]">
                  {p.mode === 'simulation' ? t('orders.filter_simulation') : p.mode === 'live' ? t('orders.filter_live') : p.mode} / {p.broker}
                </span>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider border ${
                  p.status === 'active' 
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                    : 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                }`}>
                  {p.status}
                </span>
              </div>
              
              <div className="space-y-1">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">{t('portfolio.nav')}</span>
                <div className="flex items-center gap-1.5">
                  <DollarSign size={20} className={positive ? 'text-emerald-400' : 'text-rose-400'} />
                  <span className="text-2xl font-display font-extrabold text-white leading-none">
                    {p.current_balance.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <div className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-bold border ${
                  positive 
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/15' 
                    : 'bg-rose-500/10 text-rose-400 border-rose-500/15'
                }`}>
                  {positive ? <TrendingUp size={12} strokeWidth={2.5} /> : <TrendingDown size={12} strokeWidth={2.5} />}
                  <span>
                    {positive ? '+' : ''}{(pnl ?? 0).toFixed(2)} ({positive ? '+' : ''}{(pnlPct ?? 0).toFixed(2)}%)
                  </span>
                </div>
              </div>

              <div className="pt-3 border-t border-white/[0.04] grid grid-cols-2 gap-2 text-[10px] font-semibold text-slate-400">
                <div>
                  <span className="text-slate-500 uppercase block tracking-wider mb-0.5">{t('portfolio.initial')}</span>
                  <span className="text-white font-mono font-bold">${p.initial_capital.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US')}</span>
                </div>
                <div>
                  <span className="text-slate-500 uppercase block tracking-wider mb-0.5">{t('portfolio.cash')}</span>
                  <span className="text-white font-mono font-bold">${p.cash_available.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US', { minimumFractionDigits: 2 })}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Holdings Positions Table */}
      <div className="glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-white/[0.04] flex items-center justify-between">
          <h3 className="text-sm font-display font-bold text-slate-200 flex items-center gap-2">
            <Briefcase size={16} className="text-violet-400" />
            {t('portfolio.all_positions')}
          </h3>
          <span className="text-[10px] font-bold text-violet-400 bg-violet-500/10 px-2 py-0.5 rounded-full border border-violet-500/20 uppercase tracking-wide">
            {holdings.length} Positions
          </span>
        </div>
        
        {holdings.length === 0 ? (
          <div className="p-12 text-center">
            <Briefcase size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
            <p className="text-slate-400 text-xs font-semibold">{t('portfolio.no_positions')}</p>
            <p className="text-[10px] text-slate-500 mt-1">{t('portfolio.empty_hint')}</p>
          </div>
        ) : (
          <div className="p-2">
            <AppDataGrid<HoldingRead>
              rows={holdings}
              columns={holdingColumns}
              ariaLabel={t('portfolio.col_symbol')}
              minHeight={240}
              density="compact"
              hideFooter
            />
          </div>
        )}
      </div>

      {/* ── Correlation Heatmap ─────────────────────────────────────────── */}
      <ErrorBoundary name="CorrelationHeatmap">
        <CorrelationHeatmap />
      </ErrorBoundary>
    </div>
  )
}

function corrColor(v: number | null, isDiag: boolean): string {
  // Null where two tickers share no overlapping price history, so the pair has
  // no correlation to colour rather than a correlation of zero.
  if (isDiag || v === null) return 'bg-slate-800/60 text-slate-500'
  if (v < 0) return 'bg-sky-500/20 text-sky-300'
  if (v < 0.3) return 'bg-emerald-500/20 text-emerald-300'
  if (v < 0.7) return 'bg-amber-500/20 text-amber-300'
  return 'bg-rose-500/20 text-rose-300'
}

function CorrelationHeatmap() {
  const { t } = useTranslation()
  const [period, setPeriod] = useState('90d')

  const query = useTradingGetCorrelation({ period })
  const data = query.data ?? null
  const loading = query.isPending

  const diversificationLabel = (avg: number | null) => {
    if (avg === null) return ''
    if (avg < 0.3) return `✓ ${t('portfolio.diversification_excellent')}`
    if (avg < 0.5) return `✓ ${t('portfolio.diversification_good')}`
    if (avg < 0.7) return `⚠ ${t('portfolio.diversification_moderate')}`
    return `⚠ ${t('portfolio.diversification_low')}`
  }

  return (
    <div className="glass-panel rounded-2xl overflow-hidden border border-white/[0.04]">
      <div className="px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Grid3x3 size={14} className="text-violet-400" />
          <span className="text-sm font-bold text-white">{t('portfolio.correlation_heatmap')}</span>
          <span className="text-[10px] text-slate-500 ml-1">— pairwise return correlations</span>
        </div>
        <select
          value={period}
          onChange={e => setPeriod(e.target.value)}
          className="bg-slate-900 border border-white/[0.08] text-slate-300 text-[10px] font-semibold rounded-lg px-2 py-1 outline-none cursor-pointer"
        >
          {['30d','90d','180d','1y'].map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      <div className="p-5">
        {loading && (
          <div className="flex items-center gap-2 text-[11px] text-slate-500 py-6 justify-center">
            <Loader2 size={14} className="animate-spin text-violet-400" /> Computing correlations…
          </div>
        )}

        {!loading && data?.warning && (
          <div className="text-center py-6 opacity-50">
            <Grid3x3 size={24} className="mx-auto text-slate-600 mb-2" />
            <p className="text-[11px] text-slate-500">{data.warning}</p>
          </div>
        )}

        {!loading && data && !data.warning && data.tickers.length >= 2 && (
          <div className="space-y-4">
            {data.avg_correlation !== null && (
              <div className="flex items-center gap-3">
                <div className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">{t('portfolio.avg_correlation')}</div>
                <div className={`font-mono font-bold text-sm ${data.avg_correlation >= 0.7 ? 'text-rose-400' : data.avg_correlation >= 0.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {data.avg_correlation.toFixed(3)}
                </div>
                <div className={`text-[10px] font-semibold ${data.avg_correlation >= 0.7 ? 'text-rose-400' : data.avg_correlation >= 0.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                  {diversificationLabel(data.avg_correlation)}
                </div>
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="text-[10px] font-mono border-separate border-spacing-0.5">
                <thead>
                  <tr>
                    <th className="w-16" />
                    {data.tickers.map(t => (
                      <th key={t} className="text-slate-400 font-bold px-1 text-center w-14">{t}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.tickers.map((rowTicker, i) => (
                    <tr key={rowTicker}>
                      <td className="text-slate-400 font-bold pr-2 text-right">{rowTicker}</td>
                      {data.tickers.map((_, j) => {
                        const v = data.matrix[i][j]
                        return (
                          <td key={j} className={`text-center rounded px-1 py-1.5 ${corrColor(v, i === j)}`}>
                            {i === j || v === null ? '—' : v.toFixed(2)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-white/[0.04]">
              {[
                { label: '< 0 (Neg)', cls: 'bg-sky-500/20 text-sky-300' },
                { label: '0–0.3 (Low)', cls: 'bg-emerald-500/20 text-emerald-300' },
                { label: '0.3–0.7 (Moderate)', cls: 'bg-amber-500/20 text-amber-300' },
                { label: '> 0.7 (High)', cls: 'bg-rose-500/20 text-rose-300' },
              ].map(l => (
                <div key={l.label} className="flex items-center gap-1">
                  <div className={`w-3 h-3 rounded text-[8px] flex items-center justify-center font-bold ${l.cls}`} />
                  <span className="text-[9px] text-slate-500">{l.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

