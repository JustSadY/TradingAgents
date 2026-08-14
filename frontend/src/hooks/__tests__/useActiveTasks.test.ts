import { describe, it, expect, vi, beforeEach } from 'vitest'
import { StrictMode, createElement, type ReactNode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { useActiveTasks } from '../useActiveTasks'
import { QueryWrapper } from '../../test/renderWithQuery'

// StrictMode replays effects; the query provider still has to be above the hook.
const StrictQueryWrapper = ({ children }: { children: ReactNode }) =>
  createElement(QueryWrapper, null, createElement(StrictMode, null, children))
import axios from 'axios'

const mockTasks = vi.hoisted(() => [
  { task_id: 'abc-123', ticker: 'AAPL', trade_date: '2026-07-18', asset_type: 'stock', started_at: Date.now(), status: 'running' },
  { task_id: 'def-456', ticker: 'GOOGL', trade_date: '2026-07-18', asset_type: 'stock', started_at: Date.now(), status: 'running' },
])

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  const get = vi.fn().mockResolvedValue({ data: mockTasks })
  const post = vi.fn().mockResolvedValue({ data: {} })
  // The generated query calls axios(config); route it to the same mocks.
  const instance = Object.assign(
    vi.fn((config: { url?: string; method?: string } = {}) =>
      String(config.method ?? 'get').toLowerCase() === 'get' ? get(config.url, config) : post(config.url, config),
    ),
    {
      ...(actual as any).default,
      get,
      post,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  )
  return { ...actual, default: instance }
})

describe('useActiveTasks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(axios.get).mockResolvedValue({ data: mockTasks } as any)
  })

  it('fetches active tasks on mount', async () => {
    const { result } = renderHook(() => useActiveTasks(), { wrapper: QueryWrapper })
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.activeTasks).toHaveLength(2)
    expect(result.current.activeTasks[0].ticker).toBe('AAPL')
  })

  it('provides refreshActiveTasks function', async () => {
    const { result } = renderHook(() => useActiveTasks(), { wrapper: QueryWrapper })
    await waitFor(() => {
      expect(typeof result.current.refreshActiveTasks).toBe('function')
    })
  })

  it('handles API error gracefully', async () => {
    vi.mocked(axios.get).mockRejectedValue(new Error('Network error'))
    const { result } = renderHook(() => useActiveTasks(), { wrapper: QueryWrapper })
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.activeTasks).toEqual([])
    expect(result.current.unavailable).toBe(true)
  })

  it('shares the initial request across StrictMode effect replay', async () => {
    const { result } = renderHook(() => useActiveTasks(), { wrapper: StrictQueryWrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(axios.get).toHaveBeenCalledTimes(1)
  })

  it('treats a non-array response as unavailable instead of propagating it to consumers', async () => {
    vi.mocked(axios.get).mockResolvedValue({ data: { unexpected: true } } as any)
    const { result } = renderHook(() => useActiveTasks(), { wrapper: QueryWrapper })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.activeTasks).toEqual([])
    expect(result.current.unavailable).toBe(true)
  })
})
