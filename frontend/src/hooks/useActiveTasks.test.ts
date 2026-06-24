import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import axios from 'axios'
import { useActiveTasks } from './useActiveTasks'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))

const mockedGet = vi.mocked(axios.get)

const task = {
  task_id: 't-1',
  ticker: 'AAPL',
  trade_date: '2026-06-12',
  asset_type: 'stock',
  started_at: 0,
  status: 'running',
}

describe('useActiveTasks', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => vi.restoreAllMocks())

  it('fetches active tasks on mount', async () => {
    mockedGet.mockResolvedValue({ data: [task] })
    const { result } = renderHook(() => useActiveTasks())

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeTasks).toEqual([task])
    expect(mockedGet).toHaveBeenCalledWith('/api/analysis/active')
  })

  it('keeps an empty list and stops loading when the fetch fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    mockedGet.mockRejectedValue(new Error('network down'))
    const { result } = renderHook(() => useActiveTasks())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeTasks).toEqual([])
  })

  it('refreshActiveTasks refetches on demand', async () => {
    mockedGet.mockResolvedValueOnce({ data: [] }).mockResolvedValueOnce({ data: [task] })
    const { result } = renderHook(() => useActiveTasks())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeTasks).toEqual([])

    await act(() => result.current.refreshActiveTasks())
    expect(result.current.activeTasks).toEqual([task])
  })
})
