import { useCallback } from 'react'
import { useNewsNewsFeed } from '../api/generated/news/news'

interface NewsItem {
  title: string
  url: string
  source: string
  published_at: string
  ticker: string
}

export function useNewsFeed(tickers: string[], limit: number = 4) {
  const tickersKey = tickers.join(',')

  const query = useNewsNewsFeed(
    { tickers: tickersKey, limit },
    { query: { enabled: tickers.length > 0, refetchInterval: 5 * 60 * 1000 } },
  )
  // /api/news/feed items are typed as free-form objects in OpenAPI; the local
  // NewsItem shape above stays the contract consumers render against.
  const news = (query.data ?? []) as unknown as NewsItem[]
  const loading = tickers.length > 0 && query.isPending
  const fetchNews = useCallback(() => query.refetch(), [query])

  return { news, loading, refreshNews: fetchNews }
}
