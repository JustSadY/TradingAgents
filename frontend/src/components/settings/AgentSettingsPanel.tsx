import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Save, Settings2 } from 'lucide-react'
import {
  useSettingsGetUserAgents,
  useSettingsUpdateUserAgents,
  useSettingsGetServerAgents,
  useSettingsUpdateServerAgents,
  useSettingsGetOtherUserAgents,
  useSettingsUpdateOtherUserAgents,
} from '../../api/generated/settings/settings'
import { useTranslation } from '../../contexts/LanguageContext'
import { useMeta, triggerMetaRefetch } from '../../hooks/useMeta'
import { useLlmCatalog, type LlmCatalog } from '../../hooks/useLlmCatalog'
import { notify } from '../../utils/notify'
import type { AgentMeta } from '../../api/generated/model'
import AppSchemaForm, { legacyFieldsToSchema } from '../ui/AppSchemaForm'
import { AppAlert, AppButton, AppSwitch } from '../ui/AppPrimitives'

// Shape comes from the generated client; it used to be a narrower hand-written
// mirror with a cast, for the same reason as the tool panel.

interface AgentSettingState {
  enabled: boolean
  settings: Record<string, unknown>
}

interface AgentSettingsData {
  agents: Record<string, AgentSettingState>
}

interface AgentSettingsPanelProps {
  userId?: number
  serverScope?: boolean
  /**
   * Hide the panel's own save button when the host page already has one.
   *
   * The Settings page's Save calls this panel's `save()` through its ref, so
   * showing both put two save buttons on the same screen doing the same thing.
   * `ToolSettingsPanel` takes the same prop for the same reason.
   */
  hideSaveButton?: boolean
}

export interface AgentSettingsPanelHandle {
  save: () => Promise<void>
}

const MAIN_AGENT_KEYS = new Set([
  'portfolio_manager',
  'market_intelligence',
  'research_manager',
  'risk_debate',
])

function buildChildrenMap(agents: AgentMeta[]): Map<string | null, AgentMeta[]> {
  const map = new Map<string | null, AgentMeta[]>()
  for (const agent of agents) {
    const parent = agent.parent_key ?? null
    map.set(parent, [...(map.get(parent) ?? []), agent])
  }
  return map
}

interface AgentNodeProps {
  agent: AgentMeta
  settings: AgentSettingsData
  childrenMap: Map<string | null, AgentMeta[]>
  parentDisabled: boolean
  llmCatalog: LlmCatalog
  translate: (key: string) => string
  onToggle: (key: string, enabled: boolean) => void
  onSettingsChange: (key: string, settings: Record<string, unknown>) => void
  nested?: boolean
}

function AgentNode({
  agent,
  settings,
  childrenMap,
  parentDisabled,
  llmCatalog,
  translate,
  onToggle,
  onSettingsChange,
  nested = false,
}: AgentNodeProps) {
  const [expanded, setExpanded] = useState(!nested)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const state = settings.agents[agent.key] ?? { enabled: agent.default_enabled, settings: {} }
  const enabled = state.enabled && !parentDisabled
  const children = (childrenMap.get(agent.key) ?? []).filter(child => !MAIN_AGENT_KEYS.has(child.key))
  const { schema, uiSchema } = legacyFieldsToSchema(agent.settings_schema ?? [], translate)

  return (
    <div className={`rounded-xl border transition-all ${enabled ? 'border-violet-500/15 bg-white/[0.015]' : 'border-white/[0.04] bg-white/[0.005] opacity-65'}`}>
      <div className="flex items-start gap-3 p-3">
        <button
          type="button"
          className="mt-0.5 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer shrink-0"
          aria-label={translate(expanded ? 'settings.collapse_agent' : 'settings.expand_agent')}
          onClick={() => setExpanded(value => !value)}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h5 className={`${nested ? 'text-xs' : 'text-sm'} font-bold text-white tracking-wide`}>{agent.label}</h5>
              <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">{agent.description}</p>
            </div>
            <AppSwitch
              checked={state.enabled}
              disabled={parentDisabled}
              name={`${agent.key}-enabled`}
              onChange={value => onToggle(agent.key, value)}
            />
          </div>

          {expanded ? (
            <div className="pt-3 mt-3 border-t border-white/[0.04] space-y-3">
              {agent.settings_schema?.length ? (
                <>
                  <AppButton
                    variant="text"
                    size="small"
                    startIcon={<Settings2 size={12} />}
                    onClick={() => setSettingsOpen(value => !value)}
                  >
                    {translate(settingsOpen ? 'settings.hide_llm_settings' : 'settings.configure_llm_settings')}
                  </AppButton>
                  {settingsOpen ? (
                    <AppSchemaForm
                      schema={schema}
                      uiSchema={uiSchema}
                      formData={state.settings}
                      formContext={{
                        llmCatalog,
                        formData: state.settings,
                        inheritLabel: translate('settings.analyst_default_provider'),
                        customLabel: translate('settings.custom_model_option'),
                      }}
                      disabled={!enabled}
                      onChange={next => onSettingsChange(agent.key, next)}
                    />
                  ) : null}
                </>
              ) : null}

              {children.length ? (
                <div className={`space-y-2 ${!enabled ? 'pointer-events-none opacity-50' : ''}`}>
                  <p className="text-[9px] font-bold uppercase tracking-widest text-slate-600">{translate('settings.sub_agents')}</p>
                  {children.map(child => (
                    <AgentNode
                      key={child.key}
                      agent={child}
                      settings={settings}
                      childrenMap={childrenMap}
                      parentDisabled={!enabled}
                      llmCatalog={llmCatalog}
                      translate={translate}
                      onToggle={onToggle}
                      onSettingsChange={onSettingsChange}
                      nested
                    />
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

const AgentSettingsPanel = forwardRef<AgentSettingsPanelHandle, AgentSettingsPanelProps>(({
  userId,
  serverScope = false,
  hideSaveButton = false,
}, ref) => {
  const { t } = useTranslation()
  const meta = useMeta()
  const llmCatalog = useLlmCatalog()
  const [settings, setSettings] = useState<AgentSettingsData | null>(null)

  const otherUserId = !serverScope && userId ? userId : 0
  const serverQuery = useSettingsGetServerAgents({ query: { enabled: serverScope } })
  const otherUserQuery = useSettingsGetOtherUserAgents(otherUserId, {
    query: { enabled: !serverScope && Boolean(userId) },
  })
  const ownQuery = useSettingsGetUserAgents({ query: { enabled: !serverScope && !userId } })
  const activeQuery = serverScope ? serverQuery : userId ? otherUserQuery : ownQuery

  useEffect(() => {
    if (activeQuery.data) setSettings(activeQuery.data as unknown as AgentSettingsData)
  }, [activeQuery.data])

  const saveServer = useSettingsUpdateServerAgents()
  const saveOtherUser = useSettingsUpdateOtherUserAgents()
  const saveOwn = useSettingsUpdateUserAgents()
  const saving = saveServer.isPending || saveOtherUser.isPending || saveOwn.isPending

  const save = async () => {
    if (!settings) return
    try {
      const body = settings as unknown as Parameters<typeof saveOwn.mutateAsync>[0]['data']
      const response = serverScope
        ? await saveServer.mutateAsync({ data: body })
        : userId
          ? await saveOtherUser.mutateAsync({ userId, data: body })
          : await saveOwn.mutateAsync({ data: body })
      setSettings(response as unknown as AgentSettingsData)
      triggerMetaRefetch()
      notify('success', t('settings.agents_saved'))
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || t('settings.agents_save_failed')
      notify('error', message, 'Agent settings')
      throw new Error(message, { cause: error })
    }
  }

  useImperativeHandle(ref, () => ({ save }))

  const agents = meta?.agents ?? []
  const childrenMap = useMemo(() => buildChildrenMap(agents), [agents])
  const mainAgents = useMemo(() => agents
    .filter(agent => MAIN_AGENT_KEYS.has(agent.key))
    .sort((a, b) => {
      if (a.key === 'portfolio_manager') return -1
      if (b.key === 'portfolio_manager') return 1
      return 0
    }), [agents])

  const updateEnabled = (agentKey: string, enabled: boolean) => {
    setSettings(current => {
      if (!current) return current
      const existing = current.agents[agentKey] ?? { enabled, settings: {} }
      return {
        ...current,
        agents: { ...current.agents, [agentKey]: { ...existing, enabled } },
      }
    })
  }

  const updateSettings = (agentKey: string, next: Record<string, unknown>) => {
    setSettings(current => {
      if (!current) return current
      const existing = current.agents[agentKey] ?? { enabled: true, settings: {} }
      return {
        ...current,
        agents: { ...current.agents, [agentKey]: { ...existing, settings: next } },
      }
    })
  }

  if (activeQuery.isPending) {
    return <div className="text-slate-500 text-xs font-semibold p-4">{t('common.loading')}</div>
  }

  if (activeQuery.error) {
    const detail = (activeQuery.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    return <AppAlert severity="error">{detail || 'Failed to load agent settings.'}</AppAlert>
  }

  if (agents.length === 0) {
    return <AppAlert severity="info">{t('settings.agents_empty')}</AppAlert>
  }

  if (!settings) {
    return <AppAlert severity="error">{t('settings.agents_load_failed')}</AppAlert>
  }

  const portfolioManagerEnabled = settings.agents.portfolio_manager?.enabled ?? true

  return (
    <div className="space-y-5 animate-in fade-in duration-150">
      <div className="flex justify-between items-center gap-4 bg-white/[0.01] border border-white/[0.04] p-3 rounded-2xl sticky top-0 z-10 backdrop-blur-sm">
        <div>
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
            {t(serverScope ? 'settings.server_agent_overrides' : 'settings.personal_agent_config')}
          </span>
          <p className="text-[9px] text-slate-600 mt-0.5">
            {t('settings.agent_config_hint')}
          </p>
        </div>
        {!hideSaveButton ? (
          <AppButton
            onClick={() => void save()}
            disabled={saving}
            startIcon={saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          >
            {t(saving ? 'settings.saving' : 'settings.save_agents')}
          </AppButton>
        ) : null}
      </div>

      <div className="text-[10px] text-slate-600 bg-white/[0.01] border border-white/[0.03] rounded-xl px-3 py-2 leading-relaxed">
        <span className="text-violet-400 font-bold">{t('settings.hierarchy_label')}</span>{' '}
        {t('settings.hierarchy_hint')}
      </div>

      <div className="space-y-4">
        {mainAgents.map(agent => (
          <AgentNode
            key={agent.key}
            agent={agent}
            settings={settings}
            childrenMap={childrenMap}
            parentDisabled={agent.key !== 'portfolio_manager' && !portfolioManagerEnabled}
            llmCatalog={llmCatalog}
            translate={t}
            onToggle={updateEnabled}
            onSettingsChange={updateSettings}
          />
        ))}
      </div>
    </div>
  )
})

AgentSettingsPanel.displayName = 'AgentSettingsPanel'

export default AgentSettingsPanel
