import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useNewsFeed } from '../useNewsFeed'

const mockNews = vi.hoisted(() => [
  { title: 'AAPL hits新高', url: 'https://example.com', source: 'Yahoo', published_at: '2026-07-18T12:00:00Z', ticker: 'AAPL' },
  { title: 'GOOGL earnings', url: 'https://example.com', source: 'Reuters', published_at: '2026-07-18T11:00:00Z', ticker: 'GOOGL' },
])

vi.mock('../../utils/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: mockNews }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  },
}))

describe('useNewsFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns empty news when tickers is empty', async () => {
    const { result } = renderHook(() => useNewsFeed([]))
    expect(result.current.news).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  it('fetches news for given tickers', async () => {
    const { result } = renderHook(() => useNewsFeed(['AAPL', 'GOOGL']))
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.news).toHaveLength(2)
    expect(result.current.news[0].ticker).toBe('AAPL')
  })

  it('passes correct params to API', async () => {
    const apiMock = (await import('../../utils/api')).default
    renderHook(() => useNewsFeed(['AAPL'], 5))
    await waitFor(() => {
      expect(apiMock.get).toHaveBeenCalledWith('/api/news/feed', {
        params: { tickers: 'AAPL', limit: 5 },
      })
    })
  })

  it('provides refreshNews function', async () => {
    const { result } = renderHook(() => useNewsFeed(['AAPL']))
    expect(typeof result.current.refreshNews).toBe('function')
  })
})
