import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  Save, BookmarkPlus, Trash2, Play, Bell,
  Settings as SettingsIcon, Brain, ShieldAlert, Clock, Wrench
} from 'lucide-react'
import { useMeta, triggerMetaRefetch } from '../hooks/useMeta'
import { useAuth } from '../contexts/AuthContext'
import { requestBrowserNotifyPermission, setBrowserNotifyPref, isBrowserNotifyEnabled } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import AgentSettingsPanel from '../components/settings/AgentSettingsPanel'

interface Settings {
  cron_enabled: boolean
  cron_schedule: string
  price_tolerance_pct: number
  llm_provider: string
  llm_model: string
  backend_url: string | null
  openai_reasoning_effort: string | null
  anthropic_effort: string | null
  google_thinking_level: string | null
  output_language: string
  investor_persona: string
  analyst_concurrency_limit: number
  max_recur_limit: number
  benchmark_ticker: string | null
  azure_deployment: string | null
  max_debate_rounds: number
  max_risk_rounds: number
  max_position_size_pct: number
  max_risk_per_trade_pct: number
  strict_stop_loss_mode: boolean
  webhook_url: string | null
  webhook_enabled: boolean
  webhook_events: string
  watchlist: string[]
  node_retry_attempts: number
  node_retry_base_delay: number
}

interface Preset { id: number; name: string; description: string | null; created_at: string }

const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4">
      <h3 className="text-xs font-bold text-violet-400 uppercase tracking-wider border-b border-white/[0.04] pb-2.5">{title}</h3>
      <div className="space-y-4 pt-1">{children}</div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3 last:border-b-0 last:pb-0">
      <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{label}</span>
      <div className="flex-1 sm:max-w-xs w-full">{children}</div>
    </div>
  )
}

export default function Settings({ userId }: { userId?: number } = {}) {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [s, setS] = useState<Settings | null>(null)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [browserNotify, setBrowserNotify] = useState(isBrowserNotifyEnabled())
  const [webhookTesting, setWebhookTesting] = useState(false)
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'general' | 'llm' | 'agents' | 'risk' | 'webhooks' | 'presets' | 'advanced' | 'cron' | 'tools'>('general')
  const [allowedSettings, setAllowedSettings] = useState<string[]>([])
  const [cronStatus, setCronStatus] = useState<{ running: boolean; job_configured: boolean; next_run_time: string | null } | null>(null)
  const meta = useMeta()

  useEffect(() => {
    const settingsUrl = userId ? `/api/settings/users/${userId}` : '/api/settings'
    const permUrl = userId ? `/api/users/${userId}/setting-permissions` : '/api/users/me/setting-permissions'
    Promise.all([
      axios.get(settingsUrl).then(r => r.data),
      axios.get('/api/presets').then(r => r.data).catch(() => []),
      axios.get(permUrl).then(r => r.data.allowed_settings || r.data.permissions || []).catch(() => []),
      axios.get('/api/cron/status').then(r => r.data).catch(() => null),
    ]).then(([settings, presetList, allowedSet, cStatus]) => {
      setS(settings)
      setPresets(presetList)
      setAllowedSettings(userId ? ['general', 'llm', 'risk', 'webhooks', 'cron'] : allowedSet)
      setCronStatus(cStatus)

      const defaultTabs = ['general', 'llm', 'risk', 'webhooks', 'cron']
      const activeDefault = defaultTabs.find(tab => userId || allowedSet.includes(tab))
      if (activeDefault) {
        setActiveTab(activeDefault as any)
      } else if (isAdmin) {
        setActiveTab('advanced')
      }
    })
  }, [isAdmin, userId])

  const loadPresets = () => axios.get('/api/presets').then(r => setPresets(r.data))

  const savePreset = async () => {
    if (!presetName.trim() || !s) return
    setPresetSaving(true)
    try {
      await axios.post('/api/presets', { name: presetName.trim(), settings_json: JSON.stringify(s) })
      setPresetName('')
      await loadPresets()
    } finally { setPresetSaving(false) }
  }

  const applyPreset = async (id: number) => {
    await axios.post(`/api/presets/${id}/apply`)
    const settingsUrl = userId ? `/api/settings/users/${userId}` : '/api/settings'
    const settingsRes = await axios.get(settingsUrl)
    setS(settingsRes.data)
  }

  const deletePreset = async (id: number) => {
    await axios.delete(`/api/presets/${id}`)
    setPresets(prev => prev.filter(p => p.id !== id))
  }

  const testWebhook = async () => {
    if (!s?.webhook_url) return
    setWebhookTesting(true); setWebhookTestResult(null)
    try {
      await axios.post('/api/settings/test-webhook', { url: s.webhook_url })
      setWebhookTestResult(t('settings.webhook_success'))
    } catch { setWebhookTestResult(t('settings.webhook_failed')) }
    finally { setWebhookTesting(false) }
  }

  const toggleBrowserNotify = async () => {
    if (!browserNotify) {
      const granted = await requestBrowserNotifyPermission()
      setBrowserNotify(granted)
    } else {
      setBrowserNotifyPref(false)
      setBrowserNotify(false)
    }
  }

  const save = async () => {
    setSaveError(null)
    try {
      const url = userId ? `/api/settings/users/${userId}` : '/api/settings'
      await axios.put(url, s)
      triggerMetaRefetch()
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || t('settings.save_error_default'))
    }
  }

  if (!s) return <div className="p-8 text-slate-500 text-xs font-semibold">{t('settings.loading')}</div>

  const update = (k: keyof Settings, v: any) => setS(prev => prev ? { ...prev, [k]: v } : prev)

  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]

  const TABS = [
    { key: 'general',  label: t('settings.general') || 'Preferences',      icon: <SettingsIcon size={14} /> },
    { key: 'agents',   label: 'AI Configuration',                          icon: <Brain size={14} /> },
    { key: 'tools',    label: t('settings.section_tools') || 'Agent Tools', icon: <Wrench size={14} /> },
    { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety', icon: <ShieldAlert size={14} /> },
    { key: 'webhooks', label: t('settings.section_notifications') || 'Alerts', icon: <Bell size={14} /> },
    { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler', icon: <Clock size={14} /> },
    ...(userId ? [] : [{ key: 'presets',  label: t('settings.section_presets') || 'Templates',  icon: <BookmarkPlus size={14} /> }]),
  ].filter(tab => isAdmin || tab.key === 'tools' || tab.key === 'agents' || allowedSettings.includes(tab.key))

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-white/[0.04] pb-4 gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('settings.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">Configure your personal trading agent preferences and models</p>
        </div>
        <div className="flex items-center gap-3">
          {saveError && <span className="text-rose-400 text-xs font-semibold">{saveError}</span>}
          <button onClick={save} className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-xs font-semibold shadow-md shadow-violet-500/20 transition-all shrink-0 cursor-pointer">
            <Save size={14} /> {saved ? t('settings.save_button_saved') : t('settings.save_button')}
          </button>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-6 items-start">
        {/* Settings Navigation Menu */}
        <div className="w-full md:w-52 flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0 shrink-0 border-b md:border-b-0 md:border-r border-white/[0.04] pr-0 md:pr-4">
          {TABS.map(tb => {
            const isActive = activeTab === tb.key
            return (
              <button
                key={tb.key}
                onClick={() => setActiveTab(tb.key as any)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-bold transition-all whitespace-nowrap text-left w-full border border-transparent cursor-pointer ${
                  isActive
                    ? 'bg-violet-500/10 text-violet-300 border-violet-500/20 active-nav-glow'
                    : 'text-slate-400 hover:text-white hover:bg-white/[0.02]'
                }`}
              >
                {tb.icon}
                <span>{tb.label}</span>
              </button>
            )
          })}
        </div>

        {/* Setting details panel */}
        <div className="flex-1 space-y-4 min-w-0 w-full animate-in fade-in duration-150">

          {/* Preferences */}
          {activeTab === 'general' && (
            <div className="space-y-4">
              <Section title={t('settings.general') || 'Preferences'}>
                <Row label={t('settings.row_output_language')}>
                  <select className={Input} value={s.output_language} onChange={e => update('output_language', e.target.value)}>
                    {languages.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </Row>
                <Row label={t('settings.row_investor_persona')}>
                  <select className={Input} value={s.investor_persona} onChange={e => update('investor_persona', e.target.value)}>
                    <option value="conservative">{t('settings.persona_conservative')}</option>
                    <option value="risk_loving">{t('settings.persona_risk_loving')}</option>
                    <option value="esg_focused">{t('settings.persona_esg_focused')}</option>
                  </select>
                </Row>
                <Row label={t('settings.row_benchmark_symbol')}>
                  <input className={Input} value={s.benchmark_ticker || ''} onChange={e => update('benchmark_ticker', e.target.value || null)} placeholder={t('settings.benchmark_placeholder')} />
                </Row>
              </Section>

              <Section title={t('settings.llm_settings') || 'Core Engine Configuration'}>
                <p className="text-[10px] text-slate-500 -mt-1 leading-relaxed mb-2">
                  Global LLM settings and performance parameters. Per-agent models are configured in the AI Configuration tab.
                </p>

                <Row label="Reasoning Effort">
                  <select className={Input} value={s.openai_reasoning_effort || ''} onChange={e => update('openai_reasoning_effort', e.target.value || null)}>
                    <option value="">{t('settings.effort_default')}</option>
                    <option value="low">{t('settings.effort_low_fast_cheap')}</option>
                    <option value="medium">{t('settings.effort_medium_balanced')}</option>
                    <option value="high">{t('settings.effort_high_deep')}</option>
                  </select>
                </Row>
                
                <Row label="Thinking Effort">
                  <select className={Input} value={s.anthropic_effort || ''} onChange={e => update('anthropic_effort', e.target.value || null)}>
                    <option value="">{t('settings.effort_default')}</option>
                    <option value="low">{t('settings.effort_low_fast')}</option>
                    <option value="medium">{t('settings.effort_medium_balanced')}</option>
                    <option value="high">{t('settings.effort_high_extended')}</option>
                  </select>
                </Row>
                
                <Row label="Thinking Level">
                  <select className={Input} value={s.google_thinking_level || ''} onChange={e => update('google_thinking_level', e.target.value || null)}>
                    <option value="">{t('settings.effort_default')}</option>
                    <option value="minimal">{t('settings.effort_minimal_fastest')}</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">{t('settings.effort_high_deepest')}</option>
                  </select>
                </Row>

                <Row label={t('settings.row_max_recursion')}>
                  <input
                    type="number"
                    min="1"
                    max="5000"
                    className={Input}
                    value={s.max_recur_limit}
                    onChange={e => update('max_recur_limit', parseInt(e.target.value) || 1000)}
                  />
                </Row>
              </Section>
            </div>
          )}

          {/* Risk Management */}
          {activeTab === 'risk' && (
            <Section title={t('settings.section_risk') || 'Risk Management'}>
              <Row label={t('settings.row_risk_per_trade')}>
                <input type="number" step="0.1" min="0.1" max="50" className={Input} value={s.max_risk_per_trade_pct} onChange={e => update('max_risk_per_trade_pct', parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_max_position_size')}>
                <input type="number" step="1" min="1" max="100" className={Input} value={s.max_position_size_pct} onChange={e => update('max_position_size_pct', parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_debate_rounds')}>
                <input type="number" min="1" max="10" className={Input} value={s.max_debate_rounds} onChange={e => update('max_debate_rounds', parseInt(e.target.value))} />
              </Row>
              <Row label={t('settings.row_risk_rounds')}>
                <input type="number" min="1" max="10" className={Input} value={s.max_risk_rounds} onChange={e => update('max_risk_rounds', parseInt(e.target.value))} />
              </Row>
              <Row label={t('settings.row_price_tolerance')}>
                <input type="number" step="0.1" min="0" max="10" className={Input} value={s.price_tolerance_pct} onChange={e => update('price_tolerance_pct', parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_parallel_analysts')}>
                <input type="number" min="1" max="16" className={Input} value={s.analyst_concurrency_limit} onChange={e => update('analyst_concurrency_limit', parseInt(e.target.value))} />
              </Row>

              <div className="border-t border-white/[0.04] pt-4 mt-2 space-y-3">
                <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-1">Agent Run Resilience</h4>
                <Row label={t('settings.row_node_retry_attempts') || 'Node Retry Attempts'}>
                  <input type="number" min="1" max="10" className={Input} value={s.node_retry_attempts ?? 2} onChange={e => update('node_retry_attempts', parseInt(e.target.value))} />
                </Row>
                <Row label={t('settings.row_node_retry_base_delay') || 'Retry Base Delay (s)'}>
                  <input type="number" step="0.1" min="0.1" max="10" className={Input} value={s.node_retry_base_delay ?? 1.0} onChange={e => update('node_retry_base_delay', parseFloat(e.target.value))} />
                </Row>
              </div>

              <div className="border-t border-white/[0.04] pt-4 mt-2 space-y-3">
                <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-1">Institutional Features</h4>

                <label className="flex items-center justify-between p-2 rounded-xl hover:bg-white/[0.02] cursor-pointer transition-colors group">
                  <span className="text-xs font-semibold text-slate-300 group-hover:text-white transition-colors">{t('settings.row_strict_stop_loss')}</span>
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded cursor-pointer" checked={s.strict_stop_loss_mode} onChange={e => update('strict_stop_loss_mode', e.target.checked)} />
                </label>
                </div>
            </Section>
          )}

          {/* Webhooks & Alerts */}
          {activeTab === 'webhooks' && (
            <Section title={t('settings.section_notifications') || 'Alerts & Webhooks'}>
              <Row label={t('settings.row_webhook_url')}>
                <input
                  className={Input}
                  placeholder="https://hooks.slack.com/..."
                  value={s.webhook_url || ''}
                  onChange={e => update('webhook_url', e.target.value || null)}
                />
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
                      {webhookTesting ? '...' : t('settings.webhook_test_button')}
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
                  {([
                    ['analysis_complete', t('settings.event_analysis_complete')],
                    ['trade_executed', t('settings.event_trade_executed')],
                    ['alert_triggered', t('settings.event_alert_triggered')],
                  ] as [string, string][]).map(([key, label]) => (
                    <label key={key} className="flex items-center gap-2 text-xs font-medium text-slate-400 cursor-pointer hover:text-slate-300 select-none">
                      <input
                        type="checkbox"
                        className="accent-violet-600 rounded w-4 h-4 cursor-pointer"
                        checked={s.webhook_events.includes(key)}
                        onChange={e => {
                          const events = s.webhook_events ? s.webhook_events.split(',').filter(Boolean) : []
                          const next = e.target.checked ? [...events, key] : events.filter(x => x !== key)
                          update('webhook_events', next.join(','))
                        }}
                      />
                      {label}
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
            </Section>
          )}

          {/* Presets / Templates */}
          {activeTab === 'presets' && (
            <Section title={t('settings.section_presets') || 'Presets Templates'}>
              <div className="flex gap-2">
                <input
                  className={Input}
                  placeholder={t('settings.preset_name_placeholder')}
                  value={presetName}
                  onChange={e => setPresetName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && savePreset()}
                />
                <button
                  onClick={savePreset}
                  disabled={presetSaving || !presetName.trim()}
                  className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-semibold px-4 py-2 rounded-xl transition whitespace-nowrap cursor-pointer shadow shadow-violet-500/10"
                >
                  <BookmarkPlus size={14} /> {t('settings.preset_save_button')}
                </button>
              </div>
              {presets.length === 0 ? (
                <p className="text-slate-600 text-xs text-center py-4">{t('settings.preset_no_presets')}</p>
              ) : (
                <div className="space-y-2 pt-1">
                  {presets.map(p => (
                    <div key={p.id} className="flex items-center justify-between bg-slate-900/40 border border-white/[0.04] rounded-xl px-4 py-2.5">
                      <span className="text-xs text-slate-300 font-semibold">{p.name}</span>
                      <div className="flex items-center gap-3">
                        <button onClick={() => applyPreset(p.id)} className="text-violet-400 hover:text-violet-300 p-1 transition-colors cursor-pointer" title={t('settings.preset_apply_title')}>
                          <Play size={14} fill="currentColor" />
                        </button>
                        <button onClick={() => deletePreset(p.id)} className="text-slate-500 hover:text-rose-400 p-1 transition-colors cursor-pointer">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          )}

          {/* Cron Scheduler */}
          {activeTab === 'cron' && (
            <Section title={t('settings.section_cron') || 'Cron Scheduler'}>
              <div className="flex items-center justify-between bg-white/[0.02] border border-white/[0.04] p-3 rounded-xl mb-2">
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Engine Status</span>
                  <div className="flex items-center gap-2 mt-1">
                    <div className={`w-2 h-2 rounded-full ${cronStatus?.running ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-rose-500'}`} />
                    <span className="text-xs font-bold text-slate-200">
                      {cronStatus?.running ? 'Scheduler Core Online' : 'Scheduler Core Offline'}
                    </span>
                  </div>
                </div>
                {cronStatus?.job_configured && (
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Next Run (UTC)</span>
                    <div className="text-xs font-mono text-violet-300 mt-1">
                      {cronStatus.next_run_time ? new Date(cronStatus.next_run_time).toLocaleString() : '—'}
                    </div>
                  </div>
                )}
              </div>

              <Row label="Active">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    className="accent-violet-600 w-5 h-5 rounded cursor-pointer"
                    checked={s.cron_enabled}
                    onChange={e => update('cron_enabled', e.target.checked)}
                  />
                  <span className={`text-[10px] font-bold uppercase tracking-widest ${s.cron_enabled ? 'text-emerald-400' : 'text-slate-500'}`}>
                    {s.cron_enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
              </Row>
              <Row label="Schedule (Cron)">
                <input
                  className={Input}
                  value={s.cron_schedule}
                  onChange={e => update('cron_schedule', e.target.value)}
                  placeholder="e.g. 0 9 * * 1-5"
                />
                <p className="text-[10px] text-slate-500 mt-1.5 font-medium leading-relaxed">
                  Standard 5-field cron schedule format (UTC time). <br/>
                  Example: <code className="text-violet-400">0 9 * * 1-5</code> runs every weekday at 09:00 UTC.
                </p>
              </Row>
            </Section>
          )}

          {activeTab === 'tools' && (
            <ToolSettingsPanel userId={userId} />
          )}

          {activeTab === 'agents' && (
            <AgentSettingsPanel userId={userId} />
          )}

        </div>
      </div>
    </div>
  )
}
