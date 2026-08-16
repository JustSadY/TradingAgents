import { isRecord } from '../utils/isRecord'

/**
 * Which current agent key a streamed token writes into, and which fields the
 * Reports tab shows.
 *
 * The backend owns agent identifiers. Token callbacks attach the current
 * `AgentInfo.key` as metadata, so this map intentionally contains only the
 * canonical keys that can produce report content now. Historical callback
 * aliases must not accumulate here.
 */

export type LiveDebateMessage = { sender: string; content: string; type: string }

/** The built-in fields, in the order the Reports tab has always shown them. */
export const KNOWN_REPORT_KEYS = [
  'market_report', 'sentiment_report', 'news_report',
  'fundamentals_report', 'macro_report', 'options_report',
  'quant_report', 'earnings_report', 'insider_report',
  'ownership_report', 'ratings_report', 'short_interest_report',
  'valuation_report', 'catalyst_report', 'review_report',
  'synthesis_report', 'audit_report', 'agent_qa_report',
] as const

export function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {}
  const reports: Record<string, string> = {}
  for (const [section, report] of Object.entries(value)) {
    if (typeof report === 'string') reports[section] = report
  }
  return reports
}

/** Built-in fields first in their familiar order, then any extras, sorted. */
export function visibleReportEntries(value: unknown): Array<[string, string]> {
  if (!isRecord(value)) return []

  const readable = (key: string): string | null => {
    const report = value[key]
    return typeof report === 'string' && report.trim() ? report : null
  }
  const known = KNOWN_REPORT_KEYS.flatMap(key => {
    const report = readable(key)
    return report === null ? [] : [[key, report] as [string, string]]
  })
  const knownKeys = new Set<string>(KNOWN_REPORT_KEYS)
  const extra = Object.keys(value)
    .filter(key => key.endsWith('_report') && !knownKeys.has(key))
    .sort()
    .flatMap(key => {
      const report = readable(key)
      return report === null ? [] : [[key, report] as [string, string]]
    })
  return [...known, ...extra]
}

export function readableSectionLabel(sectionLabels: Record<string, string>, key: string): string {
  const configured = sectionLabels[key]
  if (configured) return configured
  // Preserve the existing fallback for built-in API fields while metadata is
  // still loading. New registry fields get a readable fallback below.
  if ((KNOWN_REPORT_KEYS as readonly string[]).includes(key)) return key
  return key
    .replace(/_report$/, '')
    .split('_')
    .filter(Boolean)
    .map(part => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(' ')
}

/** Map current streaming agent keys to their report fields. */
export const STREAMING_REPORT_KEYS: Record<string, string> = {
  market: 'market_report',
  social: 'sentiment_report',
  news: 'news_report',
  fundamentals: 'fundamentals_report',
  macro: 'macro_report',
  options: 'options_report',
  quant: 'quant_report',
  earnings: 'earnings_report',
  insider: 'insider_report',
  ownership: 'ownership_report',
  ratings: 'ratings_report',
  short_interest: 'short_interest_report',
  valuation: 'valuation_report',
  catalyst: 'catalyst_report',
  review: 'review_report',
  synthesis_manager: 'synthesis_report',
  auditor: 'audit_report',
  agent_qa: 'agent_qa_report',
  portfolio_manager: 'final_decision',
  research_manager: 'investment_plan',
}

/**
 * Resolve an agent key to its report field. Normalisation is retained only for
 * harmless transport spelling differences; retired semantic aliases are not.
 * `thinking` and `system` are status chatter, not reports.
 */
export function reportKeyForStreamingAgent(agent: string): string | null {
  const normalized = agent
    .trim()
    .replace(/([a-z])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .replace(/[\s-]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '')
  if (!normalized || normalized === 'thinking' || normalized === 'system') return null
  return STREAMING_REPORT_KEYS[normalized]
    ?? (normalized.endsWith('_report') ? normalized : null)
}

export function liveDebateMessages(value: unknown): LiveDebateMessage[] {
  if (!Array.isArray(value)) return []
  return value.flatMap(item => {
    if (!isRecord(item) || typeof item.sender !== 'string' || typeof item.content !== 'string' || typeof item.type !== 'string') return []
    return [{ sender: item.sender, content: item.content, type: item.type }]
  })
}
