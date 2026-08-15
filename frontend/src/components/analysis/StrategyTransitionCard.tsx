import { useTranslation } from '../../contexts/LanguageContext'

type JsonObject = Record<string, unknown>

export interface StrategyTransitionCardProps {
  analysisPlan?: unknown
  strategyBefore?: unknown
  strategyAfter?: unknown
  strategyCandidate?: unknown
  pmProposal?: unknown
  acceptedDecision?: unknown
  transition?: unknown
  calibratedConfidence?: number | null
  strategyUpdateStatus?: string | null
  strategyBeforeVersion?: number | null
  strategyAfterVersion?: number | null
}

function asObject(value: unknown): JsonObject | null {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) return value as JsonObject
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const parsed: unknown = JSON.parse(value)
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed as JsonObject : null
  } catch {
    return null
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function enumLabel(value: string | null | undefined): string {
  return value ? value.replaceAll('_', ' ') : '—'
}

function percent(value: number | null): string {
  if (value === null) return '—'
  return `${(value <= 1 ? value * 100 : value).toFixed(0)}%`
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.flatMap(item => typeof item === 'string' && item.trim() ? [item.trim()] : [])
}

function unique(values: string[]): string[] {
  return [...new Set(values)]
}

function decisionFrom(value: unknown): JsonObject | null {
  const record = asObject(value)
  if (!record) return null
  for (const key of ['proposed_decision', 'decision', 'accepted_decision']) {
    const nested = asObject(record[key])
    if (nested) {
      const decision = decisionFrom(nested)
      if (decision) return decision
    }
  }
  return stringValue(record.rating) || stringValue(record.action) ? record : null
}

function questionsFromPlan(plan: JsonObject | null): string[] {
  if (!plan) return []
  const direct = strings(plan.unresolved_questions)
  const analystQuestions = asObject(plan.analyst_questions)
  const planned = analystQuestions
    ? Object.values(analystQuestions).flatMap(value => strings(value))
    : []
  return unique([...direct, ...planned])
}

function snapshotFrom(value: unknown): JsonObject | null {
  const snapshot = asObject(value)
  return snapshot && (stringValue(snapshot.strategic_bias) || stringValue(snapshot.accepted_rating) || numberValue(snapshot.version) !== null)
    ? snapshot
    : null
}

function Snapshot({
  title,
  snapshot,
  version,
}: {
  title: string
  snapshot: JsonObject | null
  version: number | null
}) {
  const { t } = useTranslation()
  const bias = stringValue(snapshot?.strategic_bias)
  const rating = stringValue(snapshot?.accepted_rating)
  const conviction = numberValue(snapshot?.conviction)
  const status = stringValue(snapshot?.status)
  const resolvedVersion = numberValue(snapshot?.version) ?? version

  return (
    <div className="min-w-0 rounded-xl border border-white/[0.06] bg-slate-950/35 p-3 space-y-2">
      <h5 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{title}</h5>
      {snapshot ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
          <Field label={t('analysis.strategy.version')} value={resolvedVersion === null ? '—' : `v${resolvedVersion}`} />
          <Field label={t('analysis.strategy.bias')} value={enumLabel(bias)} />
          <Field label={t('analysis.strategy.conviction')} value={percent(conviction)} />
          <Field label={t('analysis.strategy.rating')} value={enumLabel(rating)} />
          {status && <Field label={t('analysis.strategy.status')} value={enumLabel(status)} />}
        </div>
      ) : (
        <p className="text-[11px] text-slate-500">{t('analysis.strategy.none')}</p>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <span className="block text-slate-500 uppercase tracking-wide font-semibold">{label}</span>
      <span className="block truncate font-mono text-slate-200" title={value}>{value}</span>
    </div>
  )
}

function DecisionSummary({
  title,
  decision,
  confidence,
  accepted,
}: {
  title: string
  decision: JsonObject | null
  // `??` below handles the absent case, so undefined is as usable as null.
  confidence: number | null | undefined
  accepted?: boolean
}) {
  const { t } = useTranslation()
  const rating = stringValue(decision?.rating) ?? stringValue(decision?.action)
  const allocation = numberValue(
    decision?.target_allocation_pct ?? decision?.position_size_pct ?? decision?.target_weight,
  )
  return (
    <div className={`min-w-0 rounded-xl border p-3 space-y-2 ${accepted ? 'border-emerald-500/20 bg-emerald-500/[0.05]' : 'border-violet-500/20 bg-violet-500/[0.05]'}`}>
      <div className="flex items-center justify-between gap-2">
        <h5 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{title}</h5>
        {rating && <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${accepted ? 'bg-emerald-500/15 text-emerald-300' : 'bg-violet-500/15 text-violet-300'}`}>{enumLabel(rating)}</span>}
      </div>
      {decision ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[10px]">
          <Field label={t('analysis.strategy.rating')} value={enumLabel(rating)} />
          <Field label={t('analysis.strategy.confidence')} value={percent(confidence ?? numberValue(decision.confidence_score))} />
          {allocation !== null && <Field label={t('analysis.strategy.allocation')} value={percent(allocation)} />}
        </div>
      ) : (
        <p className="text-[11px] text-slate-500">{t('analysis.strategy.none')}</p>
      )}
    </div>
  )
}

/**
 * Renders the auditable path from a neutral research plan to an accepted
 * decision. In shadow/off mode the physical portfolio decision stays the PM
 * canonical output, while controller output is explicitly counterfactual.
 * It accepts JSON columns as either parsed objects or serialized strings so
 * legacy/history responses remain safe to render.
 */
export function StrategyTransitionCard(props: StrategyTransitionCardProps) {
  const { t } = useTranslation()
  const plan = asObject(props.analysisPlan)
  const candidate = asObject(props.strategyCandidate)
  const transition = asObject(props.transition)
  const before = snapshotFrom(props.strategyBefore) ?? snapshotFrom(candidate?.strategy_before)
  const after = snapshotFrom(props.strategyAfter) ?? snapshotFrom(candidate?.strategy_after)
  const pmContainer = asObject(props.pmProposal) ?? asObject(transition?.pm_proposal)
  const physicalDecisionContainer = asObject(props.acceptedDecision)
  const acceptedContainer = physicalDecisionContainer ?? asObject(transition?.accepted_decision)
  const pmDecision = decisionFrom(pmContainer)
  const acceptedDecision = decisionFrom(acceptedContainer)
  const controllerDecision = decisionFrom(transition?.accepted_decision)
  const effectiveAcceptedDecision = acceptedDecision ?? controllerDecision
  const physicalDecision = decisionFrom(physicalDecisionContainer) ?? pmDecision
  const controllerMode = stringValue(transition?.mode)?.toLowerCase()
  const controllerCounterfactual = (controllerMode === 'shadow' || controllerMode === 'off')
    && transition?.canonical_enforced !== true
  const displayedDecision = controllerCounterfactual ? physicalDecision : effectiveAcceptedDecision
  const displayedDecisionConfidence = controllerCounterfactual
    ? numberValue(physicalDecision?.confidence_score)
    : props.calibratedConfidence
  const candidateAction = stringValue(candidate?.revision_action)
  const updateStatus = stringValue(props.strategyUpdateStatus)
  const outcome = stringValue(transition?.outcome) ?? stringValue(transition?.status)
  const executionAction = stringValue(acceptedContainer?.execution_action)
    ?? stringValue(transition?.execution_action)
    ?? stringValue(asObject(transition?.accepted_decision)?.execution_action)
  const tacticalAction = stringValue(acceptedContainer?.tactical_action)
    ?? stringValue(asObject(transition?.accepted_decision)?.tactical_action)
  const calibratedConfidence = props.calibratedConfidence
    ?? numberValue(acceptedContainer?.calibrated_confidence)
    ?? numberValue(transition?.calibrated_confidence)
    ?? numberValue(asObject(transition?.accepted_decision)?.calibrated_confidence)
  const reason = stringValue(transition?.reason) ?? stringValue(candidate?.revision_reason)
  const reasons = unique([
    ...strings(transition?.reason_codes),
    ...strings(transition?.reasons),
    ...(reason ? [reason] : []),
  ])
  const questions = questionsFromPlan(plan)
  const controllerResult = controllerDecision ?? effectiveAcceptedDecision
  const holdOrNoOrder = executionAction === 'NO_NEW_ORDER'
    || executionAction === 'FREEZE'
    || executionAction === 'no_order'
    || executionAction === 'freeze'
    || tacticalAction === 'HOLD'
    || stringValue(controllerResult?.rating)?.toLowerCase() === 'hold'

  const hasData = Boolean(
    plan || before || after || candidate || pmDecision || effectiveAcceptedDecision || transition || updateStatus || props.calibratedConfidence != null,
  )
  if (!hasData) return null

  return (
    <section data-testid="strategy-transition-card" className="rounded-2xl border border-cyan-500/20 bg-cyan-500/[0.035] p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-cyan-300">{t('analysis.strategy.title')}</h4>
          <p className="text-[11px] leading-relaxed text-slate-400">
            {controllerCounterfactual ? t('analysis.strategy.subtitle_counterfactual') : t('analysis.strategy.subtitle')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {candidateAction && <span className="rounded-md border border-cyan-400/20 bg-cyan-400/10 px-2 py-0.5 text-[10px] font-bold text-cyan-200">{enumLabel(candidateAction)}</span>}
          {controllerCounterfactual && (
            <span data-testid="strategy-controller-counterfactual" className="rounded-md border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-[10px] font-bold text-amber-200">
              {enumLabel(controllerMode)} · {t('analysis.strategy.counterfactual')}
            </span>
          )}
          {updateStatus && <span data-testid="strategy-update-status" className="rounded-md border border-slate-500/25 bg-slate-500/10 px-2 py-0.5 text-[10px] font-bold text-slate-300">{enumLabel(updateStatus)}</span>}
        </div>
      </div>

      {plan && (
        <div className="rounded-xl border border-white/[0.06] bg-slate-950/30 p-3 space-y-2">
          <div className="flex flex-wrap justify-between gap-2">
            <h5 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{t('analysis.strategy.analysis_plan')}</h5>
            {stringValue(plan.horizon) && <span className="text-[10px] font-mono text-slate-400">{stringValue(plan.horizon)}</span>}
          </div>
          {stringValue(plan.objective) && <p className="text-xs leading-relaxed text-slate-200">{stringValue(plan.objective)}</p>}
          {questions.length > 0 && (
            <ul className="space-y-1 text-[11px] leading-relaxed text-slate-400 list-disc pl-4">
              {questions.slice(0, 3).map(question => <li key={question}>{question}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Snapshot title={t('analysis.strategy.before')} snapshot={before} version={props.strategyBeforeVersion ?? null} />
        <Snapshot title={t('analysis.strategy.after')} snapshot={after} version={props.strategyAfterVersion ?? null} />
      </div>

      {(candidateAction || updateStatus || reason) && (
        <div className="grid grid-cols-1 gap-x-3 gap-y-2 rounded-xl border border-white/[0.06] bg-slate-950/30 p-3 text-[10px] sm:grid-cols-3">
          <Field label={t('analysis.strategy.revision')} value={enumLabel(candidateAction)} />
          <Field label={t('analysis.strategy.change_strength')} value={enumLabel(stringValue(candidate?.change_strength))} />
          <Field label={t('analysis.strategy.status')} value={enumLabel(updateStatus)} />
          {reason && <p className="sm:col-span-3 border-t border-white/[0.06] pt-2 text-[11px] leading-relaxed text-slate-300">{reason}</p>}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <DecisionSummary title={t('analysis.strategy.pm_proposal')} decision={pmDecision} confidence={numberValue(pmContainer?.confidence_score)} />
        <DecisionSummary
          title={controllerCounterfactual ? t('analysis.strategy.pm_canonical_decision') : t('analysis.strategy.accepted_decision')}
          decision={displayedDecision}
          confidence={displayedDecisionConfidence}
          accepted={!controllerCounterfactual}
        />
      </div>

      {(outcome || reasons.length > 0 || executionAction || calibratedConfidence !== null) && (
        <div className="rounded-xl border border-white/[0.06] bg-slate-950/30 p-3 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h5 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{t('analysis.strategy.controller')}</h5>
            {outcome && <span data-testid="strategy-controller-outcome" className="rounded-md bg-slate-700/50 px-2 py-0.5 text-[10px] font-bold text-slate-200">{enumLabel(outcome)}</span>}
          </div>
          {controllerCounterfactual && (
            <p data-testid="strategy-counterfactual-note" className="rounded-lg border border-amber-500/20 bg-amber-500/[0.08] px-2.5 py-2 text-[11px] leading-relaxed text-amber-100">
              {t('analysis.strategy.counterfactual_hint')}
            </p>
          )}
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[10px] sm:grid-cols-3">
            <Field label={t('analysis.strategy.confidence')} value={percent(calibratedConfidence)} />
            <Field label={t('analysis.strategy.execution')} value={enumLabel(executionAction)} />
            <Field label={t('analysis.strategy.tactical')} value={enumLabel(tacticalAction)} />
          </div>
          {holdOrNoOrder && (
            <p data-testid="strategy-no-order" className="rounded-lg border border-amber-500/20 bg-amber-500/[0.08] px-2.5 py-2 text-[11px] font-medium text-amber-200">
              {controllerCounterfactual ? t('analysis.strategy.counterfactual_no_order') : t('analysis.strategy.no_order')}
            </p>
          )}
          {reasons.length > 0 && (
            <ul className="space-y-1 border-t border-white/[0.06] pt-2 text-[11px] leading-relaxed text-slate-400 list-disc pl-4">
              {reasons.map(item => <li key={item}>{item.replaceAll('_', ' ')}</li>)}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
