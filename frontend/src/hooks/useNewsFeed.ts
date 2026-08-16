import { useCallback } from 'react'
import { useNewsNewsFeed } from '../api/generated/news/news'

export function useNewsFeed(tickers: string[], limit: number = 4) {
  const tickersKey = tickers.join(',')

  const query = useNewsNewsFeed(
    { tickers: tickersKey, limit },
    { query: { enabled: tickers.length > 0, refetchInterval: 5 * 60 * 1000 } },
  )
  const news = query.data ?? []
  const loading = tickers.length > 0 && query.isPending
  const fetchNews = useCallback(() => query.refetch(), [query])

  return { news, loading, refreshNews: fetchNews }
}
