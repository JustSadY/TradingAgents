import { useTranslation } from '../../contexts/LanguageContext'

export interface QualityFields {
  score: number; confidence: string; reports_total: number; reports_present: number; reports_degraded: number; fallback_used: boolean
}
export type RunQuality = NonNullable<QualityFields>

export function QualityBadge({ quality }: { quality: RunQuality }) {
  const { t } = useTranslation()
  const tone: Record<string, string> = {
    high: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    medium: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
    low: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  }
  const cls = tone[quality.confidence] ?? tone.low
  const title =
    `${t('analysis.quality.reports')}: ${quality.reports_present}/${quality.reports_total}` +
    (quality.reports_degraded ? ` • ${quality.reports_degraded} ${t('analysis.quality.degraded')}` : '') +
    (quality.fallback_used ? ` • ${t('analysis.quality.fallback')}` : '')
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md border ${cls}`}
    >
      {quality.confidence ? t(`analysis.quality.${quality.confidence}`) : '?'} · {quality.score}
    </span>
  )
}
