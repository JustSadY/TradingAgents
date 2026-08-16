import { useState, useRef, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAnalysisListAnalysis,
  useAnalysisListPortfolioAnalyses,
  useAnalysisDeleteAnalysis,
  useAnalysisClearHistory,
  useAnalysisRunAnalysis,
  useAnalysisRunPortfolioRun,
  useAnalysisCancelAnalysis,
  useAnalysisCostEstimate,
  useAnalysisTimeTravelResume,
  analysisGetAnalysis,
  getAnalysisGetAnalysisQueryKey,
  analysisGetPortfolioAnalysis,
  getAnalysisGetPortfolioAnalysisQueryKey,
  analysisGetLatestAnalysis,
} from '../api/generated/analysis/analysis'
import { useShareCreateShare } from '../api/generated/share/share'
// probeActiveTask below deliberately keeps a direct axios call: it is a
// WebSocket-reconnect policy probe with its own 2s timeout that must classify
// 401/403/unavailable itself, not server state worth caching.
import axios from 'axios'
import { getAccessToken } from '../contexts/AuthContext'
import { useMeta } from '../hooks/useMeta'
import { useActiveTasks } from '../hooks/useActiveTasks'
import { notify } from '../utils/notify'
import { exportMarkdown, exportPDF } from '../utils/exportReport'
import { exportAnalysesCSV } from '../utils/csvExport'
import { sendBrowserNotification } from '../utils/browserNotify'
import { buildPublicShareUrl } from '../utils/shareLink'
import { useTranslation } from '../contexts/LanguageContext'
import {
  Loader2, CheckCircle, AlertCircle, History,
  X, BarChart2, FileText, Zap,
  Download, FileDown, AlertTriangle, Scale, Share2, Copy,
  MessageSquare, Bot, Terminal, BookOpen, Trash2
} from 'lucide-react'
import type { AnalysisListItem, AnalysisResultRead, MultiTickerListItem, MultiTickerResultRead } from '../api/generated/model'
import { SignalBadge } from '../components/analysis/SignalBadge'
import { ReportCard } from '../components/analysis/ReportCard'
import { MarkdownReport } from '../components/report/MarkdownReport'
import { AnalysisControls, type AnalysisStartError } from '../components/analysis/AnalysisControls'

import { DebateBubble, DebateHistoryWidget, parseDebateMessage } from '../components/analysis/DebateHistoryWidget'
import { AnalysisChatWidget } from '../components/analysis/AnalysisChatWidget'
import { RiskMetricsCard } from '../components/analysis/RiskMetricsCard'
import { MentalModelTicker } from '../components/analysis/MentalModelTicker'
import { StrategyTransitionCard } from '../components/analysis/StrategyTransitionCard'
import { ErrorBoundary } from '../components/ErrorBoundary'
import {
  WS_KEEPALIVE_INTERVAL_MS,
  WS_KEEPALIVE_MESSAGE,
  WS_MAX_RECONNECT_RETRIES,
  WS_NORMAL_CLOSE_CODE,
  WS_OPEN,
  closeAnalysisWebSocket,
  openAnalysisWebSocket,
  probeActiveTask,
} from '../analysis/analysisSocket'
import { isRecord } from '../utils/isRecord'
import {
  readableSectionLabel,
  reportKeyForStreamingAgent,
  visibleReportEntries,
} from '../analysis/streamingReports'
import {
  orderActionLabel,
  orderResultLogLine,
  readOrderResult,
  sameOrderResult,
  type AnalysisOrderResult,
} from '../analysis/orderResult'
import {
  STORAGE_KEY,
  TASK_KEY,
  clearTaskMarkerFor,
  loadRunState,
  type SavedRun,
} from '../analysis/runStorage'
import { readPortfolioDecision } from '../analysis/portfolioDecision'
import type { AnalysisEventType } from '../analysis/analysisEvents'
import { analysisStartError } from '../analysis/startError'

/**
 * One frame off `/ws/analysis/{task_id}`.
 *
 * `type` comes from the backend's own vocabulary rather than being `string`,
 * so a typo in a branch below is a compile error and a newly declared event is
 * caught by `analysisEvents.test.ts`. The payload fields stay optional: this
 * is a union of seventeen shapes flattened into one object, and narrowing each
 * branch properly would be a larger change than the drift it prevents.
 */
interface WsEvent {
  type: AnalysisEventType
  seconds_since_last_event?: number; threshold?: number
  section?: string; content?: string; signal?: string
  final_decision?: string; message?: string; duration_seconds?: number
  llm_calls?: number; status?: string; agent?: string; analysis_id?: number
  label?: string; stage?: string; node?: string
  thought?: string; metrics?: any; token?: string; tokens_in?: number; tokens_out?: number
  debate_type?: string; sender?: string
  attempt?: number; max_attempts?: number; error?: string; kind?: string
  error_type?: string; elapsed_seconds?: number
  estimated_cost_usd?: number
  outcome?: string; action?: string; ticker?: string; quantity?: number
  price?: number; filled_quantity?: number; filled_price?: number
  reason?: string; reason_code?: string
}
const TERMINAL_TASK_CONFIRMATION_DELAY_MS = 250

interface QualityFields {
  score: number; confidence: string; reports_total: number; reports_present: number; reports_degraded: number; fallback_used: boolean
}
type RunQuality = NonNullable<QualityFields>

function QualityBadge({ quality }: { quality: RunQuality }) {
  const { t } = useTranslation()
  const tone: Record<string, string> = {
    high: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    medium: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    low: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  }
  const cls = tone[quality.confidence] ?? tone.low
  const title =
    `${t('analysis.quality.reports')}: ${quality.reports_present}/${quality.reports_total}` +
    (quality.reports_degraded ? ` • ${quality.reports_degraded} ${t('analysis.quality.degraded')}` : '') +
    (quality.fallback_used ? ` • ${t('analysis.quality.fallback')}` : '')
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md border ${cls}`}
    >
      {quality.confidence ? t(`analysis.quality.${quality.confidence}`) : '?'} · {quality.score}
    </span>
  )
}

function PortfolioDecisionCard({
  acceptedPortfolioDecision,
  chartAnnotations,
  legacyTraderJson,
  streamedPortfolioDecision,
}: {
  acceptedPortfolioDecision?: unknown
  chartAnnotations?: unknown
  legacyTraderJson?: string | null
  streamedPortfolioDecision?: unknown
}) {
  const { t } = useTranslation()
  const decision = readPortfolioDecision(acceptedPortfolioDecision, chartAnnotations, legacyTraderJson, streamedPortfolioDecision)
  if (!decision) return null

  const confidence = decision.confidenceScore === undefined
    ? null
    : decision.confidenceScore <= 1 ? decision.confidenceScore * 100 : decision.confidenceScore
  const money = (value: number) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  const values = [
    decision.entryPrice === undefined ? null : [t('analysis.pm.entry'), money(decision.entryPrice)],
    decision.stopLoss === undefined ? null : [t('analysis.pm.stop'), money(decision.stopLoss)],
    decision.takeProfit === undefined ? null : [t('analysis.pm.target'), money(decision.takeProfit)],
    decision.positionSizePct === undefined ? null : [t('analysis.pm.allocation'), `${decision.positionSizePct.toFixed(1)}%`],
    decision.suggestedCapital === undefined ? null : [t('analysis.pm.capital'), money(decision.suggestedCapital)],
    decision.recommendedLeverage === undefined ? null : [t('analysis.pm.leverage'), `${decision.recommendedLeverage.toFixed(1)}x`],
  ].filter((entry): entry is [string, string] => entry !== null)

  return (
    <div data-testid="portfolio-decision-card" className="rounded-2xl border border-violet-500/20 bg-violet-500/[0.06] p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h4 className="text-[10px] font-bold text-violet-300 uppercase tracking-widest">{t('analysis.pm.title')}</h4>
          <p className="text-[10px] text-slate-400">
            {decision.source === 'portfolio_manager' ? t('analysis.pm.single_authority') : t('analysis.pm.legacy_fallback')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {decision.rating && <SignalBadge signal={decision.rating} />}
          {confidence !== null && <span className="rounded-md border border-violet-400/20 bg-violet-400/10 px-2 py-0.5 text-[10px] font-mono font-bold text-violet-200">{confidence.toFixed(0)}%</span>}
        </div>
      </div>
      {values.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-2 text-[10px]">
          {values.map(([label, value]) => (
            <div key={label}>
              <span className="block text-slate-500 uppercase tracking-wide font-semibold">{label}</span>
              <span className="font-mono text-slate-100">{value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Analysis completion and order execution are deliberately distinct states.
 * A final model signal is a recommendation; this card only confirms whether
 * the separately guarded execution layer actually placed a sandbox order.
 */
function AutomatedOrderResultCard({ result }: { result: AnalysisOrderResult | null }) {
  const { t } = useTranslation()
  const outcome = result?.outcome
  const presentation = outcome === 'filled'
    ? { Icon: CheckCircle, panel: 'border-emerald-500/25 bg-emerald-500/[0.06]', icon: 'text-emerald-400', text: 'text-emerald-200' }
    : outcome === 'skipped'
      ? { Icon: AlertTriangle, panel: 'border-amber-500/25 bg-amber-500/[0.06]', icon: 'text-amber-400', text: 'text-amber-100' }
      : outcome
        ? { Icon: AlertCircle, panel: 'border-rose-500/25 bg-rose-500/[0.06]', icon: 'text-rose-400', text: 'text-rose-100' }
        : { Icon: AlertTriangle, panel: 'border-slate-600/40 bg-slate-900/35', icon: 'text-slate-400', text: 'text-slate-300' }
  const status = outcome ? t(`analysis.order.outcome.${outcome}`) : t('analysis.order.pending')
  const explanation = result?.message ?? result?.reason
  const action = orderActionLabel(result?.action, t)

  return (
    <div
      data-testid="analysis-order-result"
      data-outcome={outcome ?? 'pending'}
      className={`rounded-2xl border p-4 space-y-3 ${presentation.panel}`}
    >
      <div className="flex items-start gap-2.5">
        <presentation.Icon size={16} className={`${presentation.icon} shrink-0 mt-0.5`} />
        <div className="min-w-0 space-y-0.5">
          <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('analysis.order.title')}</h3>
          <p className={`text-xs font-bold ${presentation.text}`}>{status}</p>
        </div>
      </div>

      {result ? (
        <>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
            <div>
              <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.symbol')}</span>
              <span className="font-mono text-slate-100">{result.ticker}</span>
            </div>
            {action && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.action')}</span>
                <span className="font-mono text-slate-100">{action}</span>
              </div>
            )}
            {result.quantity !== undefined && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.quantity')}</span>
                <span className="font-mono text-slate-100">{result.quantity.toLocaleString()}</span>
              </div>
            )}
            {result.price !== undefined && (
              <div>
                <span className="block text-slate-500 uppercase tracking-wide font-semibold">{t('analysis.order.price')}</span>
                <span className="font-mono text-slate-100">${result.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
            )}
          </div>
          {explanation && <p className="border-t border-white/[0.07] pt-2 text-[11px] leading-relaxed text-slate-300">{explanation}</p>}
        </>
      ) : (
        <p className="text-[11px] leading-relaxed text-slate-400">{t('analysis.order.pending_description')}</p>
      )}
    </div>
  )
}

function RunTab() {
  const { t } = useTranslation()
  // Loading from sessionStorage returns new object/array references. Keep the
  // initial snapshot stable for this mount so a streamed state update does not
  // retrigger the task-resume effect and replace the live WebSocket.
  const [saved] = useState<SavedRun>(() => loadRunState())
  const [ticker, setTicker] = useState(saved.ticker)
  const [date, setDate] = useState(saved.date)
  const [assetType, setAssetType] = useState(saved.assetType)
  const [running, setRunning] = useState(saved.runStatus === 'running')
  const [stopping, setStopping] = useState(false)
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'done' | 'error'>(saved.runStatus)
  const [signal, setSignal] = useState<string | null>(saved.signal)
  const [reports, setReports] = useState<Record<string, string>>(saved.reports)
  const [log, setLog] = useState<string[]>(saved.log)
  const [activeSection, setActiveSection] = useState<string | null>(saved.activeSection)
  const [analysisId, setAnalysisId] = useState<number | null>(saved.analysisId || null)
  const [detail, setDetail] = useState<AnalysisResultRead | null>(null)
  const [activeTab, setActiveTab] = useState<'consensus' | 'reports' | 'debate' | 'chat' | 'timetravel'>('consensus')
  const [liveDebate, setLiveDebate] = useState<{ sender: string; content: string; type: string }[]>(saved.liveDebate || [])
  const [orderResult, setOrderResult] = useState<AnalysisOrderResult | null>(saved.orderResult)
  const [liveDebateTab, setLiveDebateTab] = useState<'inv' | 'risk'>('inv')
  const [riskMetrics, setRiskMetrics] = useState<any>(null)
  const [mentalModel, setMentalModel] = useState<{ agent: string; thought: string } | null>(null)
  const [stats, setStats] = useState<{ llmCalls: number; tokensIn: number; tokensOut: number; estimatedCost?: number } | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const taskIdRef = useRef<string | null>(null)
  // Timers need to invoke the latest attach callback without making the
  // callback recursively reference its own initializer.
  const attachWsRef = useRef<(taskId: string, reconnectAttempt?: number) => void>(() => {})
  // `useActiveTasks` is intentionally polled, so it can briefly contain an
  // already-terminal task after the WebSocket delivered (or inferred) its
  // terminal state. Do not let that stale snapshot attach the task again.
  const terminalTaskIdRef = useRef<string | null>(null)
  // A persisted task should be resumed once per mount. In particular, don't
  // let a language/context rerender or a delayed API response replace an
  // already-live socket for the same task.
  const resumingTaskIdRef = useRef<string | null>(null)
  const preRefreshLogRef = useRef<string[] | null>(null)
  const seenLogRef = useRef<Set<string>>(new Set())
  const stoppedByUserRef = useRef(false)
  // Invalidate a pending POST /run when Stop is clicked before it resolves.
  // The backend may already have created the task, so the late response still
  // needs a best-effort cancel request, but it must never revive this UI.
  const runRequestRef = useRef(0)
  // `/api/analysis/latest` is only bootstrap data.  Once this mount has taken
  // ownership of an active/new run, a delayed bootstrap response is stale.
  const runStartedRef = useRef(saved.runStatus === 'running')
  // Always-current ticker for use inside the WS handler, so attachWs doesn't
  // need `ticker` in its deps (which recreated the socket on every keystroke)
  // and the completion toast never shows a stale/empty symbol.
  const tickerRef = useRef(ticker)
  useEffect(() => { tickerRef.current = ticker }, [ticker])
  const lastPersistRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wsKeepaliveRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const clearWsKeepalive = useCallback(() => {
    if (wsKeepaliveRef.current) {
      clearInterval(wsKeepaliveRef.current)
      wsKeepaliveRef.current = null
    }
  }, [])

  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? {}
  const sectionLabelsRef = useRef(sectionLabels)
  useEffect(() => { sectionLabelsRef.current = sectionLabels }, [sectionLabels])
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]
  const [currentStep, setCurrentStep] = useState<{ label: string; stage: string } | null>(null)

  const runAnalysis = useAnalysisRunAnalysis()
  const cancelAnalysis = useAnalysisCancelAnalysis()
  const [showRerunModal, setShowRerunModal] = useState(false)
  const [startError, setStartError] = useState<AnalysisStartError | null>(null)

  const handleTickerChange = useCallback((nextTicker: string) => {
    setTicker(nextTicker)
    setStartError(null)
  }, [])

  const {
    activeTasks,
    loading: activeTasksLoading,
    unavailable: activeTasksUnavailable,
  } = useActiveTasks()

  useEffect(() => {
    const now = Date.now()
    if (runStatus === 'running' && now - lastPersistRef.current < 2000) return
    lastPersistRef.current = now
    try {
      // Don't persist reports while running — they're large and will be re-streamed via WS on reconnect
      const payload = runStatus === 'running'
        ? { ticker, date, assetType, runStatus, signal, reports: {}, log: [], liveDebate: [], orderResult, activeSection, analysisId }
        : { ticker, date, assetType, runStatus, signal, reports, log, liveDebate, orderResult, activeSection, analysisId }
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // QuotaExceededError — ignore, state lives in memory
    }
  }, [ticker, date, assetType, runStatus, signal, reports, log, liveDebate, orderResult, activeSection, analysisId])

  useEffect(() => {
    if (analysisId && runStatus === 'done' && !detail) {
      analysisGetAnalysis(analysisId).then(d => setDetail(d as never)).catch(e => console.error('Failed to fetch analysis detail', e))
    }
  }, [analysisId, runStatus, detail])

  // Cross-device: mount'ta idle durumdaysak en son tamamlanmış analizi yükle
  useEffect(() => {
    if (runStartedRef.current || runStatus !== 'idle' || analysisId) return
    if (runStatus === 'idle' && !analysisId) {
      analysisGetLatestAnalysis().then(latest => {
        // A user action, active-task sync, or persisted-task resume may have
        // started while this bootstrap request was in flight.
        if (runStartedRef.current) return
        const a = latest as unknown as AnalysisResultRead | null
        // A malformed/empty payload (e.g. transient backend issue) must not
        // stomp `ticker` with undefined — every other effect assumes it's a
        // string and calls .trim()/.toUpperCase() on it unconditionally.
        if (!a || !a.ticker) return
        setTicker(a.ticker)
        setDate(a.trade_date)
        setSignal(a.signal)
        setAnalysisId(a.id)
        setRunStatus('done')
        setReports({
          ...Object.fromEntries(visibleReportEntries(a)),
          investment_plan: a.investment_plan || '',
          trader_plan: a.trader_plan || '',
          final_decision: a.final_decision || '',
        })
        setDetail(a)
      }).catch(e => console.error('Failed to load latest analysis', e))
    }
  }, [])

  const setRunning_ = (v: boolean) => {
    setRunning(v)
    if (!v) {
      setStopping(false)
      sessionStorage.removeItem(TASK_KEY)
      taskIdRef.current = null
      resumingTaskIdRef.current = null
    }
  }

  const attachWs = useCallback((taskId: string, reconnectAttempt = 0) => {
    // Stop may race a queued reconnect timer or a persisted-task probe.  Do
    // not create a new socket after the user has explicitly stopped the run.
    if (stoppedByUserRef.current) return
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    clearWsKeepalive()
    if (wsRef.current) {
      closeAnalysisWebSocket(wsRef.current, 'Replaced by a newer analysis connection')
    }
    taskIdRef.current = taskId
    const ws = openAnalysisWebSocket(taskId, getAccessToken())
    wsRef.current = ws
    let finished = false
    let terminalProbePending = false

    const appendLog = (line: string) => {
      if (preRefreshLogRef.current && preRefreshLogRef.current.length > 0) {
        const expected = preRefreshLogRef.current[0]
        if (expected === line) {
          preRefreshLogRef.current.shift()
          return
        } else {
          preRefreshLogRef.current = []
        }
      }
      if (seenLogRef.current.has(line)) return
      seenLogRef.current.add(line)
      setLog(l => [...l, line])
    }

    const markConnectionAsTerminalFailure = (message = t('analysis.ws.conn_closed')) => {
      // The task may have finished while its terminal event was being
      // persisted.  Do not let a close/reconnect loop leave the page in a
      // false "Running" state after the server has removed that task.
      finished = true
      terminalTaskIdRef.current = taskId
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      clearWsKeepalive()
      if (wsRef.current === ws) wsRef.current = null
      setRunStatus('error')
      setRunning_(false)
      setCurrentStep(null)
      setMentalModel(null)
      appendLog(message)
      notify('error', message, t('analysis.ws.analysis_interrupted'))
    }

    const scheduleRetry = (closeCode: number, taskProbeUnavailable: boolean) => {
      // Only the socket that is still current may schedule a reconnect.  This
      // prevents an old timer from replacing the socket for a newer task.
      if (stoppedByUserRef.current || finished || taskIdRef.current !== taskId || wsRef.current !== ws) return
      const nextAttempt = reconnectAttempt + 1
      if (nextAttempt <= WS_MAX_RECONNECT_RETRIES) {
        const delay = Math.min(1000 * Math.pow(2, nextAttempt - 1), 8000)
        appendLog(`🔄 Reconnecting... (attempt ${nextAttempt}/${WS_MAX_RECONNECT_RETRIES})`)
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = null
          if (stoppedByUserRef.current || finished || taskIdRef.current !== taskId || wsRef.current !== ws) return
          attachWsRef.current(taskId, nextAttempt)
        }, delay)
      } else {
        const message = taskProbeUnavailable
          ? t('analysis.ws.task_status_unavailable')
          : closeCode && closeCode !== WS_NORMAL_CLOSE_CODE
            ? t('analysis.ws.conn_closed_code').replace('{code}', String(closeCode))
            : t('analysis.ws.conn_closed')
        markConnectionAsTerminalFailure(message)
      }
    }

    const scheduleReconnect = (closeCode: number) => {
      if (
        terminalProbePending || stoppedByUserRef.current || finished ||
        taskIdRef.current !== taskId || wsRef.current !== ws
      ) return
      terminalProbePending = true

      // A normal worker shutdown closes the socket after publishing a
      // terminal event.  If that publish itself fails, blindly reconnecting
      // only creates noisy attempts and leaves the UI running.  Probe the
      // active-task registry first. A transient/unusable probe keeps the
      // bounded retry path, while a definitive auth/permission failure does
      // not retry the same doomed WebSocket handshake.
      void (async () => {
        let taskState = await probeActiveTask(taskId)
        if (taskState === 'inactive') {
          // A failed inline run can briefly disappear from the local registry
          // while its one allowed retry is being queued. Confirm the absence
          // once before declaring the run terminal, without emitting a noisy
          // reconnect entry in the meantime.
          await new Promise<void>(resolve => setTimeout(resolve, TERMINAL_TASK_CONFIRMATION_DELAY_MS))
          taskState = await probeActiveTask(taskId)
        }

        terminalProbePending = false
        if (
          stoppedByUserRef.current || finished || taskIdRef.current !== taskId ||
          wsRef.current !== ws
        ) return
        if (taskState === 'unauthorized') {
          markConnectionAsTerminalFailure(t('analysis.ws.auth_required'))
          return
        }
        if (taskState === 'forbidden') {
          markConnectionAsTerminalFailure(t('analysis.ws.access_denied'))
          return
        }
        if (taskState === 'inactive') {
          markConnectionAsTerminalFailure(t('analysis.ws.task_not_active'))
          return
        }
        scheduleRetry(closeCode, taskState === 'unavailable')
      })()
    }

    const sendKeepalive = () => {
      if (
        finished || stoppedByUserRef.current || taskIdRef.current !== taskId ||
        wsRef.current !== ws || ws.readyState !== WS_OPEN
      ) return
      try {
        ws.send(WS_KEEPALIVE_MESSAGE)
      } catch {
        // The close handler owns reconnect/terminal decisions.
      }
    }

    ws.onopen = () => {
      if (finished || stoppedByUserRef.current || taskIdRef.current !== taskId || wsRef.current !== ws) return
      sendKeepalive()
      wsKeepaliveRef.current = setInterval(sendKeepalive, WS_KEEPALIVE_INTERVAL_MS)
    }

    ws.onmessage = (e) => {
      let ev: WsEvent
      try { ev = JSON.parse(e.data) } catch { return }
      if (ev.type === 'status') {
        // Status events carry a human-readable message separately from their
        // technical producer and lifecycle fields. Do not render an agent key
        // as a user-facing fallback.
        const statusText = ev.message ?? ev.status
        if (statusText) appendLog(statusText)
      } else if (ev.type === 'progress') {
        setCurrentStep(prev => prev?.label === ev.label && prev?.stage === ev.stage ? prev : { label: ev.label || '', stage: ev.stage || '' })
        appendLog(`Progress: ${ev.label}`)
      } else if (ev.type === 'token' && ev.agent && ev.token) {
        const reportKey = reportKeyForStreamingAgent(ev.agent)
        if (!reportKey) return
        setReports(r => {
          const prevContent = r[reportKey] || ''
          return { ...r, [reportKey]: prevContent + ev.token }
        })
        // Keep the first (or user-selected/persisted) report in view instead
        // of jumping the UI to every agent as tokens arrive.
        setActiveSection(prev => prev ?? reportKey)
      } else if (ev.type === 'stats') {
        setStats(prev => {
          const next = { llmCalls: ev.llm_calls || 0, tokensIn: ev.tokens_in || 0, tokensOut: ev.tokens_out || 0 }
          if (prev?.llmCalls === next.llmCalls && prev?.tokensIn === next.tokensIn && prev?.tokensOut === next.tokensOut) return prev
          return next
        })
      } else if (ev.type === 'report' && ev.section && ev.content) {
        setReports(r => ({ ...r, [ev.section!]: ev.content! }))
        setActiveSection(prev => prev ?? ev.section!)
        appendLog(`Completed: ${sectionLabelsRef.current[ev.section!] || ev.section}`)
      } else if (ev.type === 'mental_model' && ev.agent && ev.thought) {
        setMentalModel({ agent: ev.agent, thought: ev.thought })
      } else if (ev.type === 'risk_metrics' && ev.metrics) {
        setRiskMetrics(ev.metrics)
      } else if (ev.type === 'debate_bubble' && ev.message) {
        const parsed = typeof ev.sender === 'string' && typeof ev.content === 'string'
          ? { sender: ev.sender, content: ev.content }
          : parseDebateMessage(ev.message)
        const next = { ...parsed, type: ev.debate_type || 'investment' }
        // Buffered WebSocket replay after a reconnect can repeat the last
        // event. Keep one complete turn instead of showing cloned bubbles.
        setLiveDebate(prev => {
          const last = prev.at(-1)
          return last && last.sender === next.sender && last.content === next.content && last.type === next.type
            ? prev
            : [...prev, next]
        })
      } else if (ev.type === 'retry') {
        appendLog(`⚠️ Retrying ${ev.node} (attempt ${ev.attempt}/${ev.max_attempts})`)
      } else if (ev.type === 'fallback') {
        appendLog(`⚠️ Fallback activated for ${ev.node} (${ev.kind})`)
      } else if (ev.type === 'node_error') {
        appendLog(`❌ Error in ${ev.node} (${ev.error_type})`)
      } else if (ev.type === 'circuit_open') {
        appendLog(`🔒 Circuit open for ${ev.node} (${ev.elapsed_seconds}s)`)
      } else if (ev.type === 'stall_warning') {
        // The run is still alive but has produced nothing for longer than the
        // user's configured stall timeout. Say so, rather than leaving the
        // heartbeat progress events to read as ordinary work.
        appendLog(`⏳ ${t('analysis.stalled', { seconds: ev.seconds_since_last_event, threshold: ev.threshold })}`)
      } else if (ev.type === 'decision') {
        setSignal(ev.signal || null)
      } else if (ev.type === 'order_result') {
        const nextOrderResult = readOrderResult(ev, tickerRef.current)
        if (!nextOrderResult) return
        setOrderResult(previous => sameOrderResult(previous, nextOrderResult) ? previous : nextOrderResult)
        appendLog(orderResultLogLine(nextOrderResult, t))
      } else if (ev.type === 'complete') {
        finished = true
        terminalTaskIdRef.current = taskId
        clearWsKeepalive()
        setRunStatus('done')
        setRunning_(false)
        setCurrentStep(null)
        setMentalModel(null)
        setStats(prev => prev ? { ...prev, llmCalls: ev.llm_calls || prev.llmCalls, estimatedCost: ev.estimated_cost_usd } : null)
        appendLog(`Completed in ${ev.duration_seconds}s / ${ev.llm_calls} LLM calls`)
        appendLog(t('analysis.order.analysis_complete'))
        sendBrowserNotification(
          `${tickerRef.current.toUpperCase()} Analysis Completed`,
          `Signal: ${ev.signal ?? 'N/A'} • Duration: ${ev.duration_seconds?.toFixed(0)}s`
        )
        if (ev.analysis_id) {
          setAnalysisId(ev.analysis_id)
          analysisGetAnalysis(ev.analysis_id).then(d => setDetail(d as never)).catch(e => console.error('Failed to fetch analysis detail on complete', e))
        }
      } else if (ev.type === 'error') {
        finished = true
        terminalTaskIdRef.current = taskId
        clearWsKeepalive()
        if (ev.message === "Analysis cancelled.") {
          setRunStatus('idle')
          setRunning_(false)
          setCurrentStep(null)
          setMentalModel(null)
          appendLog(t('analysis.ws.stopped'))
        } else {
          setRunStatus('error')
          setRunning_(false)
          setCurrentStep(null)
          appendLog(`Error: ${ev.message}`)
          notify('error', ev.message ?? t('analysis.ws.analysis_failed'), t('analysis.ws.analysis_error_title'))
        }
      }
    }
    ws.onclose = (event) => {
      if (!finished) {
        if (wsRef.current === ws) clearWsKeepalive()
        // These are application close codes sent after an accepted handshake.
        // They cannot be fixed by reconnecting with the same credentials.
        if (event.code === 4001) {
          markConnectionAsTerminalFailure(t('analysis.ws.auth_required'))
          return
        }
        if (event.code === 4003) {
          markConnectionAsTerminalFailure(t('analysis.ws.access_denied'))
          return
        }
        if (event.code === 1011) {
          markConnectionAsTerminalFailure(t('analysis.ws.initialization_failed'))
          return
        }
        scheduleReconnect(event.code)
      }
    }
    // ticker is intentionally read via tickerRef (not a dep) so the socket
    // isn't torn down and recreated on every ticker keystroke.
  }, [t, clearWsKeepalive])

  useEffect(() => {
    attachWsRef.current = attachWs
  }, [attachWs])

  // Effect to sync with active tasks from the server (Cross-device fix)
  useEffect(() => {
    if (stoppedByUserRef.current || activeTasks.length === 0 || running) return

    // If there's an active task on the server but we are 'idle' here, sync it.
    const task = activeTasks[0]
    if (task.status === 'failed' || task.status === 'error' || terminalTaskIdRef.current === task.task_id) return
    if (taskIdRef.current === task.task_id) return
    runStartedRef.current = true
    setTicker(task.ticker)
    setDate(task.trade_date)
    setAssetType(task.asset_type)
    setRunning(true)
    setRunStatus('running')
    setLog([])
    seenLogRef.current = new Set()
    setReports({})
    setSignal(null)
    setOrderResult(null)
    setAnalysisId(null)
    setDetail(null)
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ ticker: task.ticker, taskId: task.task_id, startedAt: new Date(task.started_at * 1000).toISOString() }))
    attachWs(task.task_id, 1)
  }, [activeTasks, running, attachWs])

  useEffect(() => {
    // `useActiveTasks` owns the only active-task request for this mount.  A
    // second probe here used to race it and, in the old implementation, was
    // retriggered after every streamed render.  Wait for that shared result
    // before deciding whether the persisted task can be resumed.
    if (activeTasksLoading) return

    const raw = sessionStorage.getItem(TASK_KEY)
    if (!raw) return
    let cancelled = false
    try {
      const { taskId, ticker: runTicker } = JSON.parse(raw)
      if (!taskId) return
      if (resumingTaskIdRef.current === taskId || taskIdRef.current === taskId) return

      const resume = () => {
        if (cancelled || stoppedByUserRef.current || resumingTaskIdRef.current === taskId || taskIdRef.current === taskId) return
        resumingTaskIdRef.current = taskId
        runStartedRef.current = true
        preRefreshLogRef.current = [...saved.log]
        setRunning(true)
        setRunStatus('running')
        if (runTicker) setTicker(runTicker)
        attachWs(taskId, 1)
      }

      if (activeTasks.some(task => task.task_id === taskId)) {
        resume()
      } else if (activeTasksUnavailable) {
        // Preserve the former offline behavior: an unavailable API should not
        // make an in-progress analysis disappear from the UI.  The bounded WS
        // reconnect logic will surface a real connection failure.
        resume()
      } else {
        clearTaskMarkerFor(taskId)
        resumingTaskIdRef.current = null
        setRunning(false)
        setRunStatus('idle')
      }
    } catch {
      sessionStorage.removeItem(TASK_KEY)
      resumingTaskIdRef.current = null
    }
    return () => { cancelled = true }
  }, [activeTasks, activeTasksLoading, activeTasksUnavailable, attachWs, saved.log])

  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      clearWsKeepalive()
      if (wsRef.current) {
        closeAnalysisWebSocket(wsRef.current, 'Analysis page unmounted')
      }
    }
  }, [])

  // Both lookups take no per-keystroke parameters, so the query key is stable
  // and the cache serves repeat renders -- the old 600ms/400ms debounces existed
  // only to stop a request firing on every character.
  const costEstimateQuery = useAnalysisCostEstimate({ query: { enabled: Boolean(ticker.trim()) && !running } })
  const costEstimate = costEstimateQuery.error ? null : (costEstimateQuery.data ?? null)

  const recentQuery = useAnalysisListAnalysis({ limit: 5 }, { query: { enabled: Boolean(ticker.trim()) } })
  const existingId = (() => {
    if (!ticker.trim() || !Array.isArray(recentQuery.data)) return null
    const match = (recentQuery.data as unknown as AnalysisListItem[])
      .find(x => x.ticker === ticker.toUpperCase() && x.trade_date === date)
    return match?.id ?? null
  })()
  useEffect(() => {
  }, [ticker, date])

  const handleStop = async () => {
    if (stopping) return
    const tid = taskIdRef.current
    setLog(l => [...l, 'Cancelling...'])

    // There is no server task id yet only while /run is still in flight. In
    // that narrow case, invalidate the pending request now; doRun will cancel
    // the task as soon as the late response gives us its id.
    if (!tid) {
      runRequestRef.current += 1
      stoppedByUserRef.current = true
    } else {
      // Do not pretend that Stop worked before the server accepted it. The
      // former best-effort implementation immediately hid the running task
      // after a failed request, while the worker continued consuming LLM/API
      // resources in the background.
      setStopping(true)
      try {
        const data = await cancelAnalysis.mutateAsync({ taskId: tid })
        if (isRecord(data) && data.cancelled === false) {
          throw new Error('Cancellation was not accepted')
        }
      } catch {
        // A terminal socket event may have won the race while the request was
        // in flight. Preserve that real terminal state instead of replacing
        // it with a misleading Stop failure.
        if (taskIdRef.current !== tid) {
          setStopping(false)
          return
        }
        const message = t('analysis.ws.stop_failed')
        setLog(l => [...l, message])
        setStopping(false)
        notify('error', message, t('analysis.ws.analysis_error_title'))
        return
      }
      if (taskIdRef.current !== tid) {
        setStopping(false)
        return
      }
      runRequestRef.current += 1
      stoppedByUserRef.current = true
      terminalTaskIdRef.current = tid
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    clearWsKeepalive()
    if (wsRef.current) {
      closeAnalysisWebSocket(wsRef.current, 'Analysis stopped by user')
      wsRef.current = null
    }
    setRunStatus('idle')
    setRunning_(false)
    seenLogRef.current = new Set()
  }

  const doRun = async () => {
    const requestId = ++runRequestRef.current
    setShowRerunModal(false)
    stoppedByUserRef.current = false
    terminalTaskIdRef.current = null
    runStartedRef.current = true
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setLiveDebate([])
    setOrderResult(null)
    setAnalysisId(null)
    setDetail(null)
    setActiveSection(null)
    setCurrentStep(null)
    setStats(null)
    setStartError(null)
    preRefreshLogRef.current = null
    seenLogRef.current = new Set()

    try {
      const data = await runAnalysis.mutateAsync({
        data: { ticker: ticker.toUpperCase(), trade_date: date, asset_type: assetType },
      }) as { task_id?: unknown }
      const taskId = data.task_id
      if (typeof taskId !== 'string' || !taskId) throw new Error('Analysis start response did not include a task ID')

      // The user may have clicked Stop while the start request was pending.
      // Do not persist/attach the returned task; cancel it server-side so a
      // queued job cannot keep running invisibly in the background.
      if (requestId !== runRequestRef.current || stoppedByUserRef.current) {
        clearTaskMarkerFor(taskId)
        try { await cancelAnalysis.mutateAsync({ taskId }) } catch { /* best-effort cancel */ }
        return
      }
      sessionStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
      attachWs(taskId, 0)
    } catch (err: any) {
      // A rejected start request after Stop is expected to leave the UI idle,
      // not replace the stopped state with an error message.
      if (requestId !== runRequestRef.current || stoppedByUserRef.current) return
      const error = analysisStartError(err, t('analysis.ws.failed_to_start'))
      setRunStatus('error')
      setRunning_(false)
      setStartError(error)
      setLog(l => [...l, `Error: ${error.message}`])
    }
  }

  const handleRun = () => {
    if (!ticker.trim()) return
    if (existingId) { setShowRerunModal(true); return }
    doRun()
  }

  const handleClear = () => {
    setRunStatus('idle'); setSignal(null); setReports({}); setLog([]); setActiveSection(null); setCurrentStep(null)
    setAnalysisId(null); setDetail(null); setLiveDebate([]); setOrderResult(null); setStats(null); setStartError(null)
  }

  const handleRollbackStart = (taskId: string) => {
    stoppedByUserRef.current = false
    terminalTaskIdRef.current = null
    runStartedRef.current = true
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setLiveDebate([])
    setOrderResult(null)
    setAnalysisId(null)
    setDetail(null)
    setActiveSection(null)
    setCurrentStep(null)
    setStats(null)
    preRefreshLogRef.current = null
    seenLogRef.current = new Set()

    sessionStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
    attachWs(taskId, 0)
  }

  const reportEntries = Object.entries(reports)

  return (
    <div className="space-y-6">
      <AnalysisControls
        ticker={ticker} setTicker={handleTickerChange}
        date={date} setDate={setDate}
        assetType={assetType} setAssetType={setAssetType}
        assetTypes={assetTypes}
        running={running} stopping={stopping} runStatus={runStatus}
        handleRun={handleRun} handleStop={handleStop} handleClear={handleClear}
        signal={signal} costEstimate={costEstimate} existingId={existingId}
        startError={startError}
        onSelectTickerSuggestion={handleTickerChange}
        t={t}
      />

      {showRerunModal && (
        <div className="fixed inset-0 bg-black/75 z-[60] flex items-center justify-center p-5 backdrop-blur-md">
          <div className="bg-slate-900 border border-white/[0.06] rounded-3xl p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <div className="space-y-2">
              <h3 className="text-white text-lg font-display font-bold flex items-center gap-2"><AlertTriangle className="text-amber-500" size={18} /> {t('analysis.rerun.title')}</h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                {t('analysis.rerun.body').replace('{ticker}', ticker.toUpperCase()).replace('{date}', date)}
              </p>
            </div>
            <div className="flex gap-3">
              <button onClick={doRun} className="flex-1 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold py-2.5 rounded-xl transition shadow shadow-violet-600/20 cursor-pointer">{t('analysis.btn.rerun')}</button>
              <button onClick={() => setShowRerunModal(false)} className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold py-2.5 rounded-xl transition cursor-pointer">{t('analysis.btn.cancel')}</button>
            </div>
          </div>
        </div>
      )}

      {running && (
        <div className="flex items-center gap-3 px-4 py-3 bg-violet-500/5 border border-violet-500/15 rounded-2xl">
          <span className="relative flex h-2 w-2 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
          </span>
          <Loader2 size={13} className="text-violet-400 animate-spin shrink-0" />
          <p className="text-violet-300 text-xs font-medium truncate flex-1">
            <span className="font-bold">{ticker}</span> {t('analysis.running')}
            {currentStep
              ? <span className="text-white ml-2 font-semibold">→ {currentStep.label}</span>
              : <span className="text-slate-400 ml-2 font-normal">{log.at(-1)}</span>}
          </p>
        </div>
      )}

      {running && mentalModel && (
        <MentalModelTicker agent={mentalModel.agent} thought={mentalModel.thought} />
      )}

      {(running || log.length > 0 || reportEntries.length > 0 || !!detail || !!orderResult) && (() => {
        const isCompleted = !!detail || runStatus === 'done';
        const activeSignal = detail ? detail.signal : signal;
        const activeRiskMetrics = detail ? detail.risk_metrics : riskMetrics;
        const activeLegacyTraderProposal = detail ? detail.trader_proposal_json : reports.trader_proposal_json;
        const activeChartAnnotations = detail?.chart_annotations ?? reports.chart_annotations;
        const activeAcceptedPortfolioDecision = detail?.portfolio_decision_json ?? reports.portfolio_decision_json;
        const streamedPortfolioDecision = reports.pm_proposal_json || reports.portfolio_decision;
        const activePortfolioDecision = readPortfolioDecision(
          activeAcceptedPortfolioDecision,
          activeChartAnnotations,
          activeLegacyTraderProposal,
          streamedPortfolioDecision,
        );
        const hasPortfolioManagerDecision = activePortfolioDecision?.source === 'portfolio_manager';
        const activeId = detail ? detail.id : analysisId;

        const activePlans = detail ? {
          investment_plan: detail.investment_plan,
          trader_plan: hasPortfolioManagerDecision ? '' : detail.trader_plan,
          final_decision: detail.final_decision,
        } : {
          investment_plan: reports.investment_plan || '',
          trader_plan: hasPortfolioManagerDecision ? '' : reports.trader_plan || reports.trader_investment_plan || '',
          final_decision: reports.final_decision || '',
        };

        const activeReports = visibleReportEntries(
          detail ? detail as unknown as Record<string, unknown> : reports,
        );

        const filteredLiveMessages = liveDebate.filter(m => {
          if (liveDebateTab === 'inv') {
            return m.type === 'investment' || m.type === 'consensus';
          } else {
            return m.type === 'risk';
          }
        });

        return (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
            {/* Left Column: Sidebar Dashboard & Terminal Log */}
            <div className="lg:col-span-1 space-y-5 flex flex-col h-full">
              {/* Engine Status & Mental Model */}
              <div className="glass-panel p-4 rounded-2xl space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('analysis.engine_status')}</span>
                  {running ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-pulse" />
                      Running
                    </span>
                  ) : runStatus === 'done' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      {t('analysis.order.analysis_complete_status')}
                    </span>
                  ) : runStatus === 'error' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                      Failed
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-500/10 text-slate-400 border border-white/[0.04]">
                      Idle
                    </span>
                  )}
                </div>

                {running && currentStep && (
                  <div className="space-y-1.5 animate-in fade-in duration-300">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide block">{t('analysis.current_action')}</span>
                    <p className="text-white text-xs font-semibold truncate flex items-center gap-1.5">
                      <Loader2 size={11} className="animate-spin text-violet-400 shrink-0" />
                      {currentStep.label}
                    </p>
                  </div>
                )}

                {running && mentalModel && (
                  <div className="border-t border-white/[0.04] pt-3 mt-3 animate-in fade-in duration-500">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide block mb-1">{t('analysis.thought_process')}</span>
                    <MentalModelTicker agent={mentalModel.agent} thought={mentalModel.thought} />
                  </div>
                )}
              </div>

              {(runStatus === 'done' || !!orderResult) && (
                <AutomatedOrderResultCard result={orderResult} />
              )}

              {/* Statistics Dashboard */}
              {(stats || detail) && (
                <div className="glass-panel p-4 rounded-2xl grid grid-cols-3 gap-2">
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">{t('analysis.llm_calls')}</span>
                    <span className="text-sm font-bold text-white font-mono">{detail ? detail.llm_calls : stats?.llmCalls || 0}</span>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">{t('analysis.tokens')}</span>
                    <span className="text-sm font-bold text-white font-mono">
                      {detail 
                        ? ((detail.tokens_in + detail.tokens_out).toLocaleString()) 
                        : (((stats?.tokensIn || 0) + (stats?.tokensOut || 0)).toLocaleString())
                      }
                    </span>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">{t('analysis.cost_est')}</span>
                    <span className="text-sm font-bold text-emerald-400 font-mono">
                      ${detail?.estimated_cost_usd
                        ? detail.estimated_cost_usd.toFixed(4)
                        : stats?.estimatedCost
                          ? stats.estimatedCost.toFixed(4)
                          : (((stats?.tokensIn || 0) * 0.000005 + (stats?.tokensOut || 0) * 0.000015).toFixed(4))
                      }
                    </span>
                  </div>
                </div>
              )}

              {/* System terminal log */}
              <div className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[28vh] sm:h-[35vh]">
                <div className="flex items-center gap-1.5 px-4 py-2.5 bg-slate-900/40 border-b border-white/[0.04]">
                  <Terminal size={12} className="text-slate-400" />
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('analysis.progress_log')}</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-950/40 space-y-2 font-mono text-[10px]">
                  {log.map((line, i) => (
                    <div key={i} className="flex gap-2.5 leading-relaxed animate-in fade-in slide-in-from-left-2 duration-300">
                      <span className="text-slate-600 shrink-0 select-none">{(i + 1).toString().padStart(2, '0')}</span>
                      <span className={`${
                        line.startsWith('Completed') || line.startsWith('✓') ? 'text-emerald-400' :
                        line.startsWith('Error') || line.startsWith('❌') ? 'text-rose-400' :
                        line.startsWith('⚠') ? 'text-amber-400' :
                        line.startsWith('Progress') ? 'text-violet-400' : 'text-slate-400'
                      }`}>
                        {line}
                      </span>
                    </div>
                  ))}
                  {log.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center opacity-25 py-12 text-slate-500 font-sans">
                      <History size={20} className="mb-1.5" />
                      <p className="text-[9px] uppercase tracking-widest font-semibold">{t('analysis.logs_empty')}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right Column: Unified Main Panel Arena */}
            <div className="lg:col-span-2 glass-panel rounded-2xl overflow-hidden flex flex-col h-[65vh] sm:h-[70vh]">
              {/* Arena tabs */}
              <div className="flex gap-0.5 p-1 bg-slate-950/60 border-b border-white/[0.04] overflow-x-auto custom-scrollbar shrink-0">
                <button
                  onClick={() => setActiveTab('consensus')}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'consensus' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  <Scale size={12} /> {sectionLabels.final_decision || 'Consensus'}
                </button>
                <button
                  onClick={() => setActiveTab('reports')}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'reports' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  <BookOpen size={12} /> {t('analysis.tab.reports')}
                </button>
                <button
                  onClick={() => setActiveTab('debate')}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  <MessageSquare size={12} /> {t('analysis.tab.debate')}
                </button>
                <button
                  onClick={() => setActiveTab('chat')}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'chat' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  <Bot size={12} /> {t('analysis.tab.qa')}
                </button>
                <button
                  onClick={() => setActiveTab('timetravel')}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'timetravel' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                  }`}
                >
                  <History size={12} /> {t('analysis.tab.timetravel')}
                </button>
              </div>

              {/* Arena Content Area */}
              <div className="flex-1 p-4 overflow-y-auto min-h-0 custom-scrollbar bg-slate-900/10">
                {activeTab === 'consensus' && (
                  <div className="space-y-4 animate-in fade-in duration-300">
                    {/* Signal & Sizing Section */}
                    <div className="flex flex-wrap gap-4 items-center justify-between p-4 bg-slate-900/50 border border-white/[0.04] rounded-2xl">
                      <div className="space-y-1">
                        <span className="text-[9px] text-slate-500 uppercase font-bold tracking-widest block">{t('analysis.consensus_recommendation')}</span>
                        <div className="flex items-center gap-2">
                          <SignalBadge signal={activeSignal} large />
                          {detail?.quality ? <QualityBadge quality={detail.quality as RunQuality} /> : null}
                        </div>
                      </div>
                      {activePortfolioDecision && (
                        <div className="flex-1 max-w-md min-w-[200px]">
                          <PortfolioDecisionCard
                            acceptedPortfolioDecision={activeAcceptedPortfolioDecision}
                            chartAnnotations={activeChartAnnotations}
                            legacyTraderJson={activeLegacyTraderProposal}
                            streamedPortfolioDecision={streamedPortfolioDecision}
                          />
                        </div>
                      )}
                    </div>

                    {/* Risk metrics if present */}
                    {activeRiskMetrics && <RiskMetricsCard metrics={activeRiskMetrics} />}

                    <StrategyTransitionCard
                      analysisPlan={detail?.analysis_plan_json ?? reports.analysis_plan_json}
                      strategyBefore={detail?.strategy_before_json ?? reports.strategy_before_json}
                      strategyAfter={detail?.strategy_after_json ?? reports.strategy_after_json}
                      strategyCandidate={detail?.strategy_candidate_json ?? reports.strategy_candidate_json}
                      pmProposal={detail?.pm_proposal_json ?? reports.pm_proposal_json}
                      acceptedDecision={activeAcceptedPortfolioDecision}
                      transition={detail?.decision_transition_json ?? reports.decision_transition_json}
                      calibratedConfidence={detail?.calibrated_confidence ?? null}
                      strategyUpdateStatus={detail?.strategy_update_status ?? null}
                      strategyBeforeVersion={detail?.strategy_before_version ?? null}
                      strategyAfterVersion={detail?.strategy_after_version ?? null}
                    />

                    {/* PM Final Decision */}
                    {activePlans.final_decision ? (
                      <div className="glass-panel p-5 rounded-2xl space-y-3 bg-slate-950/20 border border-white/[0.05]">
                        <h4 className="text-[10px] font-bold text-violet-300 uppercase tracking-widest flex items-center gap-1.5">
                          <Scale size={13} /> {sectionLabels.final_decision || 'Nihai Karar (Portfolio Manager)'}
                        </h4>
                        <MarkdownReport
                          content={activePlans.final_decision}
                          className="!text-xs !leading-relaxed !text-slate-200"
                        />
                      </div>
                    ) : (
                      <div className="text-center py-12 text-slate-500 text-xs">
                        {running ? 'Portfolio Manager decision is pending...' : 'No decision generated yet.'}
                      </div>
                    )}

                    {/* Stacked Plan Cards */}
                    <div className="grid grid-cols-1 gap-4">
                      {activePlans.investment_plan && (
                        <div className="glass-panel p-4 rounded-xl space-y-2 bg-slate-900/30">
                          <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{sectionLabels.investment_plan || 'Research Evidence Summary'}</h5>
                          <MarkdownReport
                            content={activePlans.investment_plan}
                            className="!text-xs !leading-relaxed !text-slate-300"
                          />
                        </div>
                      )}
                      {activePlans.trader_plan && (
                        <div className="glass-panel p-4 rounded-xl space-y-2 bg-slate-900/30">
                          <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{sectionLabels.trader_plan || 'Legacy Trader Proposal'}</h5>
                          <MarkdownReport
                            content={activePlans.trader_plan}
                            className="!text-xs !leading-relaxed !text-slate-300"
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'reports' && (
                  <ErrorBoundary name="AnalysisReports">
                    <div className="space-y-3 animate-in fade-in duration-300">
                      {activeReports.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-slate-600">
                          <FileText size={28} className="opacity-25 mb-2" />
                          <p className="text-xs">{t('analysis.reports.empty')}</p>
                        </div>
                      ) : (
                        activeReports.map(([key, content]) => (
                          <ReportCard
                            key={key}
                            label={readableSectionLabel(sectionLabels, key)}
                            content={content}
                            defaultOpen={key === activeSection}
                            isStreaming={running && key === activeSection}
                          />
                        ))
                      )}
                    </div>
                  </ErrorBoundary>
                )}

                {activeTab === 'debate' && (
                  <ErrorBoundary name="AnalysisDebate">
                    <div className="animate-in fade-in duration-300">
                      {isCompleted && detail ? (
                        <DebateHistoryWidget investmentHistory={detail.investment_debate_history} riskHistory={detail.risk_debate_history} />
                      ) : (
                        <div className="flex flex-col bg-slate-950/80 border border-white/[0.04] rounded-2xl p-4 space-y-4">
                          <div className="flex gap-2 p-1 bg-slate-900/50 border border-white/[0.04] rounded-xl w-fit self-center">
                            <button
                              onClick={() => setLiveDebateTab('inv')}
                              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
                                liveDebateTab === 'inv' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                              }`}
                            >
                              {t('analysis.debate.consensus')}
                            </button>
                            <button
                              onClick={() => setLiveDebateTab('risk')}
                              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
                                liveDebateTab === 'risk' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                              }`}
                            >
                              {t('analysis.section.risk_debate_history')}
                            </button>
                          </div>
                          <div className="flex-1 overflow-y-auto space-y-3 max-h-[45vh] pr-1">
                            {filteredLiveMessages.length === 0 && (
                              <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                                <MessageSquare size={30} className="mb-2" />
                                <p className="text-xs font-medium uppercase tracking-widest text-center">
                                  {running && currentStep && (currentStep.stage === 'research' || currentStep.stage === 'risk')
                                    ? t('analysis.debate.waiting')
                                    : t('analysis.debate.not_started')}
                                </p>
                              </div>
                            )}
                            {filteredLiveMessages.map((bubble, i) => (
                              <div key={`${bubble.sender}-${i}`} className="animate-in zoom-in-95 fade-in duration-300">
                                <DebateBubble message={bubble} />
                              </div>
                            ))}
                            
                            {running && currentStep && (
                              (liveDebateTab === 'inv' && currentStep.stage === 'research') ||
                              (liveDebateTab === 'risk' && currentStep.stage === 'risk')
                            ) && (
                              <div className="flex justify-start items-center gap-3 animate-pulse pl-1 pt-2">
                                <div className="w-6 h-6 rounded-full bg-slate-900/80 border border-white/[0.06] flex items-center justify-center shadow">
                                  <span className="relative flex h-2 w-2">
                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75"></span>
                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500"></span>
                                  </span>
                                </div>
                                <div className="bg-slate-900/40 border border-slate-800/40 rounded-2xl px-3.5 py-2 text-[10px] text-slate-400 flex items-center gap-1.5">
                                  <Loader2 size={10} className="animate-spin text-slate-500" />
                                  <span className="font-semibold uppercase tracking-tight">
                                    {currentStep.label} {t('analysis.debate.typing')}
                                  </span>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </ErrorBoundary>
                )}

                {activeTab === 'chat' && (
                  <ErrorBoundary name="AnalysisChat">
                    <div className="animate-in fade-in duration-300 h-full">
                      {activeId ? (
                        <AnalysisChatWidget analysisId={activeId} />
                      ) : (
                        <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                          <Bot size={36} className="opacity-25 mb-3" />
                          <p className="text-xs font-semibold">Q&A Assistant will be available once the analysis is completed.</p>
                        </div>
                      )}
                    </div>
                  </ErrorBoundary>
                )}

                {activeTab === 'timetravel' && (
                  <div className="animate-in fade-in duration-300">
                    {activeId ? (
                      <TimeTravelWidget
                        analysisId={activeId}
                        onRollbackStart={(taskId) => {
                          handleRollbackStart(taskId);
                        }}
                      />
                    ) : (
                      <div className="flex flex-col items-center justify-center py-20 text-slate-500">
                        <History size={36} className="opacity-25 mb-3" />
                        <p className="text-xs font-semibold">{t('analysis.time_travel_pending')}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  )
}

function MultiTab() {
  const { t } = useTranslation()
  const runPortfolio = useAnalysisRunPortfolioRun()
  const cancelPortfolio = useAnalysisCancelAnalysis()
  const [tickers, setTickers] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [assetType, setAssetType] = useState('stock')
  const [running, setRunning] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [done, setDone] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [startError, setStartError] = useState<AnalysisStartError | null>(null)
  const [progress, setProgress] = useState<string>('')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const shouldReconnectRef = useRef(false)
  const taskIdRef = useRef<string | null>(null)
  const runRequestRef = useRef(0)
  const stoppedByUserRef = useRef(false)
  const meta = useMeta()
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]

  const closeCurrentSocket = useCallback(() => {
    shouldReconnectRef.current = false
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    const ws = wsRef.current
    wsRef.current = null
    if (!ws) return
    // Closing a terminal/unmounted socket must not enter its reconnect path.
    closeAnalysisWebSocket(ws, 'Portfolio analysis connection closed')
  }, [])

  // Close the live-progress socket if the tab unmounts mid-run.
  useEffect(() => closeCurrentSocket, [closeCurrentSocket])

  const addTicker = () => {
    const tk = input.trim().toUpperCase()
    if (tk && !tickers.includes(tk) && tickers.length < 10) setTickers(prev => [...prev, tk])
    setInput('')
  }
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker() } }

  const connectWs = useCallback(function connectWs(taskId: string, retries = 0) {
    if (stoppedByUserRef.current || taskIdRef.current !== taskId) return
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    const previous = wsRef.current
    if (previous) {
      closeAnalysisWebSocket(previous, 'Replaced by a newer portfolio connection')
    }
    const ws = openAnalysisWebSocket(taskId, getAccessToken())
    wsRef.current = ws
    shouldReconnectRef.current = true
    let terminal = false
    let reconnectScheduled = false

    const stopReconnecting = () => {
      terminal = true
      shouldReconnectRef.current = false
      if (wsRef.current === ws) wsRef.current = null
      if (taskIdRef.current === taskId) taskIdRef.current = null
      closeAnalysisWebSocket(ws, 'Portfolio analysis completed')
    }

    const markConnectionAsTerminalFailure = (message: string) => {
      terminal = true
      shouldReconnectRef.current = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (wsRef.current === ws) wsRef.current = null
      if (taskIdRef.current === taskId) taskIdRef.current = null
      setError(message)
      setRunning(false)
      setStopping(false)
      closeAnalysisWebSocket(ws, 'Portfolio analysis connection failed')
    }

    const scheduleReconnect = () => {
      if (terminal || reconnectScheduled || stoppedByUserRef.current || !shouldReconnectRef.current || wsRef.current !== ws || taskIdRef.current !== taskId) return
      reconnectScheduled = true

      // A closed socket does not tell us whether the worker is still alive.
      // Probe before reconnecting so a terminal worker does not generate a
      // burst of duplicate 101 handshakes and changing UI status text.
      void (async () => {
        const taskState = await probeActiveTask(taskId)
        if (terminal || stoppedByUserRef.current || !shouldReconnectRef.current || wsRef.current !== ws || taskIdRef.current !== taskId) return
        if (taskState === 'unauthorized') {
          markConnectionAsTerminalFailure(t('analysis.ws.auth_required'))
          return
        }
        if (taskState === 'forbidden') {
          markConnectionAsTerminalFailure(t('analysis.ws.access_denied'))
          return
        }
        if (taskState === 'inactive') {
          markConnectionAsTerminalFailure(t('analysis.ws.task_not_active'))
          return
        }
        if (retries >= WS_MAX_RECONNECT_RETRIES) {
          markConnectionAsTerminalFailure(
            taskState === 'unavailable'
              ? t('analysis.ws.task_status_unavailable')
              : t('analysis.ws.conn_closed'),
          )
          return
        }

        const delay = Math.min(1000 * Math.pow(2, retries), 8000)
        wsRef.current = null
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = null
          if (stoppedByUserRef.current || terminal || taskIdRef.current !== taskId) return
          connectWs(taskId, retries + 1)
        }, delay)
      })()
    }

    ws.onmessage = (e) => {
      let ev: any
      try { ev = JSON.parse(e.data) } catch { return }
      if (ev.type === 'progress') {
        setProgress(ev.label || '')
      } else if (ev.type === 'complete') {
        setDone(true); setCancelled(false); setRunning(false); setStopping(false)
        stopReconnecting()
      } else if (ev.type === 'error') {
        setError(ev.message || t('analysis.multi.error_default')); setRunning(false); setStopping(false)
        stopReconnecting()
      }
    }
    ws.onclose = (event) => {
      if (terminal || stoppedByUserRef.current || !shouldReconnectRef.current || wsRef.current !== ws || taskIdRef.current !== taskId) return

      // The endpoint uses application close codes for bad credentials,
      // authorization and startup failures. These cannot recover through a
      // retry of the exact same handshake.
      const terminalMessage = event.code === 4001
        ? t('analysis.ws.auth_required')
        : event.code === 4003
          ? t('analysis.ws.access_denied')
          : event.code === 1011
            ? t('analysis.ws.initialization_failed')
            : null
      if (terminalMessage) {
        markConnectionAsTerminalFailure(terminalMessage)
        return
      }
      scheduleReconnect()
    }
  }, [t])

  const handleRun = async () => {
    if (tickers.length < 2) return
    const requestId = ++runRequestRef.current
    stoppedByUserRef.current = false
    taskIdRef.current = null
    setRunning(true); setStopping(false); setDone(false); setCancelled(false); setError(null); setStartError(null); setProgress('')
    try {
      const data = await runPortfolio.mutateAsync({ data: { tickers, trade_date: date, asset_type: assetType } }) as unknown as Record<string, unknown>
      const taskId = data.task_id
      if (typeof taskId !== 'string' || !taskId) throw new Error('Portfolio analysis start response did not include a task ID')

      // Stop may be pressed while the start request is still pending. Once a
      // late task id arrives, cancel it instead of attaching an invisible
      // background job to a UI the user believes is idle.
      if (requestId !== runRequestRef.current || stoppedByUserRef.current) {
        try { await cancelPortfolio.mutateAsync({ taskId }) } catch { /* cancellation is retried by durable server intent when accepted */ }
        return
      }
      taskIdRef.current = taskId
      connectWs(taskId, 0)
    } catch (err: unknown) {
      if (requestId !== runRequestRef.current || stoppedByUserRef.current) return
      const requestError = analysisStartError(err, t('analysis.multi.error_default'))
      setStartError(requestError)
      setError(requestError.message)
      setRunning(false)
    }
  }

  const handleStop = async () => {
    if (stopping) return
    const taskId = taskIdRef.current

    if (!taskId) {
      // The initial HTTP request is still pending. Mark it stale immediately;
      // handleRun will cancel any task id that comes back afterwards.
      runRequestRef.current += 1
      stoppedByUserRef.current = true
      closeCurrentSocket()
      setRunning(false); setDone(false); setCancelled(true); setError(null); setProgress('')
      return
    }

    setStopping(true)
    try {
      const data = await cancelPortfolio.mutateAsync({ taskId })
      if (isRecord(data) && data.cancelled === false) {
        throw new Error('Cancellation was not accepted')
      }
    } catch {
      // Retain the live socket and the running state when cancellation failed:
      // this is the key distinction that prevents a fake-success Stop button.
      if (taskIdRef.current !== taskId) {
        setStopping(false)
        return
      }
      setError(t('analysis.ws.stop_failed'))
      setStopping(false)
      return
    }

    if (taskIdRef.current !== taskId) {
      setStopping(false)
      return
    }

    runRequestRef.current += 1
    stoppedByUserRef.current = true
    taskIdRef.current = null
    closeCurrentSocket()
    setRunning(false); setStopping(false); setDone(false); setCancelled(true); setError(null); setProgress('')
  }

  const selectTickerSuggestion = (suggestion: string) => {
    const rejectedTicker = startError?.ticker
    if (!rejectedTicker) return
    // A suggestion is only applied after this explicit click; it must never
    // silently replace an instrument in a portfolio request.
    setTickers(previous => [...new Set(previous.map(ticker => ticker === rejectedTicker ? suggestion : ticker))])
    setError(null)
    setStartError(null)
  }

  const displayedError = startError?.code === 'unknown_ticker'
    ? t('analysis.ticker_error.unknown').replace('{ticker}', startError.ticker || '')
    : startError?.code === 'ticker_validation_unavailable'
      ? t('analysis.ticker_error.unavailable')
      : error

  return (
    <div className="space-y-6">
      <div className="glass-panel rounded-2xl p-5 space-y-5">
        <p className="text-slate-400 text-xs leading-relaxed">{t('analysis.multi.description')}</p>

        <div>
          <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.multi.label_symbols')}</label>
          <div className="flex flex-wrap gap-2 min-h-12 bg-slate-900/60 border border-white/[0.08] rounded-xl px-3 py-2 focus-within:border-violet-500/50 transition-colors">
            {tickers.map(tk => (
              <span key={tk} className="flex items-center gap-1.5 bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs font-mono font-bold px-2 py-0.5 rounded-lg">
                {tk}
                <button disabled={running} onClick={() => { setTickers(p => p.filter(x => x !== tk)); setError(null); setStartError(null) }} className="text-slate-500 hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 transition-colors cursor-pointer"><X size={10} /></button>
              </span>
            ))}
            {tickers.length < 10 && (
              <input
                className="bg-transparent text-white text-xs outline-none flex-1 min-w-[100px] uppercase font-mono placeholder-slate-600"
                placeholder="AAPL, Enter"
                value={input}
                onChange={e => setInput(e.target.value.toUpperCase())}
                onKeyDown={handleKeyDown}
                onBlur={addTicker}
                disabled={running}
              />
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.label.date')}</label>
            <input type="date" className="glass-input rounded-xl px-3 py-2 text-xs outline-none" value={date} onChange={e => setDate(e.target.value)} disabled={running} />
          </div>
          <div>
            <label className="text-[10px] font-bold text-slate-500 mb-1.5 block uppercase tracking-wider">{t('analysis.label.type')}</label>
            <select className="glass-input rounded-xl px-3 py-2 text-xs outline-none" value={assetType} onChange={e => setAssetType(e.target.value)} disabled={running}>
              {assetTypes.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <button
            onClick={handleRun}
            disabled={running || tickers.length < 2}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 shadow-md shadow-violet-500/20 transition-all cursor-pointer"
          >
            {running ? <Loader2 size={13} className="animate-spin" /> : <BarChart2 size={13} />}
            {running ? t('analysis.multi.running') : t('analysis.multi.btn_start')}
          </button>
          {running && (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold text-white bg-rose-600/90 hover:bg-rose-600 disabled:opacity-60 disabled:cursor-wait shadow-md shadow-rose-500/20 transition-all cursor-pointer"
            >
              {stopping ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}
              {stopping ? t('analysis.btn.stopping') : t('analysis.btn.stop')}
            </button>
          )}
        </div>

        {running && progress && <div className="flex items-center gap-2 text-violet-300 text-xs font-semibold"><Loader2 size={14} className="animate-spin" /> {progress}</div>}
        {done && <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold"><CheckCircle size={14} /> {t('analysis.multi.started')}</div>}
        {cancelled && <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold"><X size={14} /> {t('analysis.ws.stopped')}</div>}
        {error && (
          <div role="alert" className="space-y-2 text-xs font-semibold text-rose-400">
            <div className="flex items-center gap-2"><AlertCircle size={14} /> {displayedError}</div>
            {startError && startError.suggestions.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 pl-5 text-[11px]">
                <span className="text-slate-500">{t('analysis.ticker_error.suggestions')}</span>
                {startError.suggestions.map(suggestion => (
                  <button
                    key={suggestion.symbol}
                    type="button"
                    onClick={() => selectTickerSuggestion(suggestion.symbol)}
                    className="rounded-lg border border-amber-400/25 bg-amber-400/10 px-2 py-1 font-mono font-bold text-amber-200 transition hover:bg-amber-400/20"
                    title={suggestion.name || suggestion.symbol}
                  >
                    {t('analysis.ticker_error.use').replace('{ticker}', suggestion.symbol)}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <PortfolioHistorySection />
    </div>
  )
}

function PortfolioHistorySection() {
  const { t } = useTranslation()
  const [detail, setDetail] = useState<MultiTickerResultRead | null>(null)
  const queryClient = useQueryClient()

  const historyQuery = useAnalysisListPortfolioAnalyses()
  const items = (historyQuery.data ?? []) as unknown as MultiTickerListItem[]
  const loading = historyQuery.isPending

  if (loading) return <div className="text-slate-500 text-xs px-2">{t('analysis.portfolio_history.loading')}</div>

  return (
    <div className="glass-panel rounded-2xl p-5">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3.5">{t('analysis.portfolio_history.title')}</h3>
      {items.length === 0 ? <p className="text-slate-600 text-xs">{t('analysis.portfolio_history.empty')}</p> : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} onClick={() => queryClient
              .fetchQuery({
                queryKey: getAnalysisGetPortfolioAnalysisQueryKey(item.id),
                queryFn: () => analysisGetPortfolioAnalysis(item.id),
              })
              .then(d => setDetail(d as unknown as MultiTickerResultRead))
              .catch(e => console.error('Failed to load portfolio detail', e))}
              className="flex items-center justify-between p-3 rounded-xl bg-slate-900/20 hover:bg-slate-900/60 cursor-pointer transition-colors border border-white/[0.03] hover:border-white/[0.08]">
              <div className="flex items-center gap-2">
                <span className="text-white font-mono text-xs font-bold">{item.tickers.join(', ')}</span>
                <span className="text-slate-500 text-[10px]">{item.trade_date}</span>
              </div>
              <span className="text-slate-500 text-[10px] font-mono">{new Date(item.created_at).toLocaleDateString()}</span>
            </div>
          ))}
        </div>
      )}
      {detail && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-slate-900 border border-white/[0.06] rounded-2xl p-6 w-full max-w-3xl my-8 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-display font-bold text-white">{detail.tickers.join(', ')}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-500 hover:text-white transition-colors p-1.5 rounded-lg hover:bg-white/5 cursor-pointer"><X size={16} /></button>
            </div>
            <p className="text-slate-500 text-[10px] font-mono">{detail.trade_date} • {new Date(detail.created_at).toLocaleString()}</p>
            <div className="bg-slate-950 rounded-xl p-4 max-h-[50vh] overflow-y-auto border border-white/[0.04] custom-scrollbar">
              <MarkdownReport
                content={detail.super_portfolio_report || t('analysis.portfolio_history.report_not_ready')}
                className="!text-xs !leading-relaxed"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function HistoryTab({
  initialDetailId,
  onRollbackStart,
}: {
  initialDetailId?: number
  onRollbackStart: (taskId: string, ticker: string) => void
}) {
  const { t, language } = useTranslation()
  const createShare = useShareCreateShare()
  const [detail, setDetail] = useState<AnalysisResultRead | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeDetailTab, setActiveDetailTab] = useState<'reports' | 'debate' | 'chat' | 'timetravel'>('reports')
  const [shareLink, setShareLink] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<number | null>(null)
  const [showClearAllModal, setShowClearAllModal] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [clearingAll, setClearingAll] = useState(false)

  const shareReport = useCallback(async (id: number) => {
    setSharing(true)
    setShareLink(null)
    try {
      const data = await createShare.mutateAsync({ analysisId: id }) as unknown as { token: string; expires_at: string }
      const link = buildPublicShareUrl(data.token)
      setShareLink(link)
      // Clipboard access is unavailable on plain HTTP origins (including the
      // common local Docker URL).  A successful API response must still leave
      // a usable link in the UI rather than falling into the outer error path.
      let copied = false
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(link)
          copied = true
        }
      } catch {
        // The readonly link field below is the manual-copy fallback.
      }
      notify('success', copied ? 'Share link copied to clipboard' : 'Share link created — copy it from the field below', 'Share')
    } catch (e: any) {
      notify('error', e.response?.data?.detail || 'Share failed', 'Share')
    } finally {
      setSharing(false)
    }
  }, [])
  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? {}

  const deleteAnalysis = useAnalysisDeleteAnalysis()
  const clearHistory = useAnalysisClearHistory()
  const historyQuery = useAnalysisListAnalysis({ limit: 50 })
  const items = (historyQuery.data ?? []) as unknown as AnalysisListItem[]
  const loading = historyQuery.isPending
  const historyQueryClient = useQueryClient()

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    setActiveDetailTab('reports')
    // Never leave the previous record's token visible while a new detail is
    // loading; doing so made it easy to copy the wrong report's link.
    setShareLink(null)
    try {
      const data = await historyQueryClient.fetchQuery({
        queryKey: getAnalysisGetAnalysisQueryKey(id),
        queryFn: () => analysisGetAnalysis(id),
      })
      setDetail(data as never)
    } finally { setDetailLoading(false) }
  }, [])

  const confirmDeleteSingle = async () => {
    if (!itemToDelete) return
    const id = itemToDelete
    setDeletingId(id)
    try {
      await deleteAnalysis.mutateAsync({ analysisId: id })
      await historyQuery.refetch()
      notify('success', t('analysis.history.deleted_single'), t('analysis.title'))
      if (detail?.id === id) setDetail(null)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Delete failed', t('analysis.title'))
    } finally {
      setDeletingId(null)
      setItemToDelete(null)
    }
  }

  const confirmClearAll = async () => {
    setClearingAll(true)
    try {
      await clearHistory.mutateAsync()
      await historyQuery.refetch()
      setDetail(null)
      notify('success', t('analysis.history.deleted_all'), t('analysis.title'))
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Clear history failed', t('analysis.title'))
    } finally {
      setClearingAll(false)
      setShowClearAllModal(false)
    }
  }

  // Open the detail modal directly when arriving via a /analysis?id=… deep link.
  useEffect(() => {
    if (initialDetailId) openDetail(initialDetailId)
  }, [initialDetailId, openDetail])

  const historyPortfolioDecision = detail
    ? readPortfolioDecision(detail.portfolio_decision_json, detail.chart_annotations, detail.trader_proposal_json)
    : null
  const historyHasPortfolioManagerDecision = historyPortfolioDecision?.source === 'portfolio_manager'
  const historyReportEntries = detail
    ? visibleReportEntries(detail as unknown as Record<string, unknown>)
    : []

  if (loading) return <div className="p-8 text-slate-500 text-xs">{t('analysis.history.loading')}</div>

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-slate-600 text-xs text-center">{t('analysis.history.empty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="flex justify-end items-center gap-2 px-4 py-2 border-b border-white/[0.04]">
              <button
                onClick={() => exportAnalysesCSV(items)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold text-slate-500 hover:text-violet-300 hover:bg-violet-500/10 border border-white/[0.04] hover:border-violet-500/20 transition cursor-pointer"
              >
                <Download size={11} /> Export CSV
              </button>
              <button
                onClick={() => setShowClearAllModal(true)}
                disabled={clearingAll}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold text-rose-400 hover:text-white hover:bg-rose-500/20 border border-rose-500/20 transition cursor-pointer disabled:opacity-40"
              >
                {clearingAll ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                {t('analysis.history.btn_clear_all')}
              </button>
            </div>
            <table className="w-full text-xs min-w-[500px]">
              <thead>
                <tr className="text-slate-500 text-[10px] uppercase tracking-wider border-b border-white/[0.04] bg-slate-900/10">
                  <th className="px-5 py-3 text-left font-bold">{t('analysis.history.col_symbol')}</th>
                  <th className="px-5 py-3 text-left font-bold">{t('analysis.history.col_date')}</th>
                  <th className="px-5 py-3 text-left font-bold">{t('analysis.history.col_signal')}</th>
                  <th className="px-5 py-3 text-left font-bold">{t('analysis.history.col_duration')}</th>
                  <th className="px-5 py-3 text-left hidden sm:table-cell font-bold">{t('analysis.history.col_source')}</th>
                  <th className="px-5 py-3 text-left hidden md:table-cell font-bold">{t('analysis.history.col_time')}</th>
                  <th className="px-5 py-3 text-right font-bold">{t('analysis.history.col_actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.02] text-slate-300">
                {items.map(item => (
                  <tr key={item.id} onClick={() => openDetail(item.id)}
                    className="hover:bg-white/[0.02] cursor-pointer transition-colors">
                    <td className="px-5 py-3.5 font-mono font-bold text-white">{item.ticker}</td>
                    <td className="px-5 py-3.5 text-slate-400 font-semibold">{item.trade_date}</td>
                    <td className="px-5 py-3.5"><SignalBadge signal={item.signal} /></td>
                    <td className="px-5 py-3.5 text-slate-500 font-mono">{(item.duration_seconds ?? 0).toFixed(1)}s</td>
                    <td className="px-5 py-3.5 text-slate-500 hidden sm:table-cell">{item.triggered_by}</td>
                    <td className="px-5 py-3.5 text-slate-600 hidden md:table-cell font-mono">{new Date(item.created_at).toLocaleString()}</td>
                    <td className="px-5 py-3.5 text-right" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={(e) => { e.stopPropagation(); setItemToDelete(item.id) }}
                        disabled={deletingId === item.id}
                        className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer disabled:opacity-50"
                        title={t('analysis.history.confirm_delete_single')}
                      >
                        {deletingId === item.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {itemToDelete !== null && (
        <div className="fixed inset-0 bg-black/75 z-[60] flex items-center justify-center p-5 backdrop-blur-md">
          <div className="bg-slate-900 border border-white/[0.06] rounded-3xl p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <div className="space-y-2">
              <h3 className="text-white text-lg font-display font-bold flex items-center gap-2">
                <Trash2 className="text-rose-500" size={18} /> {t('analysis.history.btn_clear_all')}
              </h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                {t('analysis.history.confirm_delete_single')}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={confirmDeleteSingle}
                disabled={deletingId !== null}
                className="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold py-2.5 rounded-xl transition shadow shadow-rose-600/20 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {deletingId !== null ? <Loader2 size={13} className="animate-spin" /> : null}
                Sil
              </button>
              <button
                onClick={() => setItemToDelete(null)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold py-2.5 rounded-xl transition cursor-pointer"
              >
                {t('analysis.btn.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {showClearAllModal && (
        <div className="fixed inset-0 bg-black/75 z-[60] flex items-center justify-center p-5 backdrop-blur-md">
          <div className="bg-slate-900 border border-white/[0.06] rounded-3xl p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <div className="space-y-2">
              <h3 className="text-white text-lg font-display font-bold flex items-center gap-2">
                <AlertTriangle className="text-rose-500" size={18} /> {t('analysis.history.btn_clear_all')}
              </h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                {t('analysis.history.confirm_clear_all')}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={confirmClearAll}
                disabled={clearingAll}
                className="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold py-2.5 rounded-xl transition shadow shadow-rose-600/20 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {clearingAll ? <Loader2 size={13} className="animate-spin" /> : null}
                {t('analysis.history.btn_clear_all')}
              </button>
              <button
                onClick={() => setShowClearAllModal(false)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold py-2.5 rounded-xl transition cursor-pointer"
              >
                {t('analysis.btn.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {(detail || detailLoading) && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-3 md:p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-slate-900 border border-white/[0.06] rounded-2xl p-4 md:p-6 w-full max-w-4xl my-4 md:my-8 space-y-4 shadow-2xl flex flex-col max-h-[90vh]">
            {detailLoading ? (
              <div className="flex items-center gap-2 text-slate-400 py-12 justify-center"><Loader2 className="animate-spin" size={16} /> {t('analysis.history.detail_loading')}</div>
            ) : detail ? (
              <>
                <div className="flex items-start justify-between border-b border-white/[0.04] pb-3 shrink-0">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-xl font-display font-bold text-white font-mono">{detail.ticker}</h3>
                      <SignalBadge signal={detail.signal} large />
                      {detail.quality ? <QualityBadge quality={detail.quality as RunQuality} /> : null}
                    </div>
                    <p className="text-[10px] text-slate-500 font-semibold">{detail.trade_date} • {(detail.duration_seconds ?? 0).toFixed(1)}s • {detail.llm_calls} LLM • {(detail.tokens_in + detail.tokens_out).toLocaleString()} token{detail.estimated_cost_usd ? ` • ~$${detail.estimated_cost_usd.toFixed(4)}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => exportMarkdown(detail, language as 'en' | 'tr')} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_md')}>
                      <Download size={12} /> MD
                    </button>
                    <button onClick={() => exportPDF(detail, language as 'en' | 'tr')} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_pdf')}>
                      <FileDown size={12} /> PDF
                    </button>
                    <button
                      onClick={() => shareReport(detail.id)}
                      disabled={sharing}
                      className="flex items-center gap-1 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 text-[10px] font-bold text-violet-400 px-2.5 py-1.5 rounded-lg transition cursor-pointer disabled:opacity-40"
                      title={t('analysis.share_report')}
                    >
                      {sharing ? <Loader2 size={12} className="animate-spin" /> : <Share2 size={12} />} Share
                    </button>
                    {shareLink && (
                      <div className="flex items-center gap-1 max-w-[min(24rem,50vw)]">
                        <input
                          aria-label={t('analysis.share_link')}
                          readOnly
                          value={shareLink}
                          onFocus={event => event.currentTarget.select()}
                          className="min-w-0 flex-1 bg-slate-950/70 border border-emerald-500/20 rounded-lg px-2 py-1.5 text-[10px] text-emerald-300 font-mono outline-none focus:border-emerald-400/50"
                          title={shareLink}
                        />
                        <button
                          onClick={async () => {
                            try {
                              if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable')
                              await navigator.clipboard.writeText(shareLink)
                              notify('success', 'Share link copied to clipboard', 'Share')
                            } catch {
                              notify('error', 'Select and copy the share link manually', 'Share')
                            }
                          }}
                          className="shrink-0 flex items-center gap-1 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-[10px] font-bold text-emerald-400 px-2 py-1.5 rounded-lg transition cursor-pointer"
                          title={t('analysis.copy_share_link')}
                        >
                          <Copy size={11} /> Copy
                        </button>
                      </div>
                    )}
                    <button onClick={() => { setDetail(null); setShareLink(null) }} className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5 cursor-pointer"><X size={16} /></button>
                  </div>
                </div>

                <div className="flex items-center gap-1 p-1 bg-slate-950/60 border border-white/[0.04] rounded-xl shrink-0">
                  <button
                    onClick={() => setActiveDetailTab('reports')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'reports' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.reports')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('debate')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.debate')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('chat')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'chat' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.qa')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('timetravel')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'timetravel' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.timetravel')}
                  </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto">
                  {activeDetailTab === 'reports' && (
                    <div className="space-y-2 pr-1">
                      {detail.risk_metrics ? <RiskMetricsCard metrics={detail.risk_metrics as any} /> : null}
                      <PortfolioDecisionCard
                        acceptedPortfolioDecision={detail.portfolio_decision_json}
                        chartAnnotations={detail.chart_annotations}
                        legacyTraderJson={detail.trader_proposal_json}
                      />
                      <StrategyTransitionCard
                        analysisPlan={detail.analysis_plan_json}
                        strategyBefore={detail.strategy_before_json}
                        strategyAfter={detail.strategy_after_json}
                        strategyCandidate={detail.strategy_candidate_json}
                        pmProposal={detail.pm_proposal_json}
                        acceptedDecision={detail.portfolio_decision_json}
                        transition={detail.decision_transition_json}
                        calibratedConfidence={detail.calibrated_confidence ?? null}
                        strategyUpdateStatus={detail.strategy_update_status ?? null}
                        strategyBeforeVersion={detail.strategy_before_version ?? null}
                        strategyAfterVersion={detail.strategy_after_version ?? null}
                      />
                      {([
                        ...historyReportEntries,
                        ['investment_plan', detail.investment_plan],
                        ...(historyHasPortfolioManagerDecision ? [] : [['trader_plan', detail.trader_plan] as [string, string]]),
                        ['final_decision', detail.final_decision],
                      ] as [string, string][]).filter(entry => !!entry[1]).map(([k, v]) => (
                        <ReportCard key={k} label={readableSectionLabel(sectionLabels, k)} content={v} />
                      ))}
                      {(detail.bull_history || detail.bear_history || detail.judge_decision) && (
                        <div className="border-t border-white/[0.04] pt-3 mt-4">
                          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{t('analysis.debate_records')}</h4>
                          <div className="space-y-2">
                            {detail.bull_history ? <ReportCard label="Bull" content={detail.bull_history as string} /> : null}
                            {detail.bear_history ? <ReportCard label="Bear" content={detail.bear_history as string} /> : null}
                            {detail.judge_decision && <ReportCard label="Judge" content={detail.judge_decision} />}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {activeDetailTab === 'debate' && (
                    <DebateHistoryWidget investmentHistory={detail.investment_debate_history} riskHistory={detail.risk_debate_history} />
                  )}
                  {activeDetailTab === 'chat' && (
                    <AnalysisChatWidget analysisId={detail.id} />
                  )}
                  {activeDetailTab === 'timetravel' && (
                    <TimeTravelWidget
                      analysisId={detail.id}
                      onRollbackStart={(taskId) => onRollbackStart(taskId, detail.ticker)}
                    />
                  )}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}

type Tab = 'run' | 'multi' | 'history'

export default function Analysis() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const deepLinkId = searchParams.get('id')
  const [tab, setTab] = useState<Tab>(deepLinkId ? 'history' : 'run')

  const tabs = [
    { id: 'run' as Tab,     label: t('analysis.tab.single'), icon: <Zap size={13} /> },
    { id: 'multi' as Tab,   label: t('analysis.tab.multi'),  icon: <BarChart2 size={13} /> },
    { id: 'history' as Tab, label: t('analysis.tab.history'), icon: <History size={13} /> },
  ]

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('analysis.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">{t('analysis.multi_subtitle')}</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-900/50 border border-white/[0.04] rounded-2xl w-fit">
        {tabs.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              tab === tb.id ? 'bg-violet-600 text-white shadow shadow-violet-500/20' : 'text-slate-500 hover:text-white'
            }`}
          >
            {tb.icon} <span className="hidden sm:inline">{tb.label}</span>
          </button>
        ))}
      </div>

      {tab === 'run'     && <RunTab />}
      {tab === 'multi'   && <MultiTab />}
      {tab === 'history' && (
        <HistoryTab
          initialDetailId={deepLinkId ? Number(deepLinkId) : undefined}
          onRollbackStart={(taskId, ticker) => {
            sessionStorage.setItem(
              TASK_KEY,
              JSON.stringify({
                ticker: ticker.toUpperCase(),
                taskId,
                startedAt: new Date().toISOString(),
              })
            )
            sessionStorage.setItem(
              STORAGE_KEY,
              JSON.stringify({
                ticker: ticker.toUpperCase(),
                date: new Date().toISOString().slice(0, 10),
                assetType: 'stock',
                runStatus: 'running',
                signal: null,
                reports: {},
                log: [],
                activeSection: null,
                analysisId: null,
              })
            )
            setTab('run')
          }}
        />
      )}
    </div>
  )
}

function TimeTravelWidget({
  analysisId,
  onRollbackStart,
}: {
  analysisId: number
  onRollbackStart: (taskId: string) => void
}) {
  const { t, language } = useTranslation()
  const timeTravel = useAnalysisTimeTravelResume()
  const [checkpoints, setCheckpoints] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCp, setSelectedCp] = useState<any>(null)
  const [updateFields, setUpdateFields] = useState<Record<string, string>>({})
  const [rollbackLoading, setRollbackLoading] = useState(false)

  useEffect(() => {
    axios
      .get(`/api/analysis/${analysisId}/checkpoints`)
      .then((r) => {
        setCheckpoints(r.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [analysisId])

  const handleSelectCheckpoint = (cp: any) => {
    setSelectedCp(cp)
    const fields: Record<string, string> = {}
    if (cp.node === 'Research Manager' || cp.node === 'ResearchManager') {
      fields['investment_plan'] = ''
    } else if (cp.node === 'Portfolio Manager' || cp.node === 'portfolio_manager') {
      // The Portfolio Manager owns the sole executable decision in new runs.
      // Clear its structured output before a replay so a previous action/size
      // cannot remain visible while the new decision is being generated.
      fields['portfolio_decision_json'] = '{}'
      fields['final_trade_decision'] = ''
      fields['final_signal'] = ''
    } else if (cp.node === 'Trader') {
      // Historical checkpoints can still be inspected, but the retired node
      // cannot create a new execution recommendation in the current graph.
      fields['trader_investment_plan'] = ''
      fields['trader_proposal_json'] = '{}'
    } else if (cp.node === 'Agent Q&A' || cp.node === 'agent_qa') {
      fields['agent_qa_report'] = ''
    } else {
      fields['investment_plan'] = ''
    }
    setUpdateFields(fields)
  }

  const handleRollback = async () => {
    if (!selectedCp) return
    setRollbackLoading(true)
    try {
      const data = await timeTravel.mutateAsync({
        analysisId,
        data: {
          checkpoint_id: selectedCp.checkpoint_id,
          update_state: updateFields,
        },
      })
      notify('success', language === 'tr' ? 'Zaman yolculuğu başlatıldı!' : 'Time travel initiated!')
      onRollbackStart(data.task_id)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Rollback failed')
    } finally {
      setRollbackLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-12 justify-center">
        <Loader2 className="animate-spin" size={16} /> {t('analysis.timetravel.loading_checkpoints')}
      </div>
    )
  }

  if (checkpoints.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 text-xs">
        {t('analysis.timetravel.no_checkpoints')}
      </div>
    )
  }

  return (
    <div className="space-y-5 p-1">
      <div className="space-y-2">
        <h4 className="text-white text-xs font-bold uppercase tracking-wider">
          {t('analysis.timetravel.title')}
        </h4>
        <p className="text-slate-400 text-[11px] leading-relaxed">
          {language === 'tr'
            ? 'Mevcut analizi seçtiğiniz bir adıma geri sarıp durum verilerini değiştirerek oradan itibaren yeniden çalıştırabilirsiniz.'
            : 'Roll back the execution flow to a selected checkpoint step, edit state fields, and resume propagation.'}
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-[10px] font-bold text-slate-500 block uppercase tracking-wider">
          {t('analysis.timetravel.select_checkpoint')}
        </label>
        <div className="grid grid-cols-1 gap-2 max-h-36 overflow-y-auto pr-1">
          {checkpoints.map((cp) => (
            <div
              key={cp.checkpoint_id}
              onClick={() => handleSelectCheckpoint(cp)}
              className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${
                selectedCp?.checkpoint_id === cp.checkpoint_id
                  ? 'bg-violet-600/10 border-violet-500 text-white'
                  : 'bg-slate-900/40 border-white/[0.04] text-slate-300 hover:border-white/[0.1]'
              }`}
            >
              <div className="flex items-center gap-2 font-semibold">
                <span className="text-[10px] text-slate-500 font-mono">#{cp.step}</span>
                <span>{cp.label}</span>
              </div>
              <span className="text-[9px] text-slate-600 font-mono">
                {cp.checkpoint_id.slice(0, 8)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {selectedCp && (
        <div className="space-y-4 animate-in fade-in duration-300">
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-slate-500 block uppercase tracking-wider">
              {t('analysis.timetravel.edit_fields')}
            </label>
            {Object.keys(updateFields).map((field) => (
              <div key={field} className="space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-400 font-mono">{field}</span>
                <textarea
                  value={updateFields[field]}
                  onChange={(e) =>
                    setUpdateFields((prev) => ({ ...prev, [field]: e.target.value }))
                  }
                  className="w-full h-24 bg-slate-950 border border-white/[0.08] rounded-xl p-3 text-xs text-white outline-none focus:border-violet-500/50 font-mono leading-relaxed"
                  placeholder={
                    field === 'portfolio_decision_json'
                      ? '{"rating": "Buy", "entry_price": 150.0, "position_size_pct": 5}'
                      : `Enter custom ${field} value...`
                  }
                />
              </div>
            ))}
          </div>

          <button
            onClick={handleRollback}
            disabled={rollbackLoading}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 py-2.5 rounded-xl text-xs font-semibold text-white cursor-pointer shadow shadow-violet-600/20 transition disabled:opacity-40"
          >
            {rollbackLoading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Scale size={13} />
            )}
            {t('analysis.timetravel.btn_rollback')}
          </button>
        </div>
      )}
    </div>
  )
}
