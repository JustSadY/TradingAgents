import { isRecord } from '../utils/isRecord'
import { readOrderResult, type AnalysisOrderResult } from './orderResult'
import { liveDebateMessages, stringRecord, type LiveDebateMessage } from './streamingReports'

/**
 * The in-progress run, kept in sessionStorage so a reload does not lose it.
 *
 * Two keys, with different jobs. `ta_last_run` is the displayed run; it can be
 * stale or hand-edited, so every field is re-validated on read rather than
 * trusted. `ta_task_running` is the marker that a task is genuinely live, and
 * it is what decides whether a persisted `running` status is still true — a
 * run that was interrupted must not come back looking like it is still going.
 */

export const STORAGE_KEY = 'ta_last_run'
export const TASK_KEY = 'ta_task_running'

export type RunStatus = 'idle' | 'running' | 'done' | 'error'

export type SavedRun = {
  ticker: string
  date: string
  assetType: string
  runStatus: RunStatus
  signal: string | null
  reports: Record<string, string>
  log: string[]
  activeSection: string | null
  analysisId: number | null
  liveDebate: LiveDebateMessage[]
  orderResult: AnalysisOrderResult | null
}

export function emptyRun(): SavedRun {
  return {
    ticker: '', date: new Date().toISOString().slice(0, 10), assetType: 'stock',
    runStatus: 'idle', signal: null, reports: {}, log: [], activeSection: null,
    analysisId: null, liveDebate: [], orderResult: null,
  }
}

export function hasValidRunningTask(): boolean {
  const raw = sessionStorage.getItem(TASK_KEY)
  if (!raw) return false
  try {
    const task = JSON.parse(raw)
    if (isRecord(task) && typeof task.taskId === 'string' && task.taskId.trim()) return true
  } catch {
    // Fall through and remove the bad task marker below.
  }
  sessionStorage.removeItem(TASK_KEY)
  return false
}

// A late start response must never remove a newer task marker.  Only discard
// the marker when it belongs to the response we are deliberately abandoning.
export function clearTaskMarkerFor(taskId: string): void {
  const raw = sessionStorage.getItem(TASK_KEY)
  if (!raw) return
  try {
    const task = JSON.parse(raw)
    if (!isRecord(task) || task.taskId === taskId) {
      sessionStorage.removeItem(TASK_KEY)
    }
  } catch {
    sessionStorage.removeItem(TASK_KEY)
  }
}

export function loadRunState(): SavedRun {
  const fallback = emptyRun()
  try {
    const hasRunningTask = hasValidRunningTask()
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return hasRunningTask ? { ...fallback, runStatus: 'running' } : fallback
    const parsed: unknown = JSON.parse(raw)
    if (!isRecord(parsed)) return fallback

    const savedStatus = parsed.runStatus
    const runStatus: RunStatus = savedStatus === 'error'
      ? 'error'
      : hasRunningTask
        ? 'running'
        : savedStatus === 'idle' || savedStatus === 'done'
          ? savedStatus
          : 'idle'

    return {
      ticker: typeof parsed.ticker === 'string' ? parsed.ticker : fallback.ticker,
      date: typeof parsed.date === 'string' ? parsed.date : fallback.date,
      assetType: typeof parsed.assetType === 'string' && parsed.assetType.trim() ? parsed.assetType : fallback.assetType,
      runStatus,
      signal: typeof parsed.signal === 'string' ? parsed.signal : null,
      reports: stringRecord(parsed.reports),
      log: Array.isArray(parsed.log) ? parsed.log.filter((line): line is string => typeof line === 'string') : [],
      activeSection: typeof parsed.activeSection === 'string' ? parsed.activeSection : null,
      analysisId: typeof parsed.analysisId === 'number' && Number.isSafeInteger(parsed.analysisId) && parsed.analysisId > 0
        ? parsed.analysisId
        : null,
      liveDebate: liveDebateMessages(parsed.liveDebate),
      orderResult: readOrderResult(parsed.orderResult, typeof parsed.ticker === 'string' ? parsed.ticker : fallback.ticker),
    }
  } catch {
    return fallback
  }
}
