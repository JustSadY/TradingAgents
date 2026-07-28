import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'

export interface ActiveTask {
  task_id: string
  ticker: string
  trade_date: string
  asset_type: string
  started_at: number
  status: string
}

function sameTasks(left: ActiveTask[], right: ActiveTask[]): boolean {
  return left.length === right.length && left.every((task, index) => {
    const next = right[index]
    return task.task_id === next.task_id &&
      task.ticker === next.ticker &&
      task.trade_date === next.trade_date &&
      task.asset_type === next.asset_type &&
      task.started_at === next.started_at &&
      task.status === next.status
  })
}

export function useActiveTasks() {
  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([])
  const [loading, setLoading] = useState(true)
  const [unavailable, setUnavailable] = useState(false)
  // StrictMode replays effects in development and a slow endpoint can overlap
  // the 30-second fallback poll.  Keep one request in flight so either case
  // cannot fan out identical `/api/analysis/active` calls.
  const inFlightRef = useRef<Promise<void> | null>(null)

  const refreshActiveTasks = useCallback(() => {
    if (inFlightRef.current) return inFlightRef.current

    const request = axios.get('/api/analysis/active')
      .then(({ data }) => {
        if (!Array.isArray(data)) throw new TypeError('Invalid active-tasks response')
        setActiveTasks(previous => sameTasks(previous, data) ? previous : data)
        setUnavailable(false)
      })
      .catch(error => {
        console.error('Failed to fetch active tasks:', error)
        setUnavailable(true)
      })
      .finally(() => {
        setLoading(false)
        if (inFlightRef.current === request) inFlightRef.current = null
      })
    inFlightRef.current = request
    return request
  }, [])

  useEffect(() => {
    refreshActiveTasks()
    const interval = setInterval(refreshActiveTasks, 30000) // Poll every 30s as fallback
    return () => clearInterval(interval)
  }, [refreshActiveTasks])

  return { activeTasks, loading, unavailable, refreshActiveTasks }
}
