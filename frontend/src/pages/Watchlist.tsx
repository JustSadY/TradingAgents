import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, Star, TrendingUp } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import {
  useWatchlistGetWatchlist,
  useWatchlistGetWatchlistPrices,
  useWatchlistAddToWatchlist,
  useWatchlistRemoveFromWatchlist,
  getWatchlistGetWatchlistQueryKey,
  getWatchlistGetWatchlistPricesQueryKey,
} from '../api/generated/watchlist/watchlist'

export default function Watchlist() {
  const [input, setInput] = useState('')
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const watchlist = useWatchlistGetWatchlist()
  const tickers = watchlist.data ?? []

  // Prices poll on their own cadence; the list itself rarely changes, so it is
  // refetched only when a mutation invalidates it.
  const pricesQuery = useWatchlistGetWatchlistPrices({
    query: {
      refetchInterval: 15_000,
      enabled: tickers.length > 0,
    },
  })
  const prices = pricesQuery.data ?? {}

  const loading = watchlist.isPending

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: getWatchlistGetWatchlistQueryKey() }),
      queryClient.invalidateQueries({ queryKey: getWatchlistGetWatchlistPricesQueryKey() }),
    ])

  const addMutation = useWatchlistAddToWatchlist({ mutation: { onSuccess: invalidate } })
  const removeMutation = useWatchlistRemoveFromWatchlist({ mutation: { onSuccess: invalidate } })

  const add = () => {
    const ticker = input.trim().toUpperCase()
    if (!ticker) return
    addMutation.mutate({ ticker }, { onSuccess: () => setInput('') })
  }

  const remove = (tickerVal: string) => removeMutation.mutate({ ticker: tickerVal })

  const fetchWatchlist = () => invalidate()

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header Panel */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Star className="text-violet-400 fill-violet-400/20" size={20} />
            {t('watchlist.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">{t('watchlist.subtitle')}</p>
        </div>
        <button
          onClick={() => fetchWatchlist()}
          disabled={loading}
          className="flex items-center justify-center p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.04] text-slate-400 hover:text-white transition-all cursor-pointer"
          title={t('watchlist.refresh')}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Add Ticker Section */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="text-xs font-bold text-violet-400 uppercase tracking-widest">{t('watchlist.add_title')}</h3>
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
            <span>{t('watchlist.add')}</span>
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
          <p className="text-[10px] text-slate-500 mt-1">{t('watchlist.empty_hint')}</p>
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
                  <span className="text-[9px] text-slate-500 font-semibold uppercase tracking-wider block mt-0.5">{t('watchlist.asset_tracker')}</span>
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
                  title={t('watchlist.remove')}
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


