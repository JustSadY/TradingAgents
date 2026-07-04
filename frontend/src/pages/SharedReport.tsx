import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import {
  TrendingUp, TrendingDown, Minus, Clock, AlertCircle, Loader2,
  FileText, BookOpen, Scale, Zap,
} from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import type { SharedReportResponse } from '../api/types'

// ── Section definitions ──────────────────────────────────────────────────────

interface SectionDef {
  key: string
  labelKey: string
  fallbackLabel: string
  icon: React.ComponentType<{ size?: number; className?: string }>
  category: 'decision' | 'analyst' | 'research'
}

const FALLBACK_SECTION_DEFS: SectionDef[] = [
  { key: 'final_decision',       labelKey: 'analysis.section.final_trade_decision', fallbackLabel: 'Final Decision',  icon: Scale,        category: 'decision' },
  { key: 'investment_plan',      labelKey: 'analysis.section.investment_plan',       fallbackLabel: 'Investment Plan', icon: BookOpen,     category: 'decision' },
  { key: 'trader_plan',          labelKey: 'analysis.section.trader_investment_plan',fallbackLabel: 'Trader Proposal', icon: Zap,          category: 'decision' },
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
      <pre className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed font-mono select-text">
        {textContent}
      </pre>
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function SharedReport() {
  const { token } = useParams<{ token: string }>()
  const { t } = useTranslation()
  const [report, setReport] = useState<SharedReportResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeKey, setActiveKey] = useState<string | null>(null)
  const sectionDefs = FALLBACK_SECTION_DEFS

  useEffect(() => {
    if (!token) {
      setError(t('shared_report.error_not_found'))
      setLoading(false)
      return
    }
    axios.get<SharedReportResponse>(`/api/share/${token}`)
      .then(r => setReport(r.data))
      .catch(e => setError(e.response?.data?.detail || t('shared_report.error_not_found')))
      .finally(() => setLoading(false))
  }, [token])

  // Build available sections from report data
  const availableSections = report
    ? sectionDefs.filter(def => {
        const val = (report as unknown as Record<string, unknown>)[def.key]
        return typeof val === 'string' && val.trim().length > 0
      })
    : []

  // Set the first available section as active on data load
  useEffect(() => {
    if (availableSections.length > 0 && !activeKey) {
      setActiveKey(availableSections[0].key)
    }
  }, [availableSections.length]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <Loader2 size={28} className="animate-spin text-violet-400" />
    </div>
  )

  if (error || !report) return (
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
  const activeContent = activeSection
    ? ((report as unknown as Record<string, unknown>)[activeSection.key] as string)
    : null

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
              {activeSection && activeContent && (
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
