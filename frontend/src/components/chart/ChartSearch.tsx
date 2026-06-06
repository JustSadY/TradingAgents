import React from 'react'
import { Search, RefreshCw } from 'lucide-react'

interface ChartSearchProps {
  tickerInput: string; setTickerInput: (v: string) => void
  period: string; handlePeriod: (p: string) => void
  periods: { label: string; value: string }[]
  loading: boolean
  handleSearch: () => void
  t: any
}

export const ChartSearch: React.FC<ChartSearchProps> = ({
  tickerInput, setTickerInput, period, handlePeriod, periods, loading, handleSearch
}) => {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900/40 p-4 border-b border-white/[0.04]">
      <div className="flex items-center gap-3">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within:text-violet-400 transition-colors" size={16} />
          <input
            className="glass-input pl-10 pr-4 py-2 w-48 rounded-xl text-sm font-mono uppercase focus:ring-2 focus:ring-violet-500/20 outline-none transition-all"
            value={tickerInput}
            onChange={e => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="Symbol (AAPL)"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !tickerInput.trim()}
          className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white p-2 rounded-xl transition-all shadow-lg shadow-violet-600/20 cursor-pointer"
        >
          {loading ? <RefreshCw size={18} className="animate-spin" /> : <Search size={18} />}
        </button>
      </div>

      <div className="flex bg-slate-950/60 p-1 rounded-xl border border-white/[0.04]">
        {periods.map(p => (
          <button
            key={p.value}
            onClick={() => handlePeriod(p.value)}
            className={`px-4 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-widest transition-all cursor-pointer ${
              period === p.value ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  )
}
