import { useState, useRef, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { getAccessToken } from '../contexts/AuthContext'
import { useMeta } from '../hooks/useMeta'
import { useActiveTasks } from '../hooks/useActiveTasks'
import { notify } from '../utils/notify'
import { exportMarkdown, exportPDF } from '../utils/exportReport'
import { exportAnalysesCSV } from '../utils/csvExport'
import { sendBrowserNotification } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import {
  Loader2, CheckCircle, AlertCircle, History,
  X, BarChart2, FileText, Zap,
  Download, FileDown, AlertTriangle, Scale, Share2, Copy,
  MessageSquare, Bot, Terminal, BookOpen
} from 'lucide-react'
import type { AnalysisListItem, AnalysisResultRead, MultiTickerListItem, MultiTickerResultRead } from '../api/types'
import { SignalBadge } from '../components/analysis/SignalBadge'
import { ReportCard } from '../components/analysis/ReportCard'
import { AnalysisControls } from '../components/analysis/AnalysisControls'

import { DebateHistoryWidget, parseDebateMessage, getSenderStyles } from '../components/analysis/DebateHistoryWidget'
import { AnalysisChatWidget } from '../components/analysis/AnalysisChatWidget'
import { RiskMetricsCard } from '../components/analysis/RiskMetricsCard'
import { MentalModelTicker } from '../components/analysis/MentalModelTicker'
import { KellyPositioningCard } from '../components/analysis/KellyPositioningCard'
import { ErrorBoundary } from '../components/ErrorBoundary'

interface WsEvent {
  type: string; section?: string; content?: string; signal?: string
  final_decision?: string; message?: string; duration_seconds?: number
  llm_calls?: number; status?: string; agent?: string; analysis_id?: number
  label?: string; stage?: string; node?: string
  thought?: string; metrics?: any; token?: string; tokens_in?: number; tokens_out?: number
  debate_type?: string
  attempt?: number; max_attempts?: number; error?: string; kind?: string
  error_type?: string; elapsed_seconds?: number
  estimated_cost_usd?: number
}
const STORAGE_KEY = 'ta_last_run'
const TASK_KEY = 'ta_task_running'

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

const EMPTY_RUN = {
  ticker: '', date: new Date().toISOString().slice(0, 10), assetType: 'stock',
  runStatus: 'idle' as 'idle' | 'running' | 'done' | 'error',
  signal: null as string | null, reports: {} as Record<string, string>,
  log: [] as string[], activeSection: null as string | null,
  analysisId: null as number | null,
  liveDebate: [] as { sender: string; content: string; type: string }[],
}

function loadRunState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const hasRunningTask = !!localStorage.getItem(TASK_KEY)
    if (!raw) return EMPTY_RUN
    const parsed = JSON.parse(raw)
    if (hasRunningTask) {
      return { ...EMPTY_RUN, ...parsed, runStatus: 'running' }
    }
    const status = parsed.runStatus === 'running' ? 'idle' : parsed.runStatus
    return { ...EMPTY_RUN, ...parsed, runStatus: status }
  } catch { return EMPTY_RUN }
}

// Safely render the Kelly card from a (possibly malformed/partial) JSON string.
// trader_proposal_json is streamed over the WebSocket, so an unguarded JSON.parse
// in the render path could throw and take down the whole tab.
function KellyPositioningFromJson({ json }: { json?: string | null }) {
  if (!json || json === '{}') return null
  let parsed: any
  try { parsed = JSON.parse(json) } catch { return null }
  if (!parsed || typeof parsed !== 'object') return null
  return <KellyPositioningCard kellySize={parsed.kelly_size} suggestedCapital={parsed.suggested_capital} />
}

function RunTab() {
  const { t } = useTranslation()
  const saved = loadRunState()
  const [ticker, setTicker] = useState(saved.ticker)
  const [date, setDate] = useState(saved.date)
  const [assetType, setAssetType] = useState(saved.assetType)
  const [running, setRunning] = useState(saved.runStatus === 'running')
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'done' | 'error'>(saved.runStatus)
  const [signal, setSignal] = useState<string | null>(saved.signal)
  const [reports, setReports] = useState<Record<string, string>>(saved.reports)
  const [log, setLog] = useState<string[]>(saved.log)
  const [activeSection, setActiveSection] = useState<string | null>(saved.activeSection)
  const [analysisId, setAnalysisId] = useState<number | null>(saved.analysisId || null)
  const [detail, setDetail] = useState<AnalysisResultRead | null>(null)
  const [activeTab, setActiveTab] = useState<'consensus' | 'reports' | 'debate' | 'chat' | 'timetravel'>('consensus')
  const [liveDebate, setLiveDebate] = useState<{ sender: string; content: string; type: string }[]>(saved.liveDebate || [])
  const [liveDebateTab, setLiveDebateTab] = useState<'inv' | 'risk'>('inv')
  const [riskMetrics, setRiskMetrics] = useState<any>(null)
  const [mentalModel, setMentalModel] = useState<{ agent: string; thought: string } | null>(null)
  const [stats, setStats] = useState<{ llmCalls: number; tokensIn: number; tokensOut: number; estimatedCost?: number } | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const preRefreshLogRef = useRef<string[] | null>(null)
  const seenLogRef = useRef<Set<string>>(new Set())
  const stoppedByUserRef = useRef(false)
  // Always-current ticker for use inside the WS handler, so attachWs doesn't
  // need `ticker` in its deps (which recreated the socket on every keystroke)
  // and the completion toast never shows a stale/empty symbol.
  const tickerRef = useRef(ticker)
  useEffect(() => { tickerRef.current = ticker }, [ticker])
  const lastPersistRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? {}
  const sectionLabelsRef = useRef(sectionLabels)
  useEffect(() => { sectionLabelsRef.current = sectionLabels }, [sectionLabels])
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]
  const [currentStep, setCurrentStep] = useState<{ label: string; stage: string } | null>(null)

  const [costEstimate, setCostEstimate] = useState<{ estimated_cost_usd: number; estimated_tokens: number; estimated_duration_min: number; analyst_count: number } | null>(null)
  const [existingId, setExistingId] = useState<number | null>(null)
  const [showRerunModal, setShowRerunModal] = useState(false)

  const { activeTasks } = useActiveTasks()

  useEffect(() => {
    const now = Date.now()
    if (runStatus === 'running' && now - lastPersistRef.current < 2000) return
    lastPersistRef.current = now
    try {
      // Don't persist reports while running — they're large and will be re-streamed via WS on reconnect
      const payload = runStatus === 'running'
        ? { ticker, date, assetType, runStatus, signal, reports: {}, log: [], liveDebate: [], activeSection, analysisId }
        : { ticker, date, assetType, runStatus, signal, reports, log, liveDebate, activeSection, analysisId }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      // QuotaExceededError — ignore, state lives in memory
    }
  }, [ticker, date, assetType, runStatus, signal, reports, log, liveDebate, activeSection, analysisId])

  useEffect(() => {
    if (analysisId && runStatus === 'done' && !detail) {
      axios.get(`/api/analysis/${analysisId}`).then(r => setDetail(r.data)).catch(e => console.error('Failed to fetch analysis detail', e))
    }
  }, [analysisId, runStatus, detail])

  // Cross-device: mount'ta idle durumdaysak en son tamamlanmış analizi yükle
  useEffect(() => {
    if (runStatus === 'idle' && !analysisId) {
      axios.get('/api/analysis/latest').then(r => {
        const a = r.data
        setTicker(a.ticker)
        setDate(a.trade_date)
        setSignal(a.signal)
        setAnalysisId(a.id)
        setRunStatus('done')
        setReports({
          market_report: a.market_report || '',
          sentiment_report: a.sentiment_report || '',
          news_report: a.news_report || '',
          fundamentals_report: a.fundamentals_report || '',
          macro_report: a.macro_report || '',
          options_report: a.options_report || '',
          quant_report: a.quant_report || '',
          earnings_report: a.earnings_report || '',
          insider_report: a.insider_report || '',
          ownership_report: a.ownership_report || '',
          ratings_report: a.ratings_report || '',
          short_interest_report: a.short_interest_report || '',
          valuation_report: a.valuation_report || '',
          catalyst_report: a.catalyst_report || '',
          review_report: a.review_report || '',
          synthesis_report: a.synthesis_report || '',
          audit_report: a.audit_report || '',
          agent_qa_report: a.agent_qa_report || '',
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
      localStorage.removeItem(TASK_KEY)
      taskIdRef.current = null
    }
  }

  const maxReconnectRetries = 3

  const attachWs = useCallback((taskId: string, reconnectAttempt = 0) => {
    if (wsRef.current) {
      try {
        wsRef.current.onmessage = null
        wsRef.current.onerror = null
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch (e) {
        console.error("Error closing existing ws:", e)
      }
    }
    taskIdRef.current = taskId
    const token = getAccessToken()
    const ws = new WebSocket(`/ws/analysis/${taskId}?token=${token}`)
    wsRef.current = ws
    let finished = false

    const scheduleReconnect = () => {
      if (stoppedByUserRef.current) return
      const nextAttempt = reconnectAttempt + 1
      if (nextAttempt <= maxReconnectRetries) {
        const delay = Math.min(1000 * Math.pow(2, nextAttempt - 1), 8000)
        appendLog(`🔄 Reconnecting... (attempt ${nextAttempt}/${maxReconnectRetries})`)
        reconnectTimeoutRef.current = setTimeout(() => attachWs(taskId, nextAttempt), delay)
      } else {
        setRunStatus('error')
        setRunning_(false)
        appendLog(t('analysis.ws.conn_closed'))
        if (reconnectAttempt > 0) {
          notify('error', t('analysis.ws.conn_closed'), t('analysis.ws.analysis_interrupted'))
        }
      }
    }

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

    ws.onmessage = (e) => {
      let ev: WsEvent
      try { ev = JSON.parse(e.data) } catch { return }
      if (ev.type === 'status') {
        appendLog(`${ev.agent}`)
      } else if (ev.type === 'progress') {
        setCurrentStep(prev => prev?.label === ev.label && prev?.stage === ev.stage ? prev : { label: ev.label || '', stage: ev.stage || '' })
        appendLog(`Progress: ${ev.label}`)
      } else if (ev.type === 'token' && ev.agent && ev.token) {
        let reportKey = ev.agent
        if (ev.agent === 'portfolio_manager') {
          reportKey = 'final_decision'
        } else if (ev.agent === 'trader') {
          reportKey = 'trader_plan'
        } else if (ev.agent === 'research_manager') {
          reportKey = 'investment_plan'
        } else if (ev.agent === 'synthesis_manager') {
          reportKey = 'synthesis_report'
        } else if (ev.agent === 'auditor') {
          reportKey = 'audit_report'
        } else if (!ev.agent.endsWith('_report')) {
          reportKey = `${ev.agent}_report`
        }

        setReports(r => {
          const prevContent = r[reportKey] || ''
          return { ...r, [reportKey]: prevContent + ev.token }
        })
        setActiveSection(prev => prev === reportKey ? prev : reportKey)
      } else if (ev.type === 'stats') {
        setStats(prev => {
          const next = { llmCalls: ev.llm_calls || 0, tokensIn: ev.tokens_in || 0, tokensOut: ev.tokens_out || 0 }
          if (prev?.llmCalls === next.llmCalls && prev?.tokensIn === next.tokensIn && prev?.tokensOut === next.tokensOut) return prev
          return next
        })
      } else if (ev.type === 'report' && ev.section && ev.content) {
        setReports(r => ({ ...r, [ev.section!]: ev.content! }))
        setActiveSection(prev => prev === ev.section ? prev : ev.section!)
        appendLog(`Completed: ${sectionLabelsRef.current[ev.section!] || ev.section}`)
      } else if (ev.type === 'mental_model' && ev.agent && ev.thought) {
        setMentalModel({ agent: ev.agent, thought: ev.thought })
      } else if (ev.type === 'risk_metrics' && ev.metrics) {
        setRiskMetrics(ev.metrics)
      } else if (ev.type === 'debate_bubble' && ev.message) {
        const parsed = parseDebateMessage(ev.message)
        setLiveDebate(prev => [...prev, { ...parsed, type: ev.debate_type || 'investment' }])
      } else if (ev.type === 'retry') {
        appendLog(`⚠️ Retrying ${ev.node} (attempt ${ev.attempt}/${ev.max_attempts})`)
      } else if (ev.type === 'fallback') {
        appendLog(`⚠️ Fallback activated for ${ev.node} (${ev.kind})`)
      } else if (ev.type === 'node_error') {
        appendLog(`❌ Error in ${ev.node} (${ev.error_type})`)
      } else if (ev.type === 'circuit_open') {
        appendLog(`🔒 Circuit open for ${ev.node} (${ev.elapsed_seconds}s)`)
      } else if (ev.type === 'decision') {
        setSignal(ev.signal || null)
      } else if (ev.type === 'complete') {
        finished = true
        setRunStatus('done')
        setRunning_(false)
        setCurrentStep(null)
        setMentalModel(null)
        setStats(prev => prev ? { ...prev, llmCalls: ev.llm_calls || prev.llmCalls, estimatedCost: ev.estimated_cost_usd } : null)
        appendLog(`Completed in ${ev.duration_seconds}s / ${ev.llm_calls} LLM calls`)
        sendBrowserNotification(
          `${tickerRef.current.toUpperCase()} Analysis Completed`,
          `Signal: ${ev.signal ?? 'N/A'} • Duration: ${ev.duration_seconds?.toFixed(0)}s`
        )
        if (ev.analysis_id) {
          setAnalysisId(ev.analysis_id)
          axios.get(`/api/analysis/${ev.analysis_id}`).then(r => setDetail(r.data)).catch(e => console.error('Failed to fetch analysis detail on complete', e))
        }
      } else if (ev.type === 'error') {
        finished = true
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
    ws.onerror = () => {
      if (!finished) {
        // onclose will handle reconnect; don't set error here
      }
    }
    ws.onclose = () => {
      if (!finished) {
        scheduleReconnect()
      }
    }
    // ticker is intentionally read via tickerRef (not a dep) so the socket
    // isn't torn down and recreated on every ticker keystroke.
  }, [t])

  // Effect to sync with active tasks from the server (Cross-device fix)
  useEffect(() => {
    if (activeTasks.length > 0 && !running) {
        // If there's an active task on the server but we are 'idle' here, sync it.
        const task = activeTasks[0]
        setTicker(task.ticker)
        setDate(task.trade_date)
        setAssetType(task.asset_type)
        setRunning(true)
        setRunStatus('running')
        setLog([])
        seenLogRef.current = new Set()
        setReports({})
        setSignal(null)
        setAnalysisId(null)
        setDetail(null)
        localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: task.ticker, taskId: task.task_id, startedAt: new Date(task.started_at * 1000).toISOString() }))
        attachWs(task.task_id, 1)
    }
  }, [activeTasks, running, attachWs])

  useEffect(() => {
    const raw = localStorage.getItem(TASK_KEY)
    if (!raw) return
    let cancelled = false
    try {
      const { taskId, ticker: runTicker } = JSON.parse(raw)
      if (!taskId) return
      // Verify task is still active before reconnecting
      axios.get('/api/analysis/active').then(r => {
        if (cancelled) return
        const activeTasks: { task_id: string }[] = r.data
        if (!activeTasks.some(t => t.task_id === taskId)) {
          localStorage.removeItem(TASK_KEY)
          return
        }
        preRefreshLogRef.current = [...saved.log]
        setRunning(true)
        setRunStatus('running')
        if (runTicker) setTicker(runTicker)
        attachWs(taskId, 1)
      }).catch(() => {
        // API unavailable — attempt reconnect anyway
        if (cancelled) return
        preRefreshLogRef.current = [...saved.log]
        setRunning(true)
        setRunStatus('running')
        if (runTicker) setTicker(runTicker)
        attachWs(taskId, 1)
      })
    } catch { localStorage.removeItem(TASK_KEY) }
    return () => { cancelled = true }
  }, [attachWs, saved.log])

  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (wsRef.current) {
        try {
          wsRef.current.onmessage = null
          wsRef.current.onerror = null
          wsRef.current.onclose = null
          wsRef.current.close()
        } catch { /* ws already closed */ }
      }
    }
  }, [])

  useEffect(() => {
    if (!ticker.trim() || running) return
    const tid = setTimeout(async () => {
      try {
        const { data } = await axios.get('/api/analysis/cost-estimate')
        setCostEstimate(data)
      } catch { setCostEstimate(null) }
    }, 600)
    return () => clearTimeout(tid)
  }, [ticker, date, running])

  useEffect(() => {
    if (!ticker.trim()) { setExistingId(null); return }
    const tid = setTimeout(async () => {
      try {
        const { data } = await axios.get('/api/analysis/history', { params: { limit: 5 } })
        const match = data.find((x: AnalysisListItem) => x.ticker === ticker.toUpperCase() && x.trade_date === date)
        setExistingId(match?.id ?? null)
      } catch { setExistingId(null) }
    }, 400)
    return () => clearTimeout(tid)
  }, [ticker, date])

  const handleStop = async () => {
    const tid = taskIdRef.current
    setLog(l => [...l, 'Cancelling...'])
    stoppedByUserRef.current = true
    if (tid) {
      try { await axios.post(`/api/analysis/${tid}/cancel`) } catch { /* best-effort cancel */ }
    }
    if (wsRef.current) {
      wsRef.current.onmessage = null
      wsRef.current.onerror = null
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
    setRunStatus('idle')
    setRunning_(false)
    seenLogRef.current = new Set()
  }

  const doRun = async () => {
    setShowRerunModal(false)
    stoppedByUserRef.current = false
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setLiveDebate([])
    setAnalysisId(null)
    setDetail(null)
    setActiveSection(null)
    setCurrentStep(null)
    setStats(null)
    preRefreshLogRef.current = null
    seenLogRef.current = new Set()

    try {
      const { data } = await axios.post('/api/analysis/run', {
        ticker: ticker.toUpperCase(), trade_date: date, asset_type: assetType,
      })
      const taskId = data.task_id
      localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
      attachWs(taskId, 0)
    } catch (err: any) {
      setRunStatus('error')
      setRunning_(false)
      setLog(l => [...l, `Error: ${err.response?.data?.detail || t('analysis.ws.failed_to_start')}`])
    }
  }

  const handleRun = () => {
    if (!ticker.trim()) return
    if (existingId) { setShowRerunModal(true); return }
    doRun()
  }

  const handleClear = () => {
    setRunStatus('idle'); setSignal(null); setReports({}); setLog([]); setActiveSection(null); setCurrentStep(null)
    setAnalysisId(null); setDetail(null); setLiveDebate([]); setStats(null)
  }

  const handleRollbackStart = (taskId: string) => {
    setRunning(true)
    setRunStatus('running')
    setSignal(null)
    setReports({})
    setLog([])
    setLiveDebate([])
    setAnalysisId(null)
    setDetail(null)
    setActiveSection(null)
    setCurrentStep(null)
    setStats(null)
    preRefreshLogRef.current = null
    seenLogRef.current = new Set()

    localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
    attachWs(taskId, 0)
  }

  const reportEntries = Object.entries(reports)

  return (
    <div className="space-y-6">
      <AnalysisControls
        ticker={ticker} setTicker={setTicker}
        date={date} setDate={setDate}
        assetType={assetType} setAssetType={setAssetType}
        assetTypes={assetTypes}
        running={running} runStatus={runStatus}
        handleRun={handleRun} handleStop={handleStop} handleClear={handleClear}
        signal={signal} costEstimate={costEstimate} existingId={existingId}
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

      {(running || log.length > 0 || reportEntries.length > 0 || !!detail) && (() => {
        const isCompleted = !!detail || runStatus === 'done';
        const activeSignal = detail ? detail.signal : signal;
        const activeRiskMetrics = detail ? detail.risk_metrics : riskMetrics;
        const activeTraderProposal = detail ? detail.trader_proposal_json : reports.trader_proposal_json;
        const activeId = detail ? detail.id : analysisId;

        const activePlans = detail ? {
          investment_plan: detail.investment_plan,
          trader_plan: detail.trader_plan,
          final_decision: detail.final_decision,
        } : {
          investment_plan: reports.trader_investment_plan || reports.trader_plan || reports.investment_plan || '',
          trader_plan: reports.trader_plan || '',
          final_decision: reports.final_decision || '',
        };

        const analystReportKeys = [
          'market_report', 'sentiment_report', 'news_report',
          'fundamentals_report', 'macro_report', 'options_report',
          'quant_report', 'earnings_report', 'insider_report',
          'ownership_report', 'ratings_report', 'short_interest_report',
          'valuation_report', 'catalyst_report', 'review_report',
          'synthesis_report', 'audit_report', 'agent_qa_report',
        ];

        const activeReports = analystReportKeys
          .map(k => [k, detail ? detail[k as keyof AnalysisResultRead] : reports[k]] as [string, string])
          .filter(entry => !!entry[1]);

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
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Engine Status</span>
                  {running ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-violet-500/10 text-violet-400 border border-violet-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-violet-500 animate-pulse" />
                      Running
                    </span>
                  ) : runStatus === 'done' ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Completed
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
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide block">Current Action</span>
                    <p className="text-white text-xs font-semibold truncate flex items-center gap-1.5">
                      <Loader2 size={11} className="animate-spin text-violet-400 shrink-0" />
                      {currentStep.label}
                    </p>
                  </div>
                )}

                {running && mentalModel && (
                  <div className="border-t border-white/[0.04] pt-3 mt-3 animate-in fade-in duration-500">
                    <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wide block mb-1">Agent Thought Process</span>
                    <MentalModelTicker agent={mentalModel.agent} thought={mentalModel.thought} />
                  </div>
                )}
              </div>

              {/* Statistics Dashboard */}
              {(stats || detail) && (
                <div className="glass-panel p-4 rounded-2xl grid grid-cols-3 gap-2">
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">LLM Calls</span>
                    <span className="text-sm font-bold text-white font-mono">{detail ? detail.llm_calls : stats?.llmCalls || 0}</span>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">Tokens</span>
                    <span className="text-sm font-bold text-white font-mono">
                      {detail 
                        ? ((detail.tokens_in + detail.tokens_out).toLocaleString()) 
                        : (((stats?.tokensIn || 0) + (stats?.tokensOut || 0)).toLocaleString())
                      }
                    </span>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-slate-900/40 border border-white/[0.03]">
                    <span className="text-[9px] text-slate-500 uppercase font-bold tracking-wider block mb-0.5">Cost Est.</span>
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
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">System Progress Log</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-950/40 space-y-2 font-mono text-[10px]">
                  {log.map((line, i) => (
                    <div key={i} className="flex gap-2.5 leading-relaxed animate-in fade-in slide-in-from-left-2 duration-300">
                      <span className="text-slate-600 shrink-0 select-none">{(i + 1).toString().padStart(2, '0')}</span>
                      <span className={`${
                        line.startsWith('Completed') ? 'text-emerald-400' :
                        line.startsWith('Error') ? 'text-rose-400' :
                        line.startsWith('Progress') ? 'text-violet-400' : 'text-slate-400'
                      }`}>
                        {line}
                      </span>
                    </div>
                  ))}
                  {log.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center opacity-25 py-12 text-slate-500 font-sans">
                      <History size={20} className="mb-1.5" />
                      <p className="text-[9px] uppercase tracking-widest font-semibold">Logs are empty</p>
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
                        <span className="text-[9px] text-slate-500 uppercase font-bold tracking-widest block">Consensus Recommendation</span>
                        <div className="flex items-center gap-2">
                          <SignalBadge signal={activeSignal} large />
                          {detail?.quality ? <QualityBadge quality={detail.quality as RunQuality} /> : null}
                        </div>
                      </div>
                      {activeTraderProposal && activeTraderProposal !== '{}' && (
                        <div className="flex-1 max-w-md min-w-[200px]">
                          <KellyPositioningFromJson json={activeTraderProposal} />
                        </div>
                      )}
                    </div>

                    {/* Risk metrics if present */}
                    {activeRiskMetrics && <RiskMetricsCard metrics={activeRiskMetrics} />}

                    {/* PM Final Decision */}
                    {activePlans.final_decision ? (
                      <div className="glass-panel p-5 rounded-2xl space-y-3 bg-slate-950/20 border border-white/[0.05]">
                        <h4 className="text-[10px] font-bold text-violet-300 uppercase tracking-widest flex items-center gap-1.5">
                          <Scale size={13} /> {sectionLabels.final_decision || 'Nihai Karar (Portfolio Manager)'}
                        </h4>
                        <div className="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed select-text font-sans">
                          {activePlans.final_decision}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-12 text-slate-500 text-xs">
                        {running ? 'Portfolio Manager decision is pending...' : 'No decision generated yet.'}
                      </div>
                    )}

                    {/* Stacked Plan Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {activePlans.investment_plan && (
                        <div className="glass-panel p-4 rounded-xl space-y-2 bg-slate-900/30">
                          <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{sectionLabels.investment_plan || 'Investment Plan'}</h5>
                          <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed select-text font-sans">{activePlans.investment_plan}</div>
                        </div>
                      )}
                      {activePlans.trader_plan && (
                        <div className="glass-panel p-4 rounded-xl space-y-2 bg-slate-900/30">
                          <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{sectionLabels.trader_plan || 'Trader Proposal'}</h5>
                          <div className="text-xs text-slate-300 whitespace-pre-wrap leading-relaxed select-text font-sans">{activePlans.trader_plan}</div>
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
                            label={sectionLabels[key] || key}
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
                              Consensus Debate
                            </button>
                            <button
                              onClick={() => setLiveDebateTab('risk')}
                              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
                                liveDebateTab === 'risk' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                              }`}
                            >
                              Risk Debate
                            </button>
                          </div>
                          <div className="flex-1 overflow-y-auto space-y-3 max-h-[45vh] pr-1">
                            {filteredLiveMessages.length === 0 && (
                              <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                                <MessageSquare size={30} className="mb-2" />
                                <p className="text-xs font-medium uppercase tracking-widest text-center">
                                  {running && currentStep && (currentStep.stage === 'research' || currentStep.stage === 'risk')
                                    ? t('analysis.debate.waiting')
                                    : 'Live debate has not started yet.'}
                                </p>
                              </div>
                            )}
                            {filteredLiveMessages.map((bubble, i) => {
                              const styles = getSenderStyles(bubble.sender);
                              return (
                                <div key={i} className={`flex w-full ${styles.side} animate-in zoom-in-95 fade-in duration-300`}>
                                  <div className={`border rounded-2xl px-4 py-2.5 text-xs flex flex-col gap-1 max-w-[85%] ${styles.bg}`}>
                                    <span className="font-bold uppercase tracking-wider text-[9px] opacity-80 flex items-center gap-1">
                                      {styles.icon} {bubble.sender}
                                    </span>
                                    <span className="leading-relaxed whitespace-pre-wrap">{bubble.content}</span>
                                  </div>
                                </div>
                              );
                            })}
                            
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
                        <p className="text-xs font-semibold">Time Travel checkpoints will be available once the analysis is completed.</p>
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
  const [tickers, setTickers] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [assetType, setAssetType] = useState('stock')
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<string>('')
  const wsRef = useRef<WebSocket | null>(null)
  const meta = useMeta()
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]

  // Close the live-progress socket if the tab unmounts mid-run.
  useEffect(() => () => { try { wsRef.current?.close() } catch { /* noop */ } }, [])

  const addTicker = () => {
    const tk = input.trim().toUpperCase()
    if (tk && !tickers.includes(tk) && tickers.length < 10) setTickers(prev => [...prev, tk])
    setInput('')
  }
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker() } }

  const connectWs = useCallback(function connectWs(taskId: string, retries = 0) {
    try { wsRef.current?.close() } catch { /* noop */ }
    const token = getAccessToken()
    const ws = new WebSocket(`/ws/analysis/${taskId}?token=${token}`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      let ev: any
      try { ev = JSON.parse(e.data) } catch { return }
      if (ev.type === 'progress') {
        setProgress(ev.label || '')
      } else if (ev.type === 'complete') {
        setDone(true); setRunning(false)
        try { ws.close() } catch { /* noop */ }
      } else if (ev.type === 'error') {
        setError(ev.message || t('analysis.multi.error_default')); setRunning(false)
        try { ws.close() } catch { /* noop */ }
      }
    }
    const reconnect = () => {
      if (retries < 3) {
        const delay = Math.min(1000 * Math.pow(2, retries), 8000)
        setTimeout(() => connectWs(taskId, retries + 1), delay)
      } else {
        setError(t('analysis.ws.conn_closed') || 'Connection lost')
        setRunning(false)
      }
    }
    ws.onclose = reconnect
    ws.onerror = reconnect
  }, [t])

  const handleRun = async () => {
    if (tickers.length < 2) return
    setRunning(true); setDone(false); setError(null); setProgress('')
    try {
      const { data } = await axios.post('/api/analysis/run-portfolio', { tickers, trade_date: date, asset_type: assetType })
      const taskId = data.task_id
      if (!taskId) { setDone(true); setRunning(false); return }
      connectWs(taskId, 0)
    } catch (err: any) {
      setError(err.response?.data?.detail || t('analysis.multi.error_default'))
      setRunning(false)
    }
  }

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
                <button onClick={() => setTickers(p => p.filter(x => x !== tk))} className="text-slate-500 hover:text-rose-400 transition-colors cursor-pointer"><X size={10} /></button>
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
        </div>

        {running && progress && <div className="flex items-center gap-2 text-violet-300 text-xs font-semibold"><Loader2 size={14} className="animate-spin" /> {progress}</div>}
        {done && <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold"><CheckCircle size={14} /> {t('analysis.multi.started')}</div>}
        {error && <div className="flex items-center gap-2 text-rose-400 text-xs font-semibold"><AlertCircle size={14} /> {error}</div>}
      </div>
      <PortfolioHistorySection />
    </div>
  )
}

function PortfolioHistorySection() {
  const { t } = useTranslation()
  const [items, setItems] = useState<MultiTickerListItem[]>([])
  const [detail, setDetail] = useState<MultiTickerResultRead | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get('/api/analysis/portfolio-history').then(r => setItems(r.data)).catch(e => { console.error('Failed to load portfolio history', e); setItems([]) }).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-slate-500 text-xs px-2">{t('analysis.portfolio_history.loading')}</div>

  return (
    <div className="glass-panel rounded-2xl p-5">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3.5">{t('analysis.portfolio_history.title')}</h3>
      {items.length === 0 ? <p className="text-slate-600 text-xs">{t('analysis.portfolio_history.empty')}</p> : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} onClick={() => axios.get(`/api/analysis/portfolio/${item.id}`).then(r => setDetail(r.data)).catch(e => console.error('Failed to load portfolio detail', e))}
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
            <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-950 rounded-xl p-4 max-h-[50vh] overflow-y-auto border border-white/[0.04] font-mono leading-relaxed select-text">
              {detail.super_portfolio_report || t('analysis.portfolio_history.report_not_ready')}
            </pre>
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
  const [items, setItems] = useState<AnalysisListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<AnalysisResultRead | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeDetailTab, setActiveDetailTab] = useState<'reports' | 'debate' | 'chat' | 'timetravel'>('reports')
  const [shareLink, setShareLink] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)

  const shareReport = useCallback(async (id: number) => {
    setSharing(true)
    setShareLink(null)
    try {
      const { data } = await axios.post<{ token: string; expires_at: string }>(`/api/analysis/${id}/share`)
      const link = `${window.location.origin}/share/${data.token}`
      setShareLink(link)
      await navigator.clipboard.writeText(link).catch(() => {})
      notify('success', 'Share link copied to clipboard', 'Share')
    } catch (e: any) {
      notify('error', e.response?.data?.detail || 'Share failed', 'Share')
    } finally {
      setSharing(false)
    }
  }, [])
  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? {}

  useEffect(() => {
    axios.get('/api/analysis/history?limit=50').then(r => setItems(r.data)).catch(e => { console.error('Failed to load analysis history', e); setItems([]) }).finally(() => setLoading(false))
  }, [])

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    setActiveDetailTab('reports')
    try { const { data } = await axios.get(`/api/analysis/${id}`); setDetail(data) }
    finally { setDetailLoading(false) }
  }, [])

  // Open the detail modal directly when arriving via a /analysis?id=… deep link.
  useEffect(() => {
    if (initialDetailId) openDetail(initialDetailId)
  }, [initialDetailId, openDetail])

  if (loading) return <div className="p-8 text-slate-500 text-xs">{t('analysis.history.loading')}</div>

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-slate-600 text-xs text-center">{t('analysis.history.empty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="flex justify-end px-4 py-2 border-b border-white/[0.04]">
              <button
                onClick={() => exportAnalysesCSV(items)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold text-slate-500 hover:text-violet-300 hover:bg-violet-500/10 border border-white/[0.04] hover:border-violet-500/20 transition cursor-pointer"
              >
                <Download size={11} /> Export CSV
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
                      title="Share report link (48h)"
                    >
                      {sharing ? <Loader2 size={12} className="animate-spin" /> : <Share2 size={12} />} Share
                    </button>
                    {shareLink && (
                      <button
                        onClick={() => navigator.clipboard.writeText(shareLink)}
                        className="flex items-center gap-1 bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-bold text-emerald-400 px-2 py-1.5 rounded-lg transition cursor-pointer"
                        title={shareLink}
                      >
                        <Copy size={11} /> Copied!
                      </button>
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
                      <KellyPositioningFromJson json={detail.trader_proposal_json} />
                      {([
                        ['market_report', detail.market_report],
                        ['sentiment_report', detail.sentiment_report],
                        ['news_report', detail.news_report],
                        ['fundamentals_report', detail.fundamentals_report],
                        ['macro_report', detail.macro_report],
                        ['options_report', detail.options_report],
                        ['quant_report', detail.quant_report],
                        ['earnings_report', detail.earnings_report],
                        ['insider_report', detail.insider_report],
                        ['ownership_report', detail.ownership_report],
                        ['ratings_report', detail.ratings_report],
                        ['short_interest_report', detail.short_interest_report],
                        ['valuation_report', detail.valuation_report],
                        ['catalyst_report', detail.catalyst_report],
                        ['review_report', detail.review_report],
                        ['synthesis_report', detail.synthesis_report],
                        ['audit_report', detail.audit_report],
                        ['agent_qa_report', detail.agent_qa_report],
                        ['investment_plan', detail.investment_plan],
                        ['trader_plan', detail.trader_plan],
                        ['final_decision', detail.final_decision],
                      ] as [string, string][]).filter(entry => !!entry[1]).map(([k, v]) => (
                        <ReportCard key={k} label={sectionLabels[k] || k} content={v} />
                      ))}
                      {(detail.bull_history || detail.bear_history || detail.judge_decision) && (
                        <div className="border-t border-white/[0.04] pt-3 mt-4">
                          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Debate Records</h4>
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
          <p className="text-xs text-slate-500 mt-1">Deploy multi-agent consensus networks for specialized asset research</p>
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
            localStorage.setItem(
              TASK_KEY,
              JSON.stringify({
                ticker: ticker.toUpperCase(),
                taskId,
                startedAt: new Date().toISOString(),
              })
            )
            localStorage.setItem(
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
    } else if (cp.node === 'Trader') {
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
      const { data } = await axios.post(`/api/analysis/${analysisId}/time-travel`, {
        checkpoint_id: selectedCp.checkpoint_id,
        update_state: updateFields,
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
                    field === 'trader_proposal_json'
                      ? '{"action": "Buy", "entry_price": 150.0}'
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
