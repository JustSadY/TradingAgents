import React from 'react'
import { MessageSquare, History } from 'lucide-react'

interface AnalysisLogProps {
  leftTab: 'log' | 'debate'
  setLeftTab: (v: 'log' | 'debate') => void
  log: string[]
  liveDebate: any[]
  t: any
}

export const AnalysisLog: React.FC<AnalysisLogProps> = ({
  leftTab, setLeftTab, log, liveDebate, t
}) => {
  return (
    <div className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[55vh] lg:h-[65vh]">
      <div className="flex items-center gap-1 p-1 bg-slate-900/40 border-b border-white/[0.04]">
        <button
          onClick={() => setLeftTab('log')}
          className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${
            leftTab === 'log' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.tabs.progress')}
        </button>
        <button
          onClick={() => setLeftTab('debate')}
          className={`flex-1 text-center py-1.5 text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${
            leftTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.tabs.live_debate')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-950/40">
        {leftTab === 'log' ? (
          <div className="space-y-2">
            {log.map((line, i) => (
              <div key={i} className="flex gap-3 text-[11px] animate-in fade-in slide-in-from-left-2 duration-300">
                <span className="text-slate-600 font-mono shrink-0">{(i + 1).toString().padStart(2, '0')}</span>
                <span className={`font-mono leading-relaxed ${
                  line.startsWith('✓') ? 'text-emerald-400' :
                  line.startsWith('✗') ? 'text-rose-400' :
                  line.startsWith('▸') ? 'text-violet-400' : 'text-slate-400'
                }`}>
                  {line}
                </span>
              </div>
            ))}
            {log.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                <History size={40} className="mb-4" />
                <p className="text-xs font-medium uppercase tracking-widest">{t('analysis.log.empty')}</p>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            {liveDebate.map((bubble, i) => (
              <div key={i} className="animate-in zoom-in-95 fade-in duration-500">
                <div className="flex items-center gap-2 mb-1.5">
                  <div className="w-5 h-5 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-[8px] font-bold text-white shadow-lg shadow-violet-500/20">
                    {bubble.sender[0]}
                  </div>
                  <span className="text-[10px] font-bold text-slate-300 uppercase tracking-tight">{bubble.sender}</span>
                </div>
                <div className="bg-white/[0.03] border border-white/[0.05] rounded-2xl p-3 text-xs text-slate-300 leading-relaxed shadow-inner">
                  {bubble.content}
                </div>
              </div>
            ))}
            {liveDebate.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                <MessageSquare size={40} className="mb-4" />
                <p className="text-xs font-medium uppercase tracking-widest">{t('analysis.debate.waiting')}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
