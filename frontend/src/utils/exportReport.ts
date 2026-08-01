import type { AnalysisResultRead } from '../api/types'

type Lang = 'en' | 'tr'

const SECTION_LABELS: Record<Lang, Record<string, string>> = {
  en: {
    market_report:     'Market Analysis',
    sentiment_report:  'Sentiment Analysis',
    news_report:       'News Analysis',
    fundamentals_report: 'Fundamentals',
    macro_report:      'Macro Analysis',
    options_report:    'Options Analysis',
    quant_report:      'Quantitative Analysis',
    earnings_report:   'Earnings Analysis',
    insider_report:    'Insider Activity',
    ownership_report:  'Institutional Ownership',
    ratings_report:    'Analyst Ratings',
    short_interest_report: 'Short Interest',
    valuation_report: 'Valuation Comparison',
    catalyst_report:   'Upcoming Catalysts',
    review_report:     'Review',
    synthesis_report:  'Synthesis',
    audit_report:      'Audit',
    agent_qa_report:   'Agent Cross-Examination',
    investment_plan:   'Research Evidence Summary',
    trader_plan:       'Legacy Trader Proposal (historical only)',
    final_decision:    'Final Decision (Portfolio Manager)',
    bull_history:      'Bull Arguments',
    bear_history:      'Bear Arguments',
    investment_debate_history: 'Investment Debate',
    risk_debate_history:      'Risk Debate',
    judge_decision:    'Judge Decision',
  },
  tr: {
    market_report:     'Piyasa Analizi',
    sentiment_report:  'Duygu Analizi',
    news_report:       'Haber Analizi',
    fundamentals_report: 'Temel Analiz',
    macro_report:      'Makro Analiz',
    options_report:    'Opsiyon Analizi',
    quant_report:      'Kantitatif Analiz',
    earnings_report:   'Kazanç Analizi',
    insider_report:    'İçeriden İşlem',
    ownership_report:  'Kurumsal Sahiplik',
    ratings_report:    'Analist Tavsiyeleri',
    short_interest_report: 'Açığa Satış',
    valuation_report: 'Değerleme Karşılaştırması',
    catalyst_report:   'Yaklaşan Katalizörler',
    review_report:     'Performans İnceleme',
    synthesis_report:  'Sentez',
    audit_report:      'Denetim',
    agent_qa_report:   'Ajan Çapraz Sorgu',
    investment_plan:   'Araştırma Kanıt Özeti',
    trader_plan:       'Eski Trader Önerisi (yalnız geçmiş kayıt)',
    final_decision:    'Nihai Karar (Portfolio Manager)',
    bull_history:      'Boğa Argümanları',
    bear_history:      'Ayı Argümanları',
    investment_debate_history: 'Yatırım Tartışması',
    risk_debate_history:      'Risk Tartışması',
    judge_decision:    'Hakem Kararı',
  },
}

const SECTION_ORDER = [
  'final_decision', 'investment_plan', 'trader_plan',
  'market_report', 'fundamentals_report', 'news_report', 'sentiment_report',
  'macro_report', 'options_report', 'quant_report', 'earnings_report',
  'insider_report', 'ownership_report', 'ratings_report', 'short_interest_report', 'valuation_report', 'catalyst_report',
  'review_report', 'synthesis_report', 'audit_report', 'agent_qa_report',
  'bull_history', 'bear_history', 'investment_debate_history', 'risk_debate_history', 'judge_decision',
]

export interface ExportSection {
  key: string
  content: string
}

type AnalysisRecord = Record<string, unknown>

/**
 * Turn a persisted report value into printable text. Debate histories are JSON
 * columns, so newer runs may store them as structured turn objects rather than
 * the legacy newline-delimited string.
 */
function printableContent(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (!Array.isArray(value)) return ''

  return value.map(item => {
    if (typeof item === 'string') return item.trim()
    if (!item || typeof item !== 'object') return ''
    const turn = item as Record<string, unknown>
    const content = typeof turn.content === 'string' ? turn.content.trim() : ''
    if (!content) return ''
    const sender = typeof turn.sender === 'string' ? turn.sender.trim() : ''
    return sender ? `${sender}: ${content}` : content
  }).filter(Boolean).join('\n\n')
}

function normalizedContent(content: string): string {
  return content.replace(/\s+/g, ' ').trim()
}

/**
 * Select the report sections once for every export format.
 *
 * A completed investment debate has three representations in older results:
 * individual bull/bear histories and a combined chronological history. The
 * combined history is authoritative because it preserves turn order, so it
 * replaces the two individual copies whenever present. Likewise, the research
 * manager writes the same plan to both `investment_plan` and `judge_decision`;
 * the latter is retained only when it differs after whitespace normalisation.
 */
export function buildExportSections(analysis: AnalysisResultRead): ExportSection[] {
  const record = analysis as unknown as AnalysisRecord
  const contentByKey = Object.fromEntries(
    SECTION_ORDER.map(key => [key, printableContent(record[key])])
  ) as Record<string, string>
  const hasCombinedInvestmentDebate = Boolean(contentByKey.investment_debate_history)
  const investmentPlan = contentByKey.investment_plan

  return SECTION_ORDER.flatMap(key => {
    const content = contentByKey[key]
    if (!content) return []

    // Avoid a three-way replay of the same Bull/Bear turns in PDF/Markdown.
    if (hasCombinedInvestmentDebate && (key === 'bull_history' || key === 'bear_history')) return []

    // `judge_decision` is a legacy mirror of the Research Manager plan.
    if (
      key === 'judge_decision' &&
      investmentPlan &&
      normalizedContent(content) === normalizedContent(investmentPlan)
    ) return []

    return [{ key, content }]
  })
}

// ── Markdown export ──────────────────────────────────────────────────────────

export function exportMarkdown(analysis: AnalysisResultRead, language: Lang = 'en'): void {
  const labels = SECTION_LABELS[language]
  const meta = _metaLines(analysis, language)
  const lines: string[] = [
    `# ${analysis.ticker} — ${language === 'tr' ? 'Analiz Raporu' : 'Analysis Report'}`,
    '',
    ...meta,
    '',
    '---',
    '',
  ]

  for (const { key, content } of buildExportSections(analysis)) {
    lines.push(`## ${labels[key] ?? key}`, '', content, '', '---', '')
  }

  const blob = new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${analysis.ticker}_${analysis.trade_date}.md`
  a.click()
  URL.revokeObjectURL(url)
}

// ── PDF export ───────────────────────────────────────────────────────────────

export function exportPDF(analysis: AnalysisResultRead, language: Lang = 'en'): void {
  const labels = SECTION_LABELS[language]
  const meta = _metaLines(analysis, language)

  const metaHtml = meta.map(l => `<p class="meta-line">${escapeHtml(l)}</p>`).join('')

  let sectionsHtml = ''
  for (const { key, content } of buildExportSections(analysis)) {
    sectionsHtml += `
      <div class="section">
        <h2>${escapeHtml(labels[key] ?? key)}</h2>
        <div class="section-body">${markdownToHtml(content)}</div>
      </div>`
  }

  const signalColor = _signalColor(analysis.signal)

  const html = `<!DOCTYPE html>
<html lang="${language}">
<head>
<meta charset="utf-8">
<title>${analysis.ticker} ${analysis.trade_date}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1a202c; background: #fff; }
  .header { background: #1e1b4b; color: #fff; padding: 20px 28px; display: flex; align-items: center; justify-content: space-between; }
  .header-left h1 { font-size: 22pt; font-weight: 800; letter-spacing: -0.5px; }
  .header-left .sub { font-size: 10pt; color: #a5b4fc; margin-top: 4px; }
  .signal-badge { padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 13pt; background: ${signalColor.bg}; color: ${signalColor.fg}; }
  .meta-block { background: #f8f9ff; border-left: 3px solid #6366f1; padding: 12px 20px; margin: 20px 28px 0; border-radius: 4px; }
  .meta-line { font-size: 9.5pt; color: #4a5568; line-height: 1.7; }
  .content { padding: 8px 28px 40px; }
  .section { margin-top: 24px; page-break-inside: avoid; }
  .section h2 { font-size: 12pt; font-weight: 700; color: #312e81; border-bottom: 1.5px solid #e0e7ff; padding-bottom: 5px; margin-bottom: 10px; }
  .section-body { font-size: 10.5pt; line-height: 1.65; color: #2d3748; }
  .section-body p { margin-bottom: 8px; }
  .section-body h3 { font-size: 11pt; font-weight: 600; color: #1a202c; margin: 12px 0 5px; }
  .section-body h4 { font-size: 10.5pt; font-weight: 600; color: #2d3748; margin: 8px 0 4px; }
  .section-body ul, .section-body ol { padding-left: 20px; margin-bottom: 8px; }
  .section-body li { margin-bottom: 3px; }
  .section-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 9.5pt; }
  .section-body th, .section-body td { border: 1px solid #dbe3ee; padding: 6px 8px; text-align: left; vertical-align: top; overflow-wrap: anywhere; }
  .section-body th { background: #f1f5f9; color: #1e293b; font-weight: 600; }
  .section-body strong { font-weight: 600; }
  .section-body em { font-style: italic; color: #4a5568; }
  .section-body hr { border: none; border-top: 1px solid #e2e8f0; margin: 10px 0; }
  .section-body code { background: #f0f4f8; padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 9.5pt; }
  .footer { margin-top: 24px; padding: 10px 28px; border-top: 1px solid #e2e8f0; font-size: 8.5pt; color: #718096; text-align: center; }
  @media print {
    .header { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .signal-badge { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .section { page-break-inside: avoid; }
    .section-body thead { display: table-header-group; }
  }
</style>
</head>
<body>
  <div class="header">
    <div class="header-left">
      <h1>${escapeHtml(analysis.ticker)}</h1>
      <div class="sub">${escapeHtml(analysis.trade_date)} &nbsp;·&nbsp; TradingAgents AI Analysis</div>
    </div>
    <div class="signal-badge">${escapeHtml(analysis.signal ?? 'N/A')}</div>
  </div>
  <div class="meta-block">${metaHtml}</div>
  <div class="content">${sectionsHtml}</div>
  <div class="footer">Generated by TradingAgents &nbsp;·&nbsp; ${analysis.ticker} &nbsp;·&nbsp; ${analysis.trade_date}</div>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) return
  win.document.write(html)
  win.document.close()
  setTimeout(() => win.print(), 400)
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function _metaLines(a: AnalysisResultRead, lang: Lang): string[] {
  const lines: string[] = [
    `${lang === 'tr' ? 'Tarih' : 'Date'}: ${a.trade_date}`,
    `${lang === 'tr' ? 'Sinyal' : 'Signal'}: ${a.signal ?? 'N/A'}`,
  ]
  if (a.llm_provider || a.llm_model) {
    lines.push(`LLM: ${[a.llm_provider, a.llm_model].filter(Boolean).join(' / ')}`)
  }
  if (a.duration_seconds != null) {
    lines.push(`${lang === 'tr' ? 'Süre' : 'Duration'}: ${a.duration_seconds.toFixed(1)}s`)
  }
  if (a.llm_calls != null) {
    lines.push(`${lang === 'tr' ? 'LLM Çağrısı' : 'LLM Calls'}: ${a.llm_calls}`)
  }
  if (a.tokens_in != null && a.tokens_out != null) {
    lines.push(`${lang === 'tr' ? 'Token' : 'Tokens'}: ${(a.tokens_in + a.tokens_out).toLocaleString()} (in ${a.tokens_in.toLocaleString()} / out ${a.tokens_out.toLocaleString()})`)
  }
  return lines
}

function _signalColor(signal: string | null): { bg: string; fg: string } {
  if (!signal) return { bg: '#e2e8f0', fg: '#4a5568' }
  const s = signal.toLowerCase()
  if (s === 'buy' || s === 'overweight') return { bg: '#dcfce7', fg: '#166534' }
  if (s === 'sell' || s === 'underweight') return { bg: '#fee2e2', fg: '#991b1b' }
  return { bg: '#fef9c3', fg: '#854d0e' }
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Converts the subset of Markdown that LLMs typically produce into safe HTML. */
function splitTableRow(line: string): string[] {
  const row = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  const cells: string[] = []
  let cell = ''
  let escaped = false

  for (const char of row) {
    if (escaped) {
      cell += char
      escaped = false
    } else if (char === '\\') {
      escaped = true
    } else if (char === '|') {
      cells.push(cell.trim())
      cell = ''
    } else {
      cell += char
    }
  }
  if (escaped) cell += '\\'
  cells.push(cell.trim())
  return cells
}

function isTableSeparator(line: string): boolean {
  const cells = splitTableRow(line)
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell))
}

function isTableRow(line: string): boolean {
  return line.includes('|') && splitTableRow(line).length > 1
}

function renderTable(headers: string[], rows: string[][]): string {
  const head = headers.map(cell => `<th>${inlineFormat(cell)}</th>`).join('')
  const body = rows.map(row => {
    const cells = headers.map((_, index) => `<td>${inlineFormat(row[index] ?? '')}</td>`).join('')
    return `<tr>${cells}</tr>`
  }).join('')
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
}

/** Converts the supported, safe Markdown subset used by AI reports into HTML. */
export function markdownToHtml(md: string): string {
  const lines = md.split('\n')
  const out: string[] = []
  let inUl = false
  let inOl = false

  const closeList = () => {
    if (inUl) { out.push('</ul>'); inUl = false }
    if (inOl) { out.push('</ol>'); inOl = false }
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]

    // GFM tables need a header row followed by a separator row. Requiring the
    // separator prevents ordinary prose containing a pipe from becoming HTML.
    if (isTableRow(line) && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      closeList()
      const headers = splitTableRow(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && isTableRow(lines[index]) && lines[index].trim() !== '') {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }
      index -= 1
      out.push(renderTable(headers, rows))
      continue
    }

    if (/^#{4,}\s/.test(line)) {
      closeList()
      out.push(`<h4>${inlineFormat(line.replace(/^#+\s*/, ''))}</h4>`)
    } else if (/^###\s/.test(line)) {
      closeList()
      out.push(`<h3>${inlineFormat(line.replace(/^###\s*/, ''))}</h3>`)
    } else if (/^##\s/.test(line)) {
      closeList()
      out.push(`<h3>${inlineFormat(line.replace(/^##\s*/, ''))}</h3>`)
    } else if (/^#\s/.test(line)) {
      closeList()
      out.push(`<h3>${inlineFormat(line.replace(/^#\s*/, ''))}</h3>`)
    } else if (/^[-*]\s/.test(line)) {
      if (!inUl) { closeList(); out.push('<ul>'); inUl = true }
      out.push(`<li>${inlineFormat(line.replace(/^[-*]\s*/, ''))}</li>`)
    } else if (/^\d+\.\s/.test(line)) {
      if (!inOl) { closeList(); out.push('<ol>'); inOl = true }
      out.push(`<li>${inlineFormat(line.replace(/^\d+\.\s*/, ''))}</li>`)
    } else if (/^---+$/.test(line.trim())) {
      closeList()
      out.push('<hr>')
    } else if (line.trim() === '') {
      closeList()
      out.push('')
    } else {
      closeList()
      out.push(`<p>${inlineFormat(line)}</p>`)
    }
  }
  closeList()

  return out.join('\n')
}

function inlineFormat(s: string): string {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}
