import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import axios from 'axios'
import { TrendingUp, TrendingDown, Minus, Clock, AlertCircle, Loader2 } from 'lucide-react'

interface ReportData {
  ticker: string
  trade_date: string | null
  signal: string | null
  market_report: string | null
  sentiment_report: string | null
  news_report: string | null
  fundamental_report: string | null
  research_report: string | null
  final_decision: string | null
  duration_seconds: number | null
  llm_provider: string | null
  llm_model: string | null
  expires_at: string
  created_at: string
}

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return null
  const s = signal.toLowerCase()
  const isBuy = s.includes('buy') || s.includes('over')
  const isSell = s.includes('sell') || s.includes('under')
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

function Section({ title, content }: { title: string; content: string | null }) {
  if (!content) return null
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-white border-b border-white/[0.06] pb-2">{title}</h3>
      <div className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{content}</div>
    </div>
  )
}

export default function SharedReport() {
  const { token } = useParams<{ token: string }>()
  const [report, setReport] = useState<ReportData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    axios.get<ReportData>(`/api/share/${token}`)
      .then(r => setReport(r.data))
      .catch(e => setError(e.response?.data?.detail || 'Report not found or expired'))
      .finally(() => setLoading(false))
  }, [token])

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
        <p className="text-white font-bold">{error || 'Report unavailable'}</p>
        <p className="text-xs text-slate-500">This link may have expired or been revoked.</p>
      </div>
    </div>
  )

  const expires = new Date(report.expires_at)

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Top bar */}
      <div className="border-b border-white/[0.06] bg-slate-900/60 backdrop-blur-sm px-6 py-3 flex items-center justify-between">
        <span className="text-xs font-bold text-violet-400 uppercase tracking-widest">TradingAgents — Shared Report</span>
        <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
          <Clock size={11} />
          Expires {expires.toLocaleDateString()}
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8">
        {/* Report header */}
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-3xl font-display font-extrabold text-white tracking-tight">{report.ticker}</h1>
              {report.trade_date && <p className="text-slate-500 text-sm mt-1">{report.trade_date}</p>}
            </div>
            <SignalBadge signal={report.signal} />
          </div>

          {(report.llm_provider || report.duration_seconds) && (
            <div className="flex flex-wrap gap-3 text-[10px] text-slate-600 font-mono">
              {report.llm_provider && <span>LLM: {report.llm_provider}{report.llm_model ? ` / ${report.llm_model}` : ''}</span>}
              {report.duration_seconds && <span>Duration: {report.duration_seconds.toFixed(1)}s</span>}
            </div>
          )}
        </div>

        {/* Report sections */}
        <div className="space-y-8">
          <Section title="Portfolio Manager Decision" content={report.final_decision} />
          <Section title="Market Analysis" content={report.market_report} />
          <Section title="Research & Synthesis" content={report.research_report} />
          <Section title="Sentiment Analysis" content={report.sentiment_report} />
          <Section title="News Analysis" content={report.news_report} />
          <Section title="Fundamentals" content={report.fundamental_report} />
        </div>

        <p className="text-[10px] text-slate-700 text-center border-t border-white/[0.04] pt-6">
          Powered by TradingAgents · This is a read-only shared report
        </p>
      </div>
    </div>
  )
}
