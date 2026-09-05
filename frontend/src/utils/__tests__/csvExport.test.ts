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
  it('exports broker references for reconciliation', async () => {
    const click = vi.fn()
    document.createElement = vi.fn(() => ({
      href: '',
      download: '',
      click,
      setAttribute: vi.fn(),
    })) as any

    let exportedBlob: Blob | undefined
    URL.createObjectURL = vi.fn((blob: Blob | MediaSource) => {
      if (blob instanceof Blob) exportedBlob = blob
      return 'blob:test'
    })

    exportOrdersCSV([
      {
        ticker: 'AAPL',
        action: 'BUY',
        quantity_filled: 0,
        price_per_share: null,
        total_value: null,
        realized_pnl: null,
        external_order_id: 'client:ta-reconcile-123',
        ai_signal: 'Bullish',
        status: 'RECONCILIATION_REQUIRED',
        created_at: '2026-07-18T00:00:00Z',
      },
    ])

    expect(click).toHaveBeenCalledTimes(1)
    expect(exportedBlob).toBeInstanceOf(Blob)
    const csv = await exportedBlob!.text()
    expect(csv).toContain('Broker Reference')
    expect(csv).toContain('client:ta-reconcile-123')
    expect(csv).toContain('RECONCILIATION_REQUIRED')
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
