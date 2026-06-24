import React from 'react'

interface TechnicalControlsProps {
  showSMA: boolean; setShowSMA: (v: boolean) => void
  showEMA: boolean; setShowEMA: (v: boolean) => void
  showRSI: boolean; setShowRSI: (v: boolean) => void
  showMACD: boolean; setShowMACD: (v: boolean) => void
  showSentiment: boolean; setShowSentiment: (v: boolean) => void
  t: any
}

export const TechnicalControls: React.FC<TechnicalControlsProps> = ({
  showSMA, setShowSMA, showEMA, setShowEMA, showRSI, setShowRSI,
  showMACD, setShowMACD, showSentiment, setShowSentiment
}) => {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <button
        onClick={() => setShowSMA(!showSMA)}
        className={`px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
          showSMA ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'bg-white/5 text-slate-500 border border-transparent hover:text-slate-300'
        }`}
      >
        SMA (20)
      </button>
      <button
        onClick={() => setShowEMA(!showEMA)}
        className={`px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
          showEMA ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : 'bg-white/5 text-slate-500 border border-transparent hover:text-slate-300'
        }`}
      >
        EMA (20)
      </button>
      <button
        onClick={() => setShowRSI(!showRSI)}
        className={`px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
          showRSI ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-white/5 text-slate-500 border border-transparent hover:text-slate-300'
        }`}
      >
        RSI (14)
      </button>
      <button
        onClick={() => setShowMACD(!showMACD)}
        className={`px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
          showMACD ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-white/5 text-slate-500 border border-transparent hover:text-slate-300'
        }`}
      >
        MACD
      </button>
      <button
        onClick={() => setShowSentiment(!showSentiment)}
        className={`px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
          showSentiment ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-white/5 text-slate-500 border border-transparent hover:text-slate-300'
        }`}
      >
        Sentiment
      </button>
    </div>
  )
}
