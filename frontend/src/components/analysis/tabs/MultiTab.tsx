import { PortfolioHistorySection } from './PortfolioHistorySection'
import type { AnalysisStartError } from '../AnalysisControls'
import { WS_MAX_RECONNECT_RETRIES, closeAnalysisWebSocket, openAnalysisWebSocket, probeActiveTask } from '../../../analysis/analysisSocket'
import { analysisStartError } from '../../../analysis/startError'
import { useAnalysisCancelAnalysis, useAnalysisRunPortfolioRun } from '../../../api/generated/analysis/analysis'
import { getAccessToken } from '../../../contexts/AuthContext'
import { useTranslation } from '../../../contexts/LanguageContext'
import { useMeta } from '../../../hooks/useMeta'
import { isRecord } from '../../../utils/isRecord'
import { AlertCircle, BarChart2, CheckCircle, Loader2, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

export function MultiTab() {
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
