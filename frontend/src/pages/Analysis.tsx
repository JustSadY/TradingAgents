import { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import { getAccessToken } from '../hooks/useAuth'
import { useMeta } from '../hooks/useMeta'
import { useActiveTasks } from '../hooks/useActiveTasks'
import { notify } from '../utils/notify'
import { exportMarkdown, exportPDF } from '../utils/exportReport'
import { sendBrowserNotification } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import {
  Loader2, CheckCircle, AlertCircle, History,
  X, BarChart2, FileText, Zap, Square,
  Download, FileDown, AlertTriangle
} from 'lucide-react'

// Components
import { SignalBadge } from '../components/analysis/SignalBadge'
import { ReportCard } from '../components/analysis/ReportCard'
import { AnalysisControls } from '../components/analysis/AnalysisControls'
import { AnalysisLog } from '../components/analysis/AnalysisLog'
import { DebateHistoryWidget, getSenderStyles, parseDebateMessage } from '../components/analysis/DebateHistoryWidget'
import { AnalysisChatWidget } from '../components/analysis/AnalysisChatWidget'

interface WsEvent {
  type: string; section?: string; content?: string; signal?: string
  final_decision?: string; message?: string; duration_seconds?: number
  llm_calls?: number; status?: string; agent?: string; analysis_id?: number
  label?: string; stage?: string; node?: string
}
interface HistoryItem {
  id: number; ticker: string; trade_date: string; asset_type: string
  signal: string | null; duration_seconds: number; triggered_by: string; created_at: string
}
interface AnalysisDetail {
  id: number; ticker: string; trade_date: string; signal: string | null
  market_report: string; sentiment_report: string; news_report: string
  fundamentals_report: string; macro_report: string; options_report: string
  quant_report: string; earnings_report: string; review_report: string
  investment_plan: string; trader_plan: string; final_decision: string
  bull_history: string; bear_history: string; investment_debate_history: string
  risk_debate_history: string; judge_decision: string
  llm_calls: number; tokens_in: number; tokens_out: number; duration_seconds: number
}
interface PortfolioHistoryItem {
  id: number; tickers: string[]; trade_date: string; asset_type: string
  triggered_by: string; created_at: string
}
interface PortfolioDetail {
  id: number; tickers: string[]; trade_date: string
  super_portfolio_report: string; analysis_ids: number[]; created_at: string
}

const STORAGE_KEY = 'ta_last_run'
const TASK_KEY = 'ta_task_running'

const SECTION_LABELS: Record<string, string> = {
  market_report: 'Market', sentiment_report: 'Sentiment',
  news_report: 'News', fundamentals_report: 'Fundamentals',
  macro_report: 'Macro', options_report: 'Options',
  quant_report: 'Quant', earnings_report: 'Earnings',
  review_report: 'Review', investment_plan: 'Investment Plan',
  trader_investment_plan: 'Trader Plan', final_trade_decision: 'PM Decision',
  bull_history: 'Bull', bear_history: 'Bear',
  investment_debate_history: 'Debate', risk_debate_history: 'Risk Debate',
  judge_decision: 'Judge',
}

const EMPTY_RUN = {
  ticker: '', date: new Date().toISOString().slice(0, 10), assetType: 'stock',
  runStatus: 'idle' as 'idle' | 'running' | 'done' | 'error',
  signal: null as string | null, reports: {} as Record<string, string>,
  log: [] as string[], activeSection: null as string | null,
  analysisId: null as number | null,
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
  const [detail, setDetail] = useState<AnalysisDetail | null>(null)
  const [activeDetailTab, setActiveDetailTab] = useState<'reports' | 'debate' | 'chat'>('reports')
  const [leftTab, setLeftTab] = useState<'log' | 'debate'>('log')
  const [liveDebate, setLiveDebate] = useState<{ sender: string; content: string }[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const taskIdRef = useRef<string | null>(null)
  const preRefreshLogRef = useRef<string[] | null>(null)

  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? SECTION_LABELS
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]
  const [currentStep, setCurrentStep] = useState<{ label: string; stage: string } | null>(null)

  const [costEstimate, setCostEstimate] = useState<{ min_usd: number; max_usd: number } | null>(null)
  const [existingId, setExistingId] = useState<number | null>(null)
  const [showRerunModal, setShowRerunModal] = useState(false)

  const { activeTasks } = useActiveTasks()

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ticker, date, assetType, runStatus, signal, reports, log, activeSection, analysisId }))
  }, [ticker, date, assetType, runStatus, signal, reports, log, activeSection, analysisId])

  useEffect(() => {
    if (analysisId && runStatus === 'done' && !detail) {
      axios.get(`/api/analysis/${analysisId}`).then(r => setDetail(r.data)).catch(() => {})
    }
  }, [analysisId, runStatus, detail])

  const setRunning_ = (v: boolean) => {
    setRunning(v)
    if (!v) {
      localStorage.removeItem(TASK_KEY)
      taskIdRef.current = null
    }
  }

  const attachWs = useCallback((taskId: string, isReconnect = false) => {
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
      setLog(l => {
        if (l.length > 0 && l[l.length - 1] === line) {
          return l
        }
        return [...l, line]
      })
    }

    ws.onmessage = (e) => {
      const ev: WsEvent = JSON.parse(e.data)
      if (ev.type === 'status') {
        appendLog(`${ev.agent}`)
      } else if (ev.type === 'progress') {
        setCurrentStep({ label: ev.label || '', stage: ev.stage || '' })
        appendLog(`▸ ${ev.label}`)
      } else if (ev.type === 'report' && ev.section && ev.content) {
        setReports(r => ({ ...r, [ev.section!]: ev.content! }))
        setActiveSection(ev.section)
        appendLog(`✓ ${SECTION_LABELS[ev.section!] || ev.section}`)
      } else if (ev.type === 'debate_bubble' && ev.message) {
        const parsed = parseDebateMessage(ev.message)
        setLiveDebate(prev => [...prev, parsed])
      } else if (ev.type === 'decision') {
        setSignal(ev.signal || null)
      } else if (ev.type === 'complete') {
        finished = true
        setRunStatus('done')
        setRunning_(false)
        setCurrentStep(null)
        appendLog(`✓ Completed in ${ev.duration_seconds}s / ${ev.llm_calls} LLM calls`)
        sendBrowserNotification(
          `${ticker.toUpperCase()} Analysis Completed`,
          `Signal: ${ev.signal ?? 'N/A'} • Duration: ${ev.duration_seconds?.toFixed(0)}s`
        )
        if (ev.analysis_id) {
          setAnalysisId(ev.analysis_id)
          axios.get(`/api/analysis/${ev.analysis_id}`).then(r => setDetail(r.data)).catch(() => {})
        }
      } else if (ev.type === 'error') {
        finished = true
        setRunStatus('error')
        setRunning_(false)
        setCurrentStep(null)
        appendLog(`✗ Error: ${ev.message}`)
        notify('error', ev.message ?? t('analysis.ws.analysis_failed'), t('analysis.ws.analysis_error_title'))
      }
    }
    ws.onerror = () => {
      if (!finished) {
        setRunStatus('error'); setRunning_(false)
        setLog(l => [...l, t('analysis.ws.conn_error')])
        notify('error', t('analysis.ws.conn_error'), t('analysis.ws.analysis_error_title'))
      }
    }
    ws.onclose = () => {
      if (!finished) {
        if (isReconnect) {
          setRunStatus('idle')
          setRunning_(false)
          setLog(l => [...l, t('analysis.ws.conn_closed_reconnect')])
        } else {
          setRunStatus('error')
          setRunning_(false)
          setLog(l => [...l, t('analysis.ws.conn_closed')])
          notify('error', t('analysis.ws.conn_closed'), t('analysis.ws.analysis_interrupted'))
        }
      }
    }
  }, [ticker, t])

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
        setReports({})
        setSignal(null)
        setAnalysisId(null)
        setDetail(null)
        localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: task.ticker, taskId: task.task_id, startedAt: new Date(task.started_at * 1000).toISOString() }))
        attachWs(task.task_id, true)
    }
  }, [activeTasks, running, attachWs])

  useEffect(() => {
    const raw = localStorage.getItem(TASK_KEY)
    if (!raw) return
    try {
      const { taskId, ticker: runTicker } = JSON.parse(raw)
      if (!taskId) return
      preRefreshLogRef.current = [...saved.log]
      setRunning(true)
      setRunStatus('running')
      if (runTicker) setTicker(runTicker)
      attachWs(taskId, true)
    } catch { localStorage.removeItem(TASK_KEY) }
  }, [attachWs])

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        try {
          wsRef.current.onmessage = null
          wsRef.current.onerror = null
          wsRef.current.onclose = null
          wsRef.current.close()
        } catch {}
      }
    }
  }, [])

  useEffect(() => {
    if (!ticker.trim() || running) return
    const tid = setTimeout(async () => {
      try {
        const { data } = await axios.get('/api/analysis/cost-estimate', { params: { ticker: ticker.toUpperCase(), trade_date: date } })
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
        const match = data.find((x: HistoryItem) => x.ticker === ticker.toUpperCase() && x.trade_date === date)
        setExistingId(match?.id ?? null)
      } catch { setExistingId(null) }
    }, 400)
    return () => clearTimeout(tid)
  }, [ticker, date])

  const handleStop = async () => {
    const tid = taskIdRef.current
    wsRef.current?.close()
    wsRef.current = null
    setRunStatus('idle')
    setRunning_(false)
    setLog(l => [...l, t('analysis.ws.stopped')])
    if (tid) {
      try { await axios.post(`/api/analysis/${tid}/cancel`) } catch {  }
    }
  }

  const doRun = async () => {
    setShowRerunModal(false)
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
    preRefreshLogRef.current = null

    try {
      const { data } = await axios.post('/api/analysis/run', {
        ticker: ticker.toUpperCase(), trade_date: date, asset_type: assetType,
      })
      const taskId = data.task_id
      localStorage.setItem(TASK_KEY, JSON.stringify({ ticker: ticker.toUpperCase(), taskId, startedAt: new Date().toISOString() }))
      attachWs(taskId, false)
    } catch (err: any) {
      setRunStatus('error')
      setRunning_(false)
      setLog(l => [...l, `✗ ${err.response?.data?.detail || t('analysis.ws.failed_to_start')}`])
    }
  }

  const handleRun = () => {
    if (!ticker.trim()) return
    if (existingId) { setShowRerunModal(true); return }
    doRun()
  }

  const handleClear = () => {
    setRunStatus('idle'); setSignal(null); setReports({}); setLog([]); setActiveSection(null); setCurrentStep(null)
    setAnalysisId(null); setDetail(null); setLiveDebate([])
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

      {(log.length > 0 || reportEntries.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <AnalysisLog leftTab={leftTab} setLeftTab={setLeftTab} log={log} liveDebate={liveDebate} t={t} />

          <div className="lg:col-span-2 glass-panel rounded-2xl overflow-hidden flex flex-col h-[55vh] lg:h-[65vh]">
            {detail ? (
              <>
                <div className="flex items-center gap-1 p-1 bg-slate-900/40 border-b border-white/[0.04]">
                  <button onClick={() => setActiveDetailTab('reports')} className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${activeDetailTab === 'reports' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'}`}>{t('analysis.tab.reports')}</button>
                  <button onClick={() => setActiveDetailTab('debate')} className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${activeDetailTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'}`}>{t('analysis.tab.debate')}</button>
                  <button onClick={() => setActiveDetailTab('chat')} className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${activeDetailTab === 'chat' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'}`}>{t('analysis.tab.qa')}</button>
                </div>
                <div className="flex-1 p-4 overflow-y-auto min-h-0">
                  {activeDetailTab === 'reports' && (
                    <div className="space-y-2">
                      {reportEntries.map(([section, content]) => (
                        <ReportCard key={section} label={sectionLabels[section] || section} content={content} defaultOpen={section === activeSection} />
                      ))}
                    </div>
                  )}
                  {activeDetailTab === 'debate' && <DebateHistoryWidget investmentHistory={detail.investment_debate_history} riskHistory={detail.risk_debate_history} />}
                  {activeDetailTab === 'chat' && <AnalysisChatWidget analysisId={detail.id} />}
                </div>
              </>
            ) : (
              <>
                <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.04] bg-slate-900/20">
                  <FileText size={14} className="text-slate-400" />
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{t('analysis.reports.title')}</span>
                  <span className="ml-auto text-[10px] text-slate-600 font-semibold">{reportEntries.length} {t('analysis.reports.sections')}</span>
                </div>
                <div className="flex-1 p-4 overflow-y-auto min-h-0 space-y-2">
                  {reportEntries.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-16 text-slate-600">
                      <FileText size={28} className="opacity-25 mb-2" />
                      <p className="text-xs">{t('analysis.reports.empty')}</p>
                    </div>
                  )}
                  {reportEntries.map(([section, content]) => (
                    <ReportCard key={section} label={sectionLabels[section] || section} content={content} defaultOpen={section === activeSection} />
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}
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
  const meta = useMeta()
  const assetTypes = meta?.asset_types ?? [{ value: 'stock', label: 'Stock' }, { value: 'crypto', label: 'Crypto' }]

  const addTicker = () => {
    const tk = input.trim().toUpperCase()
    if (tk && !tickers.includes(tk) && tickers.length < 10) setTickers(prev => [...prev, tk])
    setInput('')
  }
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTicker() } }

  const handleRun = async () => {
    if (tickers.length < 2) return
    setRunning(true); setDone(false); setError(null)
    try {
      await axios.post('/api/analysis/run-portfolio', { tickers, trade_date: date, asset_type: assetType })
      setDone(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || t('analysis.multi.error_default'))
    } finally { setRunning(false) }
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

        {done && <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold"><CheckCircle size={14} /> {t('analysis.multi.started')}</div>}
        {error && <div className="flex items-center gap-2 text-rose-400 text-xs font-semibold"><AlertCircle size={14} /> {error}</div>}
      </div>
      <PortfolioHistorySection />
    </div>
  )
}

function PortfolioHistorySection() {
  const { t } = useTranslation()
  const [items, setItems] = useState<PortfolioHistoryItem[]>([])
  const [detail, setDetail] = useState<PortfolioDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get('/api/analysis/portfolio-history').then(r => setItems(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-slate-500 text-xs px-2">{t('analysis.portfolio_history.loading')}</div>

  return (
    <div className="glass-panel rounded-2xl p-5">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3.5">{t('analysis.portfolio_history.title')}</h3>
      {items.length === 0 ? <p className="text-slate-600 text-xs">{t('analysis.portfolio_history.empty')}</p> : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} onClick={() => axios.get(`/api/analysis/portfolio/${item.id}`).then(r => setDetail(r.data))}
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

function HistoryTab() {
  const { t } = useTranslation()
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<AnalysisDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeDetailTab, setActiveDetailTab] = useState<'reports' | 'debate' | 'chat'>('reports')
  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? SECTION_LABELS

  useEffect(() => {
    axios.get('/api/analysis/history?limit=50').then(r => setItems(r.data)).finally(() => setLoading(false))
  }, [])

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    setActiveDetailTab('reports')
    try { const { data } = await axios.get(`/api/analysis/${id}`); setDetail(data) }
    finally { setDetailLoading(false) }
  }, [])

  if (loading) return <div className="p-8 text-slate-500 text-xs">{t('analysis.history.loading')}</div>

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-slate-600 text-xs text-center">{t('analysis.history.empty')}</p>
        ) : (
          <div className="overflow-x-auto">
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
                    </div>
                    <p className="text-[10px] text-slate-500 font-semibold">{detail.trade_date} • {(detail.duration_seconds ?? 0).toFixed(1)}s • {detail.llm_calls} LLM • {(detail.tokens_in + detail.tokens_out).toLocaleString()} token</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => exportMarkdown(detail)} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_md')}>
                      <Download size={12} /> MD
                    </button>
                    <button onClick={() => exportPDF(detail)} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_pdf')}>
                      <FileDown size={12} /> PDF
                    </button>
                    <button onClick={() => setDetail(null)} className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5 cursor-pointer"><X size={16} /></button>
                  </div>
                </div>

                <div className="flex items-center gap-1 p-1 bg-slate-950/60 border border-white/[0.04] rounded-xl shrink-0">
                  <button
                    onClick={() => setActiveDetailTab('reports')}
                    className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'reports' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.reports')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('debate')}
                    className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.debate')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('chat')}
                    className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'chat' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.qa')}
                  </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto">
                  {activeDetailTab === 'reports' && (
                    <div className="space-y-2 pr-1">
                      {([
                        ['market_report', detail.market_report], ['sentiment_report', detail.sentiment_report],
                        ['news_report', detail.news_report], ['fundamentals_report', detail.fundamentals_report],
                        ['macro_report', detail.macro_report], ['options_report', detail.options_report],
                        ['quant_report', detail.quant_report], ['earnings_report', detail.earnings_report],
                        ['review_report', detail.review_report], ['investment_plan', detail.investment_plan],
                        ['trader_plan', detail.trader_plan], ['final_decision', detail.final_decision],
                        ['bull_history', detail.bull_history], ['bear_history', detail.bear_history],
                        ['judge_decision', detail.judge_decision],
                      ] as [string, string][]).map(([k, v]) => <ReportCard key={k} label={sectionLabels[k] || k} content={v} />)}
                    </div>
                  )}
                  {activeDetailTab === 'debate' && (
                    <DebateHistoryWidget investmentHistory={detail.investment_debate_history} riskHistory={detail.risk_debate_history} />
                  )}
                  {activeDetailTab === 'chat' && (
                    <AnalysisChatWidget analysisId={detail.id} />
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
  const [tab, setTab] = useState<Tab>('run')

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
      {tab === 'history' && <HistoryTab />}
    </div>
  )
}
