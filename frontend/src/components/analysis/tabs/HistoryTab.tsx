import { QualityBadge, type RunQuality } from '../QualityBadge'
import { PortfolioDecisionCard } from '../PortfolioDecisionCard'
import { TimeTravelWidget } from '../TimeTravelWidget'
import { readableSectionLabel, visibleReportEntries } from '../../../analysis/streamingReports'
import { analysisGetAnalysis, getAnalysisGetAnalysisQueryKey, useAnalysisClearHistory, useAnalysisDeleteAnalysis, useAnalysisListAnalysis } from '../../../api/generated/analysis/analysis'
import type { AnalysisListItem, AnalysisResultRead } from '../../../api/generated/model'
import { useShareCreateShare } from '../../../api/generated/share/share'
import { AnalysisChatWidget } from '../AnalysisChatWidget'
import { DebateHistoryWidget } from '../DebateHistoryWidget'
import { ReportCard } from '../ReportCard'
import { RiskMetricsCard } from '../RiskMetricsCard'
import { SignalBadge } from '../SignalBadge'
import { StrategyTransitionCard } from '../StrategyTransitionCard'
import { useTranslation } from '../../../contexts/LanguageContext'
import { useMeta } from '../../../hooks/useMeta'
import { exportAnalysesCSV } from '../../../utils/csvExport'
import { exportMarkdown, exportPDF } from '../../../utils/exportReport'
import { notify } from '../../../utils/notify'
import { buildPublicShareUrl } from '../../../utils/shareLink'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Copy, Download, FileDown, Loader2, Share2, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { GridColDef } from '@mui/x-data-grid'
import AppDataGrid from '../../ui/AppDataGrid'

export function HistoryTab({
  initialDetailId,
  onRollbackStart,
}: {
  initialDetailId?: number
  onRollbackStart: (taskId: string, ticker: string) => void
}) {
  const { t, language } = useTranslation()
  const createShare = useShareCreateShare()
  const [detail, setDetail] = useState<AnalysisResultRead | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [activeDetailTab, setActiveDetailTab] = useState<'reports' | 'debate' | 'chat' | 'timetravel'>('reports')
  const [shareLink, setShareLink] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)
  const [itemToDelete, setItemToDelete] = useState<number | null>(null)
  const [showClearAllModal, setShowClearAllModal] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [clearingAll, setClearingAll] = useState(false)

  const shareReport = useCallback(async (id: number) => {
    setSharing(true)
    setShareLink(null)
    try {
      const data = await createShare.mutateAsync({ analysisId: id }) as unknown as { token: string; expires_at: string }
      const link = buildPublicShareUrl(data.token)
      setShareLink(link)
      // Clipboard access is unavailable on plain HTTP origins (including the
      // common local Docker URL).  A successful API response must still leave
      // a usable link in the UI rather than falling into the outer error path.
      let copied = false
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(link)
          copied = true
        }
      } catch {
        // The readonly link field below is the manual-copy fallback.
      }
      notify('success', copied ? 'Share link copied to clipboard' : 'Share link created — copy it from the field below', 'Share')
    } catch (e: any) {
      notify('error', e.response?.data?.detail || 'Share failed', 'Share')
    } finally {
      setSharing(false)
    }
  }, [])
  const meta = useMeta()
  const sectionLabels = meta?.section_labels ?? {}

  const deleteAnalysis = useAnalysisDeleteAnalysis()
  const clearHistory = useAnalysisClearHistory()
  const historyQuery = useAnalysisListAnalysis({ limit: 50 })
  const items = (historyQuery.data ?? []) as unknown as AnalysisListItem[]
  const loading = historyQuery.isPending
  const historyQueryClient = useQueryClient()

  const openDetail = useCallback(async (id: number) => {
    setDetailLoading(true)
    setActiveDetailTab('reports')
    // Never leave the previous record's token visible while a new detail is
    // loading; doing so made it easy to copy the wrong report's link.
    setShareLink(null)
    try {
      const data = await historyQueryClient.fetchQuery({
        queryKey: getAnalysisGetAnalysisQueryKey(id),
        queryFn: () => analysisGetAnalysis(id),
      })
      setDetail(data as never)
    } finally { setDetailLoading(false) }
  }, [])

  const confirmDeleteSingle = async () => {
    if (!itemToDelete) return
    const id = itemToDelete
    setDeletingId(id)
    try {
      await deleteAnalysis.mutateAsync({ analysisId: id })
      await historyQuery.refetch()
      notify('success', t('analysis.history.deleted_single'), t('analysis.title'))
      if (detail?.id === id) setDetail(null)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Delete failed', t('analysis.title'))
    } finally {
      setDeletingId(null)
      setItemToDelete(null)
    }
  }

  const confirmClearAll = async () => {
    setClearingAll(true)
    try {
      await clearHistory.mutateAsync()
      await historyQuery.refetch()
      setDetail(null)
      notify('success', t('analysis.history.deleted_all'), t('analysis.title'))
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Clear history failed', t('analysis.title'))
    } finally {
      setClearingAll(false)
      setShowClearAllModal(false)
    }
  }

  // Open the detail modal directly when arriving via a /analysis?id=… deep link.
  useEffect(() => {
    if (initialDetailId) openDetail(initialDetailId)
  }, [initialDetailId, openDetail])

  const columns = useMemo<GridColDef<AnalysisListItem>[]>(() => [
    {
      field: 'ticker',
      headerName: t('analysis.history.col_symbol'),
      minWidth: 96,
      flex: 0.6,
      renderCell: ({ row }) => <span className="font-mono font-bold text-white">{row.ticker}</span>,
    },
    {
      field: 'trade_date',
      headerName: t('analysis.history.col_date'),
      minWidth: 104,
      renderCell: ({ row }) => <span className="text-slate-400 font-semibold">{row.trade_date}</span>,
    },
    {
      field: 'signal',
      headerName: t('analysis.history.col_signal'),
      minWidth: 104,
      renderCell: ({ row }) => <SignalBadge signal={row.signal} />,
    },
    {
      field: 'duration_seconds',
      headerName: t('analysis.history.col_duration'),
      type: 'number',
      minWidth: 96,
      renderCell: ({ row }) => <span className="text-slate-500 font-mono">{(row.duration_seconds ?? 0).toFixed(1)}s</span>,
    },
    {
      field: 'triggered_by',
      headerName: t('analysis.history.col_source'),
      minWidth: 96,
      renderCell: ({ row }) => <span className="text-slate-500">{row.triggered_by}</span>,
    },
    {
      field: 'created_at',
      headerName: t('analysis.history.col_time'),
      minWidth: 132,
      renderCell: ({ row }) => (
        <span className="text-slate-600 font-mono text-[10px]">
          {new Date(row.created_at).toLocaleString(undefined, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      ),
    },
    {
      field: 'actions',
      headerName: t('analysis.history.col_actions'),
      minWidth: 84,
      sortable: false,
      filterable: false,
      align: 'right',
      headerAlign: 'right',
      renderCell: ({ row }) => (
        <button
          onClick={event => { event.stopPropagation(); setItemToDelete(row.id) }}
          disabled={deletingId === row.id}
          className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer disabled:opacity-50"
          title={t('analysis.history.confirm_delete_single')}
        >
          {deletingId === row.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
        </button>
      ),
    },
  ], [t, deletingId])

  const historyReportEntries = detail
    ? visibleReportEntries(detail as unknown as Record<string, unknown>)
    : []

  if (loading) return <div className="p-8 text-slate-500 text-xs">{t('analysis.history.loading')}</div>

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl overflow-hidden">
        {items.length === 0 ? (
          <p className="p-6 text-slate-600 text-xs text-center">{t('analysis.history.empty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="flex justify-end items-center gap-2 px-4 py-2 border-b border-white/[0.04]">
              <button
                onClick={() => exportAnalysesCSV(items)}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold text-slate-500 hover:text-violet-300 hover:bg-violet-500/10 border border-white/[0.04] hover:border-violet-500/20 transition cursor-pointer"
              >
                <Download size={11} /> Export CSV
              </button>
              <button
                onClick={() => setShowClearAllModal(true)}
                disabled={clearingAll}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold text-rose-400 hover:text-white hover:bg-rose-500/20 border border-rose-500/20 transition cursor-pointer disabled:opacity-40"
              >
                {clearingAll ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                {t('analysis.history.btn_clear_all')}
              </button>
            </div>
            <AppDataGrid<AnalysisListItem>
              rows={items}
              columns={columns}
              ariaLabel={t('analysis.history.col_symbol')}
              minHeight={280}
              density="compact"
              hideFooter
              onRowClick={params => openDetail(params.row.id)}
              sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
            />
          </div>
        )}
      </div>

      {itemToDelete !== null && (
        <div className="fixed inset-0 bg-black/75 z-[60] flex items-center justify-center p-5 backdrop-blur-md">
          <div className="bg-slate-900 border border-white/[0.06] rounded-3xl p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <div className="space-y-2">
              <h3 className="text-white text-lg font-display font-bold flex items-center gap-2">
                <Trash2 className="text-rose-500" size={18} /> {t('analysis.history.btn_clear_all')}
              </h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                {t('analysis.history.confirm_delete_single')}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={confirmDeleteSingle}
                disabled={deletingId !== null}
                className="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold py-2.5 rounded-xl transition shadow shadow-rose-600/20 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {deletingId !== null ? <Loader2 size={13} className="animate-spin" /> : null}
                Sil
              </button>
              <button
                onClick={() => setItemToDelete(null)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold py-2.5 rounded-xl transition cursor-pointer"
              >
                {t('analysis.btn.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {showClearAllModal && (
        <div className="fixed inset-0 bg-black/75 z-[60] flex items-center justify-center p-5 backdrop-blur-md">
          <div className="bg-slate-900 border border-white/[0.06] rounded-3xl p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <div className="space-y-2">
              <h3 className="text-white text-lg font-display font-bold flex items-center gap-2">
                <AlertTriangle className="text-rose-500" size={18} /> {t('analysis.history.btn_clear_all')}
              </h3>
              <p className="text-slate-400 text-xs leading-relaxed">
                {t('analysis.history.confirm_clear_all')}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={confirmClearAll}
                disabled={clearingAll}
                className="flex-1 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold py-2.5 rounded-xl transition shadow shadow-rose-600/20 cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                {clearingAll ? <Loader2 size={13} className="animate-spin" /> : null}
                {t('analysis.history.btn_clear_all')}
              </button>
              <button
                onClick={() => setShowClearAllModal(false)}
                className="flex-1 bg-white/5 hover:bg-white/10 text-slate-300 text-xs font-semibold py-2.5 rounded-xl transition cursor-pointer"
              >
                {t('analysis.btn.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {(detail || detailLoading) && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center p-3 md:p-4 overflow-y-auto backdrop-blur-sm">
          <div className="bg-slate-900 border border-white/[0.06] rounded-2xl p-4 md:p-6 w-full max-w-4xl my-4 md:my-8 space-y-4 shadow-2xl flex flex-col max-h-[90vh]">
            {detailLoading ? (
              <div className="flex items-center gap-2 text-slate-400 py-12 justify-center"><Loader2 className="animate-spin" size={16} /> {t('analysis.history.detail_loading')}</div>
            ) : detail ? (
              <>
                <div className="flex items-start justify-between border-b border-white/[0.04] pb-3 shrink-0">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-xl font-display font-bold text-white font-mono">{detail.ticker}</h3>
                      <SignalBadge signal={detail.signal} large />
                      {detail.quality ? <QualityBadge quality={detail.quality as RunQuality} /> : null}
                    </div>
                    <p className="text-[10px] text-slate-500 font-semibold">{detail.trade_date} • {(detail.duration_seconds ?? 0).toFixed(1)}s • {detail.llm_calls} LLM • {(detail.tokens_in + detail.tokens_out).toLocaleString()} token{detail.estimated_cost_usd ? ` • ~$${detail.estimated_cost_usd.toFixed(4)}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <button onClick={() => exportMarkdown(detail, language as 'en' | 'tr')} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_md')}>
                      <Download size={12} /> MD
                    </button>
                    <button onClick={() => exportPDF(detail, language as 'en' | 'tr')} className="flex items-center gap-1 bg-white/5 hover:bg-white/10 text-[10px] font-bold text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer" title={t('analysis.history.btn_download_pdf')}>
                      <FileDown size={12} /> PDF
                    </button>
                    <button
                      onClick={() => shareReport(detail.id)}
                      disabled={sharing}
                      className="flex items-center gap-1 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 text-[10px] font-bold text-violet-400 px-2.5 py-1.5 rounded-lg transition cursor-pointer disabled:opacity-40"
                      title={t('analysis.share_report')}
                    >
                      {sharing ? <Loader2 size={12} className="animate-spin" /> : <Share2 size={12} />} Share
                    </button>
                    {shareLink && (
                      <div className="flex items-center gap-1 max-w-[min(24rem,50vw)]">
                        <input
                          aria-label={t('analysis.share_link')}
                          readOnly
                          value={shareLink}
                          onFocus={event => event.currentTarget.select()}
                          className="min-w-0 flex-1 bg-slate-950/70 border border-emerald-500/20 rounded-lg px-2 py-1.5 text-[10px] text-emerald-300 font-mono outline-none focus:border-emerald-400/50"
                          title={shareLink}
                        />
                        <button
                          onClick={async () => {
                            try {
                              if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable')
                              await navigator.clipboard.writeText(shareLink)
                              notify('success', 'Share link copied to clipboard', 'Share')
                            } catch {
                              notify('error', 'Select and copy the share link manually', 'Share')
                            }
                          }}
                          className="shrink-0 flex items-center gap-1 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-[10px] font-bold text-emerald-400 px-2 py-1.5 rounded-lg transition cursor-pointer"
                          title={t('analysis.copy_share_link')}
                        >
                          <Copy size={11} /> Copy
                        </button>
                      </div>
                    )}
                    <button onClick={() => { setDetail(null); setShareLink(null) }} className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5 cursor-pointer"><X size={16} /></button>
                  </div>
                </div>

                <div className="flex items-center gap-1 p-1 bg-slate-950/60 border border-white/[0.04] rounded-xl shrink-0">
                  <button
                    onClick={() => setActiveDetailTab('reports')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'reports' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.reports')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('debate')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'debate' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.debate')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('chat')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'chat' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.qa')}
                  </button>
                  <button
                    onClick={() => setActiveDetailTab('timetravel')}
                    className={`flex-1 text-center py-2.5 text-xs sm:py-1.5 sm:text-[10px] uppercase tracking-wider font-bold rounded-lg transition ${
                      activeDetailTab === 'timetravel' ? 'bg-white/5 text-white' : 'text-slate-500 hover:text-white'
                    }`}
                  >
                    {t('analysis.tab.timetravel')}
                  </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto">
                  {activeDetailTab === 'reports' && (
                    <div className="space-y-2 pr-1">
                      {detail.risk_metrics ? <RiskMetricsCard metrics={detail.risk_metrics as any} /> : null}
                      <PortfolioDecisionCard
                        acceptedPortfolioDecision={detail.portfolio_decision_json}
                      />
                      <StrategyTransitionCard
                        analysisPlan={detail.analysis_plan_json}
                        strategyBefore={detail.strategy_before_json}
                        strategyAfter={detail.strategy_after_json}
                        strategyCandidate={detail.strategy_candidate_json}
                        pmProposal={detail.pm_proposal_json}
                        acceptedDecision={detail.portfolio_decision_json}
                        transition={detail.decision_transition_json}
                        calibratedConfidence={detail.calibrated_confidence ?? null}
                        strategyUpdateStatus={detail.strategy_update_status ?? null}
                        strategyBeforeVersion={detail.strategy_before_version ?? null}
                        strategyAfterVersion={detail.strategy_after_version ?? null}
                      />
                      {([
                        ...historyReportEntries,
                        ['investment_plan', detail.investment_plan],
                        ['final_decision', detail.final_decision],
                      ] as [string, string][]).filter(entry => !!entry[1]).map(([k, v]) => (
                        <ReportCard key={k} label={readableSectionLabel(sectionLabels, k)} content={v} />
                      ))}
                      {(detail.bull_history || detail.bear_history || detail.judge_decision) && (
                        <div className="border-t border-white/[0.04] pt-3 mt-4">
                          <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{t('analysis.debate_records')}</h4>
                          <div className="space-y-2">
                            {detail.bull_history ? <ReportCard label="Bull" content={detail.bull_history as string} /> : null}
                            {detail.bear_history ? <ReportCard label="Bear" content={detail.bear_history as string} /> : null}
                            {detail.judge_decision && <ReportCard label="Judge" content={detail.judge_decision} />}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {activeDetailTab === 'debate' && (
                    <DebateHistoryWidget investmentHistory={detail.investment_debate_history} riskHistory={detail.risk_debate_history} />
                  )}
                  {activeDetailTab === 'chat' && (
                    <AnalysisChatWidget analysisId={detail.id} />
                  )}
                  {activeDetailTab === 'timetravel' && (
                    <TimeTravelWidget
                      analysisId={detail.id}
                      onRollbackStart={(taskId) => onRollbackStart(taskId, detail.ticker)}
                    />
                  )}
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
