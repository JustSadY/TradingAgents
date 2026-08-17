import { useAnalysisTimeTravelResume } from '../../api/generated/analysis/analysis'
import { useTranslation } from '../../contexts/LanguageContext'
import { notify } from '../../utils/notify'
import axios from 'axios'
import { Loader2, Scale } from 'lucide-react'
import { useEffect, useState } from 'react'

export function TimeTravelWidget({
  analysisId,
  onRollbackStart,
}: {
  analysisId: number
  onRollbackStart: (taskId: string) => void
}) {
  const { t, language } = useTranslation()
  const timeTravel = useAnalysisTimeTravelResume()
  const [checkpoints, setCheckpoints] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedCp, setSelectedCp] = useState<any>(null)
  const [updateFields, setUpdateFields] = useState<Record<string, string>>({})
  const [rollbackLoading, setRollbackLoading] = useState(false)

  useEffect(() => {
    axios
      .get(`/api/analysis/${analysisId}/checkpoints`)
      .then((r) => {
        setCheckpoints(r.data)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [analysisId])

  const handleSelectCheckpoint = (cp: any) => {
    setSelectedCp(cp)
    const fields: Record<string, string> = {}
    if (cp.node === 'Research Manager' || cp.node === 'ResearchManager') {
      fields['investment_plan'] = ''
    } else if (cp.node === 'Portfolio Manager' || cp.node === 'portfolio_manager') {
      // Preserve the PM proposal stored at this checkpoint; it is the input to
      // the downstream stability controller. Clear only downstream canonical
      // outputs so a previous controller result cannot leak into the replay.
      fields['portfolio_decision_json'] = '{}'
      fields['decision_transition_json'] = '{}'
      fields['final_trade_decision'] = ''
      fields['final_signal'] = ''
    } else if (cp.node === 'Agent Q&A' || cp.node === 'agent_qa') {
      fields['agent_qa_report'] = ''
    } else {
      fields['investment_plan'] = ''
    }
    setUpdateFields(fields)
  }

  const handleRollback = async () => {
    if (!selectedCp) return
    setRollbackLoading(true)
    try {
      const data = await timeTravel.mutateAsync({
        analysisId,
        data: {
          checkpoint_id: selectedCp.checkpoint_id,
          update_state: updateFields,
        },
      })
      notify('success', language === 'tr' ? 'Zaman yolculuğu başlatıldı!' : 'Time travel initiated!')
      onRollbackStart(data.task_id)
    } catch (err: any) {
      notify('error', err.response?.data?.detail || 'Rollback failed')
    } finally {
      setRollbackLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-12 justify-center">
        <Loader2 className="animate-spin" size={16} /> {t('analysis.timetravel.loading_checkpoints')}
      </div>
    )
  }

  if (checkpoints.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 text-xs">
        {t('analysis.timetravel.no_checkpoints')}
      </div>
    )
  }

  return (
    <div className="space-y-5 p-1">
      <div className="space-y-2">
        <h4 className="text-white text-xs font-bold uppercase tracking-wider">
          {t('analysis.timetravel.title')}
        </h4>
        <p className="text-slate-400 text-[11px] leading-relaxed">
          {language === 'tr'
            ? 'Mevcut analizi seçtiğiniz bir adıma geri sarıp durum verilerini değiştirerek oradan itibaren yeniden çalıştırabilirsiniz.'
            : 'Roll back the execution flow to a selected checkpoint step, edit state fields, and resume propagation.'}
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-[10px] font-bold text-slate-500 block uppercase tracking-wider">
          {t('analysis.timetravel.select_checkpoint')}
        </label>
        <div className="grid grid-cols-1 gap-2 max-h-36 overflow-y-auto pr-1">
          {checkpoints.map((cp) => (
            <div
              key={cp.checkpoint_id}
              onClick={() => handleSelectCheckpoint(cp)}
              className={`p-3 rounded-xl border text-xs cursor-pointer transition-all flex items-center justify-between ${
                selectedCp?.checkpoint_id === cp.checkpoint_id
                  ? 'bg-violet-600/10 border-violet-500 text-white'
                  : 'bg-slate-900/40 border-white/[0.04] text-slate-300 hover:border-white/[0.1]'
              }`}
            >
              <div className="flex items-center gap-2 font-semibold">
                <span className="text-[10px] text-slate-500 font-mono">#{cp.step}</span>
                <span>{cp.label}</span>
              </div>
              <span className="text-[9px] text-slate-600 font-mono">
                {cp.checkpoint_id.slice(0, 8)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {selectedCp && (
        <div className="space-y-4 animate-in fade-in duration-300">
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-slate-500 block uppercase tracking-wider">
              {t('analysis.timetravel.edit_fields')}
            </label>
            {Object.keys(updateFields).map((field) => (
              <div key={field} className="space-y-1.5">
                <span className="text-[10px] font-semibold text-slate-400 font-mono">{field}</span>
                <textarea
                  value={updateFields[field]}
                  onChange={(e) =>
                    setUpdateFields((prev) => ({ ...prev, [field]: e.target.value }))
                  }
                  className="w-full h-24 bg-slate-950 border border-white/[0.08] rounded-xl p-3 text-xs text-white outline-none focus:border-violet-500/50 font-mono leading-relaxed"
                  placeholder={
                    field === 'portfolio_decision_json'
                      ? '{"rating": "Buy", "entry_price": 150.0, "position_size_pct": 5}'
                      : `Enter custom ${field} value...`
                  }
                />
              </div>
            ))}
          </div>

          <button
            onClick={handleRollback}
            disabled={rollbackLoading}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 py-2.5 rounded-xl text-xs font-semibold text-white cursor-pointer shadow shadow-violet-600/20 transition disabled:opacity-40"
          >
            {rollbackLoading ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Scale size={13} />
            )}
            {t('analysis.timetravel.btn_rollback')}
          </button>
        </div>
      )}
    </div>
  )
}
