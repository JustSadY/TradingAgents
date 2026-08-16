import React from 'react'

/**
 * The layout vocabulary the settings tabs are written in.
 *
 * Lifted out of `pages/Settings.tsx` when the tabs became their own
 * components — every one of them needs these, and a page that only routes
 * between tabs should not also be the place they are defined.
 */

export const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4">
      <h3 className="text-xs font-bold text-violet-400 uppercase tracking-wider border-b border-white/[0.04] pb-2.5">{title}</h3>
      <div className="space-y-4 pt-1">{children}</div>
    </div>
  )
}

export function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3 last:border-b-0 last:pb-0">
      <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{label}</span>
      <div className="flex-1 sm:max-w-xs w-full">{children}</div>
    </div>
  )
}

export const CompactInputStyle = "w-24 text-right bg-slate-950/90 border border-white/10 hover:border-violet-500/40 focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20 rounded-lg px-2.5 py-1 text-xs font-mono font-semibold text-violet-200 outline-none transition-all shadow-inner"

export function RiskRowItem({
  label,
  hint,
  unit,
  children,
  className,
}: {
  label: string
  hint?: string
  unit?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/60 hover:bg-slate-900/90 border border-white/[0.04] transition-all group ${className || ''}`}>
      <div className="flex flex-col min-w-0 pr-1">
        <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">{label}</span>
        {hint && <span className="text-[10px] text-slate-400 mt-0.5 leading-tight">{hint}</span>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {children}
        {unit && (
          <span className="text-[11px] font-bold text-violet-400/90 bg-violet-500/10 border border-violet-500/20 rounded-md px-1.5 py-0.5 min-w-[24px] text-center select-none">
            {unit}
          </span>
        )}
      </div>
    </div>
  )
}

export function ToggleItem({
  label,
  hint,
  checked,
  onChange,
  warning,
  className,
}: {
  label: string
  hint?: string
  checked: boolean
  onChange: (checked: boolean) => void
  warning?: string
  className?: string
}) {
  return (
    <div className={`flex flex-col gap-1.5 p-3 rounded-xl bg-slate-900/60 hover:bg-slate-900/90 border border-white/[0.04] transition-all group ${className || ''}`}>
      <label className="flex items-center justify-between gap-3 cursor-pointer">
        <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors min-w-0 pr-2">{label}</span>
        <div className="relative inline-flex items-center shrink-0">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={checked}
            onChange={e => onChange(e.target.checked)}
          />
          <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-violet-500/30 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gradient-to-r peer-checked:from-violet-600 peer-checked:to-indigo-600 shadow-inner" />
        </div>
      </label>
      {hint && <span className="text-[10px] text-slate-400 leading-tight">{hint}</span>}
      {warning && <span className="text-[10px] text-amber-300/80 leading-tight font-medium mt-0.5">{warning}</span>}
    </div>
  )
}
