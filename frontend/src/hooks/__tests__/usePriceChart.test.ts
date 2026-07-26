import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePriceChart, type ChartCandle, type ChartAnalysis } from '../usePriceChart'

const {
  mockCreateChart, mockCandlestickSeries, mockHistogramSeries, mockLineSeries,
  mockCreateSeriesMarkers, mockSetMarkers,
  mockRemovePriceLine, mockCreatePriceLine,
  mockCandleSeries, mockVolSeries, mockSmaSeries, mockEmaSeries,
  mockPriceScale, mockChart,
  resetSeriesCounter,
} = vi.hoisted(() => {
  const _candleSetData = vi.fn()
  const _volSetData = vi.fn()
  const _smaSetData = vi.fn()
  const _emaSetData = vi.fn()

  const _removePriceLine = vi.fn()
  const _createPriceLine = vi.fn(() => ({ remove: vi.fn() }))

  const _seriesProto = {
    createPriceLine: _createPriceLine,
    removePriceLine: _removePriceLine,
  }
  const _candleSeries = { ..._seriesProto, setData: _candleSetData }
  const _volSeries = { ..._seriesProto, setData: _volSetData }
  const _smaSeries = { ..._seriesProto, setData: _smaSetData }
  const _emaSeries = { ..._seriesProto, setData: _emaSetData }

  const _priceScale = vi.fn(() => ({ applyOptions: vi.fn() }))
  const _timeScale = { fitContent: vi.fn() }
  const _removeSeries = vi.fn()
  const _applyOptions = vi.fn()

  const _candlestickSeries = Symbol('CandlestickSeries')
  const _histogramSeries = Symbol('HistogramSeries')
  const _lineSeries = Symbol('LineSeries')

  // Track which LineSeries call we're on (first = SMA, second = EMA)
  let _lineSeriesCallCount = 0

  const _createChart = vi.fn()
  const _chart = {
    addSeries: vi.fn((seriesType) => {
      if (seriesType === _candlestickSeries) return _candleSeries
      if (seriesType === _histogramSeries) return _volSeries
      if (seriesType === _lineSeries) {
        // First LineSeries call returns SMA, second returns EMA
        const series = _lineSeriesCallCount === 0 ? _smaSeries : _emaSeries
        _lineSeriesCallCount++
        return series
      }
      return { ..._seriesProto, setData: vi.fn() }
    }),
    priceScale: _priceScale,
    timeScale: () => _timeScale,
    remove: vi.fn(),
    applyOptions: _applyOptions,
    removeSeries: _removeSeries,
  }
  _createChart.mockReturnValue(_chart)

  const _setMarkers = vi.fn()
  // Forward markers to _setMarkers so first-call assertions work
  const _createSeriesMarkers = vi.fn((_series, markers) => {
    _setMarkers(markers)
    return { setMarkers: _setMarkers }
  })

  return {
    mockCreateChart: _createChart,
    mockCandlestickSeries: _candlestickSeries,
    mockHistogramSeries: _histogramSeries,
    mockLineSeries: _lineSeries,
    mockCreateSeriesMarkers: _createSeriesMarkers,
    mockSetMarkers: _setMarkers,
    mockRemovePriceLine: _removePriceLine,
    mockCreatePriceLine: _createPriceLine,
    mockCandleSeries: _candleSeries,
    mockVolSeries: _volSeries,
    mockSmaSeries: _smaSeries,
    mockEmaSeries: _emaSeries,
    mockPriceScale: _priceScale,
    mockChart: _chart,
    resetSeriesCounter: () => { _lineSeriesCallCount = 0 },
  }
})

vi.mock('lightweight-charts', () => ({
  createChart: (...args: any[]) => mockCreateChart(...args),
  ColorType: { Solid: 'solid' },
  CandlestickSeries: mockCandlestickSeries,
  HistogramSeries: mockHistogramSeries,
  LineSeries: mockLineSeries,
  LineStyle: { Dashed: 2, LargeDashed: 4, Solid: 0 },
  createSeriesMarkers: (...args: any[]) => mockCreateSeriesMarkers(...args),
}))

function createMockRef() {
  const div = document.createElement('div')
  Object.defineProperty(div, 'clientWidth', { value: 800 })
  return { current: div } as React.RefObject<HTMLDivElement>
}

function candle(time: string, overrides: Partial<ChartCandle> = {}): ChartCandle {
  return { time, open: 100, high: 105, low: 95, close: 102, volume: 1000, sma: null, ema: null, ...overrides }
}

function analysis(id: number, overrides: Partial<ChartAnalysis> = {}): ChartAnalysis {
  return {
    id, trade_date: '2026-07-18', signal: null, chart_annotations: null, ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  resetSeriesCounter()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('usePriceChart', () => {
  it('creates chart on mount', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [], [], false, false))
    expect(mockCreateChart).toHaveBeenCalledTimes(1)
    expect(mockChart.addSeries).toHaveBeenCalledTimes(4)
    expect(mockPriceScale).toHaveBeenCalledWith('volume-scale')
  })

  it('sets candle data from sorted candles', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-19'), candle('2026-07-18')]
    renderHook(() => usePriceChart(ref, candles, [], false, false))
    expect(mockCandleSeries.setData).toHaveBeenCalled()
    const data = mockCandleSeries.setData.mock.calls[0][0]
    expect(data[0].time).toBe('2026-07-18')
    expect(data[1].time).toBe('2026-07-19')
  })

  it('sets volume data with color based on close vs open', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18'), candle('2026-07-19', { close: 98 })]
    renderHook(() => usePriceChart(ref, candles, [], false, false))
    const volData = mockVolSeries.setData.mock.calls[0][0]
    expect(volData[0].color).toContain('10b981')
    expect(volData[1].color).toContain('ef4444')
  })

  it('sets SMA data when showSMA is true', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18', { sma: 101 })]
    renderHook(() => usePriceChart(ref, candles, [], true, false))
    expect(mockSmaSeries.setData).toHaveBeenCalled()
    const smaData = mockSmaSeries.setData.mock.calls[0][0]
    expect(smaData[0].value).toBe(101)
  })

  it('clears SMA when showSMA is false', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18', { sma: 101 })]
    renderHook(() => usePriceChart(ref, candles, [], false, false))
    expect(mockSmaSeries.setData).toHaveBeenCalledWith([])
  })

  it('shows EMA when showEMA is true', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18', { ema: 100.5 })]
    renderHook(() => usePriceChart(ref, candles, [], false, true))
    const emaData = mockEmaSeries.setData.mock.calls[0][0]
    expect(emaData[0].value).toBe(100.5)
  })

  it('clears EMA when showEMA is false', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18', { ema: 100.5 })]
    renderHook(() => usePriceChart(ref, candles, [], false, false))
    expect(mockEmaSeries.setData).toHaveBeenCalledWith([])
  })

  it('renders support and resistance price lines', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({ support_levels: [95, 93], resistance_levels: [105, 108] })
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann, signal: 'Buy' })], false, false))
    expect(mockCreatePriceLine).toHaveBeenCalledTimes(4)
  })

  it('renders target price line', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({ target_price: 110 })
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockCreatePriceLine).toHaveBeenCalledWith(expect.objectContaining({ price: 110 }))
  })

  it('renders stop loss price line', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({ stop_loss: 90 })
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockCreatePriceLine).toHaveBeenCalledWith(expect.objectContaining({ price: 90 }))
  })

  it('renders liquidation price line with leverage label', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({ liquidation_price: 85, leverage: 5 })
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockCreatePriceLine).toHaveBeenCalledWith(expect.objectContaining({ price: 85, title: expect.stringContaining('5') }))
  })

  it('skips analysis when trade_date not in candle range', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-17', signal: 'Buy' })], false, false))
    expect(mockCreatePriceLine).not.toHaveBeenCalled()
  })

  it('renders signal markers for Buy/Sell signals', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', signal: 'Buy' })], false, false))
    expect(mockCreateSeriesMarkers).toHaveBeenCalled()
    expect(mockSetMarkers).toHaveBeenCalled()
  })

  it('renders trendline annotations', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({
      annotations: [{ type: 'trendline', time: '2026-07-18', price: 100, time2: '2026-07-19', price2: 105, text: 'uptrend' }],
    })
    const candles = [candle('2026-07-18'), candle('2026-07-19')]
    renderHook(() => usePriceChart(ref, candles, [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockChart.addSeries).toHaveBeenCalledWith(mockLineSeries, expect.objectContaining({ title: 'uptrend' }))
  })

  it('handles chart_annotations as object (parsed)', () => {
    const ref = createMockRef()
    const ann = { support_levels: [95], resistance_levels: [105] }
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockCreatePriceLine).toHaveBeenCalledTimes(2)
  })

  it('handles null chart_annotations gracefully', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18' })], false, false))
    expect(mockCreatePriceLine).not.toHaveBeenCalled()
  })

  it('handles corrupted JSON annotations gracefully', () => {
    const ref = createMockRef()
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: '{bad json}' })], false, false))
    expect(consoleSpy).toHaveBeenCalled()
    consoleSpy.mockRestore()
  })

  it('handles empty candles gracefully', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [], [], false, false))
    expect(mockCandleSeries.setData).not.toHaveBeenCalled()
  })

  it('cleans up on unmount', () => {
    const ref = createMockRef()
    const { unmount } = renderHook(() => usePriceChart(ref, [], [], false, false))
    unmount()
    expect(mockChart.remove).toHaveBeenCalled()
  })

  it('skips duplicate candle timestamps', () => {
    const ref = createMockRef()
    const candles = [candle('2026-07-18'), candle('2026-07-18', { close: 103 })]
    renderHook(() => usePriceChart(ref, candles, [], false, false))
    const data = mockCandleSeries.setData.mock.calls[0][0]
    expect(data).toHaveLength(1)
  })

  it('returns chartRef from the hook', () => {
    const ref = createMockRef()
    const { result } = renderHook(() => usePriceChart(ref, [], [], false, false))
    expect(result.current).toHaveProperty('chartRef')
  })

  it('renders visual markers from annotations', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({
      annotations: [{ type: 'arrowUp', time: '2026-07-18', text: 'Entry' }],
    })
    renderHook(() => usePriceChart(ref, [candle('2026-07-18')], [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockCreateSeriesMarkers).toHaveBeenCalled()
  })

  it('renders custom indicator overlays', () => {
    const ref = createMockRef()
    const ann = JSON.stringify({
      custom_indicators: [{ overlay: true, values: { '2026-07-18': 50, '2026-07-19': 55 }, label: 'RSI' }],
    })
    const candles = [candle('2026-07-18'), candle('2026-07-19')]
    renderHook(() => usePriceChart(ref, candles, [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann })], false, false))
    expect(mockChart.addSeries).toHaveBeenCalledWith(mockLineSeries, expect.objectContaining({ title: 'RSI' }))
  })

  it('clears overlays between analysis re-renders', () => {
    const ref = createMockRef()
    const ann1 = JSON.stringify({ support_levels: [95] })
    const ann2 = JSON.stringify({ support_levels: [90] })
    const { rerender } = renderHook(
      ({ candles, analyses }) => usePriceChart(ref, candles, analyses, false, false),
      { initialProps: { candles: [candle('2026-07-18')], analyses: [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann1 })] } },
    )
    rerender({ candles: [candle('2026-07-18')], analyses: [analysis(1, { trade_date: '2026-07-18', chart_annotations: ann2 })] })
    expect(mockRemovePriceLine).toHaveBeenCalled()
  })

  it('adjusts chart size on container ref (single init)', () => {
    const ref = createMockRef()
    renderHook(() => usePriceChart(ref, [], [], false, false))
    expect(mockCreateChart.mock.calls[0][0]).toBe(ref.current)
    expect(mockCreateChart.mock.calls[0][1]).toHaveProperty('width', 800)
  })
})
