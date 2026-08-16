import { Bell, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import type { SettingsRead, WebhookDeliveryRead } from '../../../api/generated/model'
import type { Meta } from '../../../hooks/useMeta'
import { ErrorBoundary } from '../../ErrorBoundary'
import { Input, Row, Section } from './primitives'

/** Fallback list for while `/api/meta` is still loading. */
const DEFAULT_WEBHOOK_EVENTS = ['analysis_complete', 'trade_executed', 'alert_triggered', 'signal_flip']

type Settings = SettingsRead
type Translate = (key: string, options?: Record<string, unknown>) => string
type Update = (key: keyof Settings, value: unknown) => void

interface WebhooksTabProps {
  s: Settings
  t: Translate
  update: Update
  meta: Meta | null
  userId: number | undefined
  webhookEvents: string[]
  deliveries: WebhookDeliveryRead[]
  loadingDeliveries: boolean
  loadDeliveries: () => void
  testWebhook: () => void
  toggleBrowserNotify: () => void
  browserNotify: boolean
  webhookTesting: boolean
  webhookTestResult: string | null
}

export function WebhooksTab({ s, t, update, meta, userId, webhookEvents, deliveries, loadingDeliveries, loadDeliveries, testWebhook, toggleBrowserNotify, browserNotify, webhookTesting, webhookTestResult }: WebhooksTabProps) {
  return (
    <ErrorBoundary name="SettingsWebhooks">
    <Section title={t('settings.section_notifications')}>
      <Row label={t('settings.row_webhook_url')}>
        <div className="flex flex-col gap-1">
          <input
            className={Input}
            placeholder={t('settings.webhook_url_placeholder')}
            value={s.webhook_url || ''}
            onChange={e => update('webhook_url', e.target.value || null)}
          />
          <p className="text-xs text-slate-400 leading-relaxed">
            {t('settings.webhook_help')}
          </p>
        </div>
      </Row>
      <Row label={t('settings.row_webhook_active')}>
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={s.webhook_enabled}
            onChange={e => update('webhook_enabled', e.target.checked)}
            className="w-5 h-5 accent-violet-600 cursor-pointer"
          />
          {s.webhook_url && (
            <button
              onClick={testWebhook}
              disabled={webhookTesting}
              className="text-[10px] bg-white/5 hover:bg-white/10 text-slate-300 px-2.5 py-1.5 rounded-lg transition cursor-pointer font-bold"
            >
              {webhookTesting ? t('settings.webhook_testing') : t('settings.webhook_test_button')}
            </button>
          )}
          {webhookTestResult && (
            <span className={`text-[10px] font-bold ${webhookTestResult.startsWith('✓') ? 'text-emerald-400' : 'text-rose-400'}`}>
              {webhookTestResult}
            </span>
          )}
        </div>
      </Row>
      <Row label={t('settings.row_notification_events')}>
        <div className="flex flex-col gap-2.5 pt-1">
          {(meta?.webhook_events ?? DEFAULT_WEBHOOK_EVENTS).map(key => (
            <label key={key} className="flex items-center gap-2 text-xs font-medium text-slate-400 cursor-pointer hover:text-slate-300 select-none">
              <input
                type="checkbox"
                className="accent-violet-600 rounded w-4 h-4 cursor-pointer"
                checked={webhookEvents.includes(key)}
                onChange={e => {
                  const next = e.target.checked
                    ? [...webhookEvents, key]
                    : webhookEvents.filter(event => event !== key)
                  update('webhook_events', next)
                }}
              />
              {t(`settings.event_${key}`) || key}
            </label>
          ))}
        </div>
      </Row>
      {!userId && (
        <Row label={t('settings.row_browser_notifications')}>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleBrowserNotify}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors cursor-pointer ${browserNotify ? 'bg-violet-600' : 'bg-slate-700'}`}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${browserNotify ? 'translate-x-4.5' : 'translate-x-0.5'}`} />
            </button>
            <Bell size={14} className={browserNotify ? 'text-violet-400' : 'text-slate-600'} />
            <span className="text-[10px] text-slate-500 font-semibold">{browserNotify ? t('settings.browser_notify_on') : t('settings.browser_notify_off')}</span>
          </div>
        </Row>
      )}

      {/* Delivery History */}
      <div className="mt-2 pt-4 border-t border-white/[0.04] space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{t('settings.webhook_recent_deliveries')}</span>
          <button
            onClick={loadDeliveries}
            disabled={loadingDeliveries}
            className="p-1 rounded text-slate-600 hover:text-violet-400 transition cursor-pointer"
            title={t('settings.webhook_refresh_delivery_log')}
          >
            <RefreshCw size={12} className={loadingDeliveries ? 'animate-spin' : ''} />
          </button>
        </div>
        {deliveries.length === 0 ? (
          <p className="text-[10px] text-slate-600 italic">{t('settings.webhook_no_deliveries')}</p>
        ) : (
          <div className="space-y-1.5">
            {deliveries.map(d => (
              <div key={d.id} className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-[10px] ${d.success ? 'bg-emerald-500/5 border-emerald-500/10' : 'bg-rose-500/5 border-rose-500/10'}`}>
                {d.success
                  ? <CheckCircle2 size={12} className="text-emerald-400 shrink-0 mt-0.5" />
                  : <XCircle size={12} className="text-rose-400 shrink-0 mt-0.5" />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-white">{d.event.replace(/_/g, ' ')}</span>
                    {d.status_code && <span className="text-slate-500">HTTP {d.status_code}</span>}
                    <span className="text-slate-600 ml-auto">{new Date(d.created_at).toLocaleTimeString()}</span>
                  </div>
                  {d.error && <p className="text-rose-400 mt-0.5 truncate">{d.error}</p>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
    </ErrorBoundary>
  )
}
