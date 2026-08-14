import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  useSettingsGetSettings,
  useSettingsUpdateSettings,
  useSettingsGetUserSettingsById,
  useSettingsUpdateUserSettingsById,
  useSettingsGetLlmCatalog,
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
  useUsersSetMyApiKey,
  useUsersDeleteMyApiKey,
  useUsersSetUserApiKeyEndpoint,
  useUsersDeleteUserApiKeyEndpoint,
} from '../api/generated/users/users'
import { useCronCronStatus } from '../api/generated/cron/cron'
import {
  usePersonasListAllPersonas,
  usePersonasCreatePersona,
  usePersonasUpdatePersona,
  usePersonasDeletePersona,
} from '../api/generated/personas/personas'
import {
  Save, BookmarkPlus, Trash2, Play, Bell,
  Settings as SettingsIcon, Brain, ShieldAlert, Clock, Wrench, Database,
  CheckCircle2, XCircle, RefreshCw, UserCircle, Plus, Pencil
} from 'lucide-react'

import { useMeta, triggerMetaRefetch } from '../hooks/useMeta'
import { useAuth } from '../contexts/AuthContext'
import { requestBrowserNotifyPermission, setBrowserNotifyPref, isBrowserNotifyEnabled } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import { ErrorBoundary } from '../components/ErrorBoundary'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import type { ToolSettingsPanelHandle } from '../components/settings/ToolSettingsPanel'
import AgentSettingsPanel from '../components/settings/AgentSettingsPanel'
import type { AgentSettingsPanelHandle } from '../components/settings/AgentSettingsPanel'
import type { WebhookDeliveryRead, SettingsRead, PresetRead } from '../api/types'

type Settings = SettingsRead
type LlmModelOption = { value: string; label: string; supported_output_languages?: string[] }
type LlmCatalog = Record<string, { label: string; models: LlmModelOption[] }>
type FallbackLLMEntry = { provider: string; model: string }

const DEFAULT_WEBHOOK_EVENTS = ['analysis_complete', 'trade_executed', 'alert_triggered', 'signal_flip']
const MAX_FALLBACK_CHAIN_LENGTH = 3

function normalizeLlmCatalog(value: unknown): LlmCatalog {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {}
  const catalog: LlmCatalog = {}
  for (const [provider, entry] of Object.entries(value)) {
    if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) continue
    const rawModels = (entry as Record<string, unknown>).models
    if (!Array.isArray(rawModels)) continue
    const models = rawModels.flatMap(model => {
      if (typeof model !== 'object' || model === null || Array.isArray(model)) return []
      const option = model as Record<string, unknown>
      if (typeof option.value !== 'string' || typeof option.label !== 'string') return []
      const supported_output_languages = Array.isArray(option.supported_output_languages)
        ? option.supported_output_languages.filter((language): language is string => typeof language === 'string')
        : undefined
      return [{ value: option.value, label: option.label, supported_output_languages }]
    })
    catalog[provider] = {
      label: typeof (entry as Record<string, unknown>).label === 'string'
        ? (entry as Record<string, unknown>).label as string
        : provider,
      models,
    }
  }
  return catalog
}

function lacksVerifiedOutputLanguage(model: LlmModelOption | undefined, language: string): boolean {
  const supported = model?.supported_output_languages
  return Boolean(
    supported?.length
      && !supported.some(candidate => candidate.localeCompare(language, undefined, { sensitivity: 'accent' }) === 0),
  )
}

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

const CompactInputStyle = "w-24 text-right bg-slate-950/90 border border-white/10 hover:border-violet-500/40 focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20 rounded-lg px-2.5 py-1 text-xs font-mono font-semibold text-violet-200 outline-none transition-all shadow-inner"

function RiskRowItem({
  label,
  hint,
  unit,
  children,
  className,
}: {
  label: string
  hint?: string
  unit?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-900/60 hover:bg-slate-900/90 border border-white/[0.04] transition-all group ${className || ''}`}>
      <div className="flex flex-col min-w-0 pr-1">
        <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors">{label}</span>
        {hint && <span className="text-[10px] text-slate-400 mt-0.5 leading-tight">{hint}</span>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {children}
        {unit && (
          <span className="text-[11px] font-bold text-violet-400/90 bg-violet-500/10 border border-violet-500/20 rounded-md px-1.5 py-0.5 min-w-[24px] text-center select-none">
            {unit}
          </span>
        )}
      </div>
    </div>
  )
}

function ToggleItem({
  label,
  hint,
  checked,
  onChange,
  warning,
  className,
}: {
  label: string
  hint?: string
  checked: boolean
  onChange: (checked: boolean) => void
  warning?: string
  className?: string
}) {
  return (
    <div className={`flex flex-col gap-1.5 p-3 rounded-xl bg-slate-900/60 hover:bg-slate-900/90 border border-white/[0.04] transition-all group ${className || ''}`}>
      <label className="flex items-center justify-between gap-3 cursor-pointer">
        <span className="text-xs font-semibold text-slate-200 group-hover:text-white transition-colors min-w-0 pr-2">{label}</span>
        <div className="relative inline-flex items-center shrink-0">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={checked}
            onChange={e => onChange(e.target.checked)}
          />
          <div className="w-9 h-5 bg-slate-800 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-violet-500/30 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-gradient-to-r peer-checked:from-violet-600 peer-checked:to-indigo-600 shadow-inner" />
        </div>
      </label>
      {hint && <span className="text-[10px] text-slate-400 leading-tight">{hint}</span>}
      {warning && <span className="text-[10px] text-amber-300/80 leading-tight font-medium mt-0.5">{warning}</span>}
    </div>
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
  const deliveries = (deliveriesQuery.data ?? []) as unknown as WebhookDeliveryRead[]
  const loadingDeliveries = deliveriesQuery.isFetching
  // Deliveries are only fetched when the webhooks tab asks for them.
  const loadDeliveries = useCallback(() => { void deliveriesQuery.refetch() }, [deliveriesQuery])
  const [activeTab, setActiveTab] = useState<'general' | 'llm' | 'agents' | 'risk' | 'alerts' | 'webhooks' | 'presets' | 'advanced' | 'cron' | 'tools' | 'memory' | 'personas'>('general')
  const [pineconeKey, setPineconeKey] = useState('')
  const [pineconeSaving, setPineconeSaving] = useState(false)
  const memoryQuery = useSettingsGetMemoryStatus(userId ? { user_id: userId } : undefined)
  const memoryStatus = memoryQuery.data ?? null
  const loadMemoryStatus = useCallback(() => { void memoryQuery.refetch() }, [memoryQuery])
  const [allowedSettings, setAllowedSettings] = useState<string[]>([])
  const meta = useMeta()
  
  const updateOwnSettings = useSettingsUpdateSettings()
  const updateOtherSettings = useSettingsUpdateUserSettingsById()
  const createPreset = usePresetsCreatePresetRun()
  const applyPresetMutation = usePresetsApplyPreset()
  const deletePresetMutation = usePresetsDeletePreset()
  const testWebhookMutation = useSettingsTestWebhook()
  const setOwnKey = useUsersSetMyApiKey()
  const deleteOwnKey = useUsersDeleteMyApiKey()
  const setOtherUserKey = useUsersSetUserApiKeyEndpoint()
  const deleteOtherUserKey = useUsersDeleteUserApiKeyEndpoint()

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
  const presets = (presetsQuery.data ?? []) as unknown as PresetRead[]
  const cronQuery = useCronCronStatus()
  const catalogQuery = useSettingsGetLlmCatalog()

  const cronStatus = (cronQuery.data ?? null) as { running: boolean; job_configured: boolean; next_run_time: string | null } | null
  const llmCatalog = useMemo(
    () => (catalogQuery.data ? normalizeLlmCatalog(catalogQuery.data) : {}),
    [catalogQuery.data],
  )

  useEffect(() => {
    if (!settingsQuery.data || !permsQuery.isFetched) return
    const settings = settingsQuery.data
    const permPayload = permsQuery.data as { allowed_settings?: string[]; permissions?: string[] } | undefined
    const allowedSet = permPayload?.allowed_settings || permPayload?.permissions || []
    {
      setS(settings as never)
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
      const presetSettings = { ...s }
      delete presetSettings.updated_at
      delete presetSettings.active_preset_name
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
    if (refreshed.data) setS(refreshed.data as never)
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
  const primaryModels = llmCatalog[s.llm_provider]?.models ?? []
  const primaryUsesCustomModel = !primaryModels.some(model => model.value === s.llm_model)
  const primaryModel = primaryModels.find(model => model.value === s.llm_model)
  const fallbackChain = s.fallback_llm_chain ?? []
  const webhookEvents = s.webhook_events ?? []
  const metaProviders = Object.entries(meta?.provider_labels ?? {})
  const providerOptions = metaProviders.length > 0
    ? metaProviders
    : Object.entries(llmCatalog).map(([key, entry]) => [key, entry.label] as [string, string])

  const updateFallbackEntry = (index: number, patch: Partial<FallbackLLMEntry>) => {
    update('fallback_llm_chain', fallbackChain.map((entry, position) => (
      position === index ? { ...entry, ...patch } : entry
    )))
  }

  const addFallbackEntry = () => {
    const provider = providerOptions[0]?.[0] ?? s.llm_provider
    const model = llmCatalog[provider]?.models[0]?.value ?? s.llm_model
    update('fallback_llm_chain', [...fallbackChain, { provider, model }])
  }

  const savePineconeKey = async () => {
    if (!pineconeKey.trim()) return
    setPineconeSaving(true)
    try {
      const data = { provider: 'pinecone', api_key: pineconeKey.trim() }
      if (userId) await setOtherUserKey.mutateAsync({ userId, data })
      else await setOwnKey.mutateAsync({ data })
      setPineconeKey('')
      loadMemoryStatus()
    } finally { setPineconeSaving(false) }
  }
  const deletePineconeKey = async () => {
    try {
      if (userId) await deleteOtherUserKey.mutateAsync({ userId, provider: 'pinecone' })
      else await deleteOwnKey.mutateAsync({ provider: 'pinecone' })
    } catch (e) {
      console.error('Failed to delete Pinecone key', e)
    }
    loadMemoryStatus()
  }

  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]

  const TABS = [
    { key: 'general',  label: t('settings.general') || 'Preferences',      icon: <SettingsIcon size={14} /> },
    { key: 'agents',   label: t('settings.tab_agents'),                    icon: <Brain size={14} /> },
    { key: 'tools',    label: t('settings.section_tools') || 'Agent Tools', icon: <Wrench size={14} /> },
    { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety', icon: <ShieldAlert size={14} /> },
    { key: 'alerts',   label: t('settings.section_alert_guardrails'),       icon: <Bell size={14} /> },
    { key: 'webhooks', label: t('settings.section_notifications') || 'Alerts', icon: <Bell size={14} /> },
    { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler', icon: <Clock size={14} /> },
    { key: 'memory',   label: t('settings.tab_memory'),                    icon: <Database size={14} /> },
    { key: 'presets',  label: t('settings.section_presets') || 'Templates',  icon: <BookmarkPlus size={14} /> },
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
                <Section title={t('settings.general') || 'Preferences'}>
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
                  <Section title={t('settings.llm_settings') || 'Core Engine Configuration'}>
                    <p className="text-[10px] text-slate-500 -mt-1 leading-relaxed mb-2">
                      {t('settings.llm_settings_description')}
                    </p>

                    <Row label={t('settings.row_llm_provider') || 'LLM Provider'}>
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
                    <Row label={t('settings.row_llm_model') || 'LLM Model'}>
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
                          const models = llmCatalog[entry.provider]?.models ?? []
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
                                    const model = llmCatalog[provider]?.models[0]?.value ?? entry.model
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
          {activeTab === 'risk' && (
            <ErrorBoundary name="SettingsRisk">
              <div className="space-y-6">
                {/* 1. Risk & Capital Limits */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400">
                      <ShieldAlert className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_risk') || 'Risk & Capital Limits'}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <RiskRowItem label={t('settings.row_risk_per_trade')} unit="%">
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        max="50"
                        className={CompactInputStyle}
                        value={s.max_risk_per_trade_pct}
                        onChange={e => update('max_risk_per_trade_pct', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_max_position_size')} unit="%">
                      <input
                        type="number"
                        step="1"
                        min="1"
                        max="100"
                        className={CompactInputStyle}
                        value={s.max_position_size_pct}
                        onChange={e => update('max_position_size_pct', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_max_concentration')} unit="%">
                      <input
                        type="number"
                        step="1"
                        min="1"
                        max="100"
                        className={CompactInputStyle}
                        value={s.max_concentration_pct}
                        onChange={e => update('max_concentration_pct', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_max_gross_exposure')} unit="×">
                      <input
                        type="number"
                        step="0.1"
                        min="1"
                        max="10"
                        className={CompactInputStyle}
                        value={s.max_gross_exposure}
                        onChange={e => update('max_gross_exposure', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <ToggleItem
                      label={t('settings.row_allow_short_selling')}
                      checked={s.allow_short_selling}
                      onChange={v => update('allow_short_selling', v)}
                      className="md:col-span-2"
                    />
                  </div>
                </div>

                {/* 2. Debate & Execution Rules */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400">
                      <Brain className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_execution_rules') || 'Debate & Execution Rules'}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <RiskRowItem label={t('settings.row_debate_rounds')} unit="tur">
                      <input
                        type="number"
                        min="1"
                        max="10"
                        className={CompactInputStyle}
                        value={s.max_debate_rounds}
                        onChange={e => update('max_debate_rounds', Number.parseInt(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_risk_rounds')} unit="tur">
                      <input
                        type="number"
                        min="1"
                        max="10"
                        className={CompactInputStyle}
                        value={s.max_risk_rounds}
                        onChange={e => update('max_risk_rounds', Number.parseInt(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_price_tolerance')} unit="%">
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max="10"
                        className={CompactInputStyle}
                        value={s.price_tolerance_pct}
                        onChange={e => update('price_tolerance_pct', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_parallel_analysts')} unit="analist">
                      <input
                        type="number"
                        min="1"
                        max="16"
                        className={CompactInputStyle}
                        value={s.analyst_concurrency_limit}
                        onChange={e => update('analyst_concurrency_limit', Number.parseInt(e.target.value))}
                      />
                    </RiskRowItem>
                  </div>
                </div>

                {/* 3. Agent Resilience & Timeouts */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                      <RefreshCw className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_agent_resilience') || 'Agent Resilience & Timeouts'}
                    </h3>
                  </div>

                  <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
                    {t('settings.hard_timeout_hint') || 'Hard wall-clock limits per node / tool. If exceeded the call is treated as a transient error and retried automatically.'}
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <RiskRowItem label={t('settings.row_node_retry_attempts') || 'Node Retry Attempts'} unit="deneme">
                      <input
                        type="number"
                        min="1"
                        max="10"
                        className={CompactInputStyle}
                        value={s.node_retry_attempts ?? 2}
                        onChange={e => update('node_retry_attempts', Number.parseInt(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_node_retry_base_delay') || 'Retry Base Delay'} unit="sn">
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        max="10"
                        className={CompactInputStyle}
                        value={s.node_retry_base_delay ?? 1.0}
                        onChange={e => update('node_retry_base_delay', Number.parseFloat(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_node_timeout_seconds') || 'Node Timeout'} unit="sn">
                      <input
                        type="number"
                        step="10"
                        min="30"
                        max="600"
                        className={CompactInputStyle}
                        value={s.node_timeout_seconds ?? 120}
                        onChange={e => update('node_timeout_seconds', Number.parseInt(e.target.value) || 120)}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_tool_timeout_seconds') || 'Tool Timeout'} unit="sn">
                      <input
                        type="number"
                        step="5"
                        min="15"
                        max="300"
                        className={CompactInputStyle}
                        value={s.tool_timeout_seconds ?? 60}
                        onChange={e => update('tool_timeout_seconds', Number.parseInt(e.target.value) || 60)}
                      />
                    </RiskRowItem>
                  </div>
                </div>

                {/* 4. Circuit Breaker & Stall Protection */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400">
                      <Clock className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_circuit_stall') || 'Circuit Breaker & Stall Protection'}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <RiskRowItem
                      label={t('settings.row_circuit_breaker_threshold') || 'Circuit Breaker Threshold'}
                      hint={t('settings.circuit_breaker_hint') || 'After N consecutive failures, skip to fallback.'}
                      unit="hata"
                      className="md:col-span-2"
                    >
                      <input
                        type="number"
                        min="1"
                        max="20"
                        className={CompactInputStyle}
                        value={s.circuit_breaker_threshold ?? 3}
                        onChange={e => update('circuit_breaker_threshold', Number.parseInt(e.target.value))}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_circuit_breaker_cooldown') || 'Circuit Breaker Cooldown'} unit="sn">
                      <input
                        type="number"
                        step="10"
                        min="10"
                        max="600"
                        className={CompactInputStyle}
                        value={s.circuit_breaker_cooldown ?? 60}
                        onChange={e => update('circuit_breaker_cooldown', Number.parseInt(e.target.value) || 60)}
                      />
                    </RiskRowItem>

                    <RiskRowItem
                      label={t('settings.row_stall_timeout_seconds') || 'Stall Timeout'}
                      hint={t('settings.stall_hint') || 'Warning if no output emitted for N seconds.'}
                      unit="sn"
                    >
                      <input
                        type="number"
                        step="10"
                        min="30"
                        max="600"
                        className={CompactInputStyle}
                        value={s.stall_timeout_seconds ?? 120}
                        onChange={e => update('stall_timeout_seconds', Number.parseInt(e.target.value) || 120)}
                      />
                    </RiskRowItem>
                  </div>
                </div>

                {/* 5. Token Budget & Optimization */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                      <Database className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.token_budget') || 'Token Budget & Optimization'}
                    </h3>
                  </div>

                  <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
                    {t('settings.token_budget_hint') || 'Lower values reduce LLM token cost per analysis.'}
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <ToggleItem
                      label={t('settings.row_prompt_caching') || 'Anthropic Prompt Caching'}
                      checked={s.anthropic_prompt_caching ?? true}
                      onChange={v => update('anthropic_prompt_caching', v)}
                      className="md:col-span-2"
                    />

                    <RiskRowItem label={t('settings.row_max_report_chars') || 'Max Report Chars'} unit="karakter">
                      <input
                        type="number"
                        min="500"
                        max="50000"
                        step="500"
                        className={CompactInputStyle}
                        value={s.max_report_chars_in_prompts ?? 6000}
                        onChange={e => update('max_report_chars_in_prompts', Number.parseInt(e.target.value) || 6000)}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_max_debate_history') || 'Max Debate History'} unit="karakter">
                      <input
                        type="number"
                        min="1000"
                        max="100000"
                        step="1000"
                        className={CompactInputStyle}
                        value={s.max_debate_history_chars ?? 8000}
                        onChange={e => update('max_debate_history_chars', Number.parseInt(e.target.value) || 8000)}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_max_tool_output') || 'Max Tool Output'} unit="karakter" className="md:col-span-2">
                      <input
                        type="number"
                        min="1000"
                        max="100000"
                        step="1000"
                        className={CompactInputStyle}
                        value={s.max_tool_output_chars ?? 12000}
                        onChange={e => update('max_tool_output_chars', Number.parseInt(e.target.value) || 12000)}
                      />
                    </RiskRowItem>

                    <ToggleItem
                      label={t('settings.row_summary_only_mode') || 'Summary-Only Reports'}
                      hint={t('settings.summary_only_mode_hint') || 'Downstream agents only see executive summaries.'}
                      checked={s.summary_only_mode ?? false}
                      onChange={v => update('summary_only_mode', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_prefilter_enabled') || 'Pre-screen Weak Analysts'}
                      hint={t('settings.prefilter_hint') || 'Skip analysts with poor past hit rate on this ticker.'}
                      checked={s.analyst_prefilter_enabled ?? false}
                      onChange={v => update('analyst_prefilter_enabled', v)}
                    />

                    {s.analyst_prefilter_enabled && (
                      <>
                        <RiskRowItem label={t('settings.row_prefilter_min_samples') || 'Min. Graded Calls'} unit="çağrı">
                          <input
                            type="number"
                            min="1"
                            max="100"
                            className={CompactInputStyle}
                            value={s.analyst_prefilter_min_samples ?? 5}
                            onChange={e => update('analyst_prefilter_min_samples', Number.parseInt(e.target.value) || 5)}
                          />
                        </RiskRowItem>

                        <RiskRowItem label={t('settings.row_prefilter_max_win_rate') || 'Drop Below Win Rate'} unit="%">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            className={CompactInputStyle}
                            value={s.analyst_prefilter_max_win_rate ?? 40}
                            onChange={e => update('analyst_prefilter_max_win_rate', Number.parseFloat(e.target.value) || 40)}
                          />
                        </RiskRowItem>
                      </>
                    )}
                  </div>
                </div>

                {/* 6. Institutional Risk Features */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                      <Wrench className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_institutional_features') || 'Institutional Risk Features'}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <ToggleItem
                      label={t('settings.row_strict_stop_loss')}
                      checked={s.strict_stop_loss_mode}
                      onChange={v => update('strict_stop_loss_mode', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_correlation_risk')}
                      checked={s.correlation_risk_enabled}
                      onChange={v => update('correlation_risk_enabled', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_auto_execute_signals')}
                      warning={t('settings.auto_execute_signals_hint')}
                      checked={s.auto_execute_signals ?? false}
                      onChange={v => update('auto_execute_signals', v)}
                      className="md:col-span-2"
                    />

                    <ToggleItem
                      label={t('settings.row_quality_gate')}
                      checked={s.quality_gate_enabled}
                      onChange={v => update('quality_gate_enabled', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_drawdown_breaker')}
                      checked={s.drawdown_breaker_enabled}
                      onChange={v => update('drawdown_breaker_enabled', v)}
                    />

                    {s.drawdown_breaker_enabled && (
                      <RiskRowItem label={t('settings.row_max_drawdown_pct')} unit="%" className="md:col-span-2">
                        <input
                          type="number"
                          min={1}
                          max={100}
                          className={CompactInputStyle}
                          value={s.max_portfolio_drawdown_pct}
                          onChange={e => update('max_portfolio_drawdown_pct', Number(e.target.value))}
                        />
                      </RiskRowItem>
                    )}
                  </div>
                </div>

                {/* 7. Strategy Continuity & Decision Stability */}
                <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4 border border-white/[0.06] shadow-xl backdrop-blur-md">
                  <div className="flex items-center gap-2.5 border-b border-white/[0.06] pb-3">
                    <div className="p-1.5 rounded-lg bg-fuchsia-500/10 border border-fuchsia-500/20 text-fuchsia-300">
                      <Brain className="w-4 h-4" />
                    </div>
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">
                      {t('settings.section_strategy_continuity') || 'Strategy Continuity & Decision Stability'}
                    </h3>
                  </div>

                  <p className="text-[11px] text-slate-400 leading-relaxed -mt-1">
                    {t('settings.strategy_continuity_hint') || 'Shadow mode records the controller’s counterfactual without changing the Portfolio Manager’s executable decision.'}
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <ToggleItem
                      label={t('settings.row_strategy_learning') || 'Learn Active Asset Strategies'}
                      hint={t('settings.strategy_learning_hint') || 'Persist live strategy revisions and use them as context for later analyses.'}
                      checked={s.strategy_learning_enabled ?? true}
                      onChange={v => update('strategy_learning_enabled', v)}
                    />

                    <RiskRowItem
                      label={t('settings.row_decision_stability_mode') || 'Decision Stability Mode'}
                      hint={s.decision_stability_mode === 'enforce'
                        ? t('settings.decision_stability_enforce_warning') || 'Enforce can replace a proposal with Hold when change evidence is insufficient.'
                        : undefined}
                    >
                      <select
                        aria-label={t('settings.row_decision_stability_mode') || 'Decision Stability Mode'}
                        className={CompactInputStyle}
                        value={s.decision_stability_mode ?? 'shadow'}
                        onChange={e => update('decision_stability_mode', e.target.value)}
                      >
                        <option value="off">{t('settings.decision_stability_off') || 'Off'}</option>
                        <option value="shadow">{t('settings.decision_stability_shadow') || 'Shadow'}</option>
                        <option value="enforce">{t('settings.decision_stability_enforce') || 'Enforce'}</option>
                      </select>
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_stability_min_quality') || 'Min. Change Quality'} unit="%">
                      <input
                        aria-label={t('settings.row_stability_min_quality') || 'Min. Change Quality'}
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        className={CompactInputStyle}
                        value={s.decision_stability_min_quality ?? 70}
                        onChange={e => update('decision_stability_min_quality', Number.parseInt(e.target.value) || 0)}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_stability_min_confidence') || 'Min. Calibrated Confidence'} unit="0–1">
                      <input
                        aria-label={t('settings.row_stability_min_confidence') || 'Min. Calibrated Confidence'}
                        type="number"
                        min="0"
                        max="1"
                        step="0.01"
                        className={CompactInputStyle}
                        value={s.decision_stability_min_confidence ?? 0.65}
                        onChange={e => update('decision_stability_min_confidence', Number.parseFloat(e.target.value) || 0)}
                      />
                    </RiskRowItem>

                    <RiskRowItem label={t('settings.row_stability_min_evidence_groups') || 'Min. Independent Evidence Groups'} unit="#" className="md:col-span-2">
                      <input
                        aria-label={t('settings.row_stability_min_evidence_groups') || 'Min. Independent Evidence Groups'}
                        type="number"
                        min="1"
                        max="10"
                        step="1"
                        className={CompactInputStyle}
                        value={s.decision_stability_min_evidence_groups ?? 2}
                        onChange={e => update('decision_stability_min_evidence_groups', Number.parseInt(e.target.value) || 1)}
                      />
                    </RiskRowItem>

                    <ToggleItem
                      label={t('settings.row_reversal_verifier') || 'Verify Major Reversals'}
                      hint={t('settings.reversal_verifier_hint') || 'Require an extra independent-evidence check before a major BUY↔SELL reversal is accepted.'}
                      checked={s.reversal_verifier_enabled ?? true}
                      onChange={v => update('reversal_verifier_enabled', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_confidence_calibration') || 'Calibrate PM Confidence'}
                      hint={t('settings.confidence_calibration_hint') || 'Use realised outcomes to adjust raw Portfolio Manager confidence before stability checks.'}
                      checked={s.confidence_calibration_enabled ?? false}
                      onChange={v => update('confidence_calibration_enabled', v)}
                    />

                    <ToggleItem
                      label={t('settings.row_regime_aware_weighting') || 'Regime-Aware Analyst Weighting'}
                      hint={t('settings.regime_aware_weighting_hint') || 'Weight analyst history by the current market regime when enough realised evidence exists.'}
                      checked={s.regime_aware_weighting_enabled ?? false}
                      onChange={v => update('regime_aware_weighting_enabled', v)}
                      className="md:col-span-2"
                    />
                  </div>
                </div>
              </div>
            </ErrorBoundary>
          )}

          {/* Alert Creation Guardrails */}
          {activeTab === 'alerts' && (
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
          )}

          {/* Webhooks & Alerts */}
          {activeTab === 'webhooks' && (
            <ErrorBoundary name="SettingsWebhooks">
            <Section title={t('settings.section_notifications') || 'Alerts & Webhooks'}>
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
          )}

          {/* Presets / Templates */}
          {activeTab === 'presets' && (
            <ErrorBoundary name="SettingsPresets">
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
            </ErrorBoundary>
          )}

          {/* Cron Scheduler */}
          {activeTab === 'cron' && (
            <ErrorBoundary name="SettingsCron">
            <Section title={t('settings.section_cron') || 'Cron Scheduler'}>
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
          )}

          {activeTab === 'memory' && (
            <ErrorBoundary name="SettingsMemory">
            <Section title={t('settings.section_vector_memory')}>
              <Row label={t('settings.row_memory_store')}>
                <select className={Input} value={s.memory_store} onChange={e => update('memory_store', e.target.value)}>
                  {(meta?.memory_stores ?? [{ value: 'pinecone', label: t('settings.memory_store_pinecone') }, { value: 'pgvector', label: t('settings.memory_store_pgvector') }]).map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </Row>
              <Row label={t('settings.row_status')}>
                {memoryStatus?.enabled ? (
                  <span className="px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">{t('settings.memory_enabled')}</span>
                ) : (
                  <span className="px-2 py-0.5 rounded-lg bg-slate-700/40 text-slate-400 text-[10px] font-bold border border-white/[0.06]">
                    {s.memory_store === 'pgvector' ? t('settings.memory_disabled_pgvector') : t('settings.memory_disabled_pinecone')}
                  </span>
                )}
              </Row>
              {s.memory_store === 'pgvector' ? (
                <>
                  <Row label={t('settings.row_openai_embed_model')}><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
                  <Row label="">
                    <p className="text-[10px] text-slate-600 leading-relaxed">{t('settings.pgvector_hint')}</p>
                  </Row>
                </>
              ) : (
                <>
                  <Row label={t('settings.row_pinecone_api_key')}>
                    {memoryStatus?.enabled ? (
                      <button onClick={deletePineconeKey} className="flex items-center gap-1.5 text-xs font-semibold text-rose-400 hover:text-rose-300">
                        <Trash2 size={13} /> {t('settings.memory_remove_key')}
                      </button>
                    ) : (
                      <div className="flex gap-2 items-center">
                        <input type="password" className={Input} value={pineconeKey} onChange={e => setPineconeKey(e.target.value)} placeholder="pcsk_..." />
                        <button onClick={savePineconeKey} disabled={pineconeSaving || !pineconeKey.trim()} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-violet-600 hover:bg-violet-500 disabled:opacity-40">{t('settings.memory_save_key')}</button>
                      </div>
                    )}
                  </Row>
                  <Row label={t('settings.row_index_name')}><input className={Input} value={s.pinecone_index} onChange={e => update('pinecone_index', e.target.value)} /></Row>
                  <Row label={t('settings.row_cloud')}><input className={Input} value={s.pinecone_cloud} onChange={e => update('pinecone_cloud', e.target.value)} placeholder="aws" /></Row>
                  <Row label={t('settings.row_region')}><input className={Input} value={s.pinecone_region} onChange={e => update('pinecone_region', e.target.value)} placeholder="us-east-1" /></Row>
                  <Row label={t('settings.row_embedder')}>
                    <select className={Input} value={s.memory_embedder} onChange={e => update('memory_embedder', e.target.value)}>
                      {(meta?.embedders ?? [{ value: 'pinecone', label: t('settings.memory_embedder_pinecone') }, { value: 'openai', label: t('settings.memory_embedder_openai') }, { value: 'ollama', label: t('settings.memory_embedder_ollama') }]).map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </Row>
                  {s.memory_embedder === 'openai' && (
                    <Row label={t('settings.row_openai_embed_model')}><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
                  )}
                  {s.memory_embedder === 'ollama' && (
                    <Row label={t('settings.row_ollama_embed_model')}>
                      <input className={Input} value={s.memory_ollama_embed_model} onChange={e => update('memory_ollama_embed_model', e.target.value)} placeholder="nomic-embed-text" />
                    </Row>
                  )}
                  {s.memory_embedder === 'pinecone' && (
                    <Row label={t('settings.row_embed_model')}><input className={Input} value={s.pinecone_embed_model} onChange={e => update('pinecone_embed_model', e.target.value)} /></Row>
                  )}
                  <Row label="">
                    <p className="text-[10px] text-slate-600 leading-relaxed">
                      {t('settings.memory_help')}
                    </p>
                  </Row>
                </>
              )}
              {memoryStatus?.needs_openai_key && (
                <Row label=""><span className="text-[11px] text-amber-400">{t('settings.memory_needs_openai_key')}</span></Row>
              )}
              <Row label={t('settings.row_agent_qa')}>
                <label className="flex items-center gap-2.5 cursor-pointer text-slate-300 select-none">
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded" checked={s.agent_qa_enabled} onChange={e => update('agent_qa_enabled', e.target.checked)} />
                  <span className="text-xs font-semibold">{t('settings.agent_qa_description')}</span>
                </label>
              </Row>
              <Row label={t('settings.row_memory_recall_count')}>
                <input type="number" min={1} max={50} className={Input} value={s.memory_recall_count ?? 5} onChange={e => update('memory_recall_count', parseInt(e.target.value) || 5)} />
              </Row>
            </Section>
            </ErrorBoundary>
          )}

          {activeTab === 'tools' && (
            <ErrorBoundary name="SettingsTools">
              <ToolSettingsPanel ref={toolPanelRef} userId={userId} hideSaveButton={true} />
            </ErrorBoundary>
          )}

          {activeTab === 'agents' && (
            <ErrorBoundary name="SettingsAgents">
              <AgentSettingsPanel ref={agentPanelRef} userId={userId} />
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

interface PersonaItem {
  key: string
  label: string
  description: string
  instructions: string
  is_builtin: boolean
}

function PersonaEditor({ userId }: { userId?: number } = {}) {
  const { t } = useTranslation()
  const [showForm, setShowForm] = useState(false)
  const [editKey, setEditKey] = useState<string | null>(null)
  const [form, setForm] = useState({ key: '', label: '', description: '', instructions: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const personasQuery = usePersonasListAllPersonas(userId ? { user_id: userId } : undefined)
  const personas = (personasQuery.data ?? []) as unknown as PersonaItem[]
  const loading = personasQuery.isPending
  const load = useCallback(() => personasQuery.refetch(), [personasQuery])

  const createPersona = usePersonasCreatePersona()
  const updatePersona = usePersonasUpdatePersona()
  const deletePersona = usePersonasDeletePersona()

  const openCreate = () => { setForm({ key: '', label: '', description: '', instructions: '' }); setEditKey(null); setShowForm(true); setError(null) }
  const openEdit = (p: PersonaItem) => { setForm({ key: p.key, label: p.label, description: p.description, instructions: p.instructions }); setEditKey(p.key); setShowForm(true); setError(null) }

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
