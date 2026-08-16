import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { RefreshCw, Save } from 'lucide-react'
import { useSystemSettingsGetServerTools, useSystemSettingsUpdateServerTools } from '../../api/generated/system-settings/system-settings'
import {
  useSettingsGetUserTools,
  useSettingsUpdateUserTools,
  useSettingsGetOtherUserTools,
  useSettingsUpdateOtherUserTools,
} from '../../api/generated/settings/settings'
import { useTranslation } from '../../contexts/LanguageContext'
import { useMeta } from '../../hooks/useMeta'
import type { ToolSettingFieldMeta } from '../../api/generated/model'
import { notify } from '../../utils/notify'
import AppSchemaForm, { legacyFieldsToSchema } from '../ui/AppSchemaForm'
import { AppAlert, AppButton, AppSwitch } from '../ui/AppPrimitives'

interface ToolSettingState {
  enabled: boolean
  settings: Record<string, unknown>
}

interface ToolSettings {
  tools: Record<string, ToolSettingState>
}

// Shapes come from the generated client. They used to be narrower hand-written
// mirrors with a cast, because `/api/meta` described its option items as
// free-form objects and its `type`/`scope` as bare strings.
type ToolSchemaField = ToolSettingFieldMeta

interface ToolSettingsPanelProps {
  userId?: number
  serverScope?: boolean
  hideSaveButton?: boolean
}

export interface ToolSettingsPanelHandle {
  save: () => Promise<void>
}

const ToolSettingsPanel = forwardRef<ToolSettingsPanelHandle, ToolSettingsPanelProps>(({
  userId,
  serverScope = false,
  hideSaveButton = false,
}, ref) => {
  const { t } = useTranslation()
  const meta = useMeta()
  const [settings, setSettings] = useState<ToolSettings | null>(null)

  const otherUserId = !serverScope && userId ? userId : 0
  const serverQuery = useSystemSettingsGetServerTools({ query: { enabled: serverScope } })
  const otherUserQuery = useSettingsGetOtherUserTools(otherUserId, {
    query: { enabled: !serverScope && Boolean(userId) },
  })
  const ownQuery = useSettingsGetUserTools({ query: { enabled: !serverScope && !userId } })
  const activeQuery = serverScope ? serverQuery : userId ? otherUserQuery : ownQuery

  useEffect(() => {
    if (activeQuery.data) setSettings(activeQuery.data as unknown as ToolSettings)
  }, [activeQuery.data])

  const saveServer = useSystemSettingsUpdateServerTools()
  const saveOtherUser = useSettingsUpdateOtherUserTools()
  const saveOwn = useSettingsUpdateUserTools()
  const saving = saveServer.isPending || saveOtherUser.isPending || saveOwn.isPending

  const save = useCallback(async () => {
    if (!settings) return
    try {
      const body = settings as unknown as Parameters<typeof saveOwn.mutateAsync>[0]['data']
      const response = serverScope
        ? await saveServer.mutateAsync({ data: body })
        : userId
          ? await saveOtherUser.mutateAsync({ userId, data: body })
          : await saveOwn.mutateAsync({ data: body })
      setSettings(response as unknown as ToolSettings)
      notify('success', t('settings.tools_saved'))
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || t('settings.tools_save_failed')
      notify('error', message, 'Tool settings')
      throw new Error(message, { cause: error })
    }
  }, [saveOtherUser, saveOwn, saveServer, serverScope, settings, t, userId])

  useImperativeHandle(ref, () => ({ save }), [save])

  const tools = meta?.tools ?? []
  const categories = useMemo(() => Array.from(new Set(tools.map(tool => tool.category))), [tools])

  const scopedFields = useCallback((fields: ToolSchemaField[]) => fields.filter(field => {
    if (serverScope) return field.scope === 'server' || field.scope === 'both'
    return field.scope === 'user' || field.scope === 'both' || field.scope === undefined
  }), [serverScope])

  const updateEnabled = (toolKey: string, enabled: boolean) => {
    setSettings(current => {
      if (!current) return current
      const existing = current.tools[toolKey] ?? { enabled, settings: {} }
      return {
        ...current,
        tools: { ...current.tools, [toolKey]: { ...existing, enabled } },
      }
    })
  }

  const updateToolSettings = (toolKey: string, next: Record<string, unknown>) => {
    setSettings(current => {
      if (!current) return current
      const existing = current.tools[toolKey] ?? { enabled: true, settings: {} }
      return {
        ...current,
        tools: { ...current.tools, [toolKey]: { ...existing, settings: next } },
      }
    })
  }

  const resetDefaults = (toolKey: string, fields: ToolSchemaField[]) => {
    const defaults = Object.fromEntries(fields.filter(field => field.default !== undefined).map(field => [field.key, field.default]))
    updateToolSettings(toolKey, defaults)
  }

  if (activeQuery.isPending) {
    return <div className="text-slate-500 text-xs font-semibold p-4">{t('common.loading')}</div>
  }

  if (activeQuery.error) {
    return <AppAlert severity="error">{t('settings.tools_load_failed')}</AppAlert>
  }

  if (tools.length === 0) {
    return <AppAlert severity="info">{t('settings.tools_empty')}</AppAlert>
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center gap-3 bg-white/[0.01] border border-white/[0.04] p-3 rounded-2xl">
        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
          {t(serverScope ? 'settings.server_tool_overrides' : 'settings.personal_tool_config')}
        </span>
        {!hideSaveButton ? (
          <AppButton
            onClick={() => void save()}
            disabled={saving}
            startIcon={saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
          >
            {t(saving ? 'settings.saving' : 'settings.save_tools')}
          </AppButton>
        ) : null}
      </div>

      {categories.map(category => {
        const categoryTools = tools.filter(tool => tool.category === category)
        return (
          <section key={category} className="space-y-4">
            <h4 className="text-xs font-bold text-violet-400 uppercase tracking-widest border-b border-white/[0.04] pb-2">
              {t(`tools.category.${category}`) || category.toUpperCase()}
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {categoryTools.map(tool => {
                const toolState = settings?.tools?.[tool.key] ?? { enabled: tool.default_enabled, settings: {} }
                const fields = scopedFields(tool.settings_schema ?? [])
                const { schema, uiSchema } = legacyFieldsToSchema(fields, t)
                return (
                  <article
                    key={tool.key}
                    className={`glass-panel rounded-2xl p-4 border transition-all ${toolState.enabled ? 'border-violet-500/10 bg-white/[0.01]' : 'border-white/[0.02] opacity-60'}`}
                  >
                    <div className="flex items-start justify-between gap-3 border-b border-white/[0.04] pb-3 mb-3">
                      <div>
                        <h5 className="text-xs font-bold text-white tracking-wide">{t(tool.label_key)}</h5>
                        <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">{t(tool.description_key)}</p>
                      </div>
                      <AppSwitch
                        checked={toolState.enabled}
                        onChange={enabled => updateEnabled(tool.key, enabled)}
                        name={`${tool.key}-enabled`}
                      />
                    </div>

                    {toolState.enabled && fields.length > 0 ? (
                      <div className="space-y-3">
                        <AppSchemaForm
                          schema={schema}
                          uiSchema={uiSchema}
                          formData={toolState.settings}
                          onChange={next => updateToolSettings(tool.key, next)}
                        />
                        <AppButton
                          variant="text"
                          size="small"
                          startIcon={<RefreshCw size={12} />}
                          onClick={() => resetDefaults(tool.key, fields)}
                        >
                          Reset defaults
                        </AppButton>
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
})

ToolSettingsPanel.displayName = 'ToolSettingsPanel'

export default ToolSettingsPanel
