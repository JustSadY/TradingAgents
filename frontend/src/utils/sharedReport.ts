/**
 * Turn JSON-backed historic report fields into readable text.  Old rows can
 * contain newline strings, JSON-encoded arrays, or JSON-column values.
 */
export function formatSharedReportValue(value: unknown): string {
  if (value == null) return ''

  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return ''
    if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
      try {
        return formatSharedReportValue(JSON.parse(trimmed))
      } catch {
        // This is normal prose that happens to start with a bracket.
      }
    }
    return trimmed
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return ''
    return value
      .map(item => formatSharedReportValue(item))
      .filter(Boolean)
      .join('\n\n')
  }

  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (Object.keys(record).length === 0) return ''
    const sender = record.sender ?? record.agent ?? record.role
    const content = record.content ?? record.message ?? record.text
    if (typeof content === 'string') {
      const prefix = typeof sender === 'string' && sender.trim() ? `${sender.trim()}: ` : ''
      return `${prefix}${content.trim()}`.trim()
    }
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return ''
    }
  }

  return String(value)
}
