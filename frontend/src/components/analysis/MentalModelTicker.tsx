import { Brain } from 'lucide-react'

interface MentalModelTickerProps {
  agent: string
  thought: string
}

export function MentalModelTicker({ agent, thought }: MentalModelTickerProps) {
  if (!thought) return null

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-indigo-500/10 border border-indigo-500/20 rounded-xl mb-4 animate-in fade-in slide-in-from-top-2 duration-300">
      <Brain size={14} className="text-indigo-400 animate-pulse shrink-0" />
      <div className="flex-1 overflow-hidden">
        <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mr-2">{agent} Thought</span>
        <p className="text-xs text-indigo-200 truncate italic">{thought}</p>
      </div>
    </div>
  )
}
