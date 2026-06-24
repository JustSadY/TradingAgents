import React from 'react'
import { ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { SignalBadge } from '../analysis/SignalBadge'

interface RecentAnalysisTableProps {
  recentAnalysis: any[]
  t: any
}

export const RecentAnalysisTable: React.FC<RecentAnalysisTableProps> = ({
  recentAnalysis, t
}) => {
  const navigate = useNavigate()
  return (
    <div className="lg:col-span-2 glass-panel rounded-2xl overflow-hidden flex flex-col">
      <div className="px-5 py-4 border-b border-white/[0.04] bg-slate-900/20 flex items-center justify-between">
        <h3 className="text-xs font-bold text-white uppercase tracking-widest">{t('dashboard.recent_analysis')}</h3>
        <button onClick={() => navigate('/analysis')} className="text-[10px] font-bold text-violet-400 hover:text-violet-300 flex items-center gap-1 transition-colors cursor-pointer uppercase tracking-wider">
          {t('dashboard.view_all')} <ArrowRight size={10} />
        </button>
      </div>
      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-xs text-left">
          <tbody className="divide-y divide-white/[0.02]">
            {recentAnalysis.map(a => (
              <tr key={a.id} className="hover:bg-white/[0.02] transition-colors cursor-pointer group" onClick={() => navigate(`/analysis?id=${a.id}`)}>
                <td className="px-5 py-3.5">
                  <div className="flex flex-col">
                    <span className="font-mono font-bold text-white group-hover:text-violet-400 transition-colors">{a.ticker}</span>
                    <span className="text-[10px] text-slate-500">{a.trade_date}</span>
                  </div>
                </td>
                <td className="px-5 py-3.5 text-center">
                  <SignalBadge signal={a.signal} />
                </td>
                <td className="px-5 py-3.5 text-right">
                    <span className="text-slate-500 font-mono text-[10px]">{(a.duration_seconds ?? 0).toFixed(1)}s</span>
                </td>
              </tr>
            ))}
            {recentAnalysis.length === 0 && (
              <tr><td colSpan={3} className="px-5 py-12 text-center text-slate-600 italic">No recent analysis found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
