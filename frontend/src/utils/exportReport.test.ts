import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exportMarkdown, type AnalysisForExport } from './exportReport'

const analysis: AnalysisForExport = {
  ticker: 'AAPL',
  trade_date: '2026-06-12',
  signal: 'Buy',
  market_report: '  Strong uptrend.  ',
  final_decision: 'Buy with conviction.',
}

describe('exportMarkdown', () => {
  let capturedBlob: Blob | null
  let download: string

  beforeEach(() => {
    capturedBlob = null
    download = ''
    globalThis.URL.createObjectURL = vi.fn((blob: Blob) => {
      capturedBlob = blob
      return 'blob:fake'
    })
    globalThis.URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      download = this.download
    })
  })
  afterEach(() => vi.restoreAllMocks())

  it('downloads a markdown file named after ticker and date', async () => {
    exportMarkdown(analysis)
    expect(download).toBe('AAPL_2026-06-12.md')
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake')

    const text = await capturedBlob!.text()
    expect(text).toContain('# AAPL — Analiz Raporu')
    expect(text).toContain('**Sinyal:** Buy')
    // Sections present are included (trimmed), absent ones are skipped.
    expect(text).toContain('## Piyasa Analizi\n\nStrong uptrend.')
    expect(text).toContain('## PM Kararı')
    expect(text).not.toContain('## Haber Analizi')
  })

  it('falls back to N/A when there is no signal', async () => {
    exportMarkdown({ ...analysis, signal: null })
    const text = await capturedBlob!.text()
    expect(text).toContain('**Sinyal:** N/A')
  })
})
