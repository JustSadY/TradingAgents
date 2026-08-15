import type { Root as HastRoot } from 'hast'
import type { Heading, Root } from 'mdast'
import rehypeStringify from 'rehype-stringify'
import remarkGfm from 'remark-gfm'
import remarkParse from 'remark-parse'
import remarkRehype from 'remark-rehype'
import { unified } from 'unified'
import { visit } from 'unist-util-visit'
import i18n from '../i18n'
import { REPORT_SECTIONS } from '../report/reportSections'
import { safeImageSrc, safeLinkHref } from './safeUrl'
import type { AnalysisResultRead } from '../api/generated/model'

type Lang = 'en' | 'tr'

/**
 * Export order and headings both come from the shared section registry.
 *
 * The registry array is in share-page order, so documents sort by the explicit
 * `exportOrder` instead of reusing the array sequence.
 */
const EXPORT_SECTIONS = REPORT_SECTIONS
  .filter(section => section.exportLabelKey)
  .sort((a, b) => (a.exportOrder ?? 0) - (b.exportOrder ?? 0))
const SECTION_ORDER = EXPORT_SECTIONS.map(section => section.key)

/**
 * Heading for a section in a downloaded document.
 *
 * Resolved for the language the user picked for this export, which is not
 * necessarily the language the app is currently displaying, so the lookup is
 * pinned with `lng` rather than reading the active locale.
 */
function sectionHeading(key: string, language: Lang): string {
  const section = EXPORT_SECTIONS.find(entry => entry.key === key)
  if (!section?.exportLabelKey) return key
  return i18n.t(section.exportLabelKey, { lng: language, defaultValue: section.fallbackLabel })
}

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
    lines.push(`## ${sectionHeading(key, language)}`, '', content, '', '---', '')
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
  const meta = _metaLines(analysis, language)

  const metaHtml = meta.map(l => `<p class="meta-line">${escapeHtml(l)}</p>`).join('')

  let sectionsHtml = ''
  for (const { key, content } of buildExportSections(analysis)) {
    sectionsHtml += `
      <div class="section">
        <h2>${escapeHtml(sectionHeading(key, language))}</h2>
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

/** Escapes text interpolated into the printable page's own HTML template. */
function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ))
}

/**
 * Converts report Markdown into printable HTML.
 *
 * Shares the remark parser that {@link MarkdownReport} renders on screen, so an
 * exported report matches what the user saw. The previous hand-written
 * converter silently dropped blockquotes and mangled fenced code blocks, which
 * the on-screen renderer has always supported.
 *
 * Report text is untrusted model output, so `allowDangerousHtml` stays off:
 * remark-rehype drops raw HTML nodes rather than passing them through, and
 * rehype-stringify escapes the remaining text.
 */
export function markdownToHtml(md: string): string {
  const file = printableMarkdown.processSync(md)
  return String(file)
}

/**
 * The printable page emits each report section as an `<h2>`, so report headings
 * start one level below it instead of competing with it. Depth is clamped at
 * `h4` because the print stylesheet only styles `h3` and `h4`; anything deeper
 * would render unstyled.
 */
function demoteHeadings() {
  return (tree: Root) => {
    visit(tree, 'heading', node => {
      node.depth = Math.min(4, node.depth + 2) as Heading['depth']
    })
  }
}

/**
 * Turns raw HTML nodes into literal text before they reach rehype.
 *
 * `remark-rehype` drops `html` nodes when `allowDangerousHtml` is off, which is
 * safe but silently deletes the markup from the output. react-markdown instead
 * shows it as text, so without this the exported report and the on-screen one
 * disagree about content the model emitted — exactly the divergence this shared
 * pipeline exists to remove. Keeping it visible is also the more honest
 * rendering: a report that contains a `<script>` tag should show that it does.
 */
function htmlAsText() {
  return (tree: Root) => {
    visit(tree, 'html', (node, index, parent) => {
      if (!parent || index === null || index === undefined) return
      parent.children[index] = { type: 'text', value: node.value } as never
    })
  }
}

/**
 * Applies the same link and image policy the on-screen renderer uses.
 *
 * `remark-rehype` does no URL sanitisation of its own, so without this a model
 * could emit a `javascript:` target straight into the printable page. Sharing
 * the predicates with {@link MarkdownReport} keeps one policy rather than two
 * that can drift.
 */
function sanitizeUrls() {
  return (tree: HastRoot) => {
    visit(tree, 'element', node => {
      if (node.tagName === 'a' && typeof node.properties?.href === 'string') {
        const safe = safeLinkHref(node.properties.href)
        if (safe) node.properties.href = safe
        else delete node.properties.href
      }
      if (node.tagName === 'img' && typeof node.properties?.src === 'string') {
        const safe = safeImageSrc(node.properties.src)
        if (safe) node.properties.src = safe
        else delete node.properties.src
      }
    })
  }
}

const printableMarkdown = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(demoteHeadings)
  .use(htmlAsText)
  .use(remarkRehype)
  .use(sanitizeUrls)
  .use(rehypeStringify)
