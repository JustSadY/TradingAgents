import { useState } from 'react'
import { useSectorSectorRotation } from '../api/generated/sector/sector'
import { TrendingUp, TrendingDown, Minus, RefreshCw, Loader2, BarChart2 } from 'lucide-react'
import { useQueryErrorToast } from '../api/useQueryErrorToast'
import { useTranslation } from '../contexts/LanguageContext'

interface SectorData {
  ticker: string
  name: string
  price: number
  ret_1w: number
  ret_1m: number
  ret_3m: number
  rsi: number
  above_sma20: boolean
  volume_ratio: number
  momentum_score: number
}

type SortKey = 'momentum_score' | 'ret_1w' | 'ret_1m' | 'ret_3m'

function retColor(val: number) {
  if (val > 2) return 'text-emerald-400'
  if (val > 0) return 'text-emerald-300'
  if (val < -2) return 'text-rose-400'
  if (val < 0) return 'text-rose-300'
  return 'text-slate-400'
}

function momentumBg(score: number) {
  if (score > 0.5) return 'from-emerald-500/20 to-emerald-500/5 border-emerald-500/40'
  if (score > 0.15) return 'from-teal-500/15 to-teal-500/5 border-teal-500/25'
  if (score > -0.15) return 'from-slate-700/30 to-slate-700/10 border-white/[0.06]'
  if (score > -0.5) return 'from-amber-500/15 to-amber-500/5 border-amber-500/25'
  return 'from-rose-500/20 to-rose-500/5 border-rose-500/40'
}

function momentumLabel(score: number) {
  if (score > 0.5) return { text: 'Strong Bull', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' }
  if (score > 0.15) return { text: 'Bullish', cls: 'text-teal-400 bg-teal-500/10 border-teal-500/20' }
  if (score > -0.15) return { text: 'Neutral', cls: 'text-slate-400 bg-slate-500/10 border-slate-500/20' }
  if (score > -0.5) return { text: 'Bearish', cls: 'text-amber-400 bg-amber-500/10 border-amber-500/20' }
  return { text: 'Strong Bear', cls: 'text-rose-400 bg-rose-500/10 border-rose-500/20' }
}

function MomentumBar({ score }: { score: number }) {
  const pct = Math.round(((score + 1) / 2) * 100)
  const barCls = score > 0.15 ? 'bg-emerald-500' : score < -0.15 ? 'bg-rose-500' : 'bg-slate-500'
  return (
    <div className="w-full h-1 rounded-full bg-white/[0.04] mt-1.5">
      <div className={`h-full rounded-full ${barCls} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function RsiGauge({ rsi }: { rsi: number }) {
  const cls = rsi < 30 ? 'text-emerald-400' : rsi > 70 ? 'text-rose-400' : 'text-slate-400'
  const label = rsi < 30 ? 'OS' : rsi > 70 ? 'OB' : ''
  return (
    <span className={`font-mono text-[10px] font-bold ${cls}`}>
      RSI {rsi.toFixed(0)}{label && <span className="ml-0.5 opacity-70">{label}</span>}
    </span>
  )
}

export default function SectorRotation() {
  const { t } = useTranslation()
  const [sortKey, setSortKey] = useState<SortKey>('momentum_score')

  const SORT_OPTIONS: { key: SortKey; label: string }[] = [
    { key: 'momentum_score', label: t('sector.sort_momentum') },
    { key: 'ret_1w', label: t('sector.sort_1w') },
    { key: 'ret_1m', label: t('sector.sort_1m') },
    { key: 'ret_3m', label: t('sector.sort_3m') },
  ]
  const query = useSectorSectorRotation()
  const sectors = ((query.data as { sectors?: SectorData[] } | undefined)?.sectors ?? []) as SectorData[]
  const loading = query.isFetching
  const lastUpdated = query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null
  const load = () => query.refetch()
  useQueryErrorToast(query.error, 'Failed to load sector data', 'Sector Rotation')

  const sorted = [...sectors].sort((a, b) => b[sortKey] - a[sortKey])
  const leaders = sorted.slice(0, 3)
  const laggards = [...sectors].sort((a, b) => a[sortKey] - b[sortKey]).slice(0, 3)

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <BarChart2 className="text-violet-400" size={20} />
            {t('sector.title')}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {t('sector.subtitle')}
            {lastUpdated && <span className="ml-2 text-slate-600">· {t('sector.updated')} {lastUpdated.toLocaleTimeString()}</span>}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06] text-slate-400 text-xs font-bold transition disabled:opacity-40 cursor-pointer"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {t('sector.refresh')}
        </button>
      </div>

      {/* Sort tabs */}
      <div className="flex gap-1 bg-white/[0.02] p-0.5 rounded-xl border border-white/[0.04] w-fit">
        {SORT_OPTIONS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setSortKey(key)}
            className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition cursor-pointer ${
              sortKey === key ? 'bg-violet-600 text-white shadow' : 'text-slate-400 hover:text-white'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && sectors.length === 0 && (
        <div className="glass-panel rounded-2xl p-16 flex flex-col items-center gap-3 text-slate-500">
          <Loader2 size={28} className="animate-spin text-violet-400" />
          <p className="text-xs">{t('sector.loading')}</p>
        </div>
      )}

      {sectors.length > 0 && (
        <>
          {/* Leader / Laggard summary */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Leaders */}
            <div className="glass-panel rounded-2xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingUp size={13} className="text-emerald-400" />
                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">{t('sector.top_leaders')}</span>
              </div>
              <div className="space-y-2">
                {leaders.map((s, i) => {
                  const val = s[sortKey]
                  return (
                    <div key={s.ticker} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-600 font-mono w-4">{i + 1}</span>
                        <span className="text-xs font-bold text-white">{s.name}</span>
                        <span className="text-[9px] font-mono text-slate-500">{s.ticker}</span>
                      </div>
                      <span className={`text-xs font-mono font-bold ${retColor(val)}`}>
                        {val > 0 ? '+' : ''}{sortKey === 'momentum_score' ? val.toFixed(3) : val.toFixed(2) + '%'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Laggards */}
            <div className="glass-panel rounded-2xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <TrendingDown size={13} className="text-rose-400" />
                <span className="text-[10px] font-bold text-rose-400 uppercase tracking-widest">{t('sector.top_laggards')}</span>
              </div>
              <div className="space-y-2">
                {laggards.map((s, i) => {
                  const val = s[sortKey]
                  return (
                    <div key={s.ticker} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-slate-600 font-mono w-4">{i + 1}</span>
                        <span className="text-xs font-bold text-white">{s.name}</span>
                        <span className="text-[9px] font-mono text-slate-500">{s.ticker}</span>
                      </div>
                      <span className={`text-xs font-mono font-bold ${retColor(val)}`}>
                        {val > 0 ? '+' : ''}{sortKey === 'momentum_score' ? val.toFixed(3) : val.toFixed(2) + '%'}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Heat map grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {sorted.map((s, rank) => {
              const lbl = momentumLabel(s.momentum_score)
              return (
                <div
                  key={s.ticker}
                  className={`rounded-2xl bg-gradient-to-br border p-4 space-y-3 transition-all hover:scale-[1.01] ${momentumBg(s.momentum_score)}`}
                >
                  {/* Top row */}
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[9px] text-slate-600 font-mono">#{rank + 1}</span>
                        <span className="font-mono font-bold text-sm text-white">{s.ticker}</span>
                      </div>
                      <p className="text-[10px] text-slate-400 mt-0.5 leading-tight">{s.name}</p>
                    </div>
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border ${lbl.cls}`}>
                      {lbl.text}
                    </span>
                  </div>

                  {/* Price */}
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-base font-mono font-bold text-white">${s.price.toFixed(2)}</span>
                    <span className={`text-[10px] font-mono font-bold ${retColor(s.ret_1w)}`}>
                      {s.ret_1w > 0 ? '+' : ''}{s.ret_1w.toFixed(2)}%
                      <span className="text-slate-600 font-normal ml-0.5">1W</span>
                    </span>
                  </div>

                  {/* Returns grid */}
                  <div className="grid grid-cols-3 gap-1.5 text-center">
                    {[
                      { label: '1W', val: s.ret_1w },
                      { label: '1M', val: s.ret_1m },
                      { label: '3M', val: s.ret_3m },
                    ].map(({ label, val }) => (
                      <div key={label} className="bg-black/20 rounded-lg py-1.5">
                        <p className="text-[8px] text-slate-600 font-bold uppercase">{label}</p>
                        <p className={`text-[10px] font-mono font-bold ${retColor(val)}`}>
                          {val > 0 ? '+' : ''}{val.toFixed(1)}%
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Momentum bar */}
                  <div>
                    <div className="flex items-center justify-between">
                        <span className="text-[9px] text-slate-600 font-bold">{t('sector.momentum_label')}</span>
                      <span className={`text-[10px] font-mono font-bold ${retColor(s.momentum_score * 10)}`}>
                        {s.momentum_score > 0 ? '+' : ''}{s.momentum_score.toFixed(3)}
                      </span>
                    </div>
                    <MomentumBar score={s.momentum_score} />
                  </div>

                  {/* Bottom row: RSI + volume + SMA */}
                  <div className="flex items-center justify-between pt-0.5">
                    <RsiGauge rsi={s.rsi} />
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] text-slate-600 font-mono">
                        Vol {s.volume_ratio.toFixed(1)}x
                      </span>
                      <span className={`text-[9px] font-bold ${s.above_sma20 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {s.above_sma20 ? '▲ SMA20' : '▼ SMA20'}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-4 text-[9px] text-slate-600">
            <span className="font-bold uppercase tracking-widest">{t('sector.legend')}</span>
            {[
              { label: t('sector.legend_strong_bull'), cls: 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400' },
              { label: t('sector.legend_bullish'), cls: 'bg-teal-500/20 border-teal-500/40 text-teal-400' },
              { label: t('sector.legend_neutral'), cls: 'bg-slate-500/20 border-slate-500/40 text-slate-400' },
              { label: t('sector.legend_bearish'), cls: 'bg-amber-500/20 border-amber-500/40 text-amber-400' },
              { label: t('sector.legend_strong_bear'), cls: 'bg-rose-500/20 border-rose-500/40 text-rose-400' },
            ].map(({ label, cls }) => (
              <span key={label} className={`px-2 py-0.5 rounded-full border font-bold ${cls}`}>{label}</span>
            ))}
            <span className="text-slate-700 ml-auto">{t('sector.legend_hint')}</span>
          </div>
        </>
      )}

      {!loading && sectors.length === 0 && (
        <div className="glass-panel rounded-2xl p-12 text-center">
          <Minus size={32} className="mx-auto text-slate-600 mb-3 opacity-30" />
          <p className="text-slate-400 text-xs font-semibold">{t('sector.empty')}</p>
          <button onClick={load} className="mt-3 text-[10px] text-violet-400 hover:text-violet-300 cursor-pointer">
            {t('sector.retry')}
          </button>
        </div>
      )}
    </div>
  )
}
