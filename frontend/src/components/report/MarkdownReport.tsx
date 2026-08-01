import type { ReactNode } from 'react'

interface MarkdownReportProps {
  content: string
  className?: string
}

/**
 * A deliberately small, safe Markdown renderer for AI report text.
 *
 * Report content is untrusted model output.  Rendering it as React text and
 * elements (rather than injecting generated HTML) means embedded HTML,
 * scripts, event handlers, and unsafe URLs remain inert text.  The supported
 * subset covers the structures the report prompts produce most often:
 * headings, paragraphs, lists, tables, blockquotes, code, links, and simple
 * inline emphasis.
 */
export function MarkdownReport({ content, className = '' }: MarkdownReportProps) {
  return (
    <div className={`markdown-report text-sm leading-7 text-slate-300 break-words ${className}`}>
      {renderBlocks(content)}
    </div>
  )
}

function renderBlocks(content: string): ReactNode[] {
  const lines = content.replace(/\r\n?/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let blockIndex = 0

  const blockKey = () => {
    blockIndex += 1
    return `markdown-block-${blockIndex}`
  }

  while (index < lines.length) {
    const line = lines[index]

    if (line.trim() === '') {
      index += 1
      continue
    }

    const fence = line.match(/^\s*```\s*([^\s`]*)?\s*$/)
    if (fence) {
      const language = fence[1]
      index += 1
      const codeLines: string[] = []
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) index += 1

      blocks.push(
        <pre key={blockKey()} className="my-4 overflow-x-auto rounded-xl border border-white/[0.08] bg-black/35 p-4 text-xs leading-6 text-slate-200">
          {language && <span className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-violet-300/80">{language}</span>}
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    if (isTableHeader(lines, index)) {
      const headers = splitTableRow(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && isTableRow(lines[index]) && lines[index].trim() !== '') {
        rows.push(splitTableRow(lines[index]))
        index += 1
      }

      blocks.push(
        <div key={blockKey()} className="my-4 overflow-x-auto rounded-xl border border-white/[0.08]">
          <table className="w-full min-w-[420px] border-collapse text-left text-xs leading-6">
            <thead className="bg-white/[0.05] text-slate-100">
              <tr>
                {headers.map((header, columnIndex) => (
                  <th key={`header-${columnIndex}`} className="border-b border-white/[0.08] px-3 py-2.5 font-bold">
                    {renderInline(header, `table-header-${columnIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.05]">
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`} className="align-top transition-colors hover:bg-white/[0.025]">
                  {headers.map((_, columnIndex) => (
                    <td key={`cell-${rowIndex}-${columnIndex}`} className="px-3 py-2 text-slate-300">
                      {renderInline(row[columnIndex] ?? '', `table-cell-${rowIndex}-${columnIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      const headingClass = level === 1
        ? 'mt-6 mb-3 text-xl font-extrabold tracking-tight text-white'
        : level === 2
          ? 'mt-6 mb-2 text-lg font-bold text-white'
          : 'mt-5 mb-2 text-base font-bold text-slate-100'
      const headingContent = renderInline(heading[2], `heading-${blockIndex}`)
      const key = blockKey()
      if (level === 1) blocks.push(<h1 key={key} className={headingClass}>{headingContent}</h1>)
      else if (level === 2) blocks.push(<h2 key={key} className={headingClass}>{headingContent}</h2>)
      else if (level === 3) blocks.push(<h3 key={key} className={headingClass}>{headingContent}</h3>)
      else blocks.push(<h4 key={key} className={headingClass}>{headingContent}</h4>)
      index += 1
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ''))
        index += 1
      }
      blocks.push(
        <blockquote key={blockKey()} className="my-4 border-l-2 border-violet-400/70 bg-violet-500/[0.06] px-4 py-3 text-slate-300">
          {renderLines(quoteLines, 'quote')}
        </blockquote>,
      )
      continue
    }

    if (isUnorderedListItem(line)) {
      const items: string[] = []
      while (index < lines.length && isUnorderedListItem(lines[index])) {
        items.push(lines[index].replace(/^\s*[-+*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={blockKey()} className="my-3 list-disc space-y-1 pl-5 marker:text-violet-300">
          {items.map((item, itemIndex) => <li key={`ul-${itemIndex}`}>{renderInline(item, `ul-${itemIndex}`)}</li>)}
        </ul>,
      )
      continue
    }

    if (isOrderedListItem(line)) {
      const items: string[] = []
      while (index < lines.length && isOrderedListItem(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ol key={blockKey()} className="my-3 list-decimal space-y-1 pl-5 marker:font-semibold marker:text-violet-300">
          {items.map((item, itemIndex) => <li key={`ol-${itemIndex}`}>{renderInline(item, `ol-${itemIndex}`)}</li>)}
        </ol>,
      )
      continue
    }

    if (/^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={blockKey()} className="my-5 border-0 border-t border-white/[0.08]" />)
      index += 1
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length && lines[index].trim() !== '' && !startsBlock(lines, index)) {
      paragraphLines.push(lines[index])
      index += 1
    }

    // `startsBlock` is false for the first normal prose line.  This fallback
    // keeps parsing progressing if future Markdown input introduces a form we
    // intentionally render as plain text.
    if (paragraphLines.length === 0) {
      paragraphLines.push(lines[index])
      index += 1
    }

    blocks.push(
      <p key={blockKey()} className="my-3 whitespace-normal">
        {renderLines(paragraphLines, `paragraph-${blockIndex}`)}
      </p>,
    )
  }

  return blocks
}

function renderLines(lines: string[], keyPrefix: string): ReactNode[] {
  return lines.flatMap((line, index) => {
    const nodes = renderInline(line, `${keyPrefix}-${index}`)
    return index < lines.length - 1 ? [...nodes, <br key={`${keyPrefix}-break-${index}`} />] : nodes
  })
}

function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index]
  return Boolean(
    /^\s*```/.test(line)
    || isTableHeader(lines, index)
    || /^(#{1,4})\s+/.test(line)
    || /^\s*>\s?/.test(line)
    || isUnorderedListItem(line)
    || isOrderedListItem(line)
    || /^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line),
  )
}

function isUnorderedListItem(line: string): boolean {
  return /^\s*[-+*]\s+/.test(line)
}

function isOrderedListItem(line: string): boolean {
  return /^\s*\d+[.)]\s+/.test(line)
}

function isTableHeader(lines: string[], index: number): boolean {
  return isTableRow(lines[index]) && index + 1 < lines.length && isTableSeparator(lines[index + 1])
}

function isTableRow(line: string): boolean {
  return line.includes('|') && splitTableRow(line).length > 1
}

function isTableSeparator(line: string): boolean {
  const cells = splitTableRow(line)
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell))
}

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

function renderInline(value: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(`[^`\n]*`|!\[[^\]\n]*\]\([^)\n]+\)|\[[^\]\n]+\]\([^)\n]+\)|\*\*[^*\n]+?\*\*|__[^_\n]+?__|\*[^*\n]+?\*|_[^_\n]+?_)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let tokenIndex = 0

  while ((match = pattern.exec(value)) !== null) {
    if (match.index > lastIndex) nodes.push(value.slice(lastIndex, match.index))

    const token = match[0]
    const key = `${keyPrefix}-${tokenIndex}`
    tokenIndex += 1

    if (token.startsWith('`')) {
      nodes.push(<code key={key} className="rounded bg-black/35 px-1.5 py-0.5 font-mono text-[0.9em] text-violet-200">{token.slice(1, -1)}</code>)
    } else {
      const image = token.match(/^!\[([^\]]*)\]\((.+)\)$/)
      const link = token.match(/^\[([^\]]+)\]\((.+)\)$/)
      if (image) {
        const src = safeImageSrc(image[2])
        if (src) {
          nodes.push(
            <img
              key={key}
              src={src}
              alt={image[1]}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
              className="my-3 max-h-[34rem] max-w-full rounded-xl border border-white/[0.08] bg-black/20 object-contain"
            />,
          )
        } else {
          nodes.push(image[1] || 'Image')
        }
      } else if (link) {
        const href = safeLinkHref(link[2])
        if (href) {
          nodes.push(
            <a key={key} href={href} target="_blank" rel="noreferrer noopener" className="font-medium text-violet-300 underline decoration-violet-400/45 underline-offset-2 transition-colors hover:text-violet-200">
              {renderInline(link[1], `${key}-label`)}
            </a>,
          )
        } else {
          nodes.push(link[1])
        }
      } else if (token.startsWith('**') || token.startsWith('__')) {
        nodes.push(<strong key={key} className="font-bold text-slate-100">{renderInline(token.slice(2, -2), `${key}-strong`)}</strong>)
      } else {
        nodes.push(<em key={key} className="italic text-slate-200">{renderInline(token.slice(1, -1), `${key}-em`)}</em>)
      }
    }

    lastIndex = pattern.lastIndex
  }

  if (lastIndex < value.length) nodes.push(value.slice(lastIndex))
  return nodes
}

function safeLinkHref(value: string): string | null {
  const href = value.trim()
  const lower = href.toLowerCase()
  if (!href || Array.from(href).some(char => char.charCodeAt(0) < 32)) return null
  if (lower.startsWith('https://') || lower.startsWith('http://') || lower.startsWith('mailto:')) return href
  if (/^(?:\/(?!\/)|\.\.?\/|#)/.test(href)) return href
  return null
}

function safeImageSrc(value: string): string | null {
  const src = safeLinkHref(value)
  if (!src || src.startsWith('mailto:') || src.startsWith('#')) return null
  return src
}
