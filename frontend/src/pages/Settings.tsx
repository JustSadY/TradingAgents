import { useCallback, useEffect, useRef, useState } from 'react'
import {
  useSettingsGetSettings,
  useSettingsUpdateSettings,
  useSettingsGetUserSettingsById,
  useSettingsUpdateUserSettingsById,
  useSettingsGetMemoryStatus,
  useSettingsGetWebhookDeliveries,
  useSettingsTestWebhook,
} from '../api/generated/settings/settings'
import {
  usePresetsListPresetsRun,
  usePresetsCreatePresetRun,
  usePresetsApplyPreset,
  usePresetsDeletePreset,
} from '../api/generated/presets/presets'
import {
  useUsersGetMySettingPermissions,
  useUsersGetUserSettingPermissions,
} from '../api/generated/users/users'
import { useCronCronStatus } from '../api/generated/cron/cron'
import {
  usePersonasListAllPersonas,
  usePersonasCreatePersona,
  usePersonasUpdatePersona,
  usePersonasDeletePersona,
} from '../api/generated/personas/personas'
import {
  Bell, BookmarkPlus, Brain, Clock, Database, Pencil, Plus, Save, Settings as SettingsIcon, ShieldAlert, Trash2, UserCircle, Wrench, XCircle
} from 'lucide-react'

import { useMeta, triggerMetaRefetch } from '../hooks/useMeta'
import { useLlmCatalog, modelsFor, providerOptionsFrom, type LlmModelOption } from '../hooks/useLlmCatalog'
import { useAuth } from '../contexts/AuthContext'
import { requestBrowserNotifyPermission, setBrowserNotifyPref, isBrowserNotifyEnabled } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Input, Row, Section } from '../components/settings/tabs/primitives'
import { RiskTab } from '../components/settings/tabs/RiskTab'
import { AlertsTab } from '../components/settings/tabs/AlertsTab'
import { CronTab } from '../components/settings/tabs/CronTab'
import { WebhooksTab } from '../components/settings/tabs/WebhooksTab'
import { PresetsTab } from '../components/settings/tabs/PresetsTab'
import { MemoryTab } from '../components/settings/tabs/MemoryTab'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import type { ToolSettingsPanelHandle } from '../components/settings/ToolSettingsPanel'
import AgentSettingsPanel from '../components/settings/AgentSettingsPanel'
import type { AgentSettingsPanelHandle } from '../components/settings/AgentSettingsPanel'
import type { PersonaRead, SettingsRead } from '../api/generated/model'

type Settings = SettingsRead
type FallbackLLMEntry = { provider: string; model: string }

const MAX_FALLBACK_CHAIN_LENGTH = 3

function lacksVerifiedOutputLanguage(model: LlmModelOption | undefined, language: string): boolean {
  const supported = model?.supported_output_languages
  return Boolean(
    supported?.length
      && !supported.some(candidate => candidate.localeCompare(language, undefined, { sensitivity: 'accent' }) === 0),
  )
}

export default function Settings({ userId }: { userId?: number } = {}) {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [s, setS] = useState<Settings | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [browserNotify, setBrowserNotify] = useState(isBrowserNotifyEnabled())
  const [webhookTesting, setWebhookTesting] = useState(false)
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(null)
  const savedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => { return () => { if (savedTimeoutRef.current) clearTimeout(savedTimeoutRef.current) } }, [])
  const deliveriesQuery = useSettingsGetWebhookDeliveries(
    userId ? { user_id: userId } : undefined,
    { query: { enabled: false } },
  )
  const deliveries = deliveriesQuery.data ?? []
  const loadingDeliveries = deliveriesQuery.isFetching
  // Deliveries are only fetched when the webhooks tab asks for them.
  const loadDeliveries = useCallback(() => { void deliveriesQuery.refetch() }, [deliveriesQuery])
  const [activeTab, setActiveTab] = useState<'general' | 'llm' | 'agents' | 'risk' | 'alerts' | 'webhooks' | 'presets' | 'advanced' | 'cron' | 'tools' | 'memory' | 'personas'>('general')
  const memoryQuery = useSettingsGetMemoryStatus(userId ? { user_id: userId } : undefined)
  const memoryStatus = memoryQuery.data ?? null
  const [allowedSettings, setAllowedSettings] = useState<string[]>([])
  const meta = useMeta()
  
  const updateOwnSettings = useSettingsUpdateSettings()
  const updateOtherSettings = useSettingsUpdateUserSettingsById()
  const createPreset = usePresetsCreatePresetRun()
  const applyPresetMutation = usePresetsApplyPreset()
  const deletePresetMutation = usePresetsDeletePreset()
  const testWebhookMutation = useSettingsTestWebhook()

  const toolPanelRef = useRef<ToolSettingsPanelHandle>(null)
  const agentPanelRef = useRef<AgentSettingsPanelHandle>(null)

  // Admin editing another user and a user editing themselves hit different
  // endpoints. Both hooks are declared and only the matching one is enabled.
  const ownSettingsQuery = useSettingsGetSettings({ query: { enabled: !userId } })
  const otherSettingsQuery = useSettingsGetUserSettingsById(userId ?? 0, { query: { enabled: Boolean(userId) } })
  const settingsQuery = userId ? otherSettingsQuery : ownSettingsQuery

  const presetsQuery = usePresetsListPresetsRun(userId ? { user_id: userId } : undefined)
  const ownPermsQuery = useUsersGetMySettingPermissions({ query: { enabled: !userId } })
  const otherPermsQuery = useUsersGetUserSettingPermissions(userId ?? 0, { query: { enabled: Boolean(userId) } })
  const permsQuery = userId ? otherPermsQuery : ownPermsQuery
  const presets = presetsQuery.data ?? []
  const cronQuery = useCronCronStatus()

  const cronStatus = cronQuery.data ?? null
  const llmCatalog = useLlmCatalog()

  useEffect(() => {
    if (!settingsQuery.data || !permsQuery.isFetched) return
    const settings = settingsQuery.data
    const permPayload = permsQuery.data as { allowed_settings?: string[]; permissions?: string[] } | undefined
    const allowedSet = permPayload?.allowed_settings || permPayload?.permissions || []
    {
      setS(settings)
      setAllowedSettings(userId ? ['general', 'agents', 'tools', 'risk', 'alerts', 'webhooks', 'cron', 'memory', 'presets', 'personas'] : allowedSet)

      const defaultTabs = ['general', 'agents', 'tools', 'risk', 'alerts', 'webhooks', 'cron']
      const activeDefault = defaultTabs.find(tab => userId || allowedSet.includes(tab))
      if (activeDefault) {
        setActiveTab(activeDefault as any)
      } else if (isAdmin) {
        setActiveTab('advanced')
      }
    }
  }, [isAdmin, userId, settingsQuery.data, permsQuery.data, permsQuery.isFetched])

  const loadPresets = useCallback(() => { void presetsQuery.refetch() }, [presetsQuery])

  const savePreset = async () => {
    if (!presetName.trim() || !s) return
    setPresetSaving(true)
    try {
      // A preset carries settings, not bookkeeping: when it was last saved and
      // which preset was active are properties of the account, not of the
      // preset being created from it.
      const { updated_at, active_preset_name, ...presetSettings } = s
      await createPreset.mutateAsync({
        params: userId ? { user_id: userId } : undefined,
        data: { name: presetName.trim(), settings_json: JSON.stringify(presetSettings) },
      })
      setPresetName('')
      await loadPresets()
    } finally { setPresetSaving(false) }
  }

  const applyPreset = async (id: number) => {
    await applyPresetMutation.mutateAsync({ presetId: id, params: userId ? { user_id: userId } : undefined })
    // Re-read the settings the preset just wrote rather than guessing them.
    const refreshed = await settingsQuery.refetch()
    if (refreshed.data) setS(refreshed.data)
  }

  const deletePreset = async (id: number) => {
    await deletePresetMutation.mutateAsync({ presetId: id, params: userId ? { user_id: userId } : undefined })
    void presetsQuery.refetch()
  }

  const testWebhook = async () => {
    if (!s?.webhook_url) return
    setWebhookTesting(true); setWebhookTestResult(null)
    try {
      await testWebhookMutation.mutateAsync({ data: { url: s.webhook_url } })
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
    setSaving(true)
    try {
      const settingsUpdate = { ...s }
      delete settingsUpdate.updated_at
      // Preset selection belongs to the preset apply endpoint. Sending the
      // read-only marker back with every full-form save would keep a stale
      // preset selected after the user changes an individual setting.
      delete settingsUpdate.active_preset_name
      if (userId) {
        await updateOtherSettings.mutateAsync({ userId, data: settingsUpdate })
      } else {
        await updateOwnSettings.mutateAsync({ data: settingsUpdate })
      }
      triggerMetaRefetch()
      void memoryQuery.refetch()
      if (agentPanelRef.current) {
        await agentPanelRef.current.save()
      }
      if (toolPanelRef.current) {
        await toolPanelRef.current.save()
      }
      setSaved(true)
      savedTimeoutRef.current = setTimeout(() => setSaved(false), 2000)
    } catch (err: any) {
      setSaveError(err.message || err.response?.data?.detail || t('settings.save_error_default'))
    } finally {
      setSaving(false)
    }
  }

  if (!s) return <div className="p-8 text-slate-500 text-xs font-semibold">{t('settings.loading')}</div>

  const update = (k: keyof Settings, v: any) => setS(prev => prev ? { ...prev, [k]: v } : prev)
  const primaryModels = modelsFor(llmCatalog, s.llm_provider)
  const primaryUsesCustomModel = !primaryModels.some(model => model.value === s.llm_model)
  const primaryModel = primaryModels.find(model => model.value === s.llm_model)
  const fallbackChain = s.fallback_llm_chain ?? []
  const webhookEvents = s.webhook_events ?? []
  // Providers and models come from the same catalog. Listing providers from
  // /api/meta's provider_labels while the models beside them came from the
  // catalog meant a provider present in one and absent from the other left the
  // model dropdown empty with no way to tell why.
  const providerOptions = providerOptionsFrom(llmCatalog)

  const updateFallbackEntry = (index: number, patch: Partial<FallbackLLMEntry>) => {
    update('fallback_llm_chain', fallbackChain.map((entry, position) => (
      position === index ? { ...entry, ...patch } : entry
    )))
  }

  const addFallbackEntry = () => {
    const provider = providerOptions[0]?.[0] ?? s.llm_provider
    const model = modelsFor(llmCatalog, provider)[0]?.value ?? s.llm_model
    update('fallback_llm_chain', [...fallbackChain, { provider, model }])
  }

  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]

  const TABS = [
    { key: 'general',  label: t('settings.general'),      icon: <SettingsIcon size={14} /> },
    { key: 'agents',   label: t('settings.tab_agents'),                    icon: <Brain size={14} /> },
    { key: 'tools',    label: t('settings.section_tools'), icon: <Wrench size={14} /> },
    { key: 'risk',     label: t('settings.section_risk'), icon: <ShieldAlert size={14} /> },
    { key: 'alerts',   label: t('settings.section_alert_guardrails'),       icon: <Bell size={14} /> },
    { key: 'webhooks', label: t('settings.section_notifications'), icon: <Bell size={14} /> },
    { key: 'cron',     label: t('settings.cron_settings'), icon: <Clock size={14} /> },
    { key: 'memory',   label: t('settings.tab_memory'),                    icon: <Database size={14} /> },
    { key: 'presets',  label: t('settings.section_presets'),  icon: <BookmarkPlus size={14} /> },
    { key: 'personas', label: t('settings.tab_personas'),                  icon: <UserCircle size={14} /> },
  ].filter(tab => isAdmin || allowedSettings.includes(tab.key))

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-white/[0.04] pb-4 gap-3">
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('settings.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">{t('settings.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          {saveError && <span className="text-rose-400 text-xs font-semibold">{saveError}</span>}
          <button onClick={save} disabled={saving} className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-xs font-semibold shadow-md shadow-violet-500/20 transition-all shrink-0 cursor-pointer disabled:opacity-50">
            <Save size={14} /> {saving ? t('settings.saving') : saved ? t('settings.save_button_saved') : t('settings.save_button')}
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
                onClick={() => { setActiveTab(tb.key as any); if (tb.key === 'webhooks') loadDeliveries() }}
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
            <ErrorBoundary name="SettingsGeneral">
              <div className="space-y-4">
                <Section title={t('settings.general')}>
                  <Row label={t('settings.row_output_language')}>
                    <select className={Input} value={s.output_language} onChange={e => update('output_language', e.target.value)}>
                      {languages.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </Row>
                  <Row label={t('settings.row_investor_persona')}>
                    <select className={Input} value={s.investor_persona} onChange={e => update('investor_persona', e.target.value)}>
                      {(meta?.investor_personas ?? []).map(p => (
                        <option key={p.value} value={p.value}>
                          {t(`settings.persona_${p.value}`) || p.label}
                        </option>
                      ))}
                    </select>
                  </Row>
                  <Row label={t('settings.row_benchmark_symbol')}>
                    <input className={Input} value={s.benchmark_ticker || ''} onChange={e => update('benchmark_ticker', e.target.value || null)} placeholder={t('settings.benchmark_placeholder')} />
                  </Row>
                </Section>

                <Section title={t('settings.section_news_sentiment')}>
                  <Row label={t('settings.row_news_article_limit')}>
                    <input type="number" min={1} max={100} className={Input} value={s.news_article_limit ?? 20} onChange={e => update('news_article_limit', parseInt(e.target.value) || 20)} />
                  </Row>
                  <Row label={t('settings.row_global_news_limit')}>
                    <input type="number" min={1} max={100} className={Input} value={s.global_news_article_limit ?? 10} onChange={e => update('global_news_article_limit', parseInt(e.target.value) || 10)} />
                  </Row>
                  <Row label={t('settings.row_global_news_lookback')}>
                    <input type="number" min={1} max={90} className={Input} value={s.global_news_lookback_days ?? 7} onChange={e => update('global_news_lookback_days', parseInt(e.target.value) || 7)} />
                  </Row>
                </Section>

                {allowedSettings.includes('llm') && (
                  <Section title={t('settings.llm_settings')}>
                    <p className="text-[10px] text-slate-500 -mt-1 leading-relaxed mb-2">
                      {t('settings.llm_settings_description')}
                    </p>

                    <Row label={t('settings.row_llm_provider')}>
                      <select
                        className={Input}
                        value={s.llm_provider}
                        onChange={e => {
                          update('llm_provider', e.target.value)
                          update('llm_model', '')
                        }}
                      >
                        {providerOptions.map(([key, label]) => (
                          <option key={key} value={key}>{label}</option>
                        ))}
                      </select>
                    </Row>
                    <Row label={t('settings.row_llm_model')}>
                      <div className="space-y-2">
                        <select
                          className={Input}
                          value={primaryUsesCustomModel ? '__custom__' : s.llm_model}
                          onChange={e => update('llm_model', e.target.value === '__custom__' ? '' : e.target.value)}
                        >
                          {primaryModels.map(model => <option key={model.value} value={model.value}>{model.label}</option>)}
                          <option value="__custom__">{t('settings.custom_model_option')}</option>
                        </select>
                        {primaryUsesCustomModel && (
                          <input
                            className={Input}
                            value={s.llm_model}
                            onChange={e => update('llm_model', e.target.value)}
                            placeholder={t('settings.custom_model_placeholder')}
                          />
                        )}
                        {lacksVerifiedOutputLanguage(primaryModel, s.output_language) && (
                          <p className="rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-2.5 py-2 text-[10px] leading-relaxed text-amber-200">
                            {t('settings.model_language_warning')} {primaryModel?.supported_output_languages?.join(', ')}.
                          </p>
                        )}
                      </div>
                    </Row>

                    <Row label={t('settings.row_fallback_chain')}>
                      <div className="space-y-2">
                        {fallbackChain.length === 0 && (
                          <p className="text-[10px] text-slate-500 leading-relaxed">{t('settings.fallback_disabled')}</p>
                        )}
                        {fallbackChain.map((entry, index) => {
                          const models = modelsFor(llmCatalog, entry.provider)
                          const usesCustomModel = !models.some(model => model.value === entry.model)
                          const selectedFallbackModel = models.find(model => model.value === entry.model)
                          return (
                            <div key={`${entry.provider}-${entry.model}-${index}`} className="space-y-2 rounded-xl border border-white/[0.05] bg-white/[0.015] p-2.5">
                              <div className="flex items-center gap-2">
                                <select
                                  aria-label={`${t('settings.fallback_step_provider')} ${index + 1}`}
                                  className={Input}
                                  value={entry.provider}
                                  onChange={e => {
                                    const provider = e.target.value
                                    const model = modelsFor(llmCatalog, provider)[0]?.value ?? entry.model
                                    updateFallbackEntry(index, { provider, model })
                                  }}
                                >
                                  {providerOptions.map(([key, label]) => (
                                    <option key={key} value={key}>{label}</option>
                                  ))}
                                </select>
                                <button
                                  type="button"
                                  onClick={() => update('fallback_llm_chain', fallbackChain.filter((_, position) => position !== index))}
                                  className="shrink-0 rounded-lg p-2 text-slate-500 hover:bg-rose-500/10 hover:text-rose-400 transition cursor-pointer"
                                  title={t('settings.fallback_remove')}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                              <select
                                aria-label={`${t('settings.fallback_step_model')} ${index + 1}`}
                                className={Input}
                                value={usesCustomModel ? '__custom__' : entry.model}
                                onChange={e => {
                                  const model = e.target.value === '__custom__' ? '' : e.target.value
                                  updateFallbackEntry(index, { model })
                                }}
                              >
                                {models.map(model => <option key={model.value} value={model.value}>{model.label}</option>)}
                                <option value="__custom__">{t('settings.custom_model_option')}</option>
                              </select>
                              {usesCustomModel && (
                                <input
                                  className={Input}
                                  value={entry.model}
                                  onChange={e => updateFallbackEntry(index, { model: e.target.value })}
                                  placeholder={t('settings.custom_model_placeholder')}
                                />
                              )}
                              {lacksVerifiedOutputLanguage(selectedFallbackModel, s.output_language) && (
                                <p className="rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-2.5 py-2 text-[10px] leading-relaxed text-amber-200">
                                  {t('settings.model_language_warning')} {selectedFallbackModel?.supported_output_languages?.join(', ')}.
                                </p>
                              )}
                            </div>
                          )
                        })}
                        <button
                          type="button"
                          onClick={addFallbackEntry}
                          disabled={fallbackChain.length >= MAX_FALLBACK_CHAIN_LENGTH || providerOptions.length === 0}
                          className="text-[10px] font-bold text-violet-300 hover:text-violet-200 disabled:cursor-not-allowed disabled:opacity-40 transition cursor-pointer"
                        >
                          + {t('settings.fallback_add')}
                        </button>
                        <p className="text-[10px] text-slate-500 leading-relaxed">
                          {t('settings.fallback_hint')}
                        </p>
                      </div>
                    </Row>

                    <Row label={t('settings.row_reasoning_effort')}>
                      <select className={Input} value={s.openai_reasoning_effort || ''} onChange={e => update('openai_reasoning_effort', e.target.value || null)}>
                        <option value="">{t('settings.effort_default')}</option>
                        {(meta?.effort_options?.openai ?? [
                          { value: 'low', label: t('settings.effort_low_fast_cheap') },
                          { value: 'medium', label: t('settings.effort_medium_balanced') },
                          { value: 'high', label: t('settings.effort_high_deep') },
                        ]).map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Row>
                    
                    <Row label={t('settings.row_thinking_effort')}>
                      <select className={Input} value={s.anthropic_effort || ''} onChange={e => update('anthropic_effort', e.target.value || null)}>
                        <option value="">{t('settings.effort_default')}</option>
                        {(meta?.effort_options?.anthropic ?? [
                          { value: 'low', label: t('settings.effort_low_fast') },
                          { value: 'medium', label: t('settings.effort_medium_balanced') },
                          { value: 'high', label: t('settings.effort_high_extended') },
                        ]).map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Row>
                    
                    <Row label={t('settings.row_thinking_level')}>
                      <select className={Input} value={s.google_thinking_level || ''} onChange={e => update('google_thinking_level', e.target.value || null)}>
                        <option value="">{t('settings.effort_default')}</option>
                        {(meta?.effort_options?.google ?? [
                          { value: 'minimal', label: t('settings.effort_minimal_fastest') },
                          { value: 'low', label: t('settings.effort_low_fast') },
                          { value: 'medium', label: t('settings.effort_medium_balanced') },
                          { value: 'high', label: t('settings.effort_high_deepest') },
                        ]).map(o => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                    </Row>

                    <Row label={t('settings.row_max_recursion')}>
                      <input
                        type="number"
                        min="1"
                        max="5000"
                        className={Input}
                        value={s.max_recur_limit}
                        onChange={e => update('max_recur_limit', Number.parseInt(e.target.value) || 1000)}
                      />
                    </Row>
                  </Section>
                )}
              </div>
            </ErrorBoundary>
          )}

          {/* Risk Management */}
          {activeTab === 'risk' && <RiskTab s={s} t={t} update={update} />}

          {activeTab === 'alerts' && <AlertsTab s={s} t={t} update={update} />}

          {activeTab === 'webhooks' && (
            <WebhooksTab
              s={s} t={t} update={update} meta={meta} userId={userId}
              webhookEvents={webhookEvents} deliveries={deliveries}
              loadingDeliveries={loadingDeliveries} loadDeliveries={loadDeliveries}
              testWebhook={testWebhook} toggleBrowserNotify={toggleBrowserNotify}
              browserNotify={browserNotify} webhookTesting={webhookTesting}
              webhookTestResult={webhookTestResult}
            />
          )}

          {activeTab === 'presets' && (
            <PresetsTab
              t={t} presets={presets} presetName={presetName} setPresetName={setPresetName}
              presetSaving={presetSaving} savePreset={savePreset}
              applyPreset={applyPreset} deletePreset={deletePreset}
            />
          )}

          {activeTab === 'cron' && <CronTab s={s} t={t} update={update} cronStatus={cronStatus} />}

          {activeTab === 'memory' && (
            <MemoryTab s={s} t={t} update={update} meta={meta} memoryStatus={memoryStatus} />
          )}

          {activeTab === 'tools' && (
            <ErrorBoundary name="SettingsTools">
              <ToolSettingsPanel ref={toolPanelRef} userId={userId} hideSaveButton={true} />
            </ErrorBoundary>
          )}

          {activeTab === 'agents' && (
            <ErrorBoundary name="SettingsAgents">
              <AgentSettingsPanel ref={agentPanelRef} userId={userId} hideSaveButton={true} />
            </ErrorBoundary>
          )}

          {activeTab === 'personas' && (
            <ErrorBoundary name="SettingsPersonas">
              <PersonaEditor userId={userId} />
            </ErrorBoundary>
          )}

        </div>
      </div>
    </div>
  )
}

function PersonaEditor({ userId }: { userId?: number } = {}) {
  const { t } = useTranslation()
  const [showForm, setShowForm] = useState(false)
  const [editKey, setEditKey] = useState<string | null>(null)
  const [form, setForm] = useState({ key: '', label: '', description: '', instructions: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const personasQuery = usePersonasListAllPersonas(userId ? { user_id: userId } : undefined)
  const personas = personasQuery.data ?? []
  const loading = personasQuery.isPending
  const load = useCallback(() => personasQuery.refetch(), [personasQuery])

  const createPersona = usePersonasCreatePersona()
  const updatePersona = usePersonasUpdatePersona()
  const deletePersona = usePersonasDeletePersona()

  const openCreate = () => { setForm({ key: '', label: '', description: '', instructions: '' }); setEditKey(null); setShowForm(true); setError(null) }
  const openEdit = (p: PersonaRead) => { setForm({ key: p.key, label: p.label, description: p.description, instructions: p.instructions }); setEditKey(p.key); setShowForm(true); setError(null) }

  const save = async () => {
    if (!form.label.trim()) { setError(t('settings.persona_label_required')); return }
    setSaving(true); setError(null)
    try {
      const params = userId ? { user_id: userId } : undefined
      if (editKey) {
        await updatePersona.mutateAsync({
          key: editKey,
          params,
          data: { label: form.label, description: form.description, instructions: form.instructions },
        })
      } else {
        if (!form.key.trim()) { setError(t('settings.persona_key_required')); setSaving(false); return }
        await createPersona.mutateAsync({ params, data: form })
      }
      setShowForm(false); await load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || t('settings.persona_save_failed'))
    } finally { setSaving(false) }
  }

  const del = async (key: string) => {
    try {
      await deletePersona.mutateAsync({ key, params: userId ? { user_id: userId } : undefined })
      await load()
    } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-bold text-white">{t('settings.personas_title')}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">{t('settings.personas_description')}</p>
        </div>
        {!showForm && (
          <button onClick={openCreate} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/20 text-violet-300 text-[10px] font-bold transition cursor-pointer">
            <Plus size={11} /> {t('settings.persona_new')}
          </button>
        )}
      </div>

      {showForm && (
        <div className="glass-panel rounded-2xl p-4 space-y-3 border border-violet-500/20">
          <p className="text-xs font-bold text-violet-300">{editKey ? t('settings.persona_edit') : t('settings.persona_new')}</p>
          {!editKey && (
            <div>
              <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{t('settings.persona_key_label')}</label>
              <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1 font-mono" placeholder={t('settings.persona_key_placeholder')} value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') }))} />
            </div>
          )}
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{t('settings.persona_display_label')}</label>
            <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1" placeholder={t('settings.persona_display_placeholder')} value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{t('settings.persona_description_label')}</label>
            <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1" placeholder={t('settings.persona_description_placeholder')} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">{t('settings.persona_instructions_label')}</label>
            <textarea rows={5} className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1 resize-y font-mono" placeholder={t('settings.persona_instructions_placeholder')} value={form.instructions} onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))} />
          </div>
          {error && <p className="text-rose-400 text-[10px] font-semibold">{error}</p>}
          <div className="flex gap-2">
            <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold transition cursor-pointer disabled:opacity-40">
              {saving ? t('settings.persona_saving') : t('settings.persona_save')}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white text-xs font-semibold transition cursor-pointer">
              {t('settings.persona_cancel')}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 opacity-40 text-[10px] text-slate-500">{t('settings.personas_loading')}</div>
      ) : (
        <div className="space-y-2">
          {personas.map(p => (
            <div key={p.key} className="flex items-start justify-between gap-3 p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.08] transition-all">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-bold text-white truncate">{p.label}</span>
                  {p.is_builtin && <span className="text-[8px] font-bold uppercase tracking-wider text-violet-400 bg-violet-500/10 px-1.5 py-0.5 rounded-full border border-violet-500/20">{t('settings.persona_builtin')}</span>}
                  <span className="text-[9px] font-mono text-slate-600">{p.key}</span>
                </div>
                <p className="text-[10px] text-slate-500 truncate">{p.description || '—'}</p>
              </div>
              {!p.is_builtin && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => openEdit(p)} className="p-1.5 rounded-lg text-slate-500 hover:text-violet-400 hover:bg-violet-500/10 transition cursor-pointer" title={t('settings.persona_edit_title')}>
                    <Pencil size={12} />
                  </button>
                  <button onClick={() => del(p.key)} className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer" title={t('settings.persona_delete_title')}>
                    <XCircle size={12} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
