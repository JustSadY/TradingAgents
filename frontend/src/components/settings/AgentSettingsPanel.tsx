import { type ReactNode, useEffect, useMemo, useState, forwardRef, useImperativeHandle, useRef } from 'react'
import axios from 'axios'
import { AlertCircle, ChevronDown, ChevronRight, Settings2, Save, Loader2 } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'
import { useMeta, triggerMetaRefetch } from '../../hooks/useMeta'

interface FieldSchema {
  key: string
  type: 'select' | 'string' | 'number' | 'textarea' | 'boolean'
  label_key: string
  description_key?: string
  placeholder_key?: string
  default: any
  required: boolean
  min?: number
  max?: number
  step?: number
  options?: { value: string; label_key: string }[]
}

interface AgentMeta {
  key: string
  label: string
  description: string
  category: string
  default_enabled: boolean
  parent_key: string | null
  settings_schema: FieldSchema[]
}

interface AgentSettingState {
  enabled: boolean
  settings: Record<string, any>
}

interface AgentSettingsData {
  agents: Record<string, AgentSettingState>
}

interface AgentSettingsPanelProps {
  userId?: number
  serverScope?: boolean
}

const MAIN_AGENT_KEYS = new Set([
  'portfolio_manager',
  'market_intelligence',
  'research_manager',
  'risk_debate',
])

const InputCls =
  'w-full glass-input rounded-xl px-3 py-2 text-xs outline-none text-slate-300 placeholder-slate-650 disabled:opacity-40 disabled:cursor-not-allowed'

function buildChildrenMap(agents: AgentMeta[]): Map<string | null, AgentMeta[]> {
  const map = new Map<string | null, AgentMeta[]>()
  for (const a of agents) {
    const p = a.parent_key ?? null
    if (!map.has(p)) map.set(p, [])
    map.get(p)!.push(a)
  }
  return map
}

function AgentSettingsFields({
  agent,
  agentState,
  disabled,
  onFieldChange,
  t,
}: {
  agent: AgentMeta
  agentState: AgentSettingState
  disabled: boolean
  onFieldChange: (fieldKey: string, value: any) => void
  t: (key: string) => string
}) {
  const fields = agent.settings_schema ?? []
  if (fields.length === 0) return null

  return (
    <div className="space-y-3 pt-3 mt-3 border-t border-white/[0.04]">
      {fields.map(field => {
        const val =
          agentState.settings?.[field.key] !== undefined
            ? agentState.settings[field.key]
            : field.default

        return (
          <div key={field.key} className="space-y-1">
            <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider block">
              {t(field.label_key)}
            </label>

            {field.type === 'select' && (
              <select
                className={InputCls}
                value={val ?? ''}
                disabled={disabled}
                onChange={e => onFieldChange(field.key, e.target.value)}
              >
                {field.options?.map(opt => (
                  <option key={opt.value} value={opt.value}>
                    {t(opt.label_key)}
                  </option>
                ))}
              </select>
            )}

            {field.type === 'string' && (
              <input
                type="text"
                className={InputCls}
                value={val ?? ''}
                disabled={disabled}
                placeholder={field.placeholder_key ? t(field.placeholder_key) : ''}
                onChange={e => onFieldChange(field.key, e.target.value)}
              />
            )}

            {field.type === 'number' && (
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 0.1}
                  className={`${InputCls} w-20`}
                  value={val ?? ''}
                  disabled={disabled}
                  onChange={e => onFieldChange(field.key, Number.parseFloat(e.target.value))}
                />
                {field.min !== undefined && field.max !== undefined && (
                  <input
                    type="range"
                    min={field.min}
                    max={field.max}
                    step={field.step ?? 0.1}
                    className="flex-1 accent-violet-500 h-1.5 rounded-lg bg-white/[0.04] cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    value={val ?? field.default ?? field.min}
                    disabled={disabled}
                    onChange={e => onFieldChange(field.key, Number.parseFloat(e.target.value))}
                  />
                )}
              </div>
            )}

            {field.type === 'textarea' && (
              <textarea
                className={`${InputCls} h-16 resize-none`}
                value={val ?? ''}
                disabled={disabled}
                placeholder={field.placeholder_key ? t(field.placeholder_key) : ''}
                onChange={e => onFieldChange(field.key, e.target.value)}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function AgentCard({
  agent,
  agentState,
  parentDisabled,
  children,
  onToggleEnabled,
  onFieldChange,
  t,
}: {
  agent: AgentMeta
  agentState: AgentSettingState
  parentDisabled: boolean
  children?: ReactNode
  onToggleEnabled: (key: string, val: boolean) => void
  onFieldChange: (key: string, fieldKey: string, value: any) => void
  t: (key: string) => string
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [childrenOpen, setChildrenOpen] = useState(false)
  const hasChildren = !!children
  const ownEnabled = agentState.enabled
  const effectivelyDisabled = parentDisabled
  const inputsDisabled = effectivelyDisabled || !ownEnabled

  return (
    <div
      className={`rounded-xl border transition-all duration-200 ${
        effectivelyDisabled
          ? 'border-white/[0.03] opacity-50'
          : ownEnabled
          ? 'border-violet-500/10 bg-white/[0.015]'
          : 'border-white/[0.04] opacity-60'
      }`}
    >
      <div className="flex items-start gap-2 p-3">
        {hasChildren ? (
          <button
            className="mt-0.5 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer shrink-0"
            onClick={() => setChildrenOpen(v => !v)}
            aria-label={childrenOpen ? 'Collapse' : 'Expand'}
          >
            {childrenOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="w-3.5 shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <h5 className="text-xs font-bold text-white tracking-wide truncate">
                {agent.label}
              </h5>
              <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed line-clamp-2">
                {agent.description}
              </p>
            </div>

            <button
              onClick={() => !effectivelyDisabled && onToggleEnabled(agent.key, !ownEnabled)}
              disabled={effectivelyDisabled}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 ${
                effectivelyDisabled
                  ? 'cursor-not-allowed'
                  : 'cursor-pointer'
              } ${ownEnabled && !effectivelyDisabled ? 'bg-violet-600' : 'bg-slate-700'}`}
              aria-label={ownEnabled ? 'Disable agent' : 'Enable agent'}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  ownEnabled && !effectivelyDisabled ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>

          <button
            className="mt-2 flex items-center gap-1 text-[10px] text-slate-500 hover:text-violet-400 transition-colors cursor-pointer"
            onClick={() => setSettingsOpen(v => !v)}
          >
            <Settings2 size={10} />
            <span>{settingsOpen ? 'Hide settings' : 'LLM settings'}</span>
            {settingsOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>

          {settingsOpen && (
            <AgentSettingsFields
              agent={agent}
              agentState={agentState}
              disabled={inputsDisabled}
              onFieldChange={(fieldKey, value) => onFieldChange(agent.key, fieldKey, value)}
              t={t}
            />
          )}
        </div>
      </div>

      {hasChildren && childrenOpen && (
        <div className="px-3 pb-3 space-y-2 border-t border-white/[0.04] pt-2">
          {children}
        </div>
      )}
    </div>
  )
}

function AgentSubTree({
  parentKey,
  childrenMap,
  settings,
  parentDisabled,
  onToggleEnabled,
  onFieldChange,
  t,
}: {
  parentKey: string
  childrenMap: Map<string | null, AgentMeta[]>
  settings: AgentSettingsData
  parentDisabled: boolean
  onToggleEnabled: (key: string, val: boolean) => void
  onFieldChange: (key: string, fieldKey: string, value: any) => void
  t: (key: string) => string
}) {
  const directChildren = (childrenMap.get(parentKey) ?? []).filter(
    a => !MAIN_AGENT_KEYS.has(a.key),
  )
  if (directChildren.length === 0) return null

  return (
    <>
      {directChildren.map(agent => {
        const agentState = settings.agents[agent.key] ?? {
          enabled: agent.default_enabled,
          settings: {},
        }
        const grandchildren = childrenMap.get(agent.key) ?? []
        const ownDisabled = parentDisabled || !agentState.enabled

        return (
          <AgentCard
            key={agent.key}
            agent={agent}
            agentState={agentState}
            parentDisabled={parentDisabled}
            onToggleEnabled={onToggleEnabled}
            onFieldChange={onFieldChange}
            t={t}
          >
            {grandchildren.length > 0 ? (
              <AgentSubTree
                parentKey={agent.key}
                childrenMap={childrenMap}
                settings={settings}
                parentDisabled={ownDisabled}
                onToggleEnabled={onToggleEnabled}
                onFieldChange={onFieldChange}
                t={t}
              />
            ) : undefined}
          </AgentCard>
        )
      })}
    </>
  )
}

function MainAgentSection({
  agent,
  childrenMap,
  settings,
  ancestorDisabled = false,
  ancestorLabel,
  onToggleEnabled,
  onFieldChange,
  t,
}: {
  agent: AgentMeta
  childrenMap: Map<string | null, AgentMeta[]>
  settings: AgentSettingsData
  ancestorDisabled?: boolean
  ancestorLabel?: string
  onToggleEnabled: (key: string, val: boolean) => void
  onFieldChange: (key: string, fieldKey: string, value: any) => void
  t: (key: string) => string
}) {
  const [expanded, setExpanded] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const agentState = settings.agents[agent.key] ?? {
    enabled: agent.default_enabled,
    settings: {},
  }
  const ownEnabled = agentState.enabled && !ancestorDisabled
  const children = childrenMap.get(agent.key) ?? []

  return (
    <div
      className={`rounded-2xl border overflow-hidden transition-all duration-200 ${
        ownEnabled
          ? 'border-violet-500/15 bg-white/[0.01]'
          : 'border-white/[0.04] bg-white/[0.005]'
      }`}
    >
      <div
        className="flex items-center gap-3 p-4 cursor-pointer select-none"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="text-slate-500 transition-colors hover:text-slate-300">
          {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4
              className={`text-sm font-bold tracking-wide transition-colors ${
                ownEnabled ? 'text-white' : 'text-slate-500'
              }`}
            >
              {agent.label}
            </h4>
            {!ownEnabled && (
              <span className="text-[9px] font-bold uppercase tracking-widest bg-rose-500/15 text-rose-400 border border-rose-500/20 rounded px-1.5 py-0.5">
                {ancestorDisabled ? `Off via ${ancestorLabel ?? 'parent'}` : 'Disabled'}
              </span>
            )}
          </div>
          <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed truncate">
            {agent.description}
          </p>
        </div>

        <button
          onClick={e => {
            e.stopPropagation()
            if (!ancestorDisabled) onToggleEnabled(agent.key, !agentState.enabled)
          }}
          disabled={ancestorDisabled}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors shrink-0 ${
            ancestorDisabled ? 'cursor-not-allowed' : 'cursor-pointer'
          } ${ownEnabled ? 'bg-violet-600' : 'bg-slate-700'}`}
          aria-label={ownEnabled ? 'Disable' : 'Enable'}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
              ownEnabled ? 'translate-x-4' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/[0.04] pt-3">
          <button
            className="flex items-center gap-1.5 text-[10px] text-slate-500 hover:text-violet-400 transition-colors cursor-pointer"
            onClick={() => setSettingsOpen(v => !v)}
          >
            <Settings2 size={11} />
            <span>{settingsOpen ? 'Hide LLM settings' : 'Configure LLM settings'}</span>
            {settingsOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>

          {settingsOpen && (
            <div
              className={`rounded-xl border border-white/[0.04] p-3 transition-opacity ${
                !ownEnabled ? 'opacity-50' : ''
              }`}
            >
              <AgentSettingsFields
                agent={agent}
                agentState={agentState}
                disabled={!ownEnabled}
                onFieldChange={(fieldKey, value) => onFieldChange(agent.key, fieldKey, value)}
                t={t}
              />
            </div>
          )}

          {children.length > 0 && (
            <div
              className={`space-y-2 transition-opacity duration-200 ${
                !ownEnabled ? 'opacity-40 pointer-events-none' : ''
              }`}
            >
              <p className="text-[9px] font-bold uppercase tracking-widest text-slate-600 pb-1">
                Sub-Agents
              </p>
              <AgentSubTree
                parentKey={agent.key}
                childrenMap={childrenMap}
                settings={settings}
                parentDisabled={!ownEnabled}
                onToggleEnabled={onToggleEnabled}
                onFieldChange={onFieldChange}
                t={t}
              />

            </div>
          )}
        </div>
      )}
    </div>
  )
}

export interface AgentSettingsPanelHandle {
  save: () => Promise<void>
}

const AgentSettingsPanel = forwardRef<AgentSettingsPanelHandle, AgentSettingsPanelProps>(({
  userId,
  serverScope = false,
}, ref) => {
  const { t } = useTranslation()
  const meta = useMeta()
  const [settings, setSettings] = useState<AgentSettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const agentTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => { return () => { if (agentTimeoutRef.current) clearTimeout(agentTimeoutRef.current) } }, [])

  const apiPath = serverScope
    ? '/api/settings/agents/server'
    : userId
    ? `/api/settings/users/${userId}/agents`
    : '/api/settings/agents'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setSaveError(null)
    axios
      .get(apiPath)
      .then(res => { if (!cancelled) setSettings(res.data) })
      .catch(err => { if (!cancelled) setSaveError(err.response?.data?.detail || 'Failed to load agent settings.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [apiPath, meta])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    setSaveSuccess(false)
    setSaveError(null)
    try {
      const res = await axios.put(apiPath, settings)
      setSettings(res.data)
      triggerMetaRefetch()
      setSaveSuccess(true)
      if (agentTimeoutRef.current) clearTimeout(agentTimeoutRef.current)
      agentTimeoutRef.current = setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to save agent settings.'
      setSaveError(msg)
      throw new Error(msg, { cause: err })
    } finally {
      setSaving(false)
    }
  }

  useImperativeHandle(ref, () => ({
    save
  }))

  const handleToggleEnabled = (agentKey: string, enabled: boolean) => {
    setSettings(prev => {
      if (!prev) return prev
      return {
        ...prev,
        agents: {
          ...prev.agents,
          [agentKey]: { ...prev.agents[agentKey], enabled },
        },
      }
    })
  }

  const handleFieldChange = (agentKey: string, fieldKey: string, value: any) => {
    setSettings(prev => {
      if (!prev) return prev
      const existing = prev.agents[agentKey] ?? { enabled: true, settings: {} }
      return {
        ...prev,
        agents: {
          ...prev.agents,
          [agentKey]: {
            ...existing,
            settings: { ...existing.settings, [fieldKey]: value },
          },
        },
      }
    })
  }

  const agents: AgentMeta[] = (meta?.agents as AgentMeta[]) ?? []

  const childrenMap = useMemo(() => buildChildrenMap(agents), [agents])

  const mainAgents = useMemo(() => {
    const mains = agents.filter(a => MAIN_AGENT_KEYS.has(a.key))
    return mains.sort((a, b) => {
      if (a.key === 'portfolio_manager') return -1
      if (b.key === 'portfolio_manager') return 1
      return 0
    })
  }, [agents])

  if (loading) {
    return (
      <div className="text-slate-500 text-xs font-semibold p-4">
        {t('common.loading') || 'Loading…'}
      </div>
    )
  }

  if (agents.length === 0) {
    return (
      <div className="flex items-center gap-2 p-4 text-xs font-semibold text-slate-500 bg-white/[0.02] rounded-xl border border-white/[0.04]">
        <AlertCircle size={14} />
        <span>No agent configurations found in meta database.</span>
      </div>
    )
  }

  if (!settings) {
    return (
      <div className="flex items-center gap-2 p-4 text-xs font-semibold text-rose-400 bg-rose-500/5 rounded-xl border border-rose-500/10">
        <AlertCircle size={14} />
        <span>{saveError || 'Could not load agent settings.'}</span>
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-in fade-in duration-150">
      <div className="flex justify-between items-center bg-white/[0.01] border border-white/[0.04] p-3 rounded-2xl sticky top-0 z-10 backdrop-blur-sm">
        <div>
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
            {serverScope ? 'Global Server Agent Overrides' : 'Personal AI Agent Configuration'}
          </span>
          <p className="text-[9px] text-slate-600 mt-0.5">
            Configure provider, model and temperature per agent. Sub-agents inherit from their parent when not overridden.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-4">
          {saveError && (
            <span className="text-rose-400 text-xs font-semibold">{saveError}</span>
          )}
          {saveSuccess && (
            <span className="text-emerald-400 text-xs font-semibold">Saved!</span>
          )}
          <button
            onClick={() => save()}
            disabled={saving}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold shadow-sm transition-all cursor-pointer disabled:opacity-50"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            <span>{saving ? 'Saving...' : 'Save Agent Settings'}</span>
          </button>
        </div>
      </div>

      <div className="text-[10px] text-slate-600 bg-white/[0.01] border border-white/[0.03] rounded-xl px-3 py-2 leading-relaxed">
        <span className="text-violet-400 font-bold">Hierarchy:</span>
        {' '}Portfolio Manager (root) → Market Intelligence / Research Manager / Risk Debate.
        The Portfolio Manager is the sole source of final order direction, sizing, and risk levels.
        Disabling a parent immediately kills its entire sub-tree — no tokens will be consumed.
        Sub-agents inherit the parent&apos;s LLM unless overridden.
      </div>

      <div className="space-y-4">
        {mainAgents.map(agent => {
          const pmEnabled = settings.agents['portfolio_manager']?.enabled ?? true
          const killedByRoot = agent.key !== 'portfolio_manager' && !pmEnabled
          return (
            <MainAgentSection
              key={agent.key}
              agent={agent}
              childrenMap={childrenMap}
              settings={settings}
              ancestorDisabled={killedByRoot}
              ancestorLabel="Portfolio Manager"
              onToggleEnabled={handleToggleEnabled}
              onFieldChange={handleFieldChange}
              t={t}
            />
          )
        })}
      </div>
    </div>
  )
})

export default AgentSettingsPanel
