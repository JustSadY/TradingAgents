import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import axios from 'axios'
import { useNewsFeed } from '../useNewsFeed'
import { QueryWrapper } from '../../test/renderWithQuery'

const mockNews = vi.hoisted(() => [
  { title: 'AAPL hits新高', url: 'https://example.com', source: 'Yahoo', published_at: '2026-07-18T12:00:00Z', ticker: 'AAPL' },
  { title: 'GOOGL earnings', url: 'https://example.com', source: 'Reuters', published_at: '2026-07-18T11:00:00Z', ticker: 'GOOGL' },
])

// The hook now goes through the generated client, which uses the global
// axios mock installed in src/test/setup.ts.

describe('useNewsFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(axios.get).mockResolvedValue({ data: mockNews })
  })

  it('returns empty news when tickers is empty', async () => {
    const { result } = renderHook(() => useNewsFeed([]), { wrapper: QueryWrapper })
    expect(result.current.news).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  it('fetches news for given tickers', async () => {
    const { result } = renderHook(() => useNewsFeed(['AAPL', 'GOOGL']), { wrapper: QueryWrapper })
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.news).toHaveLength(2)
    expect(result.current.news[0].ticker).toBe('AAPL')
  })

  it('passes correct params to API', async () => {
    renderHook(() => useNewsFeed(['AAPL'], 5), { wrapper: QueryWrapper })
    await waitFor(() => {
      // The generated client sends query params as config.params.
      expect(axios.get).toHaveBeenCalledWith(
        '/api/news/feed',
        expect.objectContaining({ params: { tickers: 'AAPL', limit: 5 } }),
      )
    })
  })

  it('provides refreshNews function', async () => {
    const { result } = renderHook(() => useNewsFeed(['AAPL']), { wrapper: QueryWrapper })
    expect(typeof result.current.refreshNews).toBe('function')
  })
})
