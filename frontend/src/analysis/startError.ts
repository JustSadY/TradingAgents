import type { AnalysisStartError, TickerSuggestion } from '../components/analysis/AnalysisControls'
import { isRecord } from '../utils/isRecord'

/**
 * Turn a rejected "start analysis" request into something the controls can
 * show. The interesting case is an unknown ticker: the backend answers with a
 * structured detail carrying candidate symbols, so the user gets a list to
 * pick from rather than a dead end. Anything else degrades to a plain message.
 */

export function tickerSuggestions(value: unknown): TickerSuggestion[] {
  if (!Array.isArray(value)) return []
  return value.flatMap(item => {
    if (!isRecord(item) || typeof item.symbol !== 'string' || !item.symbol.trim()) return []
    return [{
      symbol: item.symbol.trim().toUpperCase(),
      name: typeof item.name === 'string' ? item.name : null,
      quote_type: typeof item.quote_type === 'string' ? item.quote_type : null,
    }]
  })
}

export function analysisStartError(error: unknown, fallback: string): AnalysisStartError {
  const response = error as { response?: { data?: { detail?: unknown } } }
  const detail = response.response?.data?.detail
  if (isRecord(detail)) {
    return {
      code: typeof detail.code === 'string' ? detail.code : undefined,
      message: typeof detail.message === 'string' && detail.message.trim() ? detail.message : fallback,
      ticker: typeof detail.ticker === 'string' ? detail.ticker : undefined,
      suggestions: tickerSuggestions(detail.suggestions),
    }
  }
  return {
    message: typeof detail === 'string' && detail.trim() ? detail : fallback,
    suggestions: [],
  }
}
