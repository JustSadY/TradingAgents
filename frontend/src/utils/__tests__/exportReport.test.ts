import { describe, expect, it } from 'vitest'
import type { AnalysisResultRead } from '../../api/generated/model'
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
    // The `---:` separator carries through as a column alignment attribute.
    expect(html).toContain('<strong>30.1</strong>')
    expect(html).toMatch(/<td[^>]*align="right"[^>]*><strong>30.1<\/strong><\/td>/)
    expect(html).not.toContain('<p>| Metric | Value |</p>')
  })

  it('escapes untrusted table cell HTML', () => {
    const html = markdownToHtml('| Metric | Value |\n| --- | --- |\n| Test | <script>alert(1)</script> |')

    // Escaped as a hex entity rather than a named one; both are inert, and
    // the tag stays visible so the report shows what the model actually wrote.
    expect(html).not.toContain('<script>')
    expect(html).toMatch(/&(lt|#x3C);script/i)
    expect(html).toContain('alert(1)')
  })

  it('does not mistake ordinary pipe-containing prose for a table', () => {
    const html = markdownToHtml('Risk/reward is 1 | 3\nThis is still prose.')

    expect(html).not.toContain('<table>')
    expect(html).toContain('Risk/reward is 1 | 3')
  })

  describe('block structures', () => {
    it.each([
      ['- a\n- b', '<ul'],
      ['1. a\n2. b', '<ol'],
      ['> quoted', '<blockquote'],
      ['---', '<hr'],
      ['```\ncode\n```', '<pre'],
    ])('renders %s', (source, expected) => {
      expect(markdownToHtml(source)).toContain(expected)
    })

    it('demotes report headings so they nest under the section heading', () => {
      // The printable page emits each section as <h2>, so report content
      // starts one level below it rather than competing with it.
      const html = markdownToHtml('# Top\n\n## Second\n\n### Third')
      expect(html).not.toContain('<h1')
      expect(html).not.toContain('<h2')
      expect(html.match(/<h[34]/g)?.length).toBe(3)
    })

    it('renders inline emphasis and code', () => {
      const html = markdownToHtml('**bold** _italic_ `code`')
      expect(html).toContain('<strong>bold</strong>')
      expect(html).toContain('<em>italic</em>')
      expect(html).toContain('<code>code</code>')
    })
  })

  describe('untrusted content', () => {
    it('escapes raw HTML in prose', () => {
      const html = markdownToHtml('before <script>alert(1)</script> after')
      expect(html).not.toContain('<script>')
      expect(html).toContain('alert(1)')
    })

    it('escapes an img tag with an event handler', () => {
      const html = markdownToHtml('<img src=x onerror="alert(1)">')
      expect(html).not.toMatch(/<img[^>]*onerror/)
    })

    it('does not emit a javascript: link target', () => {
      const html = markdownToHtml('[x](javascript:alert(1))')
      expect(html).not.toContain('href="javascript:')
    })

    it('keeps a safe link', () => {
      const html = markdownToHtml('[x](https://example.com)')
      expect(html).toContain('https://example.com')
    })

    it('escapes angle brackets inside a fenced block', () => {
      const html = markdownToHtml('```\n<script>alert(1)</script>\n```')
      expect(html).not.toContain('<script>')
      expect(html).toMatch(/&(lt|#x3C);script/i)
    })
  })
})
