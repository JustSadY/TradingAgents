import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { Plus, Trash2, RefreshCw, Star, TrendingUp } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

export default function Watchlist() {
  const [tickers, setTickers] = useState<string[]>([])
  const [prices, setPrices] = useState<Record<string, { price: number; change_percent: number }>>({})
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const { t } = useTranslation()

  const fetchPrices = useCallback(async (tickersList: string[]) => {
    if (tickersList.length === 0) {
      setPrices({})
      return
    }
    try {
      const { data } = await axios.get<Record<string, { price: number; change_percent: number }>>('/api/watchlist/prices')
      setPrices(data || {})
    } catch (e) {
      console.error('Failed to fetch watchlist prices:', e)
    }
  }, [])

  const fetchWatchlist = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const { data } = await axios.get<string[]>('/api/watchlist')
      setTickers(data || [])
      await fetchPrices(data || [])
    } catch (e) {
      console.error('Failed to fetch watchlist:', e)
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [fetchPrices])

  useEffect(() => {
    const doFetch = async () => {
      await fetchWatchlist()
    }
    doFetch()
    const interval = setInterval(() => {
      fetchWatchlist(true)
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchWatchlist])

  const add = async () => {
    if (!input.trim()) return
    try {
      const res = await axios.post<string[]>(`/api/watchlist/${input.trim().toUpperCase()}`)
      setTickers(res.data)
      setInput('')
      await fetchPrices(res.data)
    } catch (e) {
      console.error(e)
    }
  }

  const remove = async (tickerVal: string) => {
    try {
      const res = await axios.delete<string[]>(`/api/watchlist/${tickerVal}`)
      setTickers(res.data)
      setPrices(prev => {
        const next = { ...prev }
        delete next[tickerVal]
        return next
      })
    } catch (e) {
      console.error(e)
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header Panel */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Star className="text-violet-400 fill-violet-400/20" size={20} />
            {t('watchlist.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">Track and monitor your favorite assets and prompt live analyses</p>
        </div>
        <button
          onClick={() => fetchWatchlist(false)}
          disabled={loading}
          className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Add Ticker Section */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="text-xs font-bold text-violet-400 uppercase tracking-widest">{t('watchlist.add') || 'Add New Asset'}</h3>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            className="flex-1 glass-input rounded-xl px-4 py-2.5 text-sm uppercase font-mono font-bold tracking-wider outline-none"
            placeholder="e.g. AAPL, BTC-USD, MSFT"
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && add()}
          />
          <button
            onClick={add}
            className="flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 text-white rounded-xl px-5 py-2.5 font-semibold text-xs transition duration-200 cursor-pointer shadow-lg shadow-violet-600/25 shrink-0"
          >
            <Plus size={14} strokeWidth={2.5} />
            <span>{t('watchlist.add') || 'Add'}</span>
          </button>
        </div>
      </div>

      {/* Tickers List */}
      {loading && tickers.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-slate-400 text-sm">{t('watchlist.loading')}</p>
        </div>
      ) : tickers.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Star size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('watchlist.empty')}</p>
          <p className="text-[10px] text-slate-500 mt-1">Add symbols using the form above to start tracking them</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {tickers.map(item => (
            <div
              key={item}
              className="glass-panel glass-panel-hover rounded-2xl flex items-center justify-between p-4 group"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center text-violet-400 font-bold shrink-0">
                  <TrendingUp size={14} />
                </div>
                <div>
                  <span className="font-mono font-bold text-white tracking-wide text-sm block">{item}</span>
                  <span className="text-[9px] text-slate-500 font-semibold uppercase tracking-wider block mt-0.5">Asset Tracker</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {prices[item] ? (
                  <div className="text-right font-mono pr-2">
                    <span className="text-xs font-bold text-white block">
                      ${prices[item].price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                    <span className={`text-[10px] font-bold ${prices[item].change_percent >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {prices[item].change_percent >= 0 ? '+' : ''}{prices[item].change_percent.toFixed(2)}%
                    </span>
                  </div>
                ) : (
                  <div className="text-right font-mono pr-2 text-slate-600 text-xs">
                    --
                  </div>
                )}
                <button
                  onClick={() => remove(item)}
                  className="text-slate-500 hover:text-rose-400 transition-colors p-2 hover:bg-white/5 rounded-lg shrink-0 cursor-pointer"
                  title="Remove"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


