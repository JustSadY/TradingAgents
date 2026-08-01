import { describe, expect, it } from 'vitest'
import type { AnalysisResultRead } from '../../api/types'
import { buildExportSections, markdownToHtml } from '../exportReport'

function analysisWith(overrides: Record<string, unknown>): AnalysisResultRead {
  return {
    ticker: 'NVDA',
    trade_date: '2026-08-01',
    signal: 'Overweight',
    ...overrides,
  } as AnalysisResultRead
}

describe('buildExportSections', () => {
  it('uses the combined investment debate instead of replaying bull and bear histories', () => {
    const sections = buildExportSections(analysisWith({
      bull_history: 'Bull Analyst: Buy',
      bear_history: 'Bear Analyst: Sell',
      investment_debate_history: 'Bull Analyst: Buy\nBear Analyst: Sell',
    }))

    expect(sections.map(section => section.key)).toEqual(['investment_debate_history'])
  })

  it('keeps individual debate histories when no combined chronology was persisted', () => {
    const sections = buildExportSections(analysisWith({
      bull_history: 'Bull Analyst: Buy',
      bear_history: 'Bear Analyst: Sell',
    }))

    expect(sections.map(section => section.key)).toEqual(['bull_history', 'bear_history'])
  })

  it('suppresses a legacy judge-decision mirror but retains a distinct decision', () => {
    const mirrored = buildExportSections(analysisWith({
      investment_plan: '**Recommendation**: Buy\n\n**Rationale**: Strong setup',
      judge_decision: ' **Recommendation**: Buy\n**Rationale**: Strong setup ',
    }))
    const distinct = buildExportSections(analysisWith({
      investment_plan: 'Recommendation: Buy',
      judge_decision: 'Recommendation: Hold',
    }))

    expect(mirrored.map(section => section.key)).toEqual(['investment_plan'])
    expect(distinct.map(section => section.key)).toEqual(['investment_plan', 'judge_decision'])
  })

  it('formats structured debate turns for a future JSON transcript', () => {
    const sections = buildExportSections(analysisWith({
      risk_debate_history: [
        { sender: 'Aggressive Analyst', content: 'Add on weakness.' },
        { sender: 'Conservative Analyst', content: 'Keep exposure capped.' },
      ],
    }))

    expect(sections).toEqual([{ key: 'risk_debate_history', content: 'Aggressive Analyst: Add on weakness.\n\nConservative Analyst: Keep exposure capped.' }])
  })
})

describe('markdownToHtml', () => {
  it('renders GFM tables instead of printing pipe-delimited rows as paragraphs', () => {
    const html = markdownToHtml([
      '| Metric | Value |',
      '| --- | ---: |',
      '| P/E | **30.1** |',
      '| P/B | 23.55 |',
    ].join('\n'))

    expect(html).toContain('<table>')
    expect(html).toContain('<th>Metric</th>')
    expect(html).toContain('<td><strong>30.1</strong></td>')
    expect(html).not.toContain('<p>| Metric | Value |</p>')
  })

  it('escapes untrusted table cell HTML', () => {
    const html = markdownToHtml('| Metric | Value |\n| --- | --- |\n| Test | <script>alert(1)</script> |')

    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).not.toContain('<script>')
  })

  it('does not mistake ordinary pipe-containing prose for a table', () => {
    const html = markdownToHtml('Risk/reward is 1 | 3\nThis is still prose.')

    expect(html).not.toContain('<table>')
    expect(html).toContain('<p>Risk/reward is 1 | 3</p>')
  })
})
