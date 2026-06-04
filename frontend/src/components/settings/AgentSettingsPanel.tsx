import { useEffect, useState } from 'react'
import axios from 'axios'
import { Save, AlertCircle } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'
import { useMeta } from '../../hooks/useMeta'

interface AgentSettingState {
  enabled: boolean
  settings: Record<string, any>
}

interface AgentSettings {
  agents: Record<string, AgentSettingState>
}

interface AgentSettingsPanelProps {
  userId?: number // If specified, read/edit user-specific settings (admin mode)
  serverScope?: boolean // If true, read/edit server-scope global settings
}

const InputClass = 'w-full glass-input rounded-xl px-3 py-2 text-xs outline-none text-slate-300 placeholder-slate-650'

export default function AgentSettingsPanel({ userId, serverScope = false }: AgentSettingsPanelProps) {
  const { t } = useTranslation()
  const meta = useMeta()
  const [settings, setSettings] = useState<AgentSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const apiPath = serverScope
    ? '/api/settings/agents/server'
    : userId
    ? `/api/settings/users/${userId}/agents`
    : '/api/settings/agents'

  const fetchSettings = async () => {
    setLoading(true)
    setSaveError(null)
    try {
      const res = await axios.get(apiPath)
      setSettings(res.data)
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || 'Failed to load agent settings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSettings()
  }, [apiPath, meta])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    setSaveSuccess(false)
    setSaveError(null)
    try {
      const res = await axios.put(apiPath, settings)
      setSettings(res.data)
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || 'Failed to save agent settings.')
    } finally {
      setSaving(false)
    }
  }

  const updateAgentEnabled = (agentKey: string, enabled: boolean) => {
    setSettings(prev => {
      if (!prev) return prev
      const agents = { ...prev.agents }
      agents[agentKey] = { ...agents[agentKey], enabled }
      return { ...prev, agents }
    })
  }

  const updateSettingField = (agentKey: string, fieldKey: string, value: any) => {
    setSettings(prev => {
      if (!prev) return prev
      const agents = { ...prev.agents }
      const agentState = { ...agents[agentKey] }
      agentState.settings = { ...agentState.settings, [fieldKey]: value }
      agents[agentKey] = agentState
      return { ...prev, agents }
    })
  }

  if (loading) {
    return <div className="text-slate-500 text-xs font-semibold p-4">{t('common.loading') || 'Loading...'}</div>
  }

  const agents = meta?.agents || []
  if (agents.length === 0) {
    return (
      <div className="flex items-center gap-2 p-4 text-xs font-semibold text-slate-500 bg-white/[0.02] rounded-xl border border-white/[0.04]">
        <AlertCircle size={14} />
        <span>No agent configurations found in meta database.</span>
      </div>
    )
  }

  const getParentLabel = (parentKey: string | null) => {
    if (!parentKey) return null
    const parent = agents.find((a: any) => a.key === parentKey)
    return parent ? (parent as any).label : parentKey
  }

  const categories = Array.from(new Set(agents.map((a: any) => a.category as string)))

  return (
    <div className="space-y-6 animate-in fade-in duration-150">
      {/* Save bar */}
      <div className="flex justify-between items-center bg-white/[0.01] border border-white/[0.04] p-3 rounded-2xl">
        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
          {serverScope ? 'Global Server Agent Overrides' : 'Personal AI Agent Configuration'}
        </span>
        <div className="flex items-center gap-3">
          {saveError && <span className="text-rose-400 text-xs font-semibold">{saveError}</span>}
          {saveSuccess && <span className="text-emerald-400 text-xs font-semibold">Saved successfully!</span>}
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-4 py-2 text-xs font-semibold transition-all shadow-md shadow-violet-500/10 cursor-pointer disabled:opacity-50"
          >
            <Save size={14} />
            {saving ? 'Saving...' : 'Save Agent Settings'}
          </button>
        </div>
      </div>

      {/* Categories */}
      {categories.map((cat: string) => {
        const catAgents = agents.filter((a: any) => a.category === cat)
        if (catAgents.length === 0) return null

        return (
          <div key={cat} className="space-y-4">
            <h4 className="text-xs font-bold text-violet-400 uppercase tracking-widest border-b border-white/[0.04] pb-2">
              {cat === 'analyst' ? 'Indicator & Data Analysts' : 'Decision Orchestration Managers'}
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {catAgents.map((agent: any) => {
                const agentState = settings?.agents?.[agent.key] || { enabled: agent.default_enabled, settings: {} }
                const isEnabled = agentState.enabled
                const schemaFields = agent.settings_schema || []
                const parentLabel = getParentLabel(agent.parent_key)

                return (
                  <div
                    key={agent.key}
                    className={`glass-panel rounded-2xl p-4 flex flex-col justify-between border transition-all ${
                      isEnabled ? 'border-violet-500/10 bg-white/[0.01]' : 'border-white/[0.02] opacity-60'
                    }`}
                  >
                    <div>
                      {/* Title & Enable switch */}
                      <div className="flex items-center justify-between border-b border-white/[0.02] pb-3 mb-3">
                        <div className="pr-2">
                          <h5 className="text-xs font-bold text-white tracking-wide">
                            {agent.label}
                          </h5>
                          <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">{agent.description}</p>
                          {parentLabel && (
                            <span className="text-[8px] bg-white/5 text-slate-400 border border-white/10 rounded px-1.5 py-0.5 font-bold uppercase tracking-wider mt-1.5 inline-block">
                              Parent: {parentLabel}
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => updateAgentEnabled(agent.key, !isEnabled)}
                          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors cursor-pointer shrink-0 ${
                            isEnabled ? 'bg-violet-600' : 'bg-slate-700'
                          }`}
                        >
                          <span
                            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                              isEnabled ? 'translate-x-4.5' : 'translate-x-0.5'
                            }`}
                          />
                        </button>
                      </div>

                      {/* Fields: Hides on close (if not enabled) */}
                      {isEnabled && schemaFields.length > 0 && (
                        <div className="space-y-3.5">
                          {schemaFields.map((field: any) => {
                            const settingsDict = (agentState.settings || {}) as Record<string, any>
                            const val = settingsDict[field.key] !== undefined ? settingsDict[field.key] : field.default

                            return (
                              <div key={field.key} className="space-y-1">
                                <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                                  {field.label_key}
                                </label>

                                {field.type === 'select' && (
                                  <select
                                    className={InputClass}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(agent.key, field.key, e.target.value)}
                                  >
                                    {field.options?.map((opt: any) => (
                                      <option key={opt.value} value={opt.value}>
                                        {opt.label_key}
                                      </option>
                                    ))}
                                  </select>
                                )}

                                {field.type === 'string' && (
                                  <input
                                    type="text"
                                    className={InputClass}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(agent.key, field.key, e.target.value)}
                                  />
                                )}

                                {field.type === 'number' && (
                                  <div className="flex items-center gap-3">
                                    <input
                                      type="number"
                                      min={field.min}
                                      max={field.max}
                                      step={field.step || 0.1}
                                      className={`${InputClass} w-20`}
                                      value={val ?? ''}
                                      onChange={e => updateSettingField(agent.key, field.key, parseFloat(e.target.value))}
                                    />
                                    {field.min !== undefined && field.max !== undefined && (
                                      <input
                                        type="range"
                                        min={field.min}
                                        max={field.max}
                                        step={field.step || 0.1}
                                        className="flex-1 accent-violet-500 h-1.5 rounded-lg bg-white/[0.04] cursor-pointer"
                                        value={val ?? field.default ?? field.min}
                                        onChange={e => updateSettingField(agent.key, field.key, parseFloat(e.target.value))}
                                      />
                                    )}
                                  </div>
                                )}

                                {field.type === 'textarea' && (
                                  <textarea
                                    className={`${InputClass} h-16 resize-none`}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(agent.key, field.key, e.target.value)}
                                  />
                                )}
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
