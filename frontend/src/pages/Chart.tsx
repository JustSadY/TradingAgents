import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
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
import { Search, TrendingUp, TrendingDown, Minus, RefreshCw, ExternalLink } from 'lucide-react'
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

function SignalBadge({ signal }: { signal: string | null }) {
  if (!signal) return <span className="text-gray-500 text-xs">—</span>
  const color = SIGNAL_COLOR[signal] ?? '#6b7280'
  const Icon = ['Buy', 'Overweight'].includes(signal) ? TrendingUp
    : ['Sell', 'Underweight'].includes(signal) ? TrendingDown : Minus
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full"
      style={{ backgroundColor: color + '22', color }}>
      <Icon size={11} />
      {signal}
    </span>
  )
}

const PERIODS = [
  { label: '1A', value: '1m' },
  { label: '3A', value: '3m' },
  { label: '6A', value: '6m' },
  { label: '1Y', value: '1y' },
  { label: '2Y', value: '2y' },
]



export default function ChartPage() {
  const navigate = useNavigate()
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

  const smaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick', any> | null>(null)
  const volSeriesRef = useRef<ISeriesApi<'Histogram', any> | null>(null)
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers> | null>(null)
  const priceLineRefs = useRef<any[]>([])
  const tRef = useRef(t)
  useEffect(() => { tRef.current = t })



  const load = useCallback(async (ticker: string, p: string) => {
    if (!ticker) return
    setLoading(true)
    setError(null)
    setSelected(null)
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

  useEffect(() => {
    if (activeTicker) load(activeTicker, period)
  }, [])



  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#111827' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: { borderColor: '#374151', timeVisible: true },
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
      color: '#374151',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    chart.priceScale('right').applyOptions({
      scaleMargins: { top: 0, bottom: 0.25 },
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
      color: c.close >= c.open ? '#10b98133' : '#ef444433',
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

    const tradeDatesInRange = new Set(candles.map(c => c.time))

    analyses.forEach(a => {
      if (!tradeDatesInRange.has(a.trade_date)) return
      const ann = parseAnnotations(a.chart_annotations)

      ;(ann.support_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: '#ef444466', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      })
      ;(ann.resistance_levels ?? []).forEach(price => {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price, color: '#3b82f666', lineWidth: 1, lineStyle: 2,
            axisLabelVisible: false, title: '',
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      })
      if (ann.target_price) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.target_price, color: '#10b98199', lineWidth: 1, lineStyle: 3,
            axisLabelVisible: true, title: tRef.current('chart.price_line_target'),
          })
          priceLineRefs.current.push(pl)
        } catch {  }
      }
      if (ann.stop_loss) {
        try {
          const pl = candleSeriesRef.current!.createPriceLine({
            price: ann.stop_loss, color: '#ef444499', lineWidth: 1, lineStyle: 3,
            axisLabelVisible: true, title: tRef.current('chart.price_line_stop'),
          })
          priceLineRefs.current.push(pl)
        } catch {  }
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
        size: 1,
      }))
      .sort((a, b) => (a.time as string).localeCompare(b.time as string))

    try {
      if (!markersRef.current) {
        markersRef.current = createSeriesMarkers(candleSeriesRef.current as any, markerData)
      } else {
        markersRef.current.setMarkers(markerData)
      }
    } catch {  }

    chartRef.current?.timeScale().fitContent()
  }, [candles, analyses, showSMA, showEMA])



  const analysesInRange = activeTicker
    ? analyses.filter(a => candles.some(c => c.time === a.trade_date))
    : []

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
    <div className="p-4 md:p-6 space-y-5 max-w-7xl">
      <h2 className="text-lg md:text-xl font-bold text-white tracking-tight">{t('chart.title')}</h2>

      {}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 bg-gray-900 border border-gray-700 rounded-xl px-3 py-2 flex-1 max-w-xs">
          <Search size={15} className="text-gray-500" />
          <input
            className="bg-transparent text-white text-sm outline-none flex-1 uppercase"
            placeholder="AAPL, TSLA, NVDA..."
            value={tickerInput}
            onChange={e => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
        </div>
        <button
          onClick={handleSearch}
          className="bg-violet-600 hover:bg-violet-500 text-white text-sm font-semibold px-4 py-2 rounded-xl transition"
        >
          {t('chart.show_button')}
        </button>

        {activeTicker && (
          <div className="flex gap-1 ml-2">
            {PERIODS.map(p => (
              <button
                key={p.value}
                onClick={() => handlePeriod(p.value)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                  period === p.value
                    ? 'bg-violet-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}

        {loading && <RefreshCw size={16} className="text-violet-400 animate-spin" />}
      </div>

      {}
      {activeTicker && (
        <div className="flex flex-wrap items-center gap-4 bg-gray-900/50 border border-gray-800/80 px-4 py-3 rounded-xl">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider mr-2">{t('chart.indicators')}:</span>
          <label className="flex items-center gap-2 text-xs text-gray-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSMA}
              onChange={e => setShowSMA(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            SMA (20)
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showEMA}
              onChange={e => setShowEMA(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            EMA (20)
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showRSI}
              onChange={e => setShowRSI(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            RSI (14)
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showMACD}
              onChange={e => setShowMACD(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            MACD
          </label>
          <label className="flex items-center gap-2 text-xs text-gray-300 hover:text-white cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSentiment}
              onChange={e => setShowSentiment(e.target.checked)}
              className="accent-violet-500 h-4 w-4 rounded border-gray-700 bg-gray-800"
            />
            {t('chart.social_sentiment')}
          </label>
        </div>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-xl px-4 py-3">
          {error}
        </div>
      )}

      {}
      <div className="flex flex-col lg:flex-row gap-5">
        {}
        <div className="flex-1 min-w-0">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
            {activeTicker && (
              <div className="px-5 py-3 border-b border-gray-800 flex items-center gap-3">
                <span className="text-white font-bold">{activeTicker}</span>
                {candles.length > 0 && (
                  <span className="text-gray-400 text-sm">
                    {candles[candles.length - 1].close.toFixed(2)} USD
                  </span>
                )}
              </div>
            )}
            <div ref={chartContainerRef} className="w-full" />
            {!activeTicker && (
              <div className="flex flex-col items-center justify-center h-[420px] text-gray-600">
                <TrendingUp size={40} className="mb-3 opacity-30" />
                <p className="text-sm">{t('chart.empty_hint')}</p>
                <p className="text-xs mt-1 opacity-60">{t('chart.empty_hint_sub')}</p>
              </div>
            )}
          </div>

          {}
          {activeTicker && (
            <div className="flex flex-wrap gap-4 mt-3 px-1 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5 bg-emerald-500 opacity-60" style={{borderTop: '2px dashed #10b981'}} /> {t('chart.legend_support')}</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '2px dashed #3b82f6'}} /> {t('chart.legend_resistance')}</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '1px solid #10b981'}} /> {t('chart.legend_target')}</span>
              <span className="flex items-center gap-1"><span className="inline-block w-4 h-0.5" style={{borderTop: '1px solid #ef4444'}} /> {t('chart.legend_stop_loss')}</span>
              <span className="flex items-center gap-1 text-emerald-400">{t('chart.legend_buy')}</span>
              <span className="flex items-center gap-1 text-red-400">{t('chart.legend_sell')}</span>
            </div>
          )}

          {}
          {showRSI && candles.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 mt-4">
              <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-3">
                RSI (14)
              </h3>
              <div className="h-36 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={candles} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 10 }} />
                    <YAxis domain={[0, 100]} stroke="#4b5563" tick={{ fontSize: 10 }} ticks={[30, 50, 70]} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                      itemStyle={{ color: '#a855f7', fontSize: '11px' }}
                    />
                    <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 3" label={{ value: 'Overbought (70)', fill: '#ef4444', fontSize: 9, position: 'insideTopLeft' }} />
                    <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" label={{ value: 'Oversold (30)', fill: '#10b981', fontSize: 9, position: 'insideBottomLeft' }} />
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

          {}
          {showMACD && candles.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 mt-4">
              <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-3">
                MACD (12, 26, 9)
              </h3>
              <div className="h-44 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={candles} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#4b5563" tick={{ fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                      itemStyle={{ fontSize: '11px' }}
                    />
                    <Bar dataKey="macd_hist" name="Histogram">
                      {candles.map((entry, index) => {
                        const val = entry.macd_hist ?? 0
                        return (
                          <Cell
                            key={`cell-${index}`}
                            fill={val >= 0 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'}
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

          {}
          {showSentiment && sentimentChartData.length > 0 && (
            <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 mt-4">
              <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-3">
                {t('chart.sentiment_correlation')}
              </h3>
              <div className="h-48 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sentimentChartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="time" stroke="#4b5563" tick={{ fontSize: 10 }} />
                    <YAxis yAxisId="left" stroke="#4b5563" tick={{ fontSize: 10 }} domain={['auto', 'auto']} label={{ value: 'Price (USD)', angle: -90, position: 'insideLeft', fill: '#9ca3af', fontSize: 10, offset: 10 }} />
                    <YAxis yAxisId="right" orientation="right" stroke="#4b5563" tick={{ fontSize: 10 }} domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} label={{ value: 'Sentiment', angle: 90, position: 'insideRight', fill: '#9ca3af', fontSize: 10, offset: 10 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111827', borderColor: '#374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af', fontSize: '11px' }}
                      itemStyle={{ fontSize: '11px' }}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="price"
                      stroke="#10b981"
                      dot={false}
                      strokeWidth={1.5}
                      name="Stock Price"
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="sentiment"
                      stroke="#a855f7"
                      dot={false}
                      strokeWidth={2}
                      name="Sentiment Score"
                    />
                    <ReferenceLine yAxisId="right" y={0} stroke="#4b5563" strokeDasharray="3 3" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>

        {}
        {activeTicker && (
          <div className="w-full lg:w-72 lg:flex-shrink-0 space-y-4">
            {}
            <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-800">
                <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">
                  {t('chart.ai_analyses')} ({analysesInRange.length})
                </h3>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {analysesInRange.length === 0 && !loading && (
                  <p className="text-gray-600 text-xs p-4">{t('chart.no_analyses_range')}</p>
                )}
                {analysesInRange
                  .sort((a, b) => b.trade_date.localeCompare(a.trade_date))
                  .map(a => (
                    <button
                      key={a.id}
                      onClick={() => setSelected(selected?.id === a.id ? null : a)}
                      className={`w-full text-left px-4 py-2.5 border-b border-gray-800 last:border-0 hover:bg-gray-800 transition ${
                        selected?.id === a.id ? 'bg-gray-800' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-white font-mono">{a.trade_date}</span>
                        <SignalBadge signal={a.signal} />
                      </div>
                    </button>
                  ))}
              </div>
            </div>

            {}
            {selected && (
              <AnalysisDetail
                analysis={selected}
                onReanalyze={() => navigate(`/analysis?ticker=${activeTicker}&date=${selected.trade_date}`)}
                onViewFull={() => navigate(`/analysis?id=${selected.id}`)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}



function AnalysisDetail({
  analysis,
  onReanalyze,
  onViewFull,
}: {
  analysis: AnalysisItem
  onReanalyze: () => void
  onViewFull: () => void
}) {
  const { t } = useTranslation()
  const ann = parseAnnotations(analysis.chart_annotations)
  const hasAnnotations = (
    (ann.support_levels?.length ?? 0) > 0 ||
    (ann.resistance_levels?.length ?? 0) > 0 ||
    ann.target_price ||
    ann.stop_loss
  )

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">{analysis.trade_date}</span>
        <SignalBadge signal={analysis.signal} />
      </div>

      {hasAnnotations && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{t('chart.ai_price_levels')}</p>
          {(ann.support_levels ?? []).map((p, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-red-400">{t('chart.support_label')} {i + 1}</span>
              <span className="text-white font-mono">${p.toFixed(2)}</span>
            </div>
          ))}
          {(ann.resistance_levels ?? []).map((p, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-blue-400">{t('chart.resistance_label')} {i + 1}</span>
              <span className="text-white font-mono">${p.toFixed(2)}</span>
            </div>
          ))}
          {ann.target_price && (
            <div className="flex justify-between text-xs">
              <span className="text-emerald-400">{t('chart.target_label')}</span>
              <span className="text-white font-mono">${ann.target_price.toFixed(2)}</span>
            </div>
          )}
          {ann.stop_loss && (
            <div className="flex justify-between text-xs">
              <span className="text-red-400">{t('chart.stop_loss_label')}</span>
              <span className="text-white font-mono">${ann.stop_loss.toFixed(2)}</span>
            </div>
          )}
          {(ann.key_levels ?? []).map((kl, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-400 truncate pr-2">{kl.label}</span>
              <span className="text-white font-mono">${kl.price.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 pt-1">
        <button
          onClick={onViewFull}
          className="flex items-center justify-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 rounded-lg py-1.5 transition"
        >
          <ExternalLink size={11} /> {t('chart.view_full_report')}
        </button>
        <button
          onClick={onReanalyze}
          className="flex items-center justify-center gap-1.5 text-xs bg-violet-600 hover:bg-violet-500 text-white rounded-lg py-1.5 transition"
        >
          <RefreshCw size={11} /> {t('chart.reanalyze')}
        </button>
      </div>
    </div>
  )
}

