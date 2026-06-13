import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createSeriesMarkers,
} from 'lightweight-charts'
import type { IChartApi, IPriceLine, ISeriesApi, SeriesMarker, Time } from 'lightweight-charts'

const SIGNAL_COLOR: Record<string, string> = {
  Buy: '#10b981',
  Overweight: '#10b981',
  Hold: '#f59e0b',
  Neutral: '#f59e0b',
  Sell: '#ef4444',
  Underweight: '#ef4444',
}

export interface ChartCandle {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  sma?: number | null
  ema?: number | null
}

interface VisualAnnotation {
  type?: string
  time?: string
  price?: number
  time2?: string
  price2?: number
  text?: string
}

interface OverlayIndicator {
  overlay?: boolean
  values?: Record<string, number>
  label?: string
  name?: string
}

interface ChartAnnotations {
  support_levels?: number[]
  resistance_levels?: number[]
  target_price?: number
  stop_loss?: number
  liquidation_price?: number
  leverage?: number
  annotations?: VisualAnnotation[]
  custom_indicators?: OverlayIndicator[]
}

export interface ChartAnalysis {
  id: number
  trade_date: string
  signal: string | null
  chart_annotations: string | ChartAnnotations | null
}

export function usePriceChart(
  containerRef: React.RefObject<HTMLDivElement>,
  candles: ChartCandle[],
  analyses: ChartAnalysis[],
  showSMA: boolean,
  showEMA: boolean
) {
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const smaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const markersApiRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null)
  const priceLineRefs = useRef<IPriceLine[]>([])
  const trendlineSeriesRefs = useRef<ISeriesApi<'Line'>[]>([])
  const overlaySeriesRefs = useRef<ISeriesApi<'Line'>[]>([])

  // 1. Initialize Chart (Run once when container is available)
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return

    const chart = createChart(containerRef.current, {
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
      width: containerRef.current.clientWidth || 800,
      height: 420,
    })

    // In v5, we use addSeries(Type, options)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#1f2937',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume-scale',
    })

    chart.priceScale('volume-scale').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    const smaSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
    })
    const emaSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volSeriesRef.current = volSeries
    smaSeriesRef.current = smaSeries
    emaSeriesRef.current = emaSeries

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)
    const ro = new ResizeObserver(handleResize)
    ro.observe(containerRef.current)

    return () => {
      window.removeEventListener('resize', handleResize)
      ro.disconnect()
      if (chartRef.current) {
        chartRef.current.remove()
        chartRef.current = null
      }
      candleSeriesRef.current = null
      volSeriesRef.current = null
      smaSeriesRef.current = null
      emaSeriesRef.current = null
      markersApiRef.current = null
    }
    // containerRef is a stable ref object; the chartRef guard prevents re-init.
  }, [containerRef])

  // Update Data and Overlays
  useEffect(() => {
    if (!candleSeriesRef.current || !volSeriesRef.current || candles.length === 0) return

    // Sort and deduplicate candles to ensure lightweight-charts doesn't crash
    const sortedCandles = [...candles]
      .filter(c => c && c.time)
      .sort((a, b) => a.time.localeCompare(b.time))
      .filter((c, i, arr) => i === 0 || c.time !== arr[i - 1].time)

    if (sortedCandles.length === 0) return

    candleSeriesRef.current.setData(sortedCandles.map(c => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    })))

    volSeriesRef.current.setData(sortedCandles.map(c => ({
      time: c.time as Time,
      value: c.volume,
      color: c.close >= c.open ? '#10b98125' : '#ef444425',
    })))

    // SMA / EMA
    if (smaSeriesRef.current) {
        smaSeriesRef.current.setData(showSMA ? sortedCandles.filter(c => c.sma != null).map(c => ({ time: c.time as Time, value: c.sma! })) : [])
    }
    if (emaSeriesRef.current) {
        emaSeriesRef.current.setData(showEMA ? sortedCandles.filter(c => c.ema != null).map(c => ({ time: c.time as Time, value: c.ema! })) : [])
    }

    // Cleanup previous overlays
    priceLineRefs.current.forEach(pl => { try { candleSeriesRef.current?.removePriceLine(pl) } catch { /* overlay already gone */ } })
    priceLineRefs.current = []
    trendlineSeriesRefs.current.forEach(ts => { try { chartRef.current?.removeSeries(ts) } catch { /* overlay already gone */ } })
    trendlineSeriesRefs.current = []
    overlaySeriesRefs.current.forEach(os => { try { chartRef.current?.removeSeries(os) } catch { /* overlay already gone */ } })
    overlaySeriesRefs.current = []

    const tradeDatesInRange = new Set(candles.map(c => c.time))

    // Helper for safe JSON parsing (backend might return string or object)
    const getAnn = (a: ChartAnalysis): ChartAnnotations => {
        if (!a.chart_annotations) return {}
        if (typeof a.chart_annotations === 'object') return a.chart_annotations
        try {
            return JSON.parse(a.chart_annotations) as ChartAnnotations
        } catch (e) {
            console.error("Failed to parse annotations for analysis", a.id, e)
            return {}
        }
    }

    // Draw Analysis Overlays
    analyses.forEach(a => {
        if (!tradeDatesInRange.has(a.trade_date)) return
        const ann = getAnn(a)

        ;(ann.support_levels ?? []).forEach(price => {
            const pl = candleSeriesRef.current!.createPriceLine({ price, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' })
            priceLineRefs.current.push(pl)
        })
        ;(ann.resistance_levels ?? []).forEach(price => {
            const pl = candleSeriesRef.current!.createPriceLine({ price, color: 'rgba(59, 130, 246, 0.4)', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: '' })
            priceLineRefs.current.push(pl)
        })
        if (ann.target_price) {
            const pl = candleSeriesRef.current!.createPriceLine({ price: ann.target_price, color: 'rgba(16, 185, 129, 0.7)', lineWidth: 2, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: 'Target' })
            priceLineRefs.current.push(pl)
        }
        if (ann.stop_loss) {
            const pl = candleSeriesRef.current!.createPriceLine({ price: ann.stop_loss, color: 'rgba(239, 68, 68, 0.7)', lineWidth: 2, lineStyle: LineStyle.LargeDashed, axisLabelVisible: true, title: 'Stop Loss' })
            priceLineRefs.current.push(pl)
        }
        if (ann.liquidation_price) {
            const levTitle = ann.leverage && ann.leverage > 1 ? `Liq. ${ann.leverage}x` : 'Liquidation'
            const pl = candleSeriesRef.current!.createPriceLine({ price: ann.liquidation_price, color: 'rgba(245, 158, 11, 0.9)', lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: levTitle })
            priceLineRefs.current.push(pl)
        }

        ;(ann.annotations ?? []).forEach(va => {
            if (va.type === 'trendline' && va.time && va.price && va.time2 && va.price2) {
                const tl = chartRef.current!.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 2, lineStyle: LineStyle.Dashed, title: va.text || 'Trendline' })
                tl.setData([{ time: va.time as Time, value: va.price }, { time: va.time2 as Time, value: va.price2 }])
                trendlineSeriesRefs.current.push(tl)
            }
        })

        ;(ann.custom_indicators ?? []).forEach(ci => {
            if (ci.overlay && ci.values) {
                const ol = chartRef.current!.addSeries(LineSeries, { color: '#06b6d4', lineWidth: 2, title: ci.label || ci.name })
                const dataPoints = Object.entries(ci.values)
                  .map(([t, v]) => ({ time: t, value: v }))
                  .sort((a, b) => a.time.localeCompare(b.time))
                  .map(p => ({ time: p.time as Time, value: p.value }))
                ol.setData(dataPoints)
                overlaySeriesRefs.current.push(ol)
            }
        })
    })

    // Markers
    const markerData: SeriesMarker<Time>[] = analyses
      .filter(a => a.signal && tradeDatesInRange.has(a.trade_date))
      .map(a => ({
        time: a.trade_date as Time,
        position: ['Buy', 'Overweight'].includes(a.signal!) ? 'belowBar' : 'aboveBar',
        color: SIGNAL_COLOR[a.signal!] ?? '#6b7280',
        shape: ['Buy', 'Overweight'].includes(a.signal!) ? 'arrowUp' : ['Sell', 'Underweight'].includes(a.signal!) ? 'arrowDown' : 'circle',
        text: a.signal!,
        size: 1.2,
      }))

    const visualMarkers: SeriesMarker<Time>[] = []
    analyses.forEach(a => {
      if (!tradeDatesInRange.has(a.trade_date)) return
      const ann = getAnn(a)
      ;(ann.annotations ?? []).forEach(va => {
        if ((va.type === 'arrowUp' || va.type === 'arrowDown' || va.type === 'circle') && va.time) {
          visualMarkers.push({
            time: va.time as Time,
            position: va.type === 'arrowUp' ? 'belowBar' : 'aboveBar',
            color: va.type === 'arrowUp' ? '#10b981' : va.type === 'arrowDown' ? '#ef4444' : '#f59e0b',
            shape: va.type,
            text: va.text || '',
            size: 1.5,
          })
        }
      })
    })

    const combinedMarkers = [...markerData, ...visualMarkers].sort((a, b) =>
        (a.time as string).localeCompare(b.time as string)
    )

    if (candleSeriesRef.current) {
        try {
            if (!markersApiRef.current) {
                markersApiRef.current = createSeriesMarkers(candleSeriesRef.current, combinedMarkers)
            } else {
                markersApiRef.current.setMarkers(combinedMarkers)
            }
        } catch (err) {
            console.error("Error setting markers:", err)
        }
    }

    if (chartRef.current) {
        chartRef.current.timeScale().fitContent()
    }
  }, [candles, analyses, showSMA, showEMA])

  return { chartRef }
}
