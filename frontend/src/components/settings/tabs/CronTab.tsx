import type { SettingsRead } from '../../../api/generated/model'
import type { CronStatusResponse } from '../../../api/generated/model'
import { ErrorBoundary } from '../../ErrorBoundary'
import { Input, Row, Section } from './primitives'

type Settings = SettingsRead
type Translate = (key: string, options?: Record<string, unknown>) => string
type Update = (key: keyof Settings, value: unknown) => void

interface CronTabProps {
  s: Settings
  t: Translate
  update: Update
  cronStatus: CronStatusResponse | null
}

/** Stable codes the backend publishes, mapped onto their explanations. */
const REASON_KEYS: Record<string, string> = {
  scheduler_not_initialized: 'settings.cron_reason_scheduler_not_initialized',
  scheduler_stopped: 'settings.cron_reason_scheduler_stopped',
  scheduler_stalled: 'settings.cron_reason_scheduler_stalled',
  bootstrap_failed: 'settings.cron_reason_bootstrap_failed',
  job_missing: 'settings.cron_reason_job_missing',
}

const OUTCOME_KEYS: Record<string, string> = {
  ok: 'settings.cron_outcome_ok',
  skipped: 'settings.cron_outcome_skipped',
  error: 'settings.cron_outcome_error',
  missed: 'settings.cron_outcome_missed',
  running: 'settings.cron_outcome_running',
}

function formatTimestamp(value?: string | null): string | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function Detail({ label, value, hint }: { label: string; value: string; hint?: string | null }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{label}</span>
      <span className="text-xs font-mono text-slate-200">{value}</span>
      {hint && <span className="text-[10px] text-slate-500 leading-relaxed">{hint}</span>}
    </div>
  )
}

export function CronTab({ s, t, update, cronStatus }: CronTabProps) {
  // A scheduler that is up but cannot run this user's scan is neither online
  // nor offline: showing it as green is what made a silently stopped schedule
  // indistinguishable from a working one.
  const degradedReason = cronStatus?.degraded_reason ?? null
  const schedulerUp = Boolean(cronStatus?.running)
  const healthy = schedulerUp && !degradedReason
  const dotClass = healthy
    ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'
    : schedulerUp
      ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'
      : 'bg-rose-500'
  const statusLabel = healthy
    ? t('settings.cron_online')
    : schedulerUp
      ? t('settings.cron_degraded')
      : t('settings.cron_offline')
  const reasonText = degradedReason
    ? REASON_KEYS[degradedReason]
      ? t(REASON_KEYS[degradedReason])
      : degradedReason
    : null

  const heartbeatAge = cronStatus?.heartbeat_age_seconds
  const lastRun = formatTimestamp(cronStatus?.last_run_at)
  const lastOutcome = cronStatus?.last_outcome
  const lastOutcomeLabel = lastOutcome
    ? OUTCOME_KEYS[lastOutcome]
      ? t(OUTCOME_KEYS[lastOutcome])
      : lastOutcome
    : null

  return (
    <ErrorBoundary name="SettingsCron">
    <Section title={t('settings.section_cron')}>
      <div className="bg-white/[0.02] border border-white/[0.04] p-3 rounded-xl mb-2">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{t('settings.cron_engine_status')}</span>
            <div className="flex items-center gap-2 mt-1">
              <div className={`w-2 h-2 rounded-full ${dotClass}`} />
              <span className="text-xs font-bold text-slate-200">{statusLabel}</span>
            </div>
          </div>
          {typeof heartbeatAge === 'number' && (
            <div className="text-right">
              <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{t('settings.cron_heartbeat')}</span>
              <div className="text-xs font-mono text-slate-300 mt-1">
                {t('settings.cron_heartbeat_seconds_ago', { seconds: Math.round(heartbeatAge) })}
              </div>
            </div>
          )}
        </div>

        {reasonText && (
          <p className="text-[11px] text-amber-300/90 mt-2 leading-relaxed">
            {reasonText}
            {cronStatus?.degraded_detail && (
              <span className="block text-[10px] text-slate-500 font-mono mt-0.5">{cronStatus.degraded_detail}</span>
            )}
          </p>
        )}

        <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-white/[0.04]">
          <Detail
            label={t('settings.cron_registered_schedule')}
            value={cronStatus?.schedule ?? '—'}
            hint={cronStatus?.timezone}
          />
          <Detail
            label={t('settings.cron_next_run')}
            value={cronStatus?.job_configured ? (formatTimestamp(cronStatus.next_run_time) ?? '—') : t('settings.cron_no_job')}
          />
          <Detail label={t('settings.cron_last_run')} value={lastRun ?? t('settings.cron_never_ran')} />
          <Detail
            label={t('settings.cron_last_outcome')}
            value={lastOutcomeLabel ?? '—'}
            hint={cronStatus?.last_outcome_detail}
          />
        </div>
      </div>

      <Row label={t('settings.row_active')}>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            className="accent-violet-600 w-5 h-5 rounded cursor-pointer"
            checked={s.cron_enabled}
            onChange={e => update('cron_enabled', e.target.checked)}
          />
          <span className={`text-[10px] font-bold uppercase tracking-widest ${s.cron_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
            {s.cron_enabled ? t('settings.cron_enabled') : t('settings.cron_disabled')}
          </span>
        </div>
      </Row>
      <Row label={t('settings.row_schedule')}>
        <input
          className={Input}
          value={s.cron_schedule}
          onChange={e => update('cron_schedule', e.target.value)}
          placeholder={t('settings.cron_schedule_placeholder')}
        />
        <p className="text-[10px] text-slate-500 mt-1.5 font-medium leading-relaxed">
          {t('settings.cron_schedule_help')} <br/>
          <span>{t('settings.cron_schedule_example')}</span>
        </p>
      </Row>
    </Section>
    </ErrorBoundary>
  )
}
