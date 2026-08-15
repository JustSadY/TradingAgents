import { useState } from 'react'
import { useLogsListLogs, useLogsListMyLogs } from '../api/generated/logs/logs'
import { RefreshCw, Terminal, Clock, ChevronDown, ChevronRight } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'

interface Log {
  id: number
  level: string
  source: string
  message: string
  details: string | null
  user_id: number | null
  created_at: string
}

const LEVEL_BADGES: Record<string, string> = {
  INFO: 'text-sky-400 bg-sky-500/10 border border-sky-500/20',
  WARNING: 'text-amber-400 bg-amber-500/10 border border-amber-500/20',
  ERROR: 'text-rose-400 bg-rose-500/10 border border-rose-500/20',
  CRITICAL: 'text-red-300 bg-red-500/15 border border-red-500/30 animate-pulse',
}

interface RunEventPayload {
  event: string
  node?: string
  kind?: string
  phase?: string
  turn?: number
  tool_results?: number
  label?: string
  tool?: string
  tools?: string[]
  analyst?: string
  error?: string
  error_type?: string
  action?: string
  attempt?: number
  attempts?: number
  ms?: number
  delay?: number
  timeout_seconds?: number
}

function parseRunEvent(message: string): RunEventPayload | null {
  if (!message.startsWith('run_event ')) return null
  const rawPayload = message.substring(10).trim()
  try {
    const jsonStr = rawPayload.replace(/'/g, '"')
    return JSON.parse(jsonStr)
  } catch {
    const eventMatch = rawPayload.match(/"event":\s*"([^"]+)"/) || rawPayload.match(/'event':\s*'([^']+)'/)
    const nodeMatch = rawPayload.match(/"node":\s*"([^"]+)"/) || rawPayload.match(/'node':\s*'([^']+)'/)
    const kindMatch = rawPayload.match(/"kind":\s*"([^"]+)"/) || rawPayload.match(/'kind':\s*'([^']+)'/)
    const phaseMatch = rawPayload.match(/"phase":\s*"([^"]+)"/) || rawPayload.match(/'phase':\s*'([^']+)'/)
    const turnMatch = rawPayload.match(/"turn":\s*([0-9]+)/) || rawPayload.match(/'turn':\s*([0-9]+)/)
    const toolResultsMatch = rawPayload.match(/"tool_results":\s*([0-9]+)/) || rawPayload.match(/'tool_results':\s*([0-9]+)/)
    const labelMatch = rawPayload.match(/"label":\s*"([^"]+)"/) || rawPayload.match(/'label':\s*'([^']+)'/)
    const toolMatch = rawPayload.match(/"tool":\s*"([^"]+)"/) || rawPayload.match(/'tool':\s*'([^']+)'/)
    const toolsMatch = rawPayload.match(/"tools":\s*\[([^\]]*)\]/) || rawPayload.match(/'tools':\s*\[([^\]]*)\]/)
    const analystMatch = rawPayload.match(/"analyst":\s*"([^"]+)"/) || rawPayload.match(/'analyst':\s*'([^']+)'/)
    const errorMatch = rawPayload.match(/["']error["']:\s*(["'])(.*?)\1/)
    const errorTypeMatch = rawPayload.match(/"error_type":\s*"([^"]+)"/) || rawPayload.match(/'error_type':\s*'([^']+)'/)
    const actionMatch = rawPayload.match(/"action":\s*"([^"]+)"/) || rawPayload.match(/'action':\s*'([^']+)'/)
    const attemptMatch = rawPayload.match(/"attempt":\s*([0-9]+)/) || rawPayload.match(/'attempt':\s*([0-9]+)/)
    const attemptsMatch = rawPayload.match(/"attempts":\s*([0-9]+)/) || rawPayload.match(/'attempts':\s*([0-9]+)/)
    const msMatch = rawPayload.match(/"ms":\s*([0-9]+)/) || rawPayload.match(/'ms':\s*([0-9]+)/)
    const delayMatch = rawPayload.match(/"delay":\s*([0-9.]+)/) || rawPayload.match(/'delay':\s*([0-9.]+)/)
    const timeoutMatch = rawPayload.match(/"timeout_seconds":\s*([0-9.]+)/) || rawPayload.match(/'timeout_seconds':\s*([0-9.]+)/)
    const tools = toolsMatch
      ? Array.from(toolsMatch[1].matchAll(/["']([^"']+)["']/g), match => match[1]).filter(Boolean)
      : undefined

    if (eventMatch) {
      return {
        event: eventMatch[1],
        node: nodeMatch ? nodeMatch[1] : undefined,
        kind: kindMatch ? kindMatch[1] : undefined,
        phase: phaseMatch ? phaseMatch[1] : undefined,
        turn: turnMatch ? Number.parseInt(turnMatch[1]) : undefined,
        tool_results: toolResultsMatch ? Number.parseInt(toolResultsMatch[1]) : undefined,
        label: labelMatch ? labelMatch[1] : undefined,
        tool: toolMatch ? toolMatch[1] : undefined,
        tools: tools && tools.length > 0 ? tools : undefined,
        analyst: analystMatch ? analystMatch[1] : undefined,
        error: errorMatch ? errorMatch[2] : undefined,
        error_type: errorTypeMatch ? errorTypeMatch[1] : undefined,
        action: actionMatch ? actionMatch[1] : undefined,
        attempt: attemptMatch ? Number.parseInt(attemptMatch[1]) : undefined,
        attempts: attemptsMatch ? Number.parseInt(attemptsMatch[1]) : undefined,
        ms: msMatch ? Number.parseInt(msMatch[1]) : undefined,
        delay: delayMatch ? Number.parseFloat(delayMatch[1]) : undefined,
        timeout_seconds: timeoutMatch ? Number.parseFloat(timeoutMatch[1]) : undefined,
      }
    }
  }
  return null
}

/** Standalone so the switch stays flat; `t` is passed in rather than hooked. */
function renderLogMessage(l: Log, t: (key: string) => string) {
  if (l.source === 'tradingagents.run') {
    const payload = parseRunEvent(l.message)
    if (payload) {
      const { event, node, kind, phase, turn, tool_results, label, tool, tools, analyst, error, error_type, action, attempt, attempts, ms, delay, timeout_seconds } = payload
      const isAnalystContinuation = kind === 'analyst' && phase === 'continuation'
      const continuationDetail = isAnalystContinuation && (
        <span className="text-slate-400 font-mono text-[10px] bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.04] shrink-0">
          turn {turn ?? 2}{tool_results !== undefined ? ` · after ${tool_results} tool result${tool_results === 1 ? '' : 's'}` : ''}
        </span>
      )
      switch (event) {
        case 'node_start':
          return (
            <span className="flex items-center gap-2 flex-wrap">
              <span className="text-violet-400 font-bold shrink-0">{isAnalystContinuation ? 'Continue after tools' : 'Start'}</span>
              <span className="text-slate-400 capitalize shrink-0">{kind}:</span>
              <span className="text-white font-semibold font-mono break-all">{node}</span>
              {continuationDetail}
            </span>
          )
        case 'node_end':
          return (
            <span className="flex items-center gap-2 flex-wrap">
              <span className="text-emerald-400 font-bold shrink-0">{isAnalystContinuation ? 'Continuation complete' : 'Success'}</span>
              <span className="text-slate-400 capitalize shrink-0">{kind}:</span>
              <span className="text-white font-semibold font-mono break-all">{node}</span>
              {continuationDetail}
              <span className="text-emerald-400 font-bold font-mono text-xs bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/15 shrink-0">{ms}ms</span>
            </span>
          )
        case 'retry':
          return (
            <span className="flex flex-col gap-1 w-full">
              <span className="flex items-center gap-2 flex-wrap">
                <span className="text-amber-400 font-bold shrink-0">{t('logs.retry')}</span>
                <span className="text-slate-400 font-mono text-[10px] bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.04] shrink-0 font-semibold">{label}</span>
                <span className="text-amber-500 font-mono text-xs font-semibold bg-amber-500/10 border border-amber-500/15 px-2 py-0.5 rounded shrink-0">Attempt {attempt}/{attempts}</span>
                <span className="text-slate-400 font-mono text-xs shrink-0">(backoff {delay}s)</span>
              </span>
              {error && <span className="text-[11px] text-amber-400/80 font-mono italic pl-2 border-l border-amber-500/20">{error}</span>}
            </span>
          )
        case 'node_error':
          return (
            <span className="flex flex-col gap-1 w-full">
              <span className="flex items-center gap-2">
                <span className="text-rose-400 font-bold shrink-0">{t('logs.error')}</span>
                <span className="text-slate-400 capitalize shrink-0">{kind}:</span>
                <span className="text-white font-semibold font-mono break-all">{node}</span>
              </span>
              {error && <span className="text-[11px] text-rose-500 font-mono pl-2 border-l border-rose-500/20">{error}</span>}
            </span>
          )
        case 'node_skipped':
          return (
            <span className="flex items-center gap-2 flex-wrap">
              <span className="text-amber-400 font-bold shrink-0">{t('logs.fallback')}</span>
              <span className="text-slate-400 capitalize shrink-0">{kind}:</span>
              <span className="text-white font-semibold font-mono break-all">{node}</span>
              <span className="text-slate-500 text-xs italic shrink-0">(skipped on retry exhaustion)</span>
            </span>
          )
        case 'tool_error':
        case 'tool_timeout':
          return (
            <span className="flex flex-col gap-1 w-full">
              <span className="flex items-center gap-2 flex-wrap">
                <span className="text-rose-400 font-bold">{event === 'tool_timeout' ? 'Tool Timed Out' : 'Tool Failed'}</span>
                {(tool || tools?.length) && (
                  <span className="text-white font-semibold font-mono break-all">
                    {tool || tools?.join(', ')}
                  </span>
                )}
                {analyst && <span className="text-slate-400 text-xs">analyst: {analyst}</span>}
                {error_type && <span className="text-amber-400 font-mono text-[10px] bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/15">{error_type}</span>}
                {timeout_seconds !== undefined && <span className="text-slate-400 text-xs">after {timeout_seconds}s</span>}
              </span>
              {error && <span className="text-[11px] text-rose-400/80 font-mono pl-2 border-l border-rose-500/20">{error}</span>}
              {action === 'continue_without_tool' && <span className="text-[11px] text-slate-500 italic">{t('logs.tool_continue')}</span>}
            </span>
          )
        case 'fallback_error':
          return (
            <span className="flex flex-col gap-1 w-full">
              <span className="flex items-center gap-2">
                <span className="text-red-400 font-bold shrink-0">{t('logs.fallback_failed')}</span>
                <span className="text-slate-400 shrink-0">node:</span>
                <span className="text-white font-semibold font-mono break-all">{node}</span>
              </span>
              {error && <span className="text-[11px] text-red-500 font-mono pl-2 border-l border-red-500/20">{error}</span>}
            </span>
          )
        default:
          return <span className="text-slate-300 font-medium">{l.message}</span>
      }
    }
  }
  return <span className="text-slate-300 font-medium">{l.message}</span>
}

export default function Logs() {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [level, setLevel] = useState('')
  const [source, setSource] = useState('')
  const [userIdFilter, setUserIdFilter] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  // Admins read the tenant-wide log; everyone else is restricted to their own.
  // Both hooks are declared unconditionally (rules of hooks) and only the one
  // matching the current role is enabled.
  const params = {
    ...(level ? { level } : {}),
    ...(source ? { source } : {}),
    ...(isAdmin && userIdFilter ? { user_id: Number(userIdFilter) } : {}),
  }
  const adminQuery = useLogsListLogs(params, { query: { enabled: isAdmin } })
  const myQuery = useLogsListMyLogs(
    { ...(level ? { level } : {}) },
    { query: { enabled: !isAdmin } },
  )
  const active = isAdmin ? adminQuery : myQuery
  const logs = (active.data ?? []) as Log[]
  const loading = active.isPending
  const fetch = () => active.refetch()

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header Panel */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Terminal className="text-violet-400" size={20} />
            {t('logs.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">{t('logs.subtitle')}</p>
        </div>
        
        <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end flex-wrap sm:flex-nowrap">
          {isAdmin && (
            <input
              type="number"
              placeholder={t('logs.user_id_placeholder')}
              className="glass-input rounded-xl px-3 py-2 text-xs outline-none w-20 sm:w-24 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
              value={userIdFilter}
              onChange={e => setUserIdFilter(e.target.value)}
            />
          )}
          <select
            className="glass-input rounded-xl px-3 py-2 text-xs outline-none cursor-pointer w-full sm:w-44"
            value={source}
            onChange={e => setSource(e.target.value)}
          >
            <option value="">{t('logs.all_sources')}</option>
            <option value="tradingagents.run">🤖 AI Run Trace</option>
            <option value="backend.services.analysis_service">📊 Analysis Service</option>
            <option value="backend.services.trading_orchestrator">💼 Trading Orchestrator</option>
          </select>
          <select
            className="glass-input rounded-xl px-3 py-2 text-xs outline-none cursor-pointer w-full sm:w-32"
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
            title={t('logs.refresh')}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-slate-400 text-sm">{t('common.loading')}</p>
        </div>
      ) : logs.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Terminal size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('logs.no_logs')}</p>
          <p className="text-[10px] text-slate-500 mt-1">{t('logs.empty_for_level')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {logs.map(l => {
            const isExpanded = expanded === l.id
            return (
              <div
                key={l.id}
                className={`group glass-panel rounded-2xl border transition-all duration-200 cursor-pointer overflow-hidden ${
                  isExpanded ? 'border-violet-500/20 bg-gray-950/60' : 'border-white/[0.04] hover:border-white/[0.08] hover:bg-white/[0.01]'
                }`}
                onClick={() => setExpanded(isExpanded ? null : l.id)}
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-center p-4">
                  {/* Status Badges & Time */}
                  <div className="flex items-center justify-between md:justify-start gap-3 shrink-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider ${LEVEL_BADGES[l.level] || 'text-slate-400'}`}>
                        {l.level}
                      </span>
                      <span className="text-violet-400 text-[10px] font-mono font-semibold bg-violet-500/10 px-2 py-0.5 rounded border border-violet-500/15">
                        {l.source}
                      </span>
                      {l.user_id !== null && l.user_id !== undefined && (
                        <span className="text-emerald-400 text-[10px] font-mono font-semibold bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/15">
                          User #{l.user_id}
                        </span>
                      )}
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
                    {renderLogMessage(l, t)}
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
