import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { queryClient } from '../../api/queryClient'
import { getMetaGetMetaQueryKey } from '../../api/generated/meta/meta'
import { clearMetaCache, useMeta, triggerMetaRefetch, type Meta } from '../useMeta'

const mockMeta = vi.hoisted((): Meta => ({
  analysts: [{ key: 'market', label: 'Market Analyst', description: 'Analyzes market', default: true }],
  tools: [],
  signals: [{ value: 'Buy', label: 'Buy', tone: 'positive' }],
  section_labels: {},
  asset_types: [],
  languages: [],
  data_vendors: [],
  trading_modes: [],
  brokers: [],
  provider_labels: {},
  webhook_events: [],
  memory_stores: [],
  embedders: [],
  page_keys: [],
  setting_keys: [],
}))

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  const get = vi.fn().mockResolvedValue({ data: mockMeta })
  const post = vi.fn().mockResolvedValue({ data: {} })
  // The generated meta query calls axios(config); route it to the same mocks.
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

// useMeta's clearMetaCache/triggerMetaRefetch act on the app's singleton client,
// so the hook must read from that same client rather than a per-test one.
const wrapper = ({ children }: { children: ReactNode }) =>
  createElement(QueryClientProvider, { client: queryClient }, children)

describe('useMeta', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clearMetaCache()
  })

  it('returns null initially', () => {
    const { result } = renderHook(() => useMeta(), { wrapper })
    expect(result.current).toBeNull()
  })

  it('fetches and returns meta data', async () => {
    const { result } = renderHook(() => useMeta(), { wrapper })
    await waitFor(() => {
      expect(result.current).not.toBeNull()
    })
    expect(result.current?.analysts).toHaveLength(1)
    expect(result.current?.analysts[0].key).toBe('market')
  })

  it('caches meta across multiple hook calls', async () => {
    const { result: r1 } = renderHook(() => useMeta(), { wrapper })
    await waitFor(() => {
      expect(r1.current).not.toBeNull()
    })
    const { result: r2 } = renderHook(() => useMeta(), { wrapper })
    expect(r2.current).not.toBeNull()
    expect(r2.current?.signals[0].value).toBe('Buy')
  })

  it('triggerMetaRefetch resets cache and re-fetches', async () => {
    const { result } = renderHook(() => useMeta(), { wrapper })
    await waitFor(() => {
      expect(result.current).not.toBeNull()
    })
    const axios = await import('axios')
    const getSpy = vi.mocked(axios.default.get)
    getSpy.mockClear()
    triggerMetaRefetch()
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/meta', expect.anything())
    })
  })

  it('clears cached metadata for an account change', async () => {
    const { result } = renderHook(() => useMeta(), { wrapper })
    await waitFor(() => {
      expect(result.current).not.toBeNull()
    })

    act(() => clearMetaCache())

    // The previous account's entry is dropped outright. No refetch is expected
    // here: on logout there is no session to fetch under, and anything shown
    // later must come from a request made by the next account.
    expect(queryClient.getQueryData(getMetaGetMetaQueryKey())).toBeUndefined()
  })
})
