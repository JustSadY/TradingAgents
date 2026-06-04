import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import axios from 'axios'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
} from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import { Search, RefreshCw, BarChart2 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  ReferenceLine, Bar, Cell, ComposedChart, CartesianGrid
} from 'recharts'

interface Candle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  sma?: number | null
  ema?: number | null
  rsi?: number | null
  macd_line?: number | null
  macd_signal?: number | null
  macd_hist?: number | null
}

interface KeyLevel { price: number; label: string; type: string }

interface ChartAnnotations {
  support_levels?: number[]
  resistance_levels?: number[]
  target_price?: number | null
  stop_loss?: number | null
  key_levels?: KeyLevel[]
  custom_indicators?: any[]
  annotations?: any[]
}

interface AnalysisItem {
  id: number
  ticker: string
  trade_date: string
  signal: string | null
  chart_annotations: string
  created_at: string
}

function parseAnnotations(raw: string): ChartAnnotations {
  try { return raw ? JSON.parse(raw) : {} } catch { return {} }
}

const SIGNAL_COLOR: Record<string, string> = {
  Buy: '#10b981',
  Overweight: '#10b981',
  Hold: '#f59e0b',
  Neutral: '#f59e0b',
  Sell: '#ef4444',
  Underweight: '#ef4444',
}

const PERIODS = [
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '6M', value: '6m' },
  { label: '1Y', value: '1y' },
  { label: '2Y', value: '2y' },
]

export default function ChartPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useTranslation()

  const [tickerInput, setTickerInput] = useState(searchParams.get('ticker') ?? '')
  const [activeTicker, setActiveTicker] = useState(searchParams.get('ticker') ?? '')
  const [period, setPeriod] = useState(searchParams.get('period') ?? '1y')
  const [candles, setCandles] = useState<Candle[]>([])
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([])
  const analysesInRange = useMemo(() => analyses, [analyses])
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

  const smaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)
  const trendlineSeriesRefs = useRef<any[]>([])
  const overlaySeriesRefs = useRef<any[]>([])

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick', any> | null>(null)
  const volSeriesRef = useRef<ISeriesApi<'Histogram', any> | null>(null)
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers> | null>(null)
  const priceLineRefs = useRef<any[]>([])
  const tRef = useRef(t)
  useEffect(() => { tRef.current = t })

  useEffect(() => {
    if (!activeTicker) return
    const ann = selected ? parseAnnotations(selected.chart_annotations) : {}
    
    const fetchCustom = async () => {
      if (ann.custom_indicators && Array.isArray(ann.custom_indicators)) {
        const list: any[] = []
        for (const ci of ann.custom_indicators) {
          if (ci.overlay) continue
          try {
            const res = await axios.get('/api/market/custom-indicator', {
              params: { ticker: activeTicker, period, formula: ci.formula }
            })
            list.push({
              name: ci.name,
              label: ci.label || ci.name,
              formula: ci.formula,
              data: res.data.series,
            })
          } catch (err) {
            console.error("Custom indicator fetch failed", err)
          }
        }
        setCustomIndicators(list)
      } else {
        setCustomIndicators([])
      }
    }
    fetchCustom()
  }, [selected, activeTicker, period])

  const load = useCallback(async (ticker: string, p: string) => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    setSelected(null)
    setCustomIndicators([])
    setUserIndicatorData([])
    setUserIndicatorLabel('')
    try {
      const [ohlcvRes, histRes, sentRes] = await Promise.all([
        axios.get('/api/market/ohlcv', { params: { ticker, period: p } }),
        axios.get('/api/analysis/history', { params: { ticker, limit: 200 } }),
        axios.get('/api/market/sentiment-history', { params: { ticker } }),
      ])
      setCandles(ohlcvRes.data.candles)
      setAnalyses(histRes.data)
      setSentimentHistory(sentRes.data.history)
    } catch (e: any) {
      setError(e.response?.data?.detail ?? tRef.current('chart.error_load'))
    } finally {
      setLoading(false)
    }
  }, [])

  const handleSearch = () => {
    const tk = tickerInput.trim().toUpperCase()
    if (!tk) return
    setActiveTicker(tk)
    setSearchParams({ ticker: tk, period })
    load(tk, period)
  }

  const handlePeriod = (p: string) => {
    setPeriod(p)
    setSearchParams({ ticker: activeTicker, period: p })
    if (activeTicker) load(activeTicker, p)
  }

  const handleCalculateUserIndicator = async () => {
    if (!userFormula.trim() || !activeTicker) return
    setLoading(true)
    setError(null)
    try {
      const res = await axios.get('/api/market/custom-indicator', {
        params: { ticker: activeTicker, period, formula: userFormula.trim() }
      })
      setUserIndicatorData(res.data.series)
      setUserIndicatorLabel(userFormula.trim())
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Failed to calculate dynamic custom formula.")
      setUserIndicatorData([])
      setUserIndicatorLabel('')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (activeTicker) load(activeTicker, period)
  }, [])

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: 'rgba(255,255,255,0.02)' },
        horzLines: { color: 'rgba(255,255,255,0.02)' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.06)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.06)', timeVisible: true },
      width: chartContainerRef.current.clientWidth,
      height: 420,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
      priceScaleId: 'right',
    })

    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#1f2937',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    chart.priceScale('right').applyOptions({
      scaleMargins: { top: 0.05, bottom: 0.2 },
    })

    const smaSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      priceScaleId: 'right',
    })
    const emaSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
      priceScaleId: 'right',
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volSeriesRef.current = volSeries
    smaSeriesRef.current = smaSeries
    emaSeriesRef.current = emaSeries

    const applyWidth = () => {
      const w = chartContainerRef.current?.clientWidth ?? 0
      if (w > 0) chart.applyOptions({ width: w })
    }
    window.addEventListener('resize', applyWidth)

    let ro: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined' && chartContainerRef.current) {
      ro = new ResizeObserver(applyWidth)
      ro.observe(chartContainerRef.current)
    }
    applyWidth()

    return () => {
      window.removeEventListener('resize', applyWidth)
      ro?.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volSeriesRef.current = null
      smaSeriesRef.current = null
      emaSeriesRef.current = null
      markersRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current || candles.length === 0) return

    candleSeriesRef.current.setData(candles.map(c => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    })))

    volSeriesRef.current.setData(candles.map(c => ({
      time: c.time as any,
      value: c.volume,
      color: c.close >= c.open ? '#10b98125' : '#ef444425',
    })))

    if (smaSeriesRef.current) {
      if (showSMA) {
        smaSeriesRef.current.setData(
          candles
            .filter(c => c.sma !== null && c.sma !== undefined)
            .map(c => ({
              time: c.time as any,
              value: c.sma as number,
            }))
        )
      } else {
        smaSeriesRef.current.setData([])
      }
    }

    if (emaSeriesRef.current) {
      if (showEMA) {
        emaSeriesRef.current.setData(
          candles
            .filter(c => c.ema !== null && c.ema !== undefined)
            .map(c => ({
              time: c.time as any,
              value: c.ema as number,
            }))
        )
      } else {
        emaSeriesRef.current.setData([])
      }
    }

    priceLineRefs.current.forEach(pl => {
      try { candleSeriesRef.current?.removePriceLine(pl) } catch {  }
    })
    priceLineRefs.current = []

    trendlineSeriesRefs.current.forEach(ts => {
      try { chartRef.current?.removeSeries(ts) } catch { }
    })
    trendlineSeriesRefs.current = []

    overlaySeriesRefs.current.forEach(os => {
      try { chartRef.current?.removeSeries(os) } catch { }
    })
    overlaySeriesRefs.current = []

    const tradeDatesInRange = new Set(candles.map(c => c.time))

    analyses.forEach(a => {
      if (!tradeDatesInRange.has(a.trade_date)) return
      const ann = parseAnnotations(a.chart_annotations)

      ;(ann.support_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      })
      ;(ann.resistance_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: 'rgba(59, 130, 246, 0.4)', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      })
      if (ann.target_price) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.target_price, color: 'rgba(16, 185, 129, 0.7)', lineWidth: 2, lineStyle: 3,
            axisLabelVisible: true, title: 'Target',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      }
      if (ann.stop_loss) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.stop_loss, color: 'rgba(239, 68, 68, 0.7)', lineWidth: 2, lineStyle: 3,
            axisLabelVisible: true, title: 'Stop Loss',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      }

      if (ann.annotations && Array.isArray(ann.annotations)) {
        ann.annotations.forEach((va: any) => {
          if (va.type === 'trendline' && va.time && va.price && va.time2 && va.price2) {
            try {
              const tl = chartRef.current!.addSeries(LineSeries, {
                color: '#f59e0b',
                lineWidth: 2,
                lineStyle: 2,
                title: va.text || 'Trendline',
              })
              tl.setData([
                { time: va.time, value: va.price },
                { time: va.time2, value: va.price2 }
              ])
              trendlineSeriesRefs.current.push(tl)
            } catch (e) {
              console.error("Trendline draw failed", e)
            }
          }
        })
      }

      if (ann.custom_indicators && Array.isArray(ann.custom_indicators)) {
        ann.custom_indicators.forEach((ci: any) => {
          if (ci.overlay && ci.values) {
            try {
              const ol = chartRef.current!.addSeries(LineSeries, {
                color: '#06b6d4',
                lineWidth: 2,
                title: ci.label || ci.name,
              })
              const dataPoints = Object.entries(ci.values)
                .map(([time, value]) => ({ time: time as any, value: value as number }))
                .sort((a, b) => a.time.localeCompare(b.time))
              ol.setData(dataPoints)
              overlaySeriesRefs.current.push(ol)
            } catch (e) {
              console.error("Overlay draw failed", e)
            }
          }
        })
      }
    })

    if (markersRef.current) {
      try { markersRef.current.setMarkers([]) } catch {  }
    }
    
    const markerData = analyses
      .filter(a => a.signal && tradeDatesInRange.has(a.trade_date))
      .map(a => ({
        time: a.trade_date as any,
        position: (['Buy', 'Overweight'].includes(a.signal!) ? 'belowBar' : 'aboveBar') as any,
        color: SIGNAL_COLOR[a.signal!] ?? '#6b7280',
        shape: (['Buy', 'Overweight'].includes(a.signal!) ? 'arrowUp' : ['Sell', 'Underweight'].includes(a.signal!) ? 'arrowDown' : 'circle') as any,
        text: a.signal!,
        size: 1.2,
      }))

    const visualMarkers: any[] = []
    analyses.forEach(a => {
      if (!tradeDatesInRange.has(a.trade_date)) return
      const ann = parseAnnotations(a.chart_annotations)
      if (ann.annotations && Array.isArray(ann.annotations)) {
        ann.annotations.forEach((va: any) => {
          if (va.type === 'arrowUp' || va.type === 'arrowDown' || va.type === 'circle') {
            visualMarkers.push({
              time: va.time,
              position: va.type === 'arrowUp' ? 'belowBar' : 'aboveBar',
              color: va.type === 'arrowUp' ? '#10b981' : va.type === 'arrowDown' ? '#ef4444' : '#f59e0b',
              shape: va.type,
              text: va.text || '',
              size: 1.5,
            })
          }
        })
      }
    })

    const combinedMarkers = [...markerData, ...visualMarkers].sort((a, b) => 
      (a.time as string).localeCompare(b.time as string)
    )

    try {
      if (!markersRef.current) {
        markersRef.current = createSeriesMarkers(candleSeriesRef.current as any, combinedMarkers)
      } else {
        markersRef.current.setMarkers(combinedMarkers)
      }
    } catch {  }

    chartRef.current?.timeScale().fitContent()
  }, [candles, analyses, showSMA, showEMA])

  const sentimentChartData = useMemo(() => {
    if (!candles.length) return []
    const sentMap = new Map(sentimentHistory.map(item => [item.time, item.value]))
    let lastSent = 0.0
    return candles.map(c => {
      const dbSent = sentMap.get(c.time)
      const sentimentVal = dbSent !== undefined ? dbSent : lastSent
      if (dbSent !== undefined) {
        lastSent = dbSent
      }
      return {
        time: c.time,
        price: c.close,
        sentiment: sentimentVal,
      }
    })
  }, [candles, sentimentHistory])

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('chart.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Visualize historical candles overlaid with AI target levels, trendlines, and breakout models</p>
        </div>
      </div>

      {/* Control Block */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2 bg-slate-900 border border-white/[0.08] rounded-xl px-3 py-2 flex-1 max-w-xs focus-within:border-violet-500/50 transition-colors">
          <Search size={15} className="text-slate-500" />
          <input
            className="bg-transparent text-white text-xs outline-none flex-1 uppercase font-semibold"
            placeholder="AAPL, TSLA, BTC-USD..."
            value={tickerInput}
            onChange={e => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <button
          onClick={handleSearch}
          className="bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold px-4 py-2 rounded-xl transition cursor-pointer"
        >
          {t('chart.show_button')}
        </button>

        {activeTicker && (
          <div className="flex gap-1 bg-slate-900 border border-white/[0.04] p-0.5 rounded-xl">
            {PERIODS.map(p => (
              <button
                key={p.value}
                onClick={() => handlePeriod(p.value)}
                className={`px-3 py-1.5 text-[10px] font-bold rounded-lg transition-all cursor-pointer ${
                  period === p.value
                    ? 'bg-violet-600 text-white'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}

        {loading && <RefreshCw size={14} className="text-violet-400 animate-spin" />}
      </div>

      {/* Indicator Selection Grid */}
      {activeTicker && (
        <div className="flex flex-wrap items-center gap-4 bg-slate-900/40 border border-white/[0.04] px-4 py-3 rounded-2xl">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mr-2">{t('chart.indicators')}:</span>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSMA}
              onChange={e => setShowSMA(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            SMA (20)
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showEMA}
              onChange={e => setShowEMA(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            EMA (20)
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showRSI}
              onChange={e => setShowRSI(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            RSI (14)
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showMACD}
              onChange={e => setShowMACD(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            MACD
          </label>
          <label className="flex items-center gap-2 text-xs font-medium text-slate-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSentiment}
              onChange={e => setShowSentiment(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            {t('chart.social_sentiment')}
          </label>
          
          <div className="flex items-center gap-2 bg-slate-950/80 border border-white/[0.04] rounded-xl px-2.5 py-1.5 ml-auto w-full sm:w-auto max-w-sm">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('chart.custom_formula')}:</span>
            <input
              className="bg-transparent text-white text-xs outline-none flex-1 font-mono placeholder-slate-700 min-w-[150px]"
              placeholder="e.g., (Close - SMA(20)) / STD(20)"
              value={userFormula}
              onChange={e => setUserFormula(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCalculateUserIndicator()}
            />
            <button
              onClick={handleCalculateUserIndicator}
              className="bg-violet-600 hover:bg-violet-500 text-white text-[10px] font-bold px-2.5 py-1 rounded-lg transition cursor-pointer"
            >
              {t('chart.calculate')}
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-rose-950/20 border border-rose-500/20 text-rose-300 text-xs rounded-xl px-4 py-3">
          {error}
        </div>
      )}

      {/* Main Charts & History list */}
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 min-w-0 space-y-4">
          <div className="glass-panel rounded-2xl overflow-hidden bg-[#090d16]">
            {activeTicker && (
              <div className="px-5 py-3 border-b border-white/[0.04] flex items-center gap-3 bg-slate-950/20">
                <span className="text-white font-mono font-bold text-sm uppercase">{activeTicker}</span>
                {candles.length > 0 && (
                  <span className="text-slate-400 font-mono text-xs">
                    ${candles[candles.length - 1].close.toLocaleString(undefined, { minimumFractionDigits: 2 })} USD
                  </span>
                )}
              </div>
            )}
            <div ref={chartContainerRef} className="w-full" />
            {!activeTicker && (
              <div className="flex flex-col items-center justify-center h-[420px] text-slate-600 bg-[#090d16]">
                <BarChart2 size={36} className="mb-2 opacity-20" />
                <p className="text-xs font-semibold">{t('chart.empty_hint')}</p>
                <p className="text-[10px] mt-1 opacity-50">{t('chart.empty_hint_sub')}</p>
              </div>
            )}
          </div>

          {activeTicker && (
            <div className="flex flex-wrap gap-x-4 gap-y-1.5 px-1 text-[10px] text-slate-500 font-semibold bg-white/[0.01] border border-white/[0.03] p-2 rounded-xl">
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 h-0 border-t border-rose-500 border-dashed" /> {t('chart.legend_support')}</span>
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 h-0 border-t border-blue-500 border-dashed" /> {t('chart.legend_resistance')}</span>
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 h-0 border-t border-emerald-500" /> {t('chart.legend_target')}</span>
              <span className="flex items-center gap-1.5"><span className="inline-block w-4 h-0 border-t border-rose-500" /> {t('chart.legend_stop_loss')}</span>
              <span className="flex items-center gap-1.5 text-emerald-400">▲ {t('chart.legend_buy')} Signal</span>
              <span className="flex items-center gap-1.5 text-rose-400">▼ {t('chart.legend_sell')} Signal</span>
            </div>
          )}

          {/* RSI subplot */}
          {showRSI && candles.length > 0 && (
            <div className="glass-panel rounded-2xl p-5">
              <h3 className="text-[10px] font-bold text-violet-400 uppercase tracking-widest mb-3">RSI (14)</h3>
              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={candles} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis domain={[0, 100]} stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} ticks={[30, 50, 70]} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                      labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                      itemStyle={{ color: '#a855f7' }}
                    />
                    <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'OB (70)', fill: '#ef4444', fontSize: 8, position: 'insideTopLeft' }} />
                    <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" label={{ value: 'OS (30)', fill: '#10b981', fontSize: 8, position: 'insideBottomLeft' }} />
                    <Line
                      type="monotone"
                      dataKey="rsi"
                      stroke="#a855f7"
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* MACD subplot */}
          {showMACD && candles.length > 0 && (
            <div className="glass-panel rounded-2xl p-5">
              <h3 className="text-[10px] font-bold text-violet-400 uppercase tracking-widest mb-3">MACD (12, 26, 9)</h3>
              <div className="h-40 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={candles} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                      labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                    />
                    <Bar dataKey="macd_hist" name="Histogram">
                      {candles.map((entry, index) => {
                        const val = entry.macd_hist ?? 0
                        return (
                          <Cell
                            key={`cell-${index}`}
                            fill={val >= 0 ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)'}
                          />
                        )
                      })}
                    </Bar>
                    <Line
                      type="monotone"
                      dataKey="macd_line"
                      stroke="#3b82f6"
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                      name="MACD"
                    />
                    <Line
                      type="monotone"
                      dataKey="macd_signal"
                      stroke="#f59e0b"
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                      name="Signal"
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Social Sentiment Subplot */}
          {showSentiment && sentimentChartData.length > 0 && (
            <div className="glass-panel rounded-2xl p-5">
              <h3 className="text-[10px] font-bold text-violet-400 uppercase tracking-widest mb-3">{t('chart.sentiment_correlation')}</h3>
              <div className="h-44 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={sentimentChartData} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis yAxisId="left" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis yAxisId="right" orientation="right" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} domain={[-1, 1]} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                      labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                    />
                    <Bar yAxisId="right" dataKey="sentiment" name="Sentiment">
                      {sentimentChartData.map((entry, index) => {
                        const val = entry.sentiment ?? 0
                        return (
                          <Cell
                            key={`cell-${index}`}
                            fill={val >= 0 ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}
                          />
                        )
                      })}
                    </Bar>
                    <Line yAxisId="left" type="monotone" dataKey="price" stroke="#a855f7" dot={false} strokeWidth={1.5} name="Price" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Dynamic Custom User indicator subplot */}
          {userIndicatorData.length > 0 && (
            <div className="glass-panel rounded-2xl p-5">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest">Custom Formula Engine</h3>
                <span className="text-[9px] font-mono bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded border border-cyan-500/20">{userIndicatorLabel}</span>
              </div>
              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={userIndicatorData} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                      labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                      itemStyle={{ color: '#06b6d4' }}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#06b6d4"
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Custom overlays / indicators parsed from Analysis annotations */}
          {customIndicators.map((ci, idx) => (
            <div key={idx} className="glass-panel rounded-2xl p-5">
              <div className="flex justify-between items-center mb-3">
                <h3 className="text-[10px] font-bold text-violet-400 uppercase tracking-widest">{ci.label}</h3>
                <span className="text-[9px] font-mono bg-violet-500/10 text-violet-400 px-2 py-0.5 rounded border border-violet-500/20">{ci.formula}</span>
              </div>
              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={ci.data} margin={{ top: 5, right: 5, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.02)" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <YAxis stroke="#4b5563" tick={{ fontSize: 9 }} tickLine={false} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: 'rgba(255,255,255,0.06)', borderRadius: '12px', fontSize: '10px' }}
                      labelStyle={{ color: '#9ca3af', fontWeight: 'bold' }}
                      itemStyle={{ color: '#8b5cf6' }}
                    />
                    <Line
                      type="monotone"
                      dataKey="value"
                      stroke="#8b5cf6"
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))}
        </div>

        {/* Right sidebar: List of analyses matching timeframe */}
        {activeTicker && (
          <div className="w-full lg:w-72 shrink-0 space-y-4">
            <div className="glass-panel rounded-2xl p-4 space-y-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider">{t('chart.recent_analyses')}</h3>
              
              {analysesInRange.length === 0 ? (
                <p className="text-[11px] text-slate-600">{t('chart.no_analyses_in_range')}</p>
              ) : (
                <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
                  {analysesInRange.map(a => {
                    const isSelected = selected?.id === a.id
                    return (
                      <div
                        key={a.id}
                        onClick={() => setSelected(isSelected ? null : a)}
                        className={`p-3 rounded-xl cursor-pointer transition-all border ${
                          isSelected
                            ? 'bg-violet-500/10 border-violet-500/30 text-white'
                            : 'bg-slate-900/20 border-white/[0.03] text-slate-400 hover:text-white hover:border-white/[0.08]'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs font-mono font-bold">{a.ticker}</span>
                          <span className="text-[9px] text-slate-500 font-semibold">{a.trade_date}</span>
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[10px] font-semibold text-slate-500">Signal:</span>
                          <span className={`text-[10px] font-bold ${a.signal && ['Buy', 'Overweight'].includes(a.signal) ? 'text-emerald-400' : a.signal && ['Sell', 'Underweight'].includes(a.signal) ? 'text-rose-400' : 'text-amber-400'}`}>
                            {a.signal || 'N/A'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
