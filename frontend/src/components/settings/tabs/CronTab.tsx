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

export function CronTab({ s, t, update, cronStatus }: CronTabProps) {
  return (
    <ErrorBoundary name="SettingsCron">
    <Section title={t('settings.section_cron')}>
      <div className="flex items-center justify-between bg-white/[0.02] border border-white/[0.04] p-3 rounded-xl mb-2">
        <div className="flex flex-col">
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{t('settings.cron_engine_status')}</span>
          <div className="flex items-center gap-2 mt-1">
            <div className={`w-2 h-2 rounded-full ${cronStatus?.running ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-rose-500'}`} />
            <span className="text-xs font-bold text-slate-200">
              {cronStatus?.running ? t('settings.cron_online') : t('settings.cron_offline')}
            </span>
          </div>
        </div>
        {cronStatus?.job_configured && (
          <div className="text-right">
            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">{t('settings.cron_next_run_utc')}</span>
            <div className="text-xs font-mono text-violet-300 mt-1">
              {cronStatus.next_run_time ? new Date(cronStatus.next_run_time).toLocaleString() : '—'}
            </div>
          </div>
        )}
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
