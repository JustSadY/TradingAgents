import React from 'react'
import { ExternalLink } from 'lucide-react'

interface NewsItem { title: string; url: string; source: string; published_at: string; ticker: string }

interface NewsFeedProps {
  news: NewsItem[]
  t: any
}

export const NewsFeed: React.FC<NewsFeedProps> = ({ news, t }) => {
  return (
    <div className="lg:col-span-1 glass-panel rounded-2xl p-5 border-white/[0.04] bg-slate-900/20">
      <h3 className="text-xs font-bold text-white uppercase tracking-widest mb-4 flex items-center justify-between">
        {t('dashboard.watchlist_news')}
        <span className="text-[9px] text-slate-500 font-normal normal-case">Live feed</span>
      </h3>
      <div className="space-y-4">
        {news.map((item, i) => (
          <a key={i} href={item.url} target="_blank" rel="noopener noreferrer" className="block group">
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-bold text-violet-400 font-mono">{item.ticker}</span>
                <span className="text-[9px] text-slate-500">{new Date(item.published_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </div>
              <p className="text-[11px] text-slate-300 leading-snug group-hover:text-white transition-colors line-clamp-2">{item.title}</p>
              <div className="flex items-center gap-1 text-[9px] text-slate-500 mt-0.5">
                <span className="truncate">{item.source}</span>
                <ExternalLink size={8} />
              </div>
            </div>
          </a>
        ))}
        {news.length === 0 && (
          <p className="text-[11px] text-slate-600 italic py-4">No news for your watchlist tickers</p>
        )}
      </div>
    </div>
  )
}
