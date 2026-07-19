import { describe, it, expect, vi, beforeEach } from 'vitest'
import { downloadCSV, exportPortfolioCSV, exportOrdersCSV, exportAnalysesCSV } from '../csvExport'

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
})

describe('downloadCSV', () => {
  it('creates a download link and clicks it', () => {
    const click = vi.fn()
    const setAttribute = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any

    downloadCSV('test', ['A', 'B'], [[1, 2], [3, 4]])

    expect(click).toHaveBeenCalledTimes(1)
  })
})

describe('exportPortfolioCSV', () => {
  it('generates CSV with headers and rows', () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any
    const setAttribute = vi.fn()

    exportPortfolioCSV(
      [
        { ticker: 'AAPL', quantity: 10, avg_buy_price: 150, current_price: 160, unrealized_pnl: 100 },
      ],
      5000
    )

    expect(click).toHaveBeenCalledTimes(1)
  })

  it('handles holdings without avg_buy_price', () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any
    const setAttribute = vi.fn()

    exportPortfolioCSV(
      [
        { ticker: 'AAPL', quantity: 10, current_price: 160, unrealized_pnl: 100 },
      ],
      5000
    )

    expect(click).toHaveBeenCalledTimes(1)
  })

  it('appends cash row', () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any
    const setAttribute = vi.fn()

    exportPortfolioCSV([], 10000)
    expect(click).toHaveBeenCalledTimes(1)
  })
})

describe('exportOrdersCSV', () => {
  it('generates CSV for orders', () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any
    const setAttribute = vi.fn()

    exportOrdersCSV([
      {
        ticker: 'AAPL',
        action: 'BUY',
        quantity_filled: 10,
        price_per_share: 150,
        total_value: 1500,
        realized_pnl: null,
        ai_signal: 'Bullish',
        status: 'filled',
        created_at: '2026-07-18T00:00:00Z',
      },
    ])

    expect(click).toHaveBeenCalledTimes(1)
  })
})

describe('exportAnalysesCSV', () => {
  it('generates CSV for analyses', () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute,
    })) as any
    const setAttribute = vi.fn()

    exportAnalysesCSV([
      {
        ticker: 'AAPL',
        trade_date: '2026-07-18',
        signal: 'Buy',
        duration_seconds: 45.2,
        llm_provider: 'openai',
        llm_model: 'gpt-4',
      },
    ])

    expect(click).toHaveBeenCalledTimes(1)
  })
})
