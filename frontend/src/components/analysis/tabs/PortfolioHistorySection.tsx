import { analysisGetPortfolioAnalysis, getAnalysisGetPortfolioAnalysisQueryKey, useAnalysisListPortfolioAnalyses } from '../../../api/generated/analysis/analysis'
import type { MultiTickerListItem, MultiTickerResultRead } from '../../../api/generated/model'
import { MarkdownReport } from '../../report/MarkdownReport'
import { useTranslation } from '../../../contexts/LanguageContext'
import { useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useState } from 'react'

export function PortfolioHistorySection() {
  const { t } = useTranslation()
  const [detail, setDetail] = useState<MultiTickerResultRead | null>(null)
  const queryClient = useQueryClient()

  const historyQuery = useAnalysisListPortfolioAnalyses()
  const items = (historyQuery.data ?? []) as unknown as MultiTickerListItem[]
  const loading = historyQuery.isPending

  if (loading) return <div className="text-slate-500 text-xs px-2">{t('analysis.portfolio_history.loading')}</div>

  return (
    <div className="glass-panel rounded-2xl p-5">
      <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3.5">{t('analysis.portfolio_history.title')}</h3>
      {items.length === 0 ? <p className="text-slate-600 text-xs">{t('analysis.portfolio_history.empty')}</p> : (
        <div className="space-y-2">
          {items.map(item => (
            <div key={item.id} onClick={() => queryClient
              .fetchQuery({
                queryKey: getAnalysisGetPortfolioAnalysisQueryKey(item.id),
                queryFn: () => analysisGetPortfolioAnalysis(item.id),
              })
              .then(d => setDetail(d as unknown as MultiTickerResultRead))
              .catch(e => console.error('Failed to load portfolio detail', e))}
              className="flex items-center justify-between p-3 rounded-xl bg-slate-900/20 hover:bg-slate-900/60 cursor-pointer transition-colors border border-white/[0.03] hover:border-white/[0.08]">
              <div className="flex items-center gap-2">
                <span className="text-white font-mono text-xs font-bold">{item.tickers.join(', ')}</span>
                <span className="text-slate-500 text-[10px]">{item.trade_date}</span>
              </div>
              <span className="text-slate-500 text-[10px] font-mono">{new Date(item.created_at).toLocaleDateString()}</span>
            </div>
          ))}
        </div>
      )}
      {detail && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-slate-900 border border-white/[0.06] rounded-2xl p-6 w-full max-w-3xl my-8 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-display font-bold text-white">{detail.tickers.join(', ')}</h3>
              <button onClick={() => setDetail(null)} className="text-slate-500 hover:text-white transition-colors p-1.5 rounded-lg hover:bg-white/5 cursor-pointer"><X size={16} /></button>
            </div>
            <p className="text-slate-500 text-[10px] font-mono">{detail.trade_date} • {new Date(detail.created_at).toLocaleString()}</p>
            <div className="bg-slate-950 rounded-xl p-4 max-h-[50vh] overflow-y-auto border border-white/[0.04] custom-scrollbar">
              <MarkdownReport
                content={detail.super_portfolio_report || t('analysis.portfolio_history.report_not_ready')}
                className="!text-xs !leading-relaxed"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
