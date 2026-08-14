import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useShareGetSharedReport } from '../api/generated/share/share'
import {
  TrendingUp, TrendingDown, Minus, Clock, AlertCircle, Loader2,
  FileText, BookOpen, Scale, Zap,
} from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import type { SharedReportResponse } from '../api/types'
import { DebateHistoryWidget } from '../components/analysis/DebateHistoryWidget'
import { MarkdownReport } from '../components/report/MarkdownReport'
import { formatSharedReportValue } from '../utils/sharedReport'

// ── Section definitions ──────────────────────────────────────────────────────

interface SectionDef {
  key: string
  labelKey: string
  fallbackLabel: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  category: 'decision' | 'analyst' | 'research'
  kind?: 'text' | 'structured' | 'debates' | 'portfolioDecision'
}

// Keep this list aligned with the public API contract.  The original shared
// page only listed the three final decision fields even though the API already
// returned every analyst report and both debate histories.  That made a valid
// share link look like it had lost most of its analysis.
const SHARED_REPORT_SECTION_DEFS: SectionDef[] = [
  { key: 'portfolio_decision', labelKey: 'analysis.pm.title', fallbackLabel: 'Portfolio Manager Recommendation', icon: Scale, category: 'decision', kind: 'portfolioDecision' },
  { key: 'final_decision', labelKey: 'analysis.section.final_trade_decision', fallbackLabel: 'Final Decision', icon: Scale, category: 'decision' },
  { key: 'investment_plan', labelKey: 'analysis.section.investment_plan', fallbackLabel: 'Research Evidence Summary', icon: BookOpen, category: 'decision' },
  { key: 'trader_plan', labelKey: 'analysis.section.trader_investment_plan', fallbackLabel: 'Legacy Trader Proposal', icon: Zap, category: 'decision' },
  { key: 'judge_decision', labelKey: 'analysis.section.judge_decision', fallbackLabel: 'Judge Decision', icon: Scale, category: 'decision' },
  { key: 'trader_proposal_json', labelKey: 'analysis.section.trader_proposal_json', fallbackLabel: 'Legacy Trade Proposal Details', icon: Zap, category: 'decision', kind: 'structured' },

  { key: 'market_report', labelKey: 'analysis.section.market_report', fallbackLabel: 'Market Analysis', icon: TrendingUp, category: 'analyst' },
  { key: 'fundamentals_report', labelKey: 'analysis.section.fundamentals_report', fallbackLabel: 'Fundamental Analysis', icon: BookOpen, category: 'analyst' },
  { key: 'news_report', labelKey: 'analysis.section.news_report', fallbackLabel: 'News Analysis', icon: FileText, category: 'analyst' },
  { key: 'sentiment_report', labelKey: 'analysis.section.sentiment_report', fallbackLabel: 'Sentiment Analysis', icon: TrendingUp, category: 'analyst' },
  { key: 'macro_report', labelKey: 'analysis.section.macro_report', fallbackLabel: 'Macro Analysis', icon: FileText, category: 'analyst' },
  { key: 'options_report', labelKey: 'analysis.section.options_report', fallbackLabel: 'Options Analysis', icon: FileText, category: 'analyst' },
  { key: 'quant_report', labelKey: 'analysis.section.quant_report', fallbackLabel: 'Quantitative Analysis', icon: FileText, category: 'analyst' },
  { key: 'earnings_report', labelKey: 'analysis.section.earnings_report', fallbackLabel: 'Earnings Analysis', icon: FileText, category: 'analyst' },
  { key: 'insider_report', labelKey: 'analysis.section.insider_report', fallbackLabel: 'Insider Activity', icon: FileText, category: 'analyst' },
  { key: 'ownership_report', labelKey: 'analysis.section.ownership_report', fallbackLabel: 'Institutional Ownership', icon: FileText, category: 'analyst' },
  { key: 'ratings_report', labelKey: 'analysis.section.ratings_report', fallbackLabel: 'Analyst Ratings', icon: FileText, category: 'analyst' },
  { key: 'short_interest_report', labelKey: 'analysis.section.short_interest_report', fallbackLabel: 'Short Interest', icon: FileText, category: 'analyst' },
  { key: 'valuation_report', labelKey: 'analysis.section.valuation_report', fallbackLabel: 'Valuation Comparison', icon: FileText, category: 'analyst' },
  { key: 'catalyst_report', labelKey: 'analysis.section.catalyst_report', fallbackLabel: 'Upcoming Catalysts', icon: FileText, category: 'analyst' },
  { key: 'review_report', labelKey: 'analysis.section.review_report', fallbackLabel: 'Performance Review', icon: FileText, category: 'analyst' },
  { key: 'synthesis_report', labelKey: 'analysis.section.synthesis_report', fallbackLabel: 'Synthesis', icon: FileText, category: 'analyst' },
  { key: 'audit_report', labelKey: 'analysis.section.audit_report', fallbackLabel: 'Audit', icon: FileText, category: 'analyst' },
  { key: 'agent_qa_report', labelKey: 'analysis.section.agent_qa_report', fallbackLabel: 'Cross-Examination', icon: FileText, category: 'analyst' },

  { key: 'bull_history', labelKey: 'analysis.section.bull_history', fallbackLabel: 'Bull Arguments', icon: TrendingUp, category: 'research', kind: 'structured' },
  { key: 'bear_history', labelKey: 'analysis.section.bear_history', fallbackLabel: 'Bear Arguments', icon: TrendingDown, category: 'research', kind: 'structured' },
  { key: 'debates', labelKey: 'analysis.section.investment_debate_history', fallbackLabel: 'Consensus & Risk Debate', icon: Scale, category: 'research', kind: 'debates' },
  { key: 'risk_metrics', labelKey: 'analysis.section.risk_metrics', fallbackLabel: 'Risk Metrics', icon: Scale, category: 'research', kind: 'structured' },
]

// ── Sub-components ───────────────────────────────────────────────────────────

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return null
  const s = signal.toLowerCase()
  const isBuy = ['buy', 'strong_buy', 'overweight'].includes(s)
  const isSell = ['sell', 'strong_sell', 'underweight'].includes(s)
  const cls = isBuy
    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
    : isSell
      ? 'bg-rose-500/15 text-rose-300 border-rose-500/30'
      : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
  const Icon = isBuy ? TrendingUp : isSell ? TrendingDown : Minus
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-sm font-bold ${cls}`}>
      <Icon size={14} /> {signal}
    </span>
  )
}

function hasSharedSectionContent(def: SectionDef, report: SharedReportResponse): boolean {
  const hasCanonicalPortfolioDecision = isNonEmptyRecord(report.portfolio_decision)
  // New reports have one final authority: the Portfolio Manager.  Keep the
  // old Trader output reachable only for historical reports that do not have
  // that canonical decision, so public links cannot show competing trade
  // sizes or directions.
  if (hasCanonicalPortfolioDecision && (def.key === 'trader_plan' || def.key === 'trader_proposal_json')) {
    return false
  }
  if (def.kind === 'portfolioDecision') return hasCanonicalPortfolioDecision
  if (def.kind === 'debates') {
    return Boolean(
      formatSharedReportValue(report.investment_debate_history)
      || formatSharedReportValue(report.risk_debate_history),
    )
  }
  return Boolean(formatSharedReportValue((report as unknown as Record<string, unknown>)[def.key]))
}

function isNonEmptyRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0)
}

function ReportContent({ content }: { content: string }) {
  // Extract embedded chart images (IMAGE_DATA:data:image/...)
  let imageSrc: string | null = null
  let textContent = content
  if (content.includes('IMAGE_DATA:')) {
    const imageRegex = /IMAGE_DATA:\s*(data:image\/(?:png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+)\s*/
    const match = content.match(imageRegex)
    if (match) {
      imageSrc = match[1]
      textContent = content.replace(imageRegex, '')
    }
  }
  return (
    <div className="space-y-4">
      {imageSrc && (
        <div className="rounded-xl overflow-hidden border border-white/[0.08] bg-black/40">
          <img src={imageSrc} alt="Chart Analysis" className="w-full h-auto" />
        </div>
      )}
      <MarkdownReport content={textContent} />
    </div>
  )
}

function PortfolioDecisionContent({ decision }: { decision: SharedReportResponse['portfolio_decision'] }) {
  const { t } = useTranslation()
  if (!isNonEmptyRecord(decision)) return null

  const label = (key: string, fallback: string) => {
    const translated = t(key)
    return translated === key ? fallback : translated
  }
  const stringValue = (key: string) => typeof decision[key] === 'string' ? decision[key].trim() : ''
  const numberValue = (key: string) => {
    const value = decision[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  const money = (value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const confidencePercent = (value: number) => `${(value * 100).toFixed(1)}%`
  // `position_size_pct` is already a percentage in the canonical PM schema.
  // Only confidence is stored as a 0..1 fraction.
  const allocationPercent = (value: number) => `${value.toFixed(1)}%`

  const rating = stringValue('rating')
  const summary = stringValue('executive_summary')
  const thesis = stringValue('investment_thesis')
  const confidence = numberValue('confidence_score')
  const values: Array<[string, string, number | null, (value: number) => string]> = [
    ['entry_price', label('analysis.pm.entry', 'Entry'), numberValue('entry_price'), money],
    ['stop_loss', label('analysis.pm.stop', 'Stop Loss'), numberValue('stop_loss'), money],
    ['take_profit_price', label('analysis.pm.target', 'Take Profit'), numberValue('take_profit_price'), money],
    ['position_size_pct', label('analysis.pm.allocation', 'Allocation'), numberValue('position_size_pct'), allocationPercent],
    ['suggested_capital', label('analysis.pm.capital', 'Suggested Capital'), numberValue('suggested_capital'), money],
    ['price_target', label('analysis.pm.price_target', 'Price Target'), numberValue('price_target'), money],
    ['recommended_leverage', label('analysis.pm.leverage', 'Leverage'), numberValue('recommended_leverage'), (value: number) => `${value.toFixed(1)}x`],
    ['liquidation_price', label('analysis.pm.liquidation', 'Liquidation Price'), numberValue('liquidation_price'), money],
  ].filter((item): item is [string, string, number, (value: number) => string] => item[2] !== null)
  const timeHorizon = stringValue('time_horizon')

  return (
    <div data-testid="shared-portfolio-decision" className="space-y-4 rounded-2xl border border-violet-400/20 bg-violet-500/[0.05] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-violet-300/10 pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-white">{label('analysis.pm.title', 'Portfolio Manager Recommendation')}</h3>
          <p className="text-[11px] text-violet-200/75">{label('analysis.pm.single_authority', 'Single AI authority for sizing and trade parameters')}</p>
        </div>
        <div className="flex items-center gap-2">
          {rating && <SignalBadge signal={rating} />}
          {confidence !== null && (
            <span className="rounded-lg border border-violet-300/20 bg-violet-400/10 px-2.5 py-1 text-xs font-mono font-bold text-violet-100">
              {confidencePercent(confidence)}
            </span>
          )}
        </div>
      </div>

      {summary && (
        <section>
          <h4 className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">{label('analysis.pm.summary', 'Executive Summary')}</h4>
          <MarkdownReport content={summary} />
        </section>
      )}

      {(values.length > 0 || timeHorizon) && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-3 rounded-xl border border-white/[0.06] bg-black/15 p-3 sm:grid-cols-3">
          {values.map(([key, valueLabel, value, formatter]) => (
            <div key={key} className="min-w-0">
              <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">{valueLabel}</span>
              <span className="font-mono text-xs text-slate-100">{formatter(value)}</span>
            </div>
          ))}
          {timeHorizon && (
            <div className="min-w-0">
              <span className="block text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label('analysis.pm.horizon', 'Time Horizon')}</span>
              <span className="text-xs text-slate-100">{timeHorizon}</span>
            </div>
          )}
        </div>
      )}

      {thesis && (
        <section className="border-t border-white/[0.06] pt-4">
          <h4 className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">{label('analysis.pm.thesis', 'Investment Thesis')}</h4>
          <MarkdownReport content={thesis} />
        </section>
      )}
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function SharedReport() {
  const { token } = useParams<{ token: string }>()
  const { t } = useTranslation()
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const sectionDefs = SHARED_REPORT_SECTION_DEFS

  // Public page: the token comes from the URL, so the query stays disabled
  // until one is present rather than requesting /api/share/undefined.
  const query = useShareGetSharedReport(token ?? '', { query: { enabled: Boolean(token) } })
  const report = (query.data ?? null) as SharedReportResponse | null
  const loading = Boolean(token) && query.isPending
  const error = query.error
    ? ((query.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || t('shared_report.error_not_found'))
    : null

  // Build available sections from all data the public API explicitly exposes.
  // This is intentionally not limited to final decisions: a shared analysis
  // should contain the same analyst evidence and debate record as the owner
  // sees in History.
  const availableSections = report
    ? sectionDefs.filter(def => hasSharedSectionContent(def, report))
    : []

  if (!token || error || (!loading && !report)) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="text-center space-y-3">
        <div className="w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mx-auto">
          <AlertCircle size={24} className="text-rose-400" />
        </div>
        <p className="text-white font-bold">{error || t('shared_report.error_not_found')}</p>
        <p className="text-xs text-slate-500">{t('shared_report.error_expired')}</p>
      </div>
    </div>
  )

  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <Loader2 size={28} className="animate-spin text-violet-400" />
    </div>
  )

  if (!report) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
      <div className="text-center space-y-3">
        <div className="w-14 h-14 rounded-full bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mx-auto">
          <AlertCircle size={24} className="text-rose-400" />
        </div>
        <p className="text-white font-bold">{error || t('shared_report.error_unavailable')}</p>
        <p className="text-xs text-slate-500">{t('shared_report.error_expired')}</p>
      </div>
    </div>
  )

  const expires = new Date(report.expires_at)
  const activeSection = availableSections.find(s => s.key === activeKey) || availableSections[0]
  const activeContent = activeSection && activeSection.kind !== 'debates' && activeSection.kind !== 'portfolioDecision'
    ? formatSharedReportValue((report as unknown as Record<string, unknown>)[activeSection.key])
    : ''

  const getLabel = (def: SectionDef) => {
    const translated = t(def.labelKey)
    return translated !== def.labelKey ? translated : def.fallbackLabel
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top bar */}
      <div className="border-b border-white/[0.06] bg-slate-900/60 backdrop-blur-sm px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <span className="text-xs font-bold text-violet-400 uppercase tracking-widest">{t('shared_report.brand')}</span>
        <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
          <Clock size={11} />
          {t('shared_report.expires')} {expires.toLocaleDateString()}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Report header */}
        <div className="space-y-3 mb-6">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-display font-extrabold text-white tracking-tight">{report.ticker}</h1>
              {report.trade_date && <p className="text-slate-500 text-sm mt-1">{report.trade_date}</p>}
            </div>
            <SignalBadge signal={report.signal ?? null} />
          </div>

          {(report.llm_provider || report.duration_seconds) && (
            <div className="flex flex-wrap gap-3 text-[10px] text-slate-600 font-mono">
              {report.llm_provider && <span>{t('shared_report.llm')}: {report.llm_provider}{report.llm_model ? ` / ${report.llm_model}` : ''}</span>}
              {report.duration_seconds != null && <span>{t('shared_report.duration')}: {report.duration_seconds.toFixed(1)}s</span>}
            </div>
          )}

          {/* Section count summary */}
          <div className="flex items-center gap-2 text-[10px] text-slate-600">
            <FileText size={11} />
            <span>{availableSections.length} {t('shared_report.sections')}</span>
          </div>
        </div>

        {availableSections.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-600">
            <FileText size={32} className="opacity-25 mb-3" />
            <p className="text-sm">{t('shared_report.no_sections')}</p>
          </div>
        ) : (
          <div className="flex flex-col lg:flex-row gap-6 items-start">
            {/* ── Sidebar (desktop: vertical, mobile: horizontal scroll) ── */}
            <nav className="w-full lg:w-64 shrink-0 lg:sticky lg:top-16">
              <div className="flex lg:flex-col gap-1.5 overflow-x-auto lg:overflow-x-visible pb-2 lg:pb-0 scrollbar-none">
                {availableSections.map(def => {
                  const Icon = def.icon
                  const isActive = def.key === activeSection?.key
                  return (
                    <button
                      key={def.key}
                      onClick={() => setActiveKey(def.key)}
                      className={`
                        flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-left transition-all duration-200
                        whitespace-nowrap lg:whitespace-normal shrink-0 lg:shrink cursor-pointer
                        ${isActive
                          ? 'bg-violet-500/15 text-violet-300 border border-violet-500/30 shadow-lg shadow-violet-500/5'
                          : 'text-slate-500 hover:text-slate-300 hover:bg-white/[0.03] border border-transparent'
                        }
                      `}
                    >
                      <Icon size={14} className={isActive ? 'text-violet-400' : 'text-slate-600'} />
                      <span className="text-[11px] font-semibold">{getLabel(def)}</span>
                    </button>
                  )
                })}
              </div>
            </nav>

            {/* ── Main content area ── */}
            <div className="flex-1 min-w-0">
              {activeSection?.kind === 'debates' ? (
                <DebateHistoryWidget
                  investmentHistory={report.investment_debate_history}
                  riskHistory={report.risk_debate_history}
                />
              ) : activeSection?.kind === 'portfolioDecision' ? (
                <PortfolioDecisionContent decision={report.portfolio_decision} />
              ) : activeSection && activeContent && (
                <div className="bg-slate-900/30 border border-white/[0.04] rounded-2xl overflow-hidden animate-in fade-in duration-300">
                  {/* Section header */}
                  <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[0.04] bg-slate-900/40">
                    <activeSection.icon size={16} className="text-violet-400 shrink-0" />
                    <h2 className="text-sm font-bold text-white">{getLabel(activeSection)}</h2>
                  </div>
                  {/* Section body */}
                  <div className="p-5">
                    <ReportContent content={activeContent} />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        <p className="text-[10px] text-slate-700 text-center border-t border-white/[0.04] pt-6 mt-8">
          {t('shared_report.footer')}
        </p>
      </div>
    </div>
  )
}
