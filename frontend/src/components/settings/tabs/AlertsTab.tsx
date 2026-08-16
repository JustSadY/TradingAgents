import type { SettingsRead } from '../../../api/generated/model'
import { ErrorBoundary } from '../../ErrorBoundary'
import { Input, Row, Section } from './primitives'

type Settings = SettingsRead
type Translate = (key: string, options?: Record<string, unknown>) => string
type Update = (key: keyof Settings, value: unknown) => void

interface AlertsTabProps {
  s: Settings
  t: Translate
  update: Update
}

export function AlertsTab({ s, t, update }: AlertsTabProps) {
  return (
      <ErrorBoundary name="SettingsAlertGuardrails">
        <Section title={t('settings.section_alert_guardrails')}>
          <p className="text-[10px] text-slate-500 px-1 leading-snug">
            {t('settings.alert_guardrails_hint')}
          </p>
          <Row label={t('settings.row_max_active_alerts')}>
            <input
              type="number"
              min="1"
              max="500"
              className={Input}
              value={s.max_active_alerts ?? 30}
              onChange={e => update('max_active_alerts', Number.parseInt(e.target.value) || 1)}
            />
          </Row>
          <Row label={t('settings.row_max_ai_alerts_per_run')}>
            <div className="space-y-1">
              <input
                type="number"
                min="0"
                max="20"
                className={Input}
                value={s.max_ai_alerts_per_run ?? 3}
                onChange={e => update('max_ai_alerts_per_run', Math.max(0, Number.parseInt(e.target.value) || 0))}
              />
              <p className="text-[10px] text-slate-500 leading-snug">{t('settings.alert_ai_limit_hint')}</p>
            </div>
          </Row>
          <Row label={t('settings.row_ai_alert_cooldown_hours')}>
            <div className="space-y-1">
              <input
                type="number"
                min="0"
                max="720"
                className={Input}
                value={s.ai_alert_cooldown_hours ?? 24}
                onChange={e => update('ai_alert_cooldown_hours', Math.max(0, Number.parseInt(e.target.value) || 0))}
              />
              <p className="text-[10px] text-slate-500 leading-snug">{t('settings.alert_cooldown_hint')}</p>
            </div>
          </Row>
        </Section>
      </ErrorBoundary>
  )
}
