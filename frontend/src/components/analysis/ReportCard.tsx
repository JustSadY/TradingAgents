import { useState, useEffect } from 'react'
import { FileText, Loader2 } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'
import { MarkdownReport } from '../report/MarkdownReport'

interface ReportCardProps {
  label: string
  content: string
  defaultOpen?: boolean
  isStreaming?: boolean
}

export function ReportCard({ label, content, defaultOpen, isStreaming }: ReportCardProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(defaultOpen)

  useEffect(() => {
    if (defaultOpen) {
      setIsOpen(true)
    }
  }, [defaultOpen])

  if (!content) return null

  // Extract embedded image if present (only if not actively streaming)
  let imageSrc = null
  let textContent = content
  if (!isStreaming && content.includes('IMAGE_DATA:')) {
    const imageRegex = /IMAGE_DATA:\s*(data:image\/(?:png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+)\s*/
    const match = content.match(imageRegex)
    if (match) {
      imageSrc = match[1]
      textContent = content.replace(imageRegex, '')
    } else {
      // Fallback to avoid truncating text if regex parsing fails
      const parts = content.split('IMAGE_DATA:')
      textContent = parts[0] + (parts[1] ? '\n' + parts[1] : '')
    }
  }

  return (
    <details open={isOpen} onToggle={(e) => setIsOpen(e.currentTarget.open)} className="group border border-white/[0.04] rounded-xl overflow-hidden bg-slate-900/20">
      <summary className="flex items-center gap-2.5 cursor-pointer select-none px-4 py-3 bg-slate-900/40 hover:bg-slate-900/80 transition-colors list-none">
        <FileText size={14} className="text-violet-400 shrink-0" />
        <span className="text-xs font-semibold text-slate-200 flex-1">{label}</span>
        <span className="text-[10px] text-slate-500 group-open:hidden">{t('analysis.report_card.show')}</span>
        <span className="text-[10px] text-slate-500 hidden group-open:inline">{t('analysis.report_card.hide')}</span>
      </summary>
      <div className="p-4 border-t border-white/[0.04] bg-slate-950/80 space-y-4">
        {isStreaming && content.includes('IMAGE_DATA:') && (
          <div className="rounded-xl overflow-hidden border border-violet-500/10 bg-violet-500/5 p-4 animate-pulse flex items-center justify-center gap-2 text-violet-400 text-xs">
            <Loader2 className="animate-spin" size={12} />
            <span>{t('analysis.generating_chart')}</span>
          </div>
        )}
        {imageSrc && (
          <div className="rounded-xl overflow-hidden border border-white/[0.08] bg-black/40">
            <img src={imageSrc} alt="Chart Analysis" className="w-full h-auto" />
          </div>
        )}
        <div className="max-h-80 overflow-y-auto select-text custom-scrollbar pr-1">
          <MarkdownReport content={textContent} className="!text-xs !leading-relaxed" />
        </div>
      </div>
    </details>
  )
}
