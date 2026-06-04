import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  Save, BookmarkPlus, Trash2, Play, Bell,
  Settings as SettingsIcon, Brain, ShieldAlert, Clock, Wrench
} from 'lucide-react'
import { useMeta, triggerMetaRefetch } from '../hooks/useMeta'
import { useAuth } from '../hooks/useAuth'
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
  include_historical_analyses: boolean
  historical_analyses_limit: number
  strict_backtest_learning: boolean
  analyst_models: Record<string, string>
  webhook_url: string | null
  webhook_enabled: boolean
  webhook_events: string
  watchlist: string[]
  selected_analysts: string[]
  node_retry_attempts: number
  node_retry_base_delay: number
}

interface Preset { id: number; name: string; description: string | null; created_at: string }

interface ModelOption { label: string; value: string }
type Catalog = Record<string, ModelOption[]>

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic (Claude)',
  google: 'Google (Gemini)',
  xai: 'xAI (Grok)',
  deepseek: 'DeepSeek',
  qwen: 'Qwen (Global)',
  'qwen-cn': 'Qwen (China)',
  glm: 'GLM / Z.AI (Global)',
  'glm-cn': 'GLM / BigModel (China)',
  minimax: 'MiniMax (Global)',
  'minimax-cn': 'MiniMax (China)',
  ollama: 'Ollama (Local)',
  nvidia: 'NVIDIA NIM',
  litellm: 'LiteLLM Proxy',
  azure: 'Azure OpenAI',
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

function ModelSelect({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: ModelOption[]
  value: string
  onChange: (v: string) => void
}) {
  const { t } = useTranslation()
  const isCustom = !options.some(o => o.value === value) || value === 'custom'
  const [showCustom, setShowCustom] = useState(isCustom)
  const [customVal, setCustomVal] = useState(isCustom ? value : '')

  useEffect(() => {
    const custom = !options.some(o => o.value === value) || value === 'custom'
    setShowCustom(custom)
    if (custom) setCustomVal(value === 'custom' ? '' : value)
  }, [value, options])

  const handleSelect = (v: string) => {
    if (v === 'custom') {
      setShowCustom(true)
      setCustomVal('')
    } else {
      setShowCustom(false)
      onChange(v)
    }
  }

  return (
    <Row label={label}>
      <div className="space-y-2 w-full">
        <select
          className={Input}
          value={showCustom ? 'custom' : value}
          onChange={e => handleSelect(e.target.value)}
        >
          {options.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
          {!options.some(o => o.value === 'custom') && (
            <option value="custom">{t('settings.custom_model_id')}</option>
          )}
        </select>
        {showCustom && (
          <input
            className={Input}
            placeholder={t('settings.model_id_placeholder')}
            value={customVal}
            onChange={e => {
              setCustomVal(e.target.value)
              onChange(e.target.value)
            }}
          />
        )}
      </div>
    </Row>
  )
}

export default function Settings({ userId }: { userId?: number } = {}) {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [s, setS] = useState<Settings | null>(null)
  const [catalog, setCatalog] = useState<Catalog>({})
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
  const meta = useMeta()

  useEffect(() => {
    const settingsUrl = userId ? `/api/settings/users/${userId}` : '/api/settings'
    const permUrl = userId ? `/api/users/${userId}/setting-permissions` : '/api/users/me/setting-permissions'
    Promise.all([
      axios.get(settingsUrl).then(r => r.data),
      axios.get('/api/settings/llm-catalog').then(r => r.data),
      axios.get('/api/presets').then(r => r.data).catch(() => []),
      axios.get(permUrl).then(r => r.data.allowed_settings || r.data.permissions || []).catch(() => []),
    ]).then(([settings, cat, presetList, allowedSet]) => {
      setS(settings)
      setCatalog(cat)
      setPresets(presetList)
      setAllowedSettings(userId ? ['general', 'llm', 'risk', 'webhooks', 'cron'] : allowedSet)

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

  const providerList = Object.keys(catalog)
  const currentProviderModels = catalog[s.llm_provider]

  const providerLabels = meta?.provider_labels ?? PROVIDER_LABELS
  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]
  const analysts = meta?.analysts ?? []

  const handleProviderChange = (provider: string) => {
    const models = catalog[provider]
    setS(prev => {
      if (!prev) return prev
      const defaultModel = models?.[0]?.value || prev.llm_model
      return {
        ...prev,
        llm_provider: provider,
        llm_model: defaultModel,
      }
    })
  }

  const TABS = [
    { key: 'general',  label: t('settings.general') || 'Preferences',      icon: <SettingsIcon size={14} /> },
    { key: 'llm',      label: t('settings.llm_settings') || 'AI Engine',   icon: <Brain size={14} /> },
    { key: 'agents',   label: 'AI Agents',                                 icon: <Brain size={14} /> },
    { key: 'tools',    label: t('settings.section_tools') || 'Agent Tools', icon: <Wrench size={14} /> },
    { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety', icon: <ShieldAlert size={14} /> },
    { key: 'webhooks', label: t('settings.section_notifications') || 'Alerts', icon: <Bell size={14} /> },
    { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler', icon: <Clock size={18} /> },
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
          )}

          {/* AI Engines */}
          {activeTab === 'llm' && (
            <div className="space-y-4">
              <Section title={t('settings.llm_settings') || 'LLM Settings'}>
                <Row label="LLM Provider">
                  <select
                    className={Input}
                    value={s.llm_provider}
                    onChange={e => handleProviderChange(e.target.value)}
                  >
                    {providerList.length > 0 ? (
                      providerList.map(p => (
                        <option key={p} value={p}>{providerLabels[p] || p}</option>
                      ))
                    ) : (
                      <>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                        <option value="google">Google (Gemini)</option>
                        <option value="xai">xAI (Grok)</option>
                        <option value="deepseek">DeepSeek</option>
                        <option value="ollama">Ollama (Local)</option>
                      </>
                    )}
                  </select>
                </Row>

                {currentProviderModels ? (
                  <ModelSelect
                    label={t('settings.row_default_model')}
                    options={currentProviderModels}
                    value={s.llm_model}
                    onChange={v => update('llm_model', v)}
                  />
                ) : (
                  <Row label={t('settings.row_default_model')}>
                    <input
                      className={Input}
                      value={s.llm_model}
                      onChange={e => update('llm_model', e.target.value)}
                      placeholder="Model ID"
                    />
                  </Row>
                )}

                {['ollama', 'litellm', 'azure', 'nvidia'].includes(s.llm_provider) && (
                  <Row label="API Base URL">
                    <input
                      className={Input}
                      value={s.backend_url || ''}
                      onChange={e => update('backend_url', e.target.value || null)}
                      placeholder="http://localhost:11434"
                    />
                  </Row>
                )}

                {s.llm_provider === 'openai' && (
                  <Row label="Reasoning Effort">
                    <select className={Input} value={s.openai_reasoning_effort || ''} onChange={e => update('openai_reasoning_effort', e.target.value || null)}>
                      <option value="">{t('settings.effort_default')}</option>
                      <option value="low">{t('settings.effort_low_fast_cheap')}</option>
                      <option value="medium">{t('settings.effort_medium_balanced')}</option>
                      <option value="high">{t('settings.effort_high_deep')}</option>
                    </select>
                  </Row>
                )}
                {s.llm_provider === 'anthropic' && (
                  <Row label="Thinking Effort">
                    <select className={Input} value={s.anthropic_effort || ''} onChange={e => update('anthropic_effort', e.target.value || null)}>
                      <option value="">{t('settings.effort_default')}</option>
                      <option value="low">{t('settings.effort_low_fast')}</option>
                      <option value="medium">{t('settings.effort_medium_balanced')}</option>
                      <option value="high">{t('settings.effort_high_extended')}</option>
                    </select>
                  </Row>
                )}
                {s.llm_provider === 'google' && (
                  <Row label="Thinking Level">
                    <select className={Input} value={s.google_thinking_level || ''} onChange={e => update('google_thinking_level', e.target.value || null)}>
                      <option value="">{t('settings.effort_default')}</option>
                      <option value="minimal">{t('settings.effort_minimal_fastest')}</option>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">{t('settings.effort_high_deepest')}</option>
                    </select>
                  </Row>
                )}

                <Row label={t('settings.row_historical_analyses')}>
                  <div className="flex flex-col gap-2 pt-1">
                    <label className="flex items-center gap-2.5 cursor-pointer text-slate-300 hover:text-white select-none">
                      <input
                        type="checkbox"
                        checked={s.include_historical_analyses}
                        onChange={e => update('include_historical_analyses', e.target.checked)}
                        className="w-4 h-4 accent-violet-600 rounded"
                      />
                      <span className="text-xs font-semibold">{t('settings.historical_analyses_hint')}</span>
                    </label>
                    {s.include_historical_analyses && (
                      <div className="flex items-center gap-2 pt-1 pl-6">
                        <span className="text-[10px] text-slate-500 font-semibold">{t('settings.historical_limit_label')}:</span>
                        <input
                          type="number"
                          min="1"
                          max="50"
                          className={`${Input} w-20 py-1 font-mono`}
                          value={s.historical_analyses_limit}
                          onChange={e => update('historical_analyses_limit', parseInt(e.target.value) || 5)}
                        />
                      </div>
                    )}
                  </div>
                </Row>
              </Section>

              <Section title={t('settings.section_active_analysts') || 'Active Analysts Mapping'}>
                {analysts.length === 0 ? (
                  <p className="text-slate-500 text-xs">{t('settings.analysts_loading')}</p>
                ) : (
                  <div className="flex flex-col gap-3 pt-1">
                    {analysts.map(a => {
                      const isActive = s.selected_analysts.includes(a.key)
                      const modelVal = s.analyst_models?.[a.key] || ''

                      let currentProvider = 'default'
                      let currentModel = modelVal
                      if (modelVal.includes(':')) {
                        const parts = modelVal.split(':')
                        currentProvider = parts[0]
                        currentModel = parts[1] || ''
                      }

                      const activeProvider = currentProvider === 'default' ? s.llm_provider : currentProvider
                      const providerModels = catalog[activeProvider]
                      const allModelValues = providerModels?.map(o => o.value) || []
                      const isCustomMode = currentModel === 'custom' || (currentModel !== '' && !allModelValues.includes(currentModel))
                      const selectModelVal = isCustomMode ? 'custom' : currentModel

                      return (
                        <div key={a.key} title={a.description} className="flex flex-col border-b border-white/[0.02] pb-3 last:border-b-0 last:pb-0">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                            <label className="flex items-center gap-2.5 text-xs font-semibold text-slate-300 cursor-pointer py-1">
                              <input
                                type="checkbox"
                                className="w-4 h-4 accent-violet-600 rounded"
                                checked={isActive}
                                onChange={e => {
                                  const next = e.target.checked
                                    ? [...s.selected_analysts, a.key]
                                    : s.selected_analysts.filter(x => x !== a.key)
                                  update('selected_analysts', next)
                                }}
                              />
                              {a.label}
                            </label>

                            {isActive && (
                              <div className="flex items-center gap-2 w-full sm:max-w-xs">
                                <select
                                  className={`${Input} py-1 text-[11px]`}
                                  value={currentProvider}
                                  onChange={e => {
                                    const nextProv = e.target.value
                                    const nextVal = nextProv === 'default' ? '' : 'custom'
                                    update('analyst_models', { ...(s.analyst_models || {}), [a.key]: nextVal })
                                  }}
                                >
                                  <option value="default">{t('settings.analyst_default_provider')}</option>
                                  {providerList.map(p => (
                                    <option key={p} value={p}>{providerLabels[p] || p}</option>
                                  ))}
                                </select>

                                <select
                                  className={`${Input} py-1 text-[11px]`}
                                  value={selectModelVal}
                                  onChange={e => {
                                    const val = e.target.value
                                    const prefix = currentProvider === 'default' ? '' : `${currentProvider}:`
                                    const nextVal = val === '' ? '' : prefix + val
                                    update('analyst_models', { ...(s.analyst_models || {}), [a.key]: nextVal })
                                  }}
                                >
                                  {currentProvider === 'default' && (
                                    <option value="">{t('settings.analyst_default_model')}</option>
                                  )}
                                  {providerModels?.map(o => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                  ))}
                                  <option value="custom">{t('settings.custom_model_option')}</option>
                                </select>
                              </div>
                            )}
                          </div>

                          {isActive && selectModelVal === 'custom' && (
                            <div className="flex justify-end pt-2">
                              <input
                                className={`${Input} py-1 w-full sm:max-w-xs font-mono`}
                                placeholder={t('settings.custom_model_placeholder')}
                                value={currentModel === 'custom' ? '' : currentModel}
                                onChange={e => {
                                  const val = e.target.value
                                  const prefix = currentProvider === 'default' ? '' : `${currentProvider}:`
                                  const nextVal = prefix + (val.trim() === '' ? 'custom' : val)
                                  update('analyst_models', { ...(s.analyst_models || {}), [a.key]: nextVal })
                                }}
                              />
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
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
                  <span className="text-xs font-semibold text-slate-300 group-hover:text-white transition-colors">Strict Backtest Learning</span>
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded cursor-pointer" checked={s.strict_backtest_learning} onChange={e => update('strict_backtest_learning', e.target.checked)} />
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
              <Row label="Active">
                <input
                  type="checkbox"
                  className="accent-violet-600 w-4 h-4 rounded cursor-pointer"
                  checked={s.cron_enabled}
                  onChange={e => update('cron_enabled', e.target.checked)}
                />
              </Row>
              <Row label="Schedule (Cron)">
                <input
                  className={Input}
                  value={s.cron_schedule}
                  onChange={e => update('cron_schedule', e.target.value)}
                  placeholder="e.g. 0 9 * * 1-5"
                />
                <p className="text-[10px] text-slate-500 mt-1.5 font-medium">Standard 5-field cron schedule format (UTC time)</p>
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
