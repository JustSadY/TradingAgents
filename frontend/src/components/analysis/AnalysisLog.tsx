import React, { useRef, useEffect } from 'react'
import { MessageSquare, History, Loader2 } from 'lucide-react'
import { getSenderStyles } from './DebateHistoryWidget'

interface AnalysisLogProps {
  leftTab: 'log' | 'debate'
  setLeftTab: (v: 'log' | 'debate') => void
  log: string[]
  liveDebate: any[]
  currentStep?: { label: string; stage: string; node?: string } | null
  stats?: { llmCalls: number; tokensIn: number; tokensOut: number } | null
  t: any
}

export const AnalysisLog: React.FC<AnalysisLogProps> = ({
  leftTab, setLeftTab, log, liveDebate, currentStep, stats, t
}) => {
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom of log or debate feed whenever new updates arrive or tabs toggle
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: 'smooth'
      })
    }
  }, [log, liveDebate, leftTab, currentStep])

  return (
    <div className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[40vh] sm:h-[50vh] lg:h-[65vh]">
      <div className="flex items-center gap-1 p-1 bg-slate-900/40 border-b border-white/[0.04]">
        <button
          onClick={() => setLeftTab('log')}
          className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${
            leftTab === 'log' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.tabs.progress')}
        </button>
        <button
          onClick={() => setLeftTab('debate')}
          className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition-all cursor-pointer ${
            leftTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
          }`}
        >
          {t('analysis.tabs.live_debate')}
        </button>
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 custom-scrollbar bg-slate-950/40 space-y-4"
      >
        {leftTab === 'log' ? (
          <div className="space-y-2">
            {log.map((line, i) => (
              <div key={i} className="flex gap-3 text-[11px] animate-in fade-in slide-in-from-left-2 duration-300">
                <span className="text-slate-600 font-mono shrink-0">{(i + 1).toString().padStart(2, '0')}</span>
                <span className={`font-mono leading-relaxed ${
                  line.startsWith('Completed') ? 'text-emerald-400' :
                  line.startsWith('Error') ? 'text-rose-400' :
                  line.startsWith('Progress') ? 'text-violet-400' : 'text-slate-400'
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
          <div className="flex flex-col space-y-4">
            {/* Live Debate Chat Bubbles */}
            {liveDebate.map((bubble, i) => {
              const styles = getSenderStyles(bubble.sender)
              return (
                <div
                  key={i}
                  className={`flex w-full ${styles.side} animate-in zoom-in-95 fade-in duration-300`}
                >
                  <div className={`border rounded-2xl px-4 py-2.5 text-xs flex flex-col gap-1 max-w-[85%] ${styles.bg}`}>
                    <span className="font-bold uppercase tracking-wider text-[9px] opacity-80 flex items-center gap-1">
                      {styles.icon} {bubble.sender}
                    </span>
                    <span className="leading-relaxed whitespace-pre-wrap">{bubble.content}</span>
                  </div>
                </div>
              )
            })}

            {/* Waiting State */}
            {liveDebate.length === 0 && (!currentStep || (currentStep.stage !== 'research' && currentStep.stage !== 'risk')) && (
              <div className="h-full flex flex-col items-center justify-center opacity-20 py-20">
                <MessageSquare size={40} className="mb-4" />
                <p className="text-xs font-medium uppercase tracking-widest text-center">
                  {t('analysis.debate.waiting')}
                </p>
              </div>
            )}

            {/* Animated Typing Indicator */}
            {currentStep && (currentStep.stage === 'research' || currentStep.stage === 'risk') && (
              <div className="flex justify-start items-center gap-3 animate-pulse pl-1 pt-2">
                <div className="w-6 h-6 rounded-full bg-slate-900/80 border border-white/[0.06] flex items-center justify-center shadow">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500"></span>
                  </span>
                </div>
                <div className="bg-slate-900/40 border border-slate-800/40 rounded-2xl px-3.5 py-2 text-[10px] text-slate-400 flex items-center gap-1.5">
                  <Loader2 size={10} className="animate-spin text-slate-500" />
                  <span className="font-semibold uppercase tracking-tight">
                    {currentStep.label} {t('analysis.debate.typing')}
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      {stats && (stats.llmCalls > 0 || stats.tokensIn > 0 || stats.tokensOut > 0) && (
        <div className="flex items-center justify-between px-4 py-2 bg-slate-950/80 border-t border-white/[0.04] text-[10px] text-slate-500 font-semibold font-mono">
          <span>LLM Calls: <span className="text-slate-300 font-bold">{stats.llmCalls}</span></span>
          <span>Tokens: <span className="text-slate-300 font-bold">{(stats.tokensIn + stats.tokensOut).toLocaleString()}</span></span>
        </div>
      )}
    </div>
  )
}
