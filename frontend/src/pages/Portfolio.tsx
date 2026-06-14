import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { TrendingUp, TrendingDown, DollarSign, Briefcase, Loader2, AlertCircle, RefreshCw, PieChart, Sparkles, X, CheckCircle2, ShieldAlert, Activity, ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { notify } from '../utils/notify'

interface Holding {
  id: number
  ticker: string
  quantity: number
  avg_buy_price: number
  current_price: number | null
  unrealized_pnl: number | null
  updated_at: string
}

interface PortfolioRow {
  id: number
  mode: string
  broker: string
  initial_capital: number
  current_balance: number
  cash_available: number
  status: string
}

interface HoldingRisk {
  ticker: string
  weight_pct: number
  volatility_annual: number | null
  beta: number | null
  sector: string
}

interface RiskData {
  portfolio_beta: number | null
  portfolio_volatility: number | null
  sector_weights: { sector: string; weight_pct: number }[]
  correlation: { ticker_a: string; ticker_b: string; correlation: number }[]
  holdings_risk: HoldingRisk[]
  message?: string
}

interface RebalanceSuggestion {
  action: 'BUY' | 'SELL'
  ticker: string
  quantity: number
  rationale: string
  urgency: 'low' | 'medium' | 'high'
}

interface RebalanceResult {
  summary: string
  score: number
  issues: string[]
  suggestions: RebalanceSuggestion[]
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

function UrgencyBadge({ urgency }: { urgency: 'low' | 'medium' | 'high' }) {
  const styles = {
    high: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    medium: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    low: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  }
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border capitalize ${styles[urgency]}`}>
      {urgency}
    </span>
  )
}

export default function Portfolio() {
  const { t, language } = useTranslation()
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [portfolios, setPortfolios] = useState<PortfolioRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [rebalancing, setRebalancing] = useState(false)
  const [rebalanceResult, setRebalanceResult] = useState<RebalanceResult | null>(null)
  const [applyingIdx, setApplyingIdx] = useState<number | null>(null)
  const [riskData, setRiskData] = useState<RiskData | null>(null)
  const [loadingRisk, setLoadingRisk] = useState(false)
  const [showRisk, setShowRisk] = useState(false)

  const fetchPortfolioData = useCallback((quiet = false) => {
    if (!quiet) setLoading(true)
    setError(false)
    Promise.all([
      axios.get<PortfolioRow[]>('/api/portfolio').then(r => r.data),
      axios.get<Holding[]>('/api/portfolio/holdings').then(r => r.data),
    ]).then(([p, h]) => {
      setPortfolios(p)
      setHoldings(h)
    }).catch(() => {
      if (!quiet) setError(true)
    }).finally(() => {
      if (!quiet) setLoading(false)
    })
  }, [])

  useEffect(() => {
    fetchPortfolioData()
    const interval = setInterval(() => {
      fetchPortfolioData(true)
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchPortfolioData])

  const runRebalance = useCallback(async () => {
    setRebalancing(true)
    try {
      const { data } = await axios.post<RebalanceResult>('/api/trading/rebalance')
      setRebalanceResult(data)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Rebalance failed', 'AI Rebalance')
    } finally {
      setRebalancing(false)
    }
  }, [])

  const loadRiskDashboard = useCallback(async () => {
    setLoadingRisk(true)
    try {
      const { data } = await axios.get<RiskData>('/api/trading/risk-dashboard')
      setRiskData(data)
      setShowRisk(true)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Risk dashboard failed', 'Risk')
    } finally {
      setLoadingRisk(false)
    }
  }, [])

  const applySuggestion = useCallback(async (s: RebalanceSuggestion, idx: number) => {
    setApplyingIdx(idx)
    try {
      await axios.post('/api/trading/order', {
        ticker: s.ticker,
        action: s.action,
        quantity: s.quantity,
      })
      notify('success', `${s.action} ${s.quantity} ${s.ticker} order placed`, 'Trade Executed')
      fetchPortfolioData(false)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Order failed', 'Trade Error')
    } finally {
      setApplyingIdx(null)
    }
  }, [fetchPortfolioData])

  if (loading && portfolios.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-slate-400 gap-3">
        <Loader2 className="animate-spin text-violet-500" size={32} />
        <p className="text-xs font-semibold uppercase tracking-wider">{t('portfolio.loading') || 'Loading portfolio...'}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6 flex flex-col items-center justify-center min-h-[300px] gap-4 text-center max-w-sm mx-auto">
        <div className="w-12 h-12 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <AlertCircle size={24} />
        </div>
        <div>
          <p className="text-sm font-bold text-white uppercase tracking-wider mb-1">{t('portfolio.error') || 'Error Loading Portfolio'}</p>
          <p className="text-xs text-slate-500 leading-relaxed">Ensure backend service is running and retry the connection request</p>
        </div>
        <button
          onClick={() => fetchPortfolioData(false)}
          className="bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold px-4 py-2.5 rounded-xl transition duration-200 cursor-pointer shadow-lg shadow-violet-600/25"
        >
          {t('common.retry') || 'Retry Connection'}
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
          <p className="text-xs text-slate-500 mt-1">Review active assets allocations, average cost basis, and real-time ledger returns</p>
        </div>
        <div className="flex items-center gap-2">
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
            onClick={() => fetchPortfolioData(false)}
            disabled={loading}
            className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
            title="Refresh"
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
              <span className="text-sm font-bold text-white">AI Portfolio Analysis</span>
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
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Issues Detected</p>
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
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Suggested Actions</p>
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
      {riskData && (
        <div className="glass-panel rounded-2xl overflow-hidden border border-slate-500/15">
          <button
            className="w-full px-5 py-3.5 border-b border-white/[0.04] flex items-center justify-between bg-slate-500/5 hover:bg-slate-500/10 transition cursor-pointer"
            onClick={() => setShowRisk(v => !v)}
          >
            <div className="flex items-center gap-2.5">
              <Activity size={15} className="text-slate-400" />
              <span className="text-sm font-bold text-white">Risk Dashboard</span>
              {riskData.portfolio_beta !== null && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full border bg-slate-500/10 text-slate-400 border-slate-500/20">
                  β {riskData.portfolio_beta.toFixed(2)} · σ {riskData.portfolio_volatility !== null ? `${(riskData.portfolio_volatility * 100).toFixed(1)}%` : '—'}
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
                  {/* Portfolio-level KPIs */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {[
                      { label: 'Portfolio Beta', value: riskData.portfolio_beta !== null ? riskData.portfolio_beta.toFixed(2) : '—', hint: 'vs SPY', color: riskData.portfolio_beta !== null && riskData.portfolio_beta > 1.5 ? 'text-rose-400' : 'text-white' },
                      { label: 'Annualized Vol', value: riskData.portfolio_volatility !== null ? `${(riskData.portfolio_volatility * 100).toFixed(1)}%` : '—', hint: 'weighted avg', color: riskData.portfolio_volatility !== null && riskData.portfolio_volatility > 0.4 ? 'text-rose-400' : 'text-amber-400' },
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
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Sector Concentration</p>
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
                    <div className="overflow-x-auto rounded-xl border border-white/[0.04]">
                      <table className="w-full text-xs min-w-[440px]">
                        <thead>
                          <tr className="text-[9px] uppercase tracking-wider text-slate-500 bg-white/[0.01]">
                            <th className="px-4 py-2.5 text-left font-bold">Ticker</th>
                            <th className="px-4 py-2.5 text-left font-bold">Sector</th>
                            <th className="px-4 py-2.5 text-right font-bold">Weight</th>
                            <th className="px-4 py-2.5 text-right font-bold">Beta</th>
                            <th className="px-4 py-2.5 text-right font-bold">Vol (ann.)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.02]">
                          {riskData.holdings_risk.map(h => (
                            <tr key={h.ticker} className="hover:bg-white/[0.01] transition-colors">
                              <td className="px-4 py-2.5 font-mono font-bold text-white">{h.ticker}</td>
                              <td className="px-4 py-2.5 text-slate-400 text-[10px]">{h.sector}</td>
                              <td className="px-4 py-2.5 text-right font-mono text-slate-300">{h.weight_pct.toFixed(1)}%</td>
                              <td className="px-4 py-2.5 text-right font-mono">
                                {h.beta !== null
                                  ? <span className={h.beta > 1.5 ? 'text-rose-400' : h.beta < 0 ? 'text-amber-400' : 'text-slate-300'}>{h.beta.toFixed(2)}</span>
                                  : <span className="text-slate-600">—</span>}
                              </td>
                              <td className="px-4 py-2.5 text-right font-mono">
                                {h.volatility_annual !== null
                                  ? <span className={h.volatility_annual > 0.5 ? 'text-rose-400' : 'text-slate-300'}>{(h.volatility_annual * 100).toFixed(1)}%</span>
                                  : <span className="text-slate-600">—</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* Top correlations */}
                  {riskData.correlation.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">High Correlations</p>
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
                          <p className="text-[11px] text-slate-500 italic">No high correlations detected — good diversification.</p>
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
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Net Asset Value (NAV)</span>
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
            <p className="text-[10px] text-slate-500 mt-1">Acquire assets via mock simulation trading or trigger autonomous strategies</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300 min-w-[650px]">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                  <th className="px-5 py-3.5 text-left font-bold">{t('portfolio.col_symbol')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_quantity')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_avg_cost')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_current_price')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_market_value')}</th>
                  <th className="px-5 py-3.5 text-right font-bold">{t('portfolio.col_unrealized_pnl')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02]">
                {holdings.map(h => {
                  const price = h.current_price ?? h.avg_buy_price
                  const marketValue = price * h.quantity
                  const pnl = h.unrealized_pnl ?? (marketValue - h.avg_buy_price * h.quantity)
                  const positive = pnl >= 0
                  
                  return (
                    <tr key={h.id} className="hover:bg-white/[0.01] transition-colors">
                      <td className="px-5 py-3.5 font-mono font-bold text-white text-sm">{h.ticker}</td>
                      <td className="px-5 py-3.5 text-right font-mono font-semibold text-slate-300">{(h.quantity ?? 0).toFixed(4)}</td>
                      <td className="px-5 py-3.5 text-right font-mono text-slate-300">${(h.avg_buy_price ?? 0).toFixed(2)}</td>
                      <td className="px-5 py-3.5 text-right font-mono text-slate-300">
                        {h.current_price != null ? `$${(h.current_price ?? 0).toFixed(2)}` : '—'}
                      </td>
                      <td className="px-5 py-3.5 text-right font-mono text-white font-bold">${(marketValue ?? 0).toFixed(2)}</td>
                      <td className="px-5 py-3.5 text-right">
                        <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-0.5 rounded-md ${
                          positive 
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/15' 
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/15'
                        }`}>
                          {positive ? '+' : ''}${(pnl ?? 0).toFixed(2)}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}


