import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useMeta, triggerMetaRefetch, type Meta } from '../useMeta'

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
  return {
    ...actual,
    default: {
      ...(actual as any).default,
      get: vi.fn().mockResolvedValue({ data: mockMeta }),
      post: vi.fn().mockResolvedValue({ data: {} }),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  }
})

describe('useMeta', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns null initially', () => {
    const { result } = renderHook(() => useMeta())
    expect(result.current).toBeNull()
  })

  it('fetches and returns meta data', async () => {
    const { result } = renderHook(() => useMeta())
    await waitFor(() => {
      expect(result.current).not.toBeNull()
    })
    expect(result.current?.analysts).toHaveLength(1)
    expect(result.current?.analysts[0].key).toBe('market')
  })

  it('caches meta across multiple hook calls', async () => {
    const { result: r1 } = renderHook(() => useMeta())
    await waitFor(() => {
      expect(r1.current).not.toBeNull()
    })
    const { result: r2 } = renderHook(() => useMeta())
    expect(r2.current).not.toBeNull()
    expect(r2.current?.signals[0].value).toBe('Buy')
  })

  it('triggerMetaRefetch resets cache and re-fetches', async () => {
    const { result } = renderHook(() => useMeta())
    await waitFor(() => {
      expect(result.current).not.toBeNull()
    })
    const axios = await import('axios')
    const getSpy = vi.mocked(axios.default.get)
    getSpy.mockClear()
    triggerMetaRefetch()
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith('/api/meta')
    })
  })
})
