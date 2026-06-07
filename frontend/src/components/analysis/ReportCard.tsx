import { FileText } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'

interface ReportCardProps {
  label: string
  content: string
  defaultOpen?: boolean
}

export function ReportCard({ label, content, defaultOpen }: ReportCardProps) {
  const { t } = useTranslation()
  if (!content) return null

  // Extract embedded image if present
  let imageSrc = null
  let textContent = content
  if (content.includes('IMAGE_DATA:')) {
    const parts = content.split('IMAGE_DATA:')
    const subParts = parts[1].split('\n\n')
    imageSrc = subParts[0]
    textContent = parts[0] + (subParts.length > 1 ? subParts.slice(1).join('\n\n') : '')
  }

  return (
    <details open={defaultOpen} className="group border border-white/[0.04] rounded-xl overflow-hidden bg-slate-900/20">
      <summary className="flex items-center gap-2.5 cursor-pointer select-none px-4 py-3 bg-slate-900/40 hover:bg-slate-900/80 transition-colors list-none">
        <FileText size={14} className="text-violet-400 shrink-0" />
        <span className="text-xs font-semibold text-slate-200 flex-1">{label}</span>
        <span className="text-[10px] text-slate-500 group-open:hidden">{t('analysis.report_card.show')}</span>
        <span className="text-[10px] text-slate-500 hidden group-open:inline">{t('analysis.report_card.hide')}</span>
      </summary>
      <div className="p-4 border-t border-white/[0.04] bg-slate-950/80 space-y-4">
        {imageSrc && (
          <div className="rounded-xl overflow-hidden border border-white/[0.08] bg-black/40">
            <img src={imageSrc} alt="Chart Analysis" className="w-full h-auto" />
          </div>
        )}
        <pre className="text-xs text-slate-300 whitespace-pre-wrap max-h-80 overflow-y-auto font-mono leading-relaxed select-text">
          {textContent}
        </pre>
      </div>
    </details>
  )
}
