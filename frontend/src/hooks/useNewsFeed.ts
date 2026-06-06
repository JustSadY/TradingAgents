import { useState, useEffect, useCallback } from 'react'
import api from '../utils/api'

interface NewsItem {
  title: string
  url: string
  source: string
  published_at: string
  ticker: string
}

export function useNewsFeed(tickers: string[], limit: number = 4) {
  const [news, setNews] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(false)

  const tickersKey = tickers.join(',')

  const fetchNews = useCallback(async () => {
    if (tickers.length === 0) {
      setNews([])
      return
    }
    setLoading(true)
    try {
      const { data } = await api.get('/api/news/feed', {
        params: { tickers: tickersKey, limit }
      })
      setNews(data)
    } catch (error) {
      console.error('Failed to fetch news feed:', error)
    } finally {
      setLoading(false)
    }
  }, [tickersKey, limit])

  useEffect(() => {
    fetchNews()
    const id = setInterval(fetchNews, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [fetchNews])

  return { news, loading, refreshNews: fetchNews }
}
