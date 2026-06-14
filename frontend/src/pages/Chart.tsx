import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../utils/api'
import { RefreshCw, BarChart2, AlertCircle, Sparkles, ScanSearch, TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { usePriceChart } from '../hooks/usePriceChart'
import { ErrorBoundary } from '../components/ErrorBoundary'

// Components
import { ChartSearch } from '../components/chart/ChartSearch'
import { TechnicalControls } from '../components/chart/TechnicalControls'
import { CustomIndicatorPane } from '../components/chart/CustomIndicatorPane'
import { AnalysisDetailSidebar } from '../components/chart/AnalysisDetailSidebar'

interface Candle {
  time: string; open: number; high: number; low: number; close: number; volume: number
  sma?: number | null; ema?: number | null; rsi?: number | null
  macd_line?: number | null; macd_signal?: number | null; macd_hist?: number | null
}
interface AnalysisItem {
  id: number; ticker: string; trade_date: string; signal: string | null; chart_annotations: string; final_decision?: string; created_at: string
}
interface PatternKeyPoint { date: string; price: number; label: string }
interface Pattern {
  type: string
  label: string
  direction: 'bullish' | 'bearish'
  start_date: string
  end_date: string
  key_points: PatternKeyPoint[]
  confidence: number
}

const PERIODS = [
  { label: '1M', value: '1m' }, { label: '3M', value: '3m' },
  { label: '6M', value: '6m' }, { label: '1Y', value: '1y' }, { label: '2Y', value: '2y' },
]

export default function ChartPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useTranslation()

  const [tickerInput, setTickerInput] = useState(searchParams.get('ticker') ?? '')
  const [activeTicker, setActiveTicker] = useState(searchParams.get('ticker') ?? '')
  const [period, setPeriod] = useState(searchParams.get('period') ?? '1y')
  const [candles, setCandles] = useState<Candle[]>([])
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([])
  const [selected, setSelected] = useState<AnalysisItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [showSMA, setShowSMA] = useState(false)
  const [showEMA, setShowEMA] = useState(false)
  const [showRSI, setShowRSI] = useState(false)
  const [showMACD, setShowMACD] = useState(false)
  const [showSentiment, setShowSentiment] = useState(false)
  const [sentimentHistory, setSentimentHistory] = useState<{ time: string; value: number }[]>([])
  const [customIndicators, setCustomIndicators] = useState<any[]>([])
  const [userFormula, setUserFormula] = useState('')
  const [userIndicatorData, setUserIndicatorData] = useState<{ time: string; value: number | null }[]>([])
  const [userIndicatorLabel, setUserIndicatorLabel] = useState('')
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [showPatterns, setShowPatterns] = useState(false)
  const [patterns, setPatterns] = useState<Pattern[]>([])
  const [patternsLoading, setPatternsLoading] = useState(false)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  usePriceChart(chartContainerRef as React.RefObject<HTMLDivElement>, candles, analyses, showSMA, showEMA)

  // Monotonic request id so that if loads overlap (e.g. rapid period switches),
  // only the most recent one's result is applied — out-of-order responses for a
  // stale ticker/period are ignored.
  const loadReqId = useRef(0)

  const load = useCallback(async (ticker: string, p: string) => {
    if (!ticker) return
    const reqId = ++loadReqId.current
    setLoading(true); setError(null); setSelected(null); setCustomIndicators([]); setUserIndicatorData([]); setUserIndicatorLabel('')
    try {
      const [ohlcvRes, histRes, sentRes] = await Promise.all([
        api.get('/api/market/ohlcv', { params: { ticker, period: p } }),
        api.get('/api/analysis/history', { params: { ticker, limit: 200 } }),
        api.get('/api/market/sentiment-history', { params: { ticker } }),
      ])
      if (reqId !== loadReqId.current) return
      // Backend can return partial/empty payloads on thin data; guard each field.
      setCandles(ohlcvRes.data?.candles ?? [])
      setAnalyses(Array.isArray(histRes.data) ? histRes.data : [])
      setSentimentHistory(sentRes.data?.history ?? [])
    } catch (e) {
      if (reqId !== loadReqId.current) return
      setError(((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail) ?? t('chart.error_load'))
    } finally {
      if (reqId === loadReqId.current) setLoading(false)
    }
  }, [t])

  useEffect(() => { if (activeTicker) load(activeTicker, period) }, [])

  const handleSearch = () => {
    const tk = tickerInput.trim().toUpperCase()
    if (!tk) return
    setActiveTicker(tk); setSearchParams({ ticker: tk, period }); load(tk, period)
  }

  const handlePeriod = (p: string) => {
    setPeriod(p); setSearchParams({ ticker: activeTicker, period: p })
    if (activeTicker) load(activeTicker, p)
  }

  const calculateIndicator = async (formula: string) => {
    if (!formula.trim() || !activeTicker) return
    setLoading(true); setError(null)
    try {
      const res = await api.get('/api/market/custom-indicator', { params: { ticker: activeTicker, period, formula: formula.trim() } })
      setUserIndicatorData(res.data?.series ?? []); setUserIndicatorLabel(formula.trim())
    } catch (err) {
      // Surface the failure (e.g. invalid formula) instead of silently clearing.
      setUserIndicatorData([]); setUserIndicatorLabel('')
      setError(((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail) ?? t('chart.error_load'))
    } finally { setLoading(false) }
  }

  const handleCalculateUserIndicator = () => calculateIndicator(userFormula)

  // Describe the indicator in plain language; the backend LLM writes a
  // validated formula, which we drop into the formula box and plot directly.
  const fetchPatterns = useCallback(async (ticker: string, p: string) => {
    setPatternsLoading(true)
    try {
      const r = await api.get(`/api/market/patterns/${ticker}`, { params: { period: p } })
      setPatterns(r.data.patterns || [])
    } catch {
      setPatterns([])
    } finally {
      setPatternsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (showPatterns && activeTicker) fetchPatterns(activeTicker, period)
    else setPatterns([])
  }, [showPatterns, activeTicker, period, fetchPatterns])

  const handleAiFormula = async () => {
    if (!aiPrompt.trim() || aiLoading) return
    setAiLoading(true); setError(null)
    try {
      const res = await api.post('/api/market/formula-assist', { prompt: aiPrompt.trim() })
      const formula: string = res.data?.formula ?? ''
      setUserFormula(formula)
      await calculateIndicator(formula)
    } catch (err) {
      setError(((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail) ?? t('chart.error_load'))
    } finally { setAiLoading(false) }
  }

  const sentimentChartData = useMemo(() => {
    if (!candles.length) return []
    const sentMap = new Map(sentimentHistory.map(item => [item.time, item.value]))
    let lastSent = 0.0
    return candles.map(c => {
      const dbSent = sentMap.get(c.time)
      const sentimentVal = dbSent !== undefined ? dbSent : lastSent
      if (dbSent !== undefined) lastSent = dbSent
      return { time: c.time, value: sentimentVal }
    })
  }, [candles, sentimentHistory])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="glass-panel rounded-3xl overflow-hidden border border-white/[0.04] shadow-2xl">
        <ChartSearch 
            tickerInput={tickerInput} setTickerInput={setTickerInput} 
            period={period} handlePeriod={handlePeriod} periods={PERIODS} 
            loading={loading} handleSearch={handleSearch} t={t} 
        />

        <div className="grid grid-cols-1 lg:grid-cols-4 min-h-[500px]">
          <div className={`${selected ? 'lg:col-span-3' : 'lg:col-span-4'} p-4 md:p-6 transition-all duration-500`}>
            {error && (
              <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/20 rounded-2xl flex items-center gap-3 text-rose-400 text-sm animate-in fade-in slide-in-from-top-2">
                <AlertCircle size={18} /> {error}
              </div>
            )}

            {!activeTicker && !loading && (
              <div className="h-[420px] flex flex-col items-center justify-center text-slate-600 space-y-4 opacity-40">
                <BarChart2 size={64} strokeWidth={1} />
                <p className="text-sm font-medium uppercase tracking-widest">{t('chart.search_prompt')}</p>
              </div>
            )}

            <div className={activeTicker ? 'space-y-4' : 'hidden'}>
              <div className="flex items-center justify-between px-1">
                  <div className="flex items-center gap-4">
                      <h2 className="text-2xl font-display font-bold text-white tracking-tight font-mono">{activeTicker}</h2>
                      {candles.length > 0 && (
                          <span className={`text-sm font-mono font-bold ${candles[candles.length-1].close >= candles[candles.length-1].open ? 'text-emerald-400' : 'text-rose-400'}`}>
                              ${candles[candles.length-1].close.toFixed(2)}
                          </span>
                      )}
                  </div>
                  <div className="flex items-center gap-2">
                    <TechnicalControls
                        showSMA={showSMA} setShowSMA={setShowSMA}
                        showEMA={showEMA} setShowEMA={setShowEMA}
                        showRSI={showRSI} setShowRSI={setShowRSI}
                        showMACD={showMACD} setShowMACD={setShowMACD}
                        showSentiment={showSentiment} setShowSentiment={setShowSentiment}
                        t={t}
                    />
                    <button
                      onClick={() => setShowPatterns(v => !v)}
                      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold border transition cursor-pointer ${
                        showPatterns
                          ? 'bg-violet-600/20 border-violet-500/40 text-violet-300'
                          : 'bg-white/[0.03] border-white/[0.06] text-slate-500 hover:text-slate-300'
                      }`}
                    >
                      <ScanSearch size={11} />
                      Patterns
                    </button>
                  </div>
              </div>

              <ErrorBoundary name="Price Chart">
                  <div ref={chartContainerRef} className="w-full h-[420px] rounded-2xl overflow-hidden border border-white/[0.04] bg-[#090d16]" />
              </ErrorBoundary>

              <div className="flex items-center gap-3 pt-2">
                <div className="flex-1 relative group">
                  <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-violet-400 transition-colors" size={14} />
                  <input
                    className="glass-input pl-10 pr-4 py-2.5 w-full rounded-xl text-xs placeholder-slate-600 outline-none transition-all"
                    placeholder={t('chart.ai_formula_placeholder')}
                    value={aiPrompt}
                    onChange={e => setAiPrompt(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAiFormula()}
                  />
                </div>
                <button
                  onClick={handleAiFormula}
                  disabled={aiLoading}
                  className="bg-violet-600/20 hover:bg-violet-600/30 disabled:opacity-50 text-violet-300 px-5 py-2.5 rounded-xl text-xs font-bold transition-all border border-violet-500/20 cursor-pointer flex items-center gap-2"
                >
                  <Sparkles size={12} /> {aiLoading ? t('chart.ai_generating') : t('chart.ai_generate')}
                </button>
              </div>

              <div className="flex items-center gap-3">
                <div className="flex-1 relative group">
                  <BarChart2 className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-violet-400 transition-colors" size={14} />
                  <input
                    className="glass-input pl-10 pr-4 py-2.5 w-full rounded-xl text-xs font-mono placeholder-slate-600 outline-none transition-all"
                    placeholder="Custom Formula (e.g. SMA(20) / Close)"
                    value={userFormula}
                    onChange={e => setUserFormula(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCalculateUserIndicator()}
                  />
                </div>
                <button
                  onClick={handleCalculateUserIndicator}
                  className="bg-white/5 hover:bg-white/10 text-slate-300 px-5 py-2.5 rounded-xl text-xs font-bold transition-all border border-white/[0.04] cursor-pointer"
                >
                  Calculate
                </button>
              </div>

              {/* Pattern Detection Panel */}
              {showPatterns && (
                <div className="rounded-2xl bg-white/[0.02] border border-white/[0.05] p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <ScanSearch size={13} className="text-violet-400" />
                    <span className="text-xs font-bold text-white">Detected Patterns</span>
                    {patternsLoading && <Loader2 size={11} className="animate-spin text-violet-400 ml-1" />}
                    {!patternsLoading && <span className="text-[10px] text-slate-600">· {patterns.length} found in {period} history</span>}
                  </div>

                  {!patternsLoading && patterns.length === 0 && (
                    <p className="text-[10px] text-slate-600 italic">No significant patterns detected for this period.</p>
                  )}

                  {patterns.length > 0 && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {patterns.map((p, i) => (
                        <div
                          key={i}
                          className={`rounded-xl border p-3 space-y-2 ${
                            p.direction === 'bullish'
                              ? 'bg-emerald-500/5 border-emerald-500/20'
                              : 'bg-rose-500/5 border-rose-500/20'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5">
                              {p.direction === 'bullish'
                                ? <TrendingUp size={11} className="text-emerald-400" />
                                : <TrendingDown size={11} className="text-rose-400" />
                              }
                              <span className="text-[10px] font-bold text-white">{p.label}</span>
                            </div>
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border ${
                              p.direction === 'bullish'
                                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                                : 'text-rose-400 bg-rose-500/10 border-rose-500/20'
                            }`}>
                              {p.direction === 'bullish' ? 'Bullish' : 'Bearish'}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 text-[9px] text-slate-500 font-mono">
                            <span>{p.start_date}</span>
                            <span>→</span>
                            <span>{p.end_date}</span>
                          </div>

                          <div className="flex flex-wrap gap-1">
                            {p.key_points.map((kp, j) => (
                              <span key={j} className="text-[8px] font-mono bg-white/[0.04] border border-white/[0.06] rounded px-1.5 py-0.5 text-slate-400">
                                {kp.label}: ${kp.price.toFixed(2)}
                              </span>
                            ))}
                          </div>

                          <div className="flex items-center gap-1.5">
                            <div className="flex-1 h-0.5 rounded-full bg-white/[0.04]">
                              <div
                                className={`h-full rounded-full ${p.direction === 'bullish' ? 'bg-emerald-500' : 'bg-rose-500'}`}
                                style={{ width: `${p.confidence * 100}%` }}
                              />
                            </div>
                            <span className="text-[9px] font-mono text-slate-600">{(p.confidence * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <AnalysisDetailSidebar selected={selected} setSelected={setSelected} t={t} />
        </div>
      </div>

      <ErrorBoundary name="Custom Indicators">
        <CustomIndicatorPane 
            showRSI={showRSI} showMACD={showMACD} showSentiment={showSentiment}
            candles={candles} sentimentChartData={sentimentChartData}
            customIndicators={customIndicators}
            userIndicatorData={userIndicatorData} userIndicatorLabel={userIndicatorLabel}
        />
      </ErrorBoundary>
      
      {analyses.length > 0 && !selected && (
        <div className="glass-panel rounded-3xl p-6">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-6 flex items-center gap-2">
                <RefreshCw size={14} className="text-violet-400" /> Recent AI Analyses for {activeTicker}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {analyses.slice(0, 8).map(a => (
                    <div key={a.id} onClick={() => setSelected(a)} className="p-4 rounded-2xl bg-slate-900/40 border border-white/[0.04] hover:border-violet-500/30 cursor-pointer transition-all hover:bg-slate-900/60 group">
                        <div className="flex items-center justify-between mb-3">
                            <span className="text-[10px] font-mono font-bold text-slate-500 group-hover:text-slate-300 transition-colors">{a.trade_date}</span>
                            {a.signal && <span className={`w-2 h-2 rounded-full ${['Buy', 'Overweight'].includes(a.signal) ? 'bg-emerald-500' : 'bg-rose-500'}`} />}
                        </div>
                        <p className="text-xs font-bold text-white truncate mb-1">{a.signal || 'Neutral'}</p>
                        <p className="text-[10px] text-slate-500 line-clamp-2 leading-relaxed italic">{a.final_decision}</p>
                    </div>
                ))}
            </div>
        </div>
      )}
    </div>
  )
}
