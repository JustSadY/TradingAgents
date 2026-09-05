function escape(val: unknown): string {
  if (val === null || val === undefined) return ''
  const s = String(val)
  return s.includes(',') || s.includes('"') || s.includes('\n')
    ? `"${s.replace(/"/g, '""')}"`
    : s
}

export function downloadCSV(filename: string, headers: string[], rows: unknown[][]): void {
  const content = [headers.join(','), ...rows.map(r => r.map(escape).join(','))].join('\n')
  const blob = new Blob(['﻿' + content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.csv') ? filename : filename + '.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function exportPortfolioCSV(holdings: { ticker: string; quantity: number; avg_buy_price?: number; current_price: number; unrealized_pnl: number }[], cashAvailable: number): void {
  const headers = ['Ticker', 'Quantity', 'Avg Buy Price', 'Current Price', 'Market Value', 'Unrealized P&L', 'P&L %']
  const rows = holdings.map(h => {
    const value = h.quantity * h.current_price
    const cost = h.avg_buy_price ? h.quantity * h.avg_buy_price : 0
    const pnlPct = cost > 0 ? ((value - cost) / cost * 100).toFixed(2) : ''
    return [h.ticker, h.quantity, h.avg_buy_price?.toFixed(4) ?? '', h.current_price.toFixed(4), value.toFixed(2), h.unrealized_pnl.toFixed(2), pnlPct]
  })
  rows.push(['CASH', '', '', '', cashAvailable.toFixed(2), '', ''])
  downloadCSV(`portfolio_${new Date().toISOString().slice(0, 10)}.csv`, headers, rows)
}

// Nullable fields mirror the generated OrderRead. Broker order ids are kept in
// exports because they are the primary reconciliation key after a page reload.
export function exportOrdersCSV(orders: {
  ticker: string
  action: string
  quantity_filled?: number | null
  price_per_share?: number | null
  total_value?: number | null
  realized_pnl?: number | null
  ai_signal?: string | null
  external_order_id?: string | null
  status: string
  created_at: string
}[]): void {
  const headers = ['Date', 'Ticker', 'Action', 'Qty Filled', 'Price/Share', 'Total Value', 'Realized P&L', 'Signal', 'Status', 'Broker Order ID']
  const rows = orders.map(o => [
    o.created_at.slice(0, 10),
    o.ticker,
    o.action,
    o.quantity_filled ?? '',
    o.price_per_share?.toFixed(4) ?? '',
    o.total_value?.toFixed(2) ?? '',
    o.realized_pnl?.toFixed(2) ?? '',
    o.ai_signal ?? '',
    o.status,
    o.external_order_id ?? '',
  ])
  downloadCSV(`orders_${new Date().toISOString().slice(0, 10)}.csv`, headers, rows)
}

export function exportAnalysesCSV(analyses: { ticker: string; trade_date: string; signal: string | null; duration_seconds?: number | null; llm_provider?: string | null; llm_model?: string | null }[]): void {
  const headers = ['Date', 'Ticker', 'Signal', 'Duration (s)', 'LLM Provider', 'LLM Model']
  const rows = analyses.map(a => [
    a.trade_date,
    a.ticker,
    a.signal ?? '',
    a.duration_seconds?.toFixed(1) ?? '',
    a.llm_provider ?? '',
    a.llm_model ?? '',
  ])
  downloadCSV(`analyses_${new Date().toISOString().slice(0, 10)}.csv`, headers, rows)
}
