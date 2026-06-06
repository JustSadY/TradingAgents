import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

export interface ActiveTask {
  task_id: string
  ticker: string
  trade_date: string
  asset_type: string
  started_at: number
  status: string
}

export function useActiveTasks() {
  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([])
  const [loading, setLoading] = useState(true)

  const refreshActiveTasks = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/analysis/active')
      setActiveTasks(data)
    } catch (error) {
      console.error('Failed to fetch active tasks:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refreshActiveTasks()
    const interval = setInterval(refreshActiveTasks, 30000) // Poll every 30s as fallback
    return () => clearInterval(interval)
  }, [refreshActiveTasks])

  return { activeTasks, loading, refreshActiveTasks }
}
