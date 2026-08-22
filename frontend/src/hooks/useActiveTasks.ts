import { useCallback } from 'react'
import { useAnalysisGetActiveTasks } from '../api/generated/analysis/analysis'

export interface ActiveTask {
  task_id: string
  ticker: string
  trade_date: string
  asset_type: string
  started_at: number
  status: string
}

const EMPTY: ActiveTask[] = []

/**
 * Poll the analyses currently running for this user.
 *
 * The previous implementation kept an in-flight ref so StrictMode's replayed
 * effects and the 30s fallback poll could not fan out duplicate requests, and
 * compared task lists by hand to avoid re-rendering on identical payloads.
 * TanStack Query already deduplicates concurrent identical queries and applies
 * structural sharing, so both are handled by the client rather than here.
 */
export function useActiveTasks() {
  const query = useAnalysisGetActiveTasks({
    query: {
      // Engine Status describes the server, not this browser tab: a run may
      // have been started from another device, or before this tab existed.
      // The shared client defaults (30s staleTime, no refetch on focus) let
      // that state sit stale, so the panel could show Idle for half a minute
      // while an analysis was running. Revalidate whenever the page is
      // mounted or looked at, and poll quickly while something is running.
      refetchInterval: query => (query.state.data as unknown[] | undefined)?.length ? 5_000 : 15_000,
      refetchIntervalInBackground: false,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
      refetchOnMount: 'always',
      staleTime: 0,
    },
  })

  // A malformed payload is treated the same as a failed request: callers gate
  // UI on `unavailable`, and rendering a non-array would throw downstream.
  const payload = query.data
  const valid = Array.isArray(payload)
  const activeTasks = (valid ? payload : EMPTY) as ActiveTask[]

  const refreshActiveTasks = useCallback(() => query.refetch(), [query])

  return {
    activeTasks,
    loading: query.isPending,
    unavailable: Boolean(query.error) || (!query.isPending && !valid),
    refreshActiveTasks,
  }
}
