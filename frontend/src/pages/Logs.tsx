import { useEffect, useState } from 'react'
import axios from 'axios'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface Log {
  id: number
  level: string
  source: string
  message: string
  details: string | null
  created_at: string
}

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'text-sky-400 bg-sky-950/40 border border-sky-900/30',
  WARNING: 'text-yellow-400 bg-yellow-950/40 border border-yellow-900/30',
  ERROR: 'text-red-400 bg-red-950/40 border border-red-900/30',
  CRITICAL: 'text-red-300 bg-red-950/50 border border-red-800/40',
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
    <div className="p-4 md:p-6 space-y-4 md:space-y-6">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-gray-800">
        <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight">{t('logs.title')}</h2>
        <div className="flex gap-3 items-center w-full sm:w-auto justify-between sm:justify-end">
          <select
            className="bg-gray-900 text-gray-200 border border-gray-800 rounded-xl px-3 py-2 text-sm outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition-all cursor-pointer w-full sm:w-40"
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
            className="flex items-center justify-center p-2 rounded-xl bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-400 hover:text-white transition-colors cursor-pointer shrink-0"
            title="Yenile"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-gray-500 text-sm">{t('common.loading')}</p>
        </div>
      ) : (
        logs.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <p className="text-gray-500 text-sm">{t('logs.no_logs')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {logs.map(l => (
              <div
                key={l.id}
                className="bg-gray-900/40 hover:bg-gray-900/80 border border-gray-800/80 hover:border-gray-700/80 rounded-xl p-3 md:px-4 md:py-3 transition-all cursor-pointer group"
                onClick={() => setExpanded(expanded === l.id ? null : l.id)}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-3 text-sm">
                  {/* Metadata Row for mobile view, aligned elements for desktop view */}
                  <div className="flex items-center justify-between md:justify-start gap-2 shrink-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] md:text-xs font-bold px-2 py-0.5 rounded tracking-wide uppercase ${LEVEL_COLORS[l.level] || 'text-slate-400'}`}>
                        {l.level}
                      </span>
                      <span className="text-indigo-400 text-xs font-mono font-semibold bg-indigo-950/40 px-1.5 py-0.5 rounded border border-indigo-900/30">
                        {l.source}
                      </span>
                    </div>
                    <span className="text-gray-500 text-[11px] md:hidden font-mono">
                      {new Date(l.created_at).toLocaleString('tr-TR')}
                    </span>
                  </div>

                  {/* Desktop Date */}
                  <span className="text-gray-400 text-xs hidden md:inline shrink-0 font-mono">
                    {new Date(l.created_at).toLocaleString('tr-TR')}
                  </span>

                  {/* Message */}
                  <span className="text-gray-300 flex-1 text-sm leading-relaxed break-words font-sans group-hover:text-white transition-colors">
                    {l.message}
                  </span>
                </div>
                {expanded === l.id && l.details && (
                  <pre className="mt-3 text-xs text-gray-300 bg-gray-950/80 border border-gray-800 rounded-lg p-3 whitespace-pre-wrap overflow-x-auto font-mono leading-relaxed shadow-inner">
                    {l.details}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}
