import React from 'react'
import { X, Calendar, Target, Shield } from 'lucide-react'
import { SignalBadge } from '../analysis/SignalBadge'

interface AnalysisDetailSidebarProps {
  selected: any
  setSelected: (v: any) => void
  t: any
}

export const AnalysisDetailSidebar: React.FC<AnalysisDetailSidebarProps> = ({
  selected, setSelected, t
}) => {
  if (!selected) return null

  return (
    <div className="lg:col-span-1 glass-panel rounded-2xl p-5 border-violet-500/20 shadow-xl shadow-violet-500/5 animate-in slide-in-from-right-4 duration-300">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-bold text-white uppercase tracking-widest">{t('chart.analysis_detail')}</h3>
        <button onClick={() => setSelected(null)} className="text-slate-500 hover:text-white transition-colors cursor-pointer p-1 rounded-lg hover:bg-white/5">
          <X size={16} />
        </button>
      </div>

      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <div className="bg-slate-900 rounded-xl p-3 border border-white/[0.04]">
            <Calendar size={16} className="text-violet-400" />
          </div>
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-0.5">{t('chart.trade_date')}</p>
            <p className="text-sm font-mono font-bold text-white">{selected.trade_date}</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="bg-slate-900 rounded-xl p-3 border border-white/[0.04]">
            <Target size={16} className="text-emerald-400" />
          </div>
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-0.5">{t('chart.signal')}</p>
            <SignalBadge signal={selected.signal} large />
          </div>
        </div>

        {selected.final_decision && (
          <div className="bg-slate-900/40 rounded-xl p-4 border border-white/[0.04]">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 flex items-center gap-2">
               <Shield size={12} className="text-blue-400" /> Executive Summary
            </p>
            <p className="text-xs text-slate-300 leading-relaxed max-h-60 overflow-y-auto pr-2 custom-scrollbar">
              {selected.final_decision}
            </p>
          </div>
        )}

        <div className="pt-4 border-t border-white/[0.04]">
            <button 
                onClick={() => window.location.href = `/analysis?id=${selected.id}`}
                className="w-full py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold transition-all shadow-lg shadow-violet-600/20 cursor-pointer"
            >
                View Full Report
            </button>
        </div>
      </div>
    </div>
  )
}
