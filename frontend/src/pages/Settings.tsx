import { useEffect, useState, useRef, useCallback } from 'react'
import axios from 'axios'
import {
  Save, BookmarkPlus, Trash2, Play, Bell,
  Settings as SettingsIcon, Brain, ShieldAlert, Clock, Wrench, Database,
  CheckCircle2, XCircle, RefreshCw, UserCircle, Plus, Pencil
} from 'lucide-react'

/** Parse webhook_events — accepts JSON array or legacy comma-separated */
function parseWebhookEvents(raw: string): string[] {
  if (!raw) return []
  const s = raw.trim()
  if (s.startsWith('[')) {
    try { const r = JSON.parse(s); return Array.isArray(r) ? r : [] } catch { /* fall through */ }
  }
  return s.split(',').map(x => x.trim()).filter(Boolean)
}

interface DeliveryRecord {
  id: number
  event: string
  url: string
  success: boolean
  status_code: number | null
  error: string | null
  created_at: string
}
import { useMeta, triggerMetaRefetch } from '../hooks/useMeta'
import { useAuth } from '../contexts/AuthContext'
import { requestBrowserNotifyPermission, setBrowserNotifyPref, isBrowserNotifyEnabled } from '../utils/browserNotify'
import { useTranslation } from '../contexts/LanguageContext'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import type { ToolSettingsPanelHandle } from '../components/settings/ToolSettingsPanel'
import AgentSettingsPanel from '../components/settings/AgentSettingsPanel'
import type { AgentSettingsPanelHandle } from '../components/settings/AgentSettingsPanel'

// ... (interfaces unchanged) ...
interface Settings {
  cron_enabled: boolean
  cron_schedule: string
  price_tolerance_pct: number
  llm_provider: string
  llm_model: string
  fallback_llm_provider: string | null
  fallback_llm_model: string | null
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
  memory_store: string
  pinecone_index: string
  pinecone_cloud: string
  pinecone_region: string
  memory_embedder: string
  pinecone_embed_model: string
  memory_openai_embed_model: string
  memory_ollama_embed_model: string
  agent_qa_enabled: boolean
  anthropic_prompt_caching: boolean
  max_report_chars_in_prompts: number
  max_debate_history_chars: number
  max_tool_output_chars: number
  analyst_prefilter_enabled: boolean
  analyst_prefilter_min_samples: number
  analyst_prefilter_max_win_rate: number
  memory_recall_count: number
  news_article_limit: number
  global_news_article_limit: number
  global_news_lookback_days: number
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
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [presetName, setPresetName] = useState('')
  const [presetSaving, setPresetSaving] = useState(false)
  const [browserNotify, setBrowserNotify] = useState(isBrowserNotifyEnabled())
  const [webhookTesting, setWebhookTesting] = useState(false)
  const [webhookTestResult, setWebhookTestResult] = useState<string | null>(null)
  const [deliveries, setDeliveries] = useState<DeliveryRecord[]>([])
  const [loadingDeliveries, setLoadingDeliveries] = useState(false)
  const loadDeliveries = useCallback(() => {
    setLoadingDeliveries(true)
    axios.get<DeliveryRecord[]>('/api/settings/webhook-deliveries')
      .then(r => setDeliveries(r.data))
      .catch(() => {})
      .finally(() => setLoadingDeliveries(false))
  }, [])
  const [activeTab, setActiveTab] = useState<'general' | 'llm' | 'agents' | 'risk' | 'webhooks' | 'presets' | 'advanced' | 'cron' | 'tools' | 'memory' | 'personas'>('general')
  const [memoryStatus, setMemoryStatus] = useState<any>(null)
  const [pineconeKey, setPineconeKey] = useState('')
  const [pineconeSaving, setPineconeSaving] = useState(false)
  const loadMemoryStatus = () => axios.get('/api/settings/memory').then(r => setMemoryStatus(r.data)).catch(() => {})
  const [allowedSettings, setAllowedSettings] = useState<string[]>([])
  const [cronStatus, setCronStatus] = useState<{ running: boolean; job_configured: boolean; next_run_time: string | null } | null>(null)
  const meta = useMeta()
  
  const toolPanelRef = useRef<ToolSettingsPanelHandle>(null)
  const agentPanelRef = useRef<AgentSettingsPanelHandle>(null)

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
      if (!userId) loadMemoryStatus()

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
    setSaving(true)
    try {
      if (activeTab === 'agents') {
        if (agentPanelRef.current) await agentPanelRef.current.save()
      } else if (activeTab === 'tools') {
        if (toolPanelRef.current) await toolPanelRef.current.save()
      } else {
        const url = userId ? `/api/settings/users/${userId}` : '/api/settings'
        await axios.put(url, s)
        triggerMetaRefetch()
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err: any) {
      setSaveError(err.message || err.response?.data?.detail || t('settings.save_error_default'))
    } finally {
      setSaving(false)
    }
  }

  if (!s) return <div className="p-8 text-slate-500 text-xs font-semibold">{t('settings.loading')}</div>

  const update = (k: keyof Settings, v: any) => setS(prev => prev ? { ...prev, [k]: v } : prev)

  const savePineconeKey = async () => {
    if (!pineconeKey.trim()) return
    setPineconeSaving(true)
    try {
      await axios.put('/api/users/me/api-keys', { provider: 'pinecone', api_key: pineconeKey.trim() })
      setPineconeKey('')
      await loadMemoryStatus()
    } finally { setPineconeSaving(false) }
  }
  const deletePineconeKey = async () => {
    await axios.delete('/api/users/me/api-keys/pinecone').catch(() => {})
    await loadMemoryStatus()
  }

  const languages = meta?.languages ?? [{ value: 'English', label: 'English' }, { value: 'Turkish', label: 'Türkçe' }]

  const TABS = [
    { key: 'general',  label: t('settings.general') || 'Preferences',      icon: <SettingsIcon size={14} /> },
    { key: 'agents',   label: 'AI Configuration',                          icon: <Brain size={14} /> },
    { key: 'tools',    label: t('settings.section_tools') || 'Agent Tools', icon: <Wrench size={14} /> },
    { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety', icon: <ShieldAlert size={14} /> },
    { key: 'webhooks', label: t('settings.section_notifications') || 'Alerts', icon: <Bell size={14} /> },
    { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler', icon: <Clock size={14} /> },
    ...(userId ? [] : [{ key: 'memory',   label: 'Memory',                          icon: <Database size={14} /> }]),
    ...(userId ? [] : [{ key: 'presets',  label: t('settings.section_presets') || 'Templates',  icon: <BookmarkPlus size={14} /> }]),
    ...(userId ? [] : [{ key: 'personas', label: 'Personas',                        icon: <UserCircle size={14} /> }]),
  ].filter(tab => isAdmin || tab.key === 'tools' || tab.key === 'agents' || tab.key === 'memory' || allowedSettings.includes(tab.key))

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
          <button onClick={save} disabled={saving} className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-xs font-semibold shadow-md shadow-violet-500/20 transition-all shrink-0 cursor-pointer disabled:opacity-50">
            <Save size={14} /> {saving ? 'Saving...' : saved ? t('settings.save_button_saved') : t('settings.save_button')}
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

              <Section title="News & Sentiment Limits">
                <Row label="News Article Limit">
                  <input type="number" min={1} max={100} className={Input} value={s.news_article_limit ?? 20} onChange={e => update('news_article_limit', parseInt(e.target.value) || 20)} />
                </Row>
                <Row label="Global News Limit">
                  <input type="number" min={1} max={100} className={Input} value={s.global_news_article_limit ?? 10} onChange={e => update('global_news_article_limit', parseInt(e.target.value) || 10)} />
                </Row>
                <Row label="Global News Lookback (Days)">
                  <input type="number" min={1} max={90} className={Input} value={s.global_news_lookback_days ?? 7} onChange={e => update('global_news_lookback_days', parseInt(e.target.value) || 7)} />
                </Row>
              </Section>

              <Section title={t('settings.llm_settings') || 'Core Engine Configuration'}>
                <p className="text-[10px] text-slate-500 -mt-1 leading-relaxed mb-2">
                  Global LLM settings and performance parameters. Per-agent models are configured in the AI Configuration tab.
                </p>

                <Row label={t('settings.row_fallback_provider')}>
                  <select
                    className={Input}
                    value={s.fallback_llm_provider || ''}
                    onChange={e => {
                      const v = e.target.value || null
                      update('fallback_llm_provider', v)
                      if (!v) update('fallback_llm_model', null)
                    }}
                  >
                    <option value="">{t('settings.fallback_disabled')}</option>
                    {Object.entries(meta?.provider_labels ?? {}).map(([key, label]) => (
                      <option key={key} value={key}>{label}</option>
                    ))}
                  </select>
                </Row>
                {s.fallback_llm_provider && (
                  <>
                    <Row label={t('settings.row_fallback_model')}>
                      <input
                        className={Input}
                        value={s.fallback_llm_model || ''}
                        onChange={e => update('fallback_llm_model', e.target.value || null)}
                        placeholder={t('settings.fallback_model_placeholder')}
                      />
                    </Row>
                    <p className="text-[10px] text-slate-500 -mt-1 leading-relaxed">
                      {t('settings.fallback_hint')}
                    </p>
                  </>
                )}

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
                    onChange={e => update('max_recur_limit', Number.parseInt(e.target.value) || 1000)}
                  />
                </Row>
              </Section>
            </div>
          )}

          {/* Risk Management */}
          {activeTab === 'risk' && (
            <Section title={t('settings.section_risk') || 'Risk Management'}>
              <Row label={t('settings.row_risk_per_trade')}>
                <input type="number" step="0.1" min="0.1" max="50" className={Input} value={s.max_risk_per_trade_pct} onChange={e => update('max_risk_per_trade_pct', Number.parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_max_position_size')}>
                <input type="number" step="1" min="1" max="100" className={Input} value={s.max_position_size_pct} onChange={e => update('max_position_size_pct', Number.parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_debate_rounds')}>
                <input type="number" min="1" max="10" className={Input} value={s.max_debate_rounds} onChange={e => update('max_debate_rounds', Number.parseInt(e.target.value))} />
              </Row>
              <Row label={t('settings.row_risk_rounds')}>
                <input type="number" min="1" max="10" className={Input} value={s.max_risk_rounds} onChange={e => update('max_risk_rounds', Number.parseInt(e.target.value))} />
              </Row>
              <Row label={t('settings.row_price_tolerance')}>
                <input type="number" step="0.1" min="0" max="10" className={Input} value={s.price_tolerance_pct} onChange={e => update('price_tolerance_pct', Number.parseFloat(e.target.value))} />
              </Row>
              <Row label={t('settings.row_parallel_analysts')}>
                <input type="number" min="1" max="16" className={Input} value={s.analyst_concurrency_limit} onChange={e => update('analyst_concurrency_limit', Number.parseInt(e.target.value))} />
              </Row>

              <div className="border-t border-white/[0.04] pt-4 mt-2 space-y-3">
                <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-1">Agent Run Resilience</h4>
                <Row label={t('settings.row_node_retry_attempts') || 'Node Retry Attempts'}>
                  <input type="number" min="1" max="10" className={Input} value={s.node_retry_attempts ?? 2} onChange={e => update('node_retry_attempts', Number.parseInt(e.target.value))} />
                </Row>
                <Row label={t('settings.row_node_retry_base_delay') || 'Retry Base Delay (s)'}>
                  <input type="number" step="0.1" min="0.1" max="10" className={Input} value={s.node_retry_base_delay ?? 1.0} onChange={e => update('node_retry_base_delay', Number.parseFloat(e.target.value))} />
                </Row>
              </div>

              <div className="border-t border-white/[0.04] pt-4 mt-2 space-y-3">
                <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest px-1">{t('settings.token_budget') || 'Token Budget'}</h4>
                <p className="text-[10px] text-slate-500 px-1 leading-snug">{t('settings.token_budget_hint') || 'Lower values reduce LLM token cost per analysis at the expense of how much detail each agent re-reads.'}</p>

                <label className="flex items-center justify-between p-2 rounded-xl hover:bg-white/[0.02] cursor-pointer transition-colors group">
                  <span className="text-xs font-semibold text-slate-300 group-hover:text-white transition-colors">{t('settings.row_prompt_caching') || 'Anthropic Prompt Caching'}</span>
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded cursor-pointer" checked={s.anthropic_prompt_caching ?? true} onChange={e => update('anthropic_prompt_caching', e.target.checked)} />
                </label>
                <Row label={t('settings.row_max_report_chars') || 'Max Report Chars / Prompt'}>
                  <input type="number" min="500" max="50000" step="500" className={Input} value={s.max_report_chars_in_prompts ?? 6000} onChange={e => update('max_report_chars_in_prompts', Number.parseInt(e.target.value) || 6000)} />
                </Row>
                <Row label={t('settings.row_max_debate_history') || 'Max Debate History Chars'}>
                  <input type="number" min="1000" max="100000" step="1000" className={Input} value={s.max_debate_history_chars ?? 8000} onChange={e => update('max_debate_history_chars', Number.parseInt(e.target.value) || 8000)} />
                </Row>
                <Row label={t('settings.row_max_tool_output') || 'Max Tool Output Chars'}>
                  <input type="number" min="1000" max="100000" step="1000" className={Input} value={s.max_tool_output_chars ?? 12000} onChange={e => update('max_tool_output_chars', Number.parseInt(e.target.value) || 12000)} />
                </Row>

                <label className="flex items-center justify-between p-2 rounded-xl hover:bg-white/[0.02] cursor-pointer transition-colors group mt-1">
                  <span className="text-xs font-semibold text-slate-300 group-hover:text-white transition-colors">{t('settings.row_prefilter_enabled') || 'Pre-screen Weak Analysts'}</span>
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded cursor-pointer" checked={s.analyst_prefilter_enabled ?? false} onChange={e => update('analyst_prefilter_enabled', e.target.checked)} />
                </label>
                <p className="text-[10px] text-slate-500 px-1 leading-snug -mt-1">{t('settings.prefilter_hint') || 'Skip analysts whose past calls on the analysed ticker have a poor hit rate. Needs realized history; core analysts are always kept.'}</p>
                {s.analyst_prefilter_enabled && (
                  <>
                    <Row label={t('settings.row_prefilter_min_samples') || 'Min. Graded Calls'}>
                      <input type="number" min="1" max="100" className={Input} value={s.analyst_prefilter_min_samples ?? 5} onChange={e => update('analyst_prefilter_min_samples', Number.parseInt(e.target.value) || 5)} />
                    </Row>
                    <Row label={t('settings.row_prefilter_max_win_rate') || 'Drop Below Win Rate (%)'}>
                      <input type="number" min="0" max="100" step="1" className={Input} value={s.analyst_prefilter_max_win_rate ?? 40} onChange={e => update('analyst_prefilter_max_win_rate', Number.parseFloat(e.target.value) || 40)} />
                    </Row>
                  </>
                )}
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
                        checked={parseWebhookEvents(s.webhook_events).includes(key)}
                        onChange={e => {
                          const events = parseWebhookEvents(s.webhook_events)
                          const next = e.target.checked ? [...events, key] : events.filter(x => x !== key)
                          update('webhook_events', JSON.stringify(next))
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

              {/* Delivery History */}
              <div className="mt-2 pt-4 border-t border-white/[0.04] space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Recent Deliveries</span>
                  <button
                    onClick={loadDeliveries}
                    disabled={loadingDeliveries}
                    className="p-1 rounded text-slate-600 hover:text-violet-400 transition cursor-pointer"
                    title="Refresh delivery log"
                  >
                    <RefreshCw size={12} className={loadingDeliveries ? 'animate-spin' : ''} />
                  </button>
                </div>
                {deliveries.length === 0 ? (
                  <p className="text-[10px] text-slate-600 italic">No deliveries logged yet. Webhook events will appear here after they fire.</p>
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

          {activeTab === 'memory' && (
            <Section title="Vector Memory">
              <Row label={t('settings.row_memory_store')}>
                <select className={Input} value={s.memory_store} onChange={e => update('memory_store', e.target.value)}>
                  <option value="pinecone">{t('settings.memory_store_pinecone')}</option>
                  <option value="pgvector">{t('settings.memory_store_pgvector')}</option>
                </select>
              </Row>
              <Row label="Status">
                {memoryStatus?.enabled ? (
                  <span className="px-2 py-0.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">ENABLED</span>
                ) : (
                  <span className="px-2 py-0.5 rounded-lg bg-slate-700/40 text-slate-400 text-[10px] font-bold border border-white/[0.06]">
                    {s.memory_store === 'pgvector' ? t('settings.memory_disabled_pgvector') : t('settings.memory_disabled_pinecone')}
                  </span>
                )}
              </Row>
              {s.memory_store === 'pgvector' ? (
                <>
                  <Row label="OpenAI Embed Model"><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
                  <Row label="">
                    <p className="text-[10px] text-slate-600 leading-relaxed">{t('settings.pgvector_hint')}</p>
                  </Row>
                </>
              ) : (
                <>
                  <Row label="Pinecone API Key">
                    {memoryStatus?.enabled ? (
                      <button onClick={deletePineconeKey} className="flex items-center gap-1.5 text-xs font-semibold text-rose-400 hover:text-rose-300">
                        <Trash2 size={13} /> Remove key
                      </button>
                    ) : (
                      <div className="flex gap-2 items-center">
                        <input type="password" className={Input} value={pineconeKey} onChange={e => setPineconeKey(e.target.value)} placeholder="pcsk_..." />
                        <button onClick={savePineconeKey} disabled={pineconeSaving || !pineconeKey.trim()} className="px-4 py-2 rounded-xl text-xs font-semibold text-white bg-violet-600 hover:bg-violet-500 disabled:opacity-40">Save</button>
                      </div>
                    )}
                  </Row>
                  <Row label="Index Name"><input className={Input} value={s.pinecone_index} onChange={e => update('pinecone_index', e.target.value)} /></Row>
                  <Row label="Cloud"><input className={Input} value={s.pinecone_cloud} onChange={e => update('pinecone_cloud', e.target.value)} placeholder="aws" /></Row>
                  <Row label="Region"><input className={Input} value={s.pinecone_region} onChange={e => update('pinecone_region', e.target.value)} placeholder="us-east-1" /></Row>
                  <Row label="Embedder">
                    <select className={Input} value={s.memory_embedder} onChange={e => update('memory_embedder', e.target.value)}>
                      <option value="pinecone">Pinecone hosted (no extra key)</option>
                      <option value="openai">OpenAI (uses your OpenAI key)</option>
                      <option value="ollama">Ollama (local, free)</option>
                    </select>
                  </Row>
                  {s.memory_embedder === 'openai' && (
                    <Row label="OpenAI Embed Model"><input className={Input} value={s.memory_openai_embed_model} onChange={e => update('memory_openai_embed_model', e.target.value)} /></Row>
                  )}
                  {s.memory_embedder === 'ollama' && (
                    <Row label="Ollama Embed Model">
                      <input className={Input} value={s.memory_ollama_embed_model} onChange={e => update('memory_ollama_embed_model', e.target.value)} placeholder="nomic-embed-text" />
                    </Row>
                  )}
                  {s.memory_embedder === 'pinecone' && (
                    <Row label="Embed Model"><input className={Input} value={s.pinecone_embed_model} onChange={e => update('pinecone_embed_model', e.target.value)} /></Row>
                  )}
                  <Row label="">
                    <p className="text-[10px] text-slate-600 leading-relaxed">
                      Use the Save button above to persist the index/embedder settings. Memory stays off until a Pinecone API key is added, and each user's memory is isolated. The OpenAI embedder reuses your OpenAI key from Profile. The Ollama embedder uses your local Ollama instance (configure host in Profile → Ollama).
                    </p>
                  </Row>
                </>
              )}
              {memoryStatus?.needs_openai_key && (
                <Row label=""><span className="text-[11px] text-amber-400">Add your OpenAI API key in Profile to use the OpenAI embedder.</span></Row>
              )}
              <Row label="Inter-Agent Q&A">
                <label className="flex items-center gap-2.5 cursor-pointer text-slate-300 select-none">
                  <input type="checkbox" className="w-5 h-5 accent-violet-600 rounded" checked={s.agent_qa_enabled} onChange={e => update('agent_qa_enabled', e.target.checked)} />
                  <span className="text-xs font-semibold">Analysts question each other after their reports</span>
                </label>
              </Row>
              <Row label="Memory Recall Count">
                <input type="number" min={1} max={50} className={Input} value={s.memory_recall_count ?? 5} onChange={e => update('memory_recall_count', parseInt(e.target.value) || 5)} />
              </Row>
            </Section>
          )}

          {activeTab === 'tools' && (
            <ToolSettingsPanel ref={toolPanelRef} userId={userId} hideSaveButton={true} />
          )}

          {activeTab === 'agents' && (
            <AgentSettingsPanel ref={agentPanelRef} userId={userId} />
          )}

          {activeTab === 'personas' && <PersonaEditor />}

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

function PersonaEditor() {
  const [personas, setPersonas] = useState<PersonaItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editKey, setEditKey] = useState<string | null>(null)
  const [form, setForm] = useState({ key: '', label: '', description: '', instructions: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { const r = await axios.get('/api/personas'); setPersonas(r.data) } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const openCreate = () => { setForm({ key: '', label: '', description: '', instructions: '' }); setEditKey(null); setShowForm(true); setError(null) }
  const openEdit = (p: PersonaItem) => { setForm({ key: p.key, label: p.label, description: p.description, instructions: p.instructions }); setEditKey(p.key); setShowForm(true); setError(null) }

  const save = async () => {
    if (!form.label.trim()) { setError('Label is required'); return }
    setSaving(true); setError(null)
    try {
      if (editKey) {
        await axios.put(`/api/personas/${editKey}`, { label: form.label, description: form.description, instructions: form.instructions })
      } else {
        if (!form.key.trim()) { setError('Key is required'); setSaving(false); return }
        await axios.post('/api/personas', form)
      }
      setShowForm(false); await load()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg || 'Failed to save persona')
    } finally { setSaving(false) }
  }

  const del = async (key: string) => {
    try { await axios.delete(`/api/personas/${key}`); await load() } catch { /* ignore */ }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-bold text-white">Investor Personas</p>
          <p className="text-[10px] text-slate-500 mt-0.5">Create custom investor personas that guide the Portfolio Manager's decision style</p>
        </div>
        {!showForm && (
          <button onClick={openCreate} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/20 text-violet-300 text-[10px] font-bold transition cursor-pointer">
            <Plus size={11} /> New Persona
          </button>
        )}
      </div>

      {showForm && (
        <div className="glass-panel rounded-2xl p-4 space-y-3 border border-violet-500/20">
          <p className="text-xs font-bold text-violet-300">{editKey ? 'Edit Persona' : 'New Persona'}</p>
          {!editKey && (
            <div>
              <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Key (a-z, 0-9, _)</label>
              <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1 font-mono" placeholder="my_persona" value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') }))} />
            </div>
          )}
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Display Label</label>
            <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1" placeholder="Momentum Trader" value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Description (short)</label>
            <input className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1" placeholder="Focuses on momentum and technical breakouts" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Instructions (injected into Portfolio Manager)</label>
            <textarea rows={5} className="w-full glass-input rounded-xl px-3 py-2 text-xs outline-none mt-1 resize-y font-mono" placeholder={'Focus on:\n- High momentum stocks with strong relative strength\n- Technical breakouts above key resistance\n- Tight stop-losses at 5-8%'} value={form.instructions} onChange={e => setForm(f => ({ ...f, instructions: e.target.value }))} />
          </div>
          {error && <p className="text-rose-400 text-[10px] font-semibold">{error}</p>}
          <div className="flex gap-2">
            <button onClick={save} disabled={saving} className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold transition cursor-pointer disabled:opacity-40">
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => setShowForm(false)} className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white text-xs font-semibold transition cursor-pointer">
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 opacity-40 text-[10px] text-slate-500">Loading personas…</div>
      ) : (
        <div className="space-y-2">
          {personas.map(p => (
            <div key={p.key} className="flex items-start justify-between gap-3 p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.08] transition-all">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-bold text-white truncate">{p.label}</span>
                  {p.is_builtin && <span className="text-[8px] font-bold uppercase tracking-wider text-violet-400 bg-violet-500/10 px-1.5 py-0.5 rounded-full border border-violet-500/20">Built-in</span>}
                  <span className="text-[9px] font-mono text-slate-600">{p.key}</span>
                </div>
                <p className="text-[10px] text-slate-500 truncate">{p.description || '—'}</p>
              </div>
              {!p.is_builtin && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <button onClick={() => openEdit(p)} className="p-1.5 rounded-lg text-slate-500 hover:text-violet-400 hover:bg-violet-500/10 transition cursor-pointer" title="Edit">
                    <Pencil size={12} />
                  </button>
                  <button onClick={() => del(p.key)} className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer" title="Delete">
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
