import { useEffect, useState } from 'react'
import axios from 'axios'
import { RefreshCw, Terminal, Clock, ChevronDown, ChevronRight } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Log {
  id: number
  level: string
  source: string
  message: string
  details: string | null
  created_at: string
}

const LEVEL_BADGES: Record<string, string> = {
  INFO: 'text-sky-400 bg-sky-500/10 border border-sky-500/20',
  WARNING: 'text-amber-400 bg-amber-500/10 border border-amber-500/20',
  ERROR: 'text-rose-400 bg-rose-500/10 border border-rose-500/20',
  CRITICAL: 'text-red-300 bg-red-500/15 border border-red-500/30 animate-pulse',
}

export default function Logs() {
  const { t } = useTranslation()
  const [logs, setLogs] = useState<Log[]>([])
  const [level, setLevel] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<number | null>(null)

  const fetch = () => {
    setLoading(true)
    const params = level ? `?level=${level}` : ''
    axios.get(`/api/logs${params}`)
      .then(r => {
        setLogs(r.data)
        setLoading(false)
      })
      .catch(() => {
        setLoading(false)
      })
  }

  useEffect(() => { fetch() }, [level])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header Panel */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Terminal className="text-violet-400" size={20} />
            {t('logs.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">Audit active process outputs, exception callstacks, and database migrations events</p>
        </div>
        
        <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
          <select
            className="glass-input rounded-xl px-3 py-2 text-xs outline-none cursor-pointer w-full sm:w-40"
            value={level}
            onChange={e => setLevel(e.target.value)}
          >
            <option value="">{t('logs.all_levels')}</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <button
            onClick={fetch}
            disabled={loading}
            className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer shrink-0"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-slate-400 text-sm">{t('common.loading') || 'Loading Logs...'}</p>
        </div>
      ) : logs.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Terminal size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('logs.no_logs')}</p>
          <p className="text-[10px] text-slate-500 mt-1">No system logs recorded for the selected severity level</p>
        </div>
      ) : (
        <div className="space-y-3">
          {logs.map(l => {
            const isExpanded = expanded === l.id
            return (
              <div
                key={l.id}
                className={`glass-panel rounded-2xl border transition-all duration-200 cursor-pointer overflow-hidden ${
                  isExpanded ? 'border-violet-500/20 bg-gray-950/60' : 'border-white/[0.04] hover:border-white/[0.08] hover:bg-white/[0.01]'
                }`}
                onClick={() => setExpanded(isExpanded ? null : l.id)}
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-center p-4">
                  {/* Status Badges & Time */}
                  <div className="flex items-center justify-between md:justify-start gap-3 shrink-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${LEVEL_BADGES[l.level] || 'text-slate-400'}`}>
                        {l.level}
                      </span>
                      <span className="text-violet-400 text-[10px] font-mono font-semibold bg-violet-500/10 px-2 py-0.5 rounded border border-violet-500/15">
                        {l.source}
                      </span>
                    </div>
                    
                    <span className="text-slate-500 text-[10px] font-mono md:hidden flex items-center gap-1">
                      <Clock size={10} />
                      {new Date(l.created_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {/* Desktop Time */}
                  <span className="text-slate-500 text-[10px] font-mono hidden md:flex items-center gap-1 shrink-0">
                    <Clock size={10} className="text-slate-600" />
                    {new Date(l.created_at).toLocaleString()}
                  </span>

                  {/* Message */}
                  <span className="text-slate-300 flex-1 text-xs md:text-sm font-sans leading-relaxed break-words font-medium pr-4">
                    {l.message}
                  </span>

                  {/* Expand Indicator */}
                  {l.details && (
                    <div className="text-slate-500 group-hover:text-white shrink-0 self-end md:self-auto transition-colors ml-auto md:ml-0">
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </div>
                  )}
                </div>

                {/* Details Callstack */}
                {isExpanded && l.details && (
                  <div className="border-t border-white/[0.04] bg-black/60 px-5 py-4">
                    <pre className="text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto max-h-96 select-text">
                      {l.details}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}


