import { Wallet } from 'lucide-react'

interface KellyPositioningCardProps {
  kellySize: number
  suggestedCapital?: number
}

export function KellyPositioningCard({ kellySize, suggestedCapital }: KellyPositioningCardProps) {
  if (kellySize <= 0) return null

  return (
    <div className="flex items-center gap-4 p-4 bg-violet-600/10 border border-violet-600/20 rounded-2xl mb-6">
      <div className="h-10 w-10 rounded-xl bg-violet-600/20 flex items-center justify-center shrink-0">
        <Wallet className="text-violet-400" size={20} />
      </div>
      <div>
        <h4 className="text-xs font-bold text-violet-300 uppercase tracking-widest mb-0.5">Kelly Optimal Sizing</h4>
        <div className="flex items-baseline gap-2">
          <span className="text-xl font-mono font-bold text-white">{(kellySize * 100).toFixed(2)}%</span>
          <span className="text-xs text-slate-500 font-medium">of portfolio</span>
          {suggestedCapital && suggestedCapital > 0 && (
            <>
              <span className="text-slate-700 mx-1">•</span>
              <span className="text-lg font-mono font-bold text-emerald-400">${suggestedCapital.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
