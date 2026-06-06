import React from 'react'
import { useMeta } from '../../hooks/useMeta'

const TONE_CLASSES: Record<string, { bg: string; text: string; border: string }> = {
  positive: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  neutral:  { bg: 'bg-amber-500/10',  text: 'text-amber-400',  border: 'border-amber-500/20' },
  negative: { bg: 'bg-rose-500/10',     text: 'text-rose-400',     border: 'border-rose-500/20' },
}
const FALLBACK_TONE: Record<string, string> = {
  Buy: 'positive', Overweight: 'positive', Hold: 'neutral', Underweight: 'negative', Sell: 'negative',
}

export function SignalBadge({ signal, large }: { signal: string | null; large?: boolean }) {
  const meta = useMeta()
  if (!signal) return null
  const sig = meta?.signals.find(s => s.value === signal)
  const tone = sig?.tone ?? FALLBACK_TONE[signal]
  const m = tone ? TONE_CLASSES[tone] : undefined
  const label = sig?.label ?? signal
  if (!m) return <span className="text-slate-400 font-semibold">{label}</span>
  return (
    <span className={`inline-flex items-center font-bold border rounded-xl ${m.bg} ${m.text} ${m.border} ${large ? 'px-4 py-1.5 text-sm' : 'px-2.5 py-0.5 text-[10px]'}`}>
      {label}
    </span>
  )
}
