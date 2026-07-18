import { useEffect, useState, forwardRef, useImperativeHandle, useRef } from 'react'
import axios from 'axios'
import { Save, RefreshCw, AlertCircle } from 'lucide-react'
import { useTranslation } from '../../contexts/LanguageContext'
import { useMeta } from '../../hooks/useMeta'

interface ToolSettingState {
  enabled: boolean
  settings: Record<string, any>
}

interface ToolSettings {
  tools: Record<string, ToolSettingState>
}

interface ToolSettingsPanelProps {
  userId?: number
  serverScope?: boolean
  hideSaveButton?: boolean
}

export interface ToolSettingsPanelHandle {
  save: () => Promise<void>
}

const InputClass = 'w-full glass-input rounded-xl px-3 py-2 text-xs outline-none text-slate-300 placeholder-slate-600'

const ToolSettingsPanel = forwardRef<ToolSettingsPanelHandle, ToolSettingsPanelProps>(({ userId, serverScope = false, hideSaveButton = false }, ref) => {
  const { t } = useTranslation()
  const meta = useMeta()
  const [settings, setSettings] = useState<ToolSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const toolTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => { return () => { if (toolTimeoutRef.current) clearTimeout(toolTimeoutRef.current) } }, [])

  const apiPath = serverScope
    ? '/api/system-settings/tools'
    : userId
    ? `/api/settings/users/${userId}/tools`
    : '/api/settings/tools'

  const fetchSettings = async () => {
    setLoading(true)
    setSaveError(null)
    try {
      const res = await axios.get(apiPath)
      setSettings(res.data)
    } catch (err: any) {
      setSaveError(err.response?.data?.detail || 'Failed to load tool settings.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSettings()
  }, [apiPath, meta])

  useImperativeHandle(ref, () => ({
    save
  }))

  const save = async () => {
    if (!settings) return
    setSaving(true)
    setSaveSuccess(false)
    setSaveError(null)
    try {
      const res = await axios.put(apiPath, settings)
      setSettings(res.data)
      setSaveSuccess(true)
      if (toolTimeoutRef.current) clearTimeout(toolTimeoutRef.current)
      toolTimeoutRef.current = setTimeout(() => setSaveSuccess(false), 2000)
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to save tool settings.'
      setSaveError(msg)
      throw new Error(msg, { cause: err })
    } finally {
      setSaving(false)
    }
  }

  const resetField = (toolKey: string, fieldKey: string) => {
    if (!settings) return
    const toolMeta = meta?.tools?.find(t => t.key === toolKey)
    const fieldMeta = toolMeta?.settings_schema?.find(f => f.key === fieldKey)
    if (!fieldMeta) return

    setSettings(prev => {
      if (!prev) return prev
      const tools = { ...prev.tools }
      const toolState = { ...tools[toolKey] }
      const settingsMap = { ...toolState.settings }
      settingsMap[fieldKey] = fieldMeta.default
      toolState.settings = settingsMap
      tools[toolKey] = toolState
      return { ...prev, tools }
    })
  }

  const updateToolEnabled = (toolKey: string, enabled: boolean) => {
    setSettings(prev => {
      if (!prev) return prev
      const tools = { ...prev.tools }
      const toolState = { ...tools[toolKey], enabled }
      tools[toolKey] = toolState
      return { ...prev, tools }
    })
  }

  const updateSettingField = (toolKey: string, fieldKey: string, value: any) => {
    setSettings(prev => {
      if (!prev) return prev
      const tools = { ...prev.tools }
      const toolState = { ...tools[toolKey] }
      const settingsMap = { ...toolState.settings, [fieldKey]: value }
      toolState.settings = settingsMap
      tools[toolKey] = toolState
      return { ...prev, tools }
    })
  }

  if (loading) {
    return <div className="text-slate-500 text-xs font-semibold p-4">{t('common.loading') || 'Loading...'}</div>
  }

  const tools = meta?.tools || []
  if (tools.length === 0) {
    return (
      <div className="flex items-center gap-2 p-4 text-xs font-semibold text-slate-500 bg-white/[0.02] rounded-xl border border-white/[0.04]">
        <AlertCircle size={14} />
        <span>No tool configurations found in meta database.</span>
      </div>
    )
  }

  const filterFields = (fields: any[]) => {
    return fields.filter(field => {
      if (serverScope) {
        return field.scope === 'server' || field.scope === 'both'
      } else {
        return field.scope === 'user' || field.scope === 'both'
      }
    })
  }

  const categories = Array.from(new Set(tools.map(t => t.category)))

  return (
    <div className="space-y-6">
      {/* Save bar */}
      <div className="flex justify-between items-center bg-white/[0.01] border border-white/[0.04] p-3 rounded-2xl">
        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
          {serverScope ? 'Global Server Tool Overrides' : 'Personal Agent Tool Configuration'}
        </span>
        <div className="flex items-center gap-3">
          {saveError && <span className="text-rose-400 text-xs font-semibold">{saveError}</span>}
          {saveSuccess && <span className="text-emerald-400 text-xs font-semibold">Saved successfully!</span>}
          {!hideSaveButton && (
            <button
              onClick={save}
              disabled={saving}
              className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-4 py-2 text-xs font-semibold transition-all shadow-md shadow-violet-500/10 cursor-pointer disabled:opacity-50"
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save Tools'}
            </button>
          )}
        </div>
      </div>

      {/* Categories */}
      {categories.map(cat => {
        const catTools = tools.filter(t => t.category === cat)
        if (catTools.length === 0) return null

        return (
          <div key={cat} className="space-y-4">
            <h4 className="text-xs font-bold text-violet-400 uppercase tracking-widest border-b border-white/[0.04] pb-2">
              {t(`tools.category.${cat}`) || cat.toUpperCase()}
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {catTools.map(tool => {
                const toolState = settings?.tools?.[tool.key] || { enabled: tool.default_enabled, settings: {} }
                const isEnabled = toolState.enabled
                const schemaFields = filterFields(tool.settings_schema || [])

                return (
                  <div
                    key={tool.key}
                    className={`glass-panel rounded-2xl p-4 flex flex-col justify-between border transition-all ${
                      isEnabled ? 'border-violet-500/10 bg-white/[0.01]' : 'border-white/[0.02] opacity-60'
                    }`}
                  >
                    <div>
                      {/* Title & Enable switch */}
                      <div className="flex items-center justify-between border-b border-white/[0.02] pb-3 mb-3">
                        <div className="pr-2">
                          <h5 className="text-xs font-bold text-white tracking-wide">{t(tool.label_key)}</h5>
                          <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">{t(tool.description_key)}</p>
                        </div>
                        <button
                          onClick={() => updateToolEnabled(tool.key, !isEnabled)}
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

                      {/* Fields */}
                      {isEnabled && schemaFields.length > 0 && (
                        <div className="space-y-3.5">
                          {schemaFields.map(field => {
                            const val = toolState.settings[field.key] !== undefined ? toolState.settings[field.key] : field.default
                            const fieldLabel = t(field.label_key)

                            return (
                              <div key={field.key} className="space-y-1">
                                <div className="flex justify-between items-center">
                                  <label className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                                    {fieldLabel}
                                  </label>
                                  {field.default !== undefined && val !== field.default && (
                                    <button
                                      onClick={() => resetField(tool.key, field.key)}
                                      className="text-[9px] text-violet-400 hover:text-violet-300 font-bold transition flex items-center gap-0.5 cursor-pointer"
                                      title="Reset to default value"
                                    >
                                      <RefreshCw size={8} /> Reset
                                    </button>
                                  )}
                                </div>

                                {/* Field input mapping */}
                                {field.type === 'boolean' && (
                                  <label className="flex items-center gap-2 cursor-pointer py-1.5">
                                    <input
                                      type="checkbox"
                                      checked={!!val}
                                      onChange={e => updateSettingField(tool.key, field.key, e.target.checked)}
                                      className="w-4 h-4 accent-violet-600 rounded cursor-pointer"
                                    />
                                    <span className="text-xs text-slate-400 font-medium">Enabled</span>
                                  </label>
                                )}

                                {field.type === 'number' && (
                                  <div className="flex items-center gap-3">
                                    <input
                                      type="number"
                                      min={field.min}
                                      max={field.max}
                                      step={field.step || 1}
                                      className={`${InputClass} w-24`}
                                      value={val ?? ''}
                                      onChange={e => updateSettingField(tool.key, field.key, Number.parseFloat(e.target.value))}
                                    />
                                    {field.min !== undefined && field.max !== undefined && (
                                      <input
                                        type="range"
                                        min={field.min}
                                        max={field.max}
                                        step={field.step || 1}
                                        className="flex-1 accent-violet-500 h-1.5 rounded-lg bg-white/[0.04] cursor-pointer"
                                        value={val ?? field.default ?? field.min}
                                        onChange={e => updateSettingField(tool.key, field.key, Number.parseFloat(e.target.value))}
                                      />
                                    )}
                                  </div>
                                )}

                                {field.type === 'string' && (
                                  <input
                                    type="text"
                                    className={InputClass}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(tool.key, field.key, e.target.value)}
                                  />
                                )}

                                {field.type === 'textarea' && (
                                  <textarea
                                    className={`${InputClass} h-16 resize-none`}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(tool.key, field.key, e.target.value)}
                                  />
                                )}

                                {field.type === 'secret' && (
                                  <input
                                    type="password"
                                    className={InputClass}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(tool.key, field.key, e.target.value)}
                                    placeholder="••••••••••••"
                                  />
                                )}

                                {field.type === 'select' && (
                                  <select
                                    className={InputClass}
                                    value={val ?? ''}
                                    onChange={e => updateSettingField(tool.key, field.key, e.target.value)}
                                  >
                                    {field.options?.map((opt: any) => (
                                      <option key={opt.value} value={opt.value}>
                                        {t(opt.label_key) || opt.value}
                                      </option>
                                    ))}
                                  </select>
                                )}

                                {field.type === 'string_list' && (
                                  <input
                                    type="text"
                                    className={InputClass}
                                    value={Array.isArray(val) ? val.join(', ') : val ?? ''}
                                    placeholder="e.g. wallstreetbets, stocks"
                                    onChange={e =>
                                      updateSettingField(
                                        tool.key,
                                        field.key,
                                        e.target.value.split(',').map(x => x.trim()).filter(Boolean)
                                      )
                                    }
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
})

export default ToolSettingsPanel
