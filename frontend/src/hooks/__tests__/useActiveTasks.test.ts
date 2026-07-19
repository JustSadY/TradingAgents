import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useActiveTasks } from '../useActiveTasks'

const mockTasks = vi.hoisted(() => [
  { task_id: 'abc-123', ticker: 'AAPL', trade_date: '2026-07-18', asset_type: 'stock', started_at: Date.now(), status: 'running' },
  { task_id: 'def-456', ticker: 'GOOGL', trade_date: '2026-07-18', asset_type: 'stock', started_at: Date.now(), status: 'running' },
])

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  return {
    ...actual,
    default: {
      ...(actual as any).default,
      get: vi.fn().mockResolvedValue({ data: mockTasks }),
      post: vi.fn().mockResolvedValue({ data: {} }),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  }
})

describe('useActiveTasks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches active tasks on mount', async () => {
    const { result } = renderHook(() => useActiveTasks())
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.activeTasks).toHaveLength(2)
    expect(result.current.activeTasks[0].ticker).toBe('AAPL')
  })

  it('provides refreshActiveTasks function', async () => {
    const { result } = renderHook(() => useActiveTasks())
    await waitFor(() => {
      expect(typeof result.current.refreshActiveTasks).toBe('function')
    })
  })

  it('handles API error gracefully', async () => {
    const axios = await import('axios')
    vi.mocked(axios.default.get).mockRejectedValue(new Error('Network error'))
    const { result } = renderHook(() => useActiveTasks())
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.activeTasks).toEqual([])
  })
})
