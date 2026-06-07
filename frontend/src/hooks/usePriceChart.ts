import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
} from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'

const SIGNAL_COLOR: Record<string, string> = {
  Buy: '#10b981',
  Overweight: '#10b981',
  Hold: '#f59e0b',
  Neutral: '#f59e0b',
  Sell: '#ef4444',
  Underweight: '#ef4444',
}

export function usePriceChart(
  containerRef: React.RefObject<HTMLDivElement>,
  candles: any[],
  analyses: any[],
  showSMA: boolean,
  showEMA: boolean
) {
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick', any> | null>(null)
  const volSeriesRef = useRef<ISeriesApi<'Histogram', any> | null>(null)
  const smaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)
  const emaSeriesRef = useRef<ISeriesApi<'Line', any> | null>(null)
  const markersApiRef = useRef<any>(null)
  const priceLineRefs = useRef<any[]>([])
  const trendlineSeriesRefs = useRef<any[]>([])
  const overlaySeriesRefs = useRef<any[]>([])

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
  }, []) // Initialize only once

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
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    })))

    volSeriesRef.current.setData(sortedCandles.map(c => ({
      time: c.time as any,
      value: c.volume,
      color: c.close >= c.open ? '#10b98125' : '#ef444425',
    })))

    // SMA / EMA
    if (smaSeriesRef.current) {
        smaSeriesRef.current.setData(showSMA ? sortedCandles.filter(c => c.sma != null).map(c => ({ time: c.time as any, value: c.sma })) : [])
    }
    if (emaSeriesRef.current) {
        emaSeriesRef.current.setData(showEMA ? sortedCandles.filter(c => c.ema != null).map(c => ({ time: c.time as any, value: c.ema })) : [])
    }

    // Cleanup previous overlays
    priceLineRefs.current.forEach(pl => { try { candleSeriesRef.current?.removePriceLine(pl) } catch {} })
    priceLineRefs.current = []
    trendlineSeriesRefs.current.forEach(ts => { try { chartRef.current?.removeSeries(ts) } catch {} })
    trendlineSeriesRefs.current = []
    overlaySeriesRefs.current.forEach(os => { try { chartRef.current?.removeSeries(os) } catch {} })
    overlaySeriesRefs.current = []

    const tradeDatesInRange = new Set(candles.map(c => c.time))

    // Helper for safe JSON parsing (backend might return string or object)
    const getAnn = (a: any) => {
        if (!a.chart_annotations) return {}
        if (typeof a.chart_annotations === 'object') return a.chart_annotations
        try {
            return JSON.parse(a.chart_annotations)
        } catch (e) {
            console.error("Failed to parse annotations for analysis", a.id, e)
            return {}
        }
    }

    // Draw Analysis Overlays
    analyses.forEach(a => {
        if (!tradeDatesInRange.has(a.trade_date)) return
        const ann = getAnn(a)
        
        ;(ann.support_levels ?? []).forEach((price: number) => {
            const pl = candleSeriesRef.current!.createPriceLine({ price, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' })
            priceLineRefs.current.push(pl)
        })
        ;(ann.resistance_levels ?? []).forEach((price: number) => {
            const pl = candleSeriesRef.current!.createPriceLine({ price, color: 'rgba(59, 130, 246, 0.4)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' })
            priceLineRefs.current.push(pl)
        })
        if (ann.target_price) {
            const pl = candleSeriesRef.current!.createPriceLine({ price: ann.target_price, color: 'rgba(16, 185, 129, 0.7)', lineWidth: 2, lineStyle: 3, axisLabelVisible: true, title: 'Target' })
            priceLineRefs.current.push(pl)
        }
        if (ann.stop_loss) {
            const pl = candleSeriesRef.current!.createPriceLine({ price: ann.stop_loss, color: 'rgba(239, 68, 68, 0.7)', lineWidth: 2, lineStyle: 3, axisLabelVisible: true, title: 'Stop Loss' })
            priceLineRefs.current.push(pl)
        }

        if (ann.annotations && Array.isArray(ann.annotations)) {
            ann.annotations.forEach((va: any) => {
                if (va.type === 'trendline' && va.time && va.price && va.time2 && va.price2) {
                    const tl = chartRef.current!.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 2, lineStyle: 2, title: va.text || 'Trendline' })
                    tl.setData([{ time: va.time, value: va.price }, { time: va.time2, value: va.price2 }])
                    trendlineSeriesRefs.current.push(tl)
                }
            })
        }

        if (ann.custom_indicators && Array.isArray(ann.custom_indicators)) {
            ann.custom_indicators.forEach((ci: any) => {
                if (ci.overlay && ci.values) {
                    const ol = chartRef.current!.addSeries(LineSeries, { color: '#06b6d4', lineWidth: 2, title: ci.label || ci.name })
                    const dataPoints = Object.entries(ci.values).map(([t, v]) => ({ time: t as any, value: v as number })).sort((a, b) => a.time.localeCompare(b.time))
                    ol.setData(dataPoints)
                    overlaySeriesRefs.current.push(ol)
                }
            })
        }
    })

    // Markers
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
      const ann = getAnn(a)
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
