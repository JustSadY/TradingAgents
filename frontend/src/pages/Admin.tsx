import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { Save, Trash2, Plus, UserCog, ShieldCheck, Globe, CheckCircle2, Key, Sliders } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../hooks/useAuth'
import Settings from './Settings'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import { useMeta } from '../hooks/useMeta'

interface UserRecord {
  id: number
  username: string
  email: string | null
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

const ALL_PAGE_KEYS = [
  'dashboard', 'analysis', 'chart', 'trading', 'portfolio',
  'watchlist', 'orders', 'performance', 'alerts', 'ab-testing', 'logs',
]

const PAGE_LABELS: Record<string, string> = {
  dashboard: 'Dashboard', analysis: 'Analysis', chart: 'Charts',
  trading: 'Simulation', portfolio: 'Portfolio', watchlist: 'Watchlist',
  orders: 'Orders', performance: 'Performance', alerts: 'Alerts',
  'ab-testing': 'A/B Testing', logs: 'Logs',
}

const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4">
      <h3 className="text-xs font-bold text-amber-400 uppercase tracking-widest border-b border-white/[0.04] pb-2.5">{title}</h3>
      {children}
    </div>
  )
}

type Tab = 'users' | 'permissions' | 'system' | 'api-keys' | 'user-settings'

export default function Admin() {
  const { t } = useTranslation()
  const { isOwner } = useAuth()
  const meta = useMeta()
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<UserRecord[]>([])
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [permissions, setPermissions] = useState<Record<string, boolean>>({})
  const [settingPermissions, setSettingPermissions] = useState<Record<string, boolean>>({})
  const [agentAccess, setAgentAccess] = useState<Record<string, boolean>>({})
  const [toolAccess, setToolAccess] = useState<Record<string, Record<string, boolean>>>({})
  const [permSaved, setPermSaved] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', email: '', role: 'user' })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [userKeyProviders, setUserKeyProviders] = useState<string[]>([])
  const [keySaved, setKeySaved] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [systemSettings, setSystemSettings] = useState<any>(null)
  const [sysSaved, setSysSaved] = useState(false)

  const loadUsers = useCallback(async () => {
    const r = await axios.get('/api/users')
    setUsers(r.data)
  }, [])

  const loadSystemSettings = useCallback(async () => {
    try {
      const r = await axios.get('/api/system-settings')
      setSystemSettings(r.data)
    } catch (err) {
      console.error('Failed to load system settings:', err)
    }
  }, [])

  useEffect(() => {
    loadUsers()
    loadSystemSettings()
  }, [loadUsers, loadSystemSettings])

  const loadUserPermissions = async (userId: number) => {
    const [pRes, sRes, agentRes, toolRes] = await Promise.all([
      axios.get(`/api/users/${userId}/permissions`),
      axios.get(`/api/users/${userId}/setting-permissions`),
      axios.get(`/api/users/${userId}/agent-access`),
      axios.get(`/api/users/${userId}/tool-access`),
    ])
    setPermissions(pRes.data.permissions)
    setSettingPermissions(sRes.data.permissions)
    setAgentAccess(agentRes.data)
    setToolAccess(toolRes.data)
    setSelectedUserId(userId)
  }

  const loadUserApiKeys = async (userId: number) => {
    setSelectedUserId(userId)
    const r = await axios.get(`/api/users/${userId}/api-keys`)
    setUserKeyProviders(r.data.providers)
  }

  const saveUserApiKey = async (userId: number, provider: string, apiKey: string) => {
    setKeyError(null)
    try {
      await axios.put(`/api/users/${userId}/api-keys`, { provider, api_key: apiKey })
      setKeySaved(true)
      setTimeout(() => setKeySaved(false), 2000)
      await loadUserApiKeys(userId)
    } catch (err: any) {
      setKeyError(err.response?.data?.detail || 'Key could not be saved')
    }
  }

  const deleteUserApiKey = async (userId: number, provider: string) => {
    setKeyError(null)
    try {
      await axios.delete(`/api/users/${userId}/api-keys/${provider}`)
      await loadUserApiKeys(userId)
    } catch (err: any) {
      setKeyError(err.response?.data?.detail || 'Key could not be deleted')
    }
  }

  const savePermissions = async () => {
    if (!selectedUserId) return
    await Promise.all([
      axios.put(`/api/users/${selectedUserId}/permissions`, { permissions }),
      axios.put(`/api/users/${selectedUserId}/setting-permissions`, { permissions: settingPermissions }),
      axios.put(`/api/users/${selectedUserId}/agent-access`, { agents: agentAccess }),
      axios.put(`/api/users/${selectedUserId}/tool-access`, { tools: toolAccess }),
    ])
    setPermSaved(true)
    setTimeout(() => setPermSaved(false), 2500)
  }

  const createUser = async () => {
    setCreateError(null)
    if (!newUser.username.trim() || !newUser.password.trim()) {
      setCreateError(t('admin.create_user_required'))
      return
    }
    setCreating(true)
    try {
      await axios.post('/api/users', {
        username: newUser.username.trim(),
        password: newUser.password.trim(),
        email: newUser.email.trim() || null,
        role: newUser.role,
      })
      setNewUser({ username: '', password: '', email: '', role: 'user' })
      await loadUsers()
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || t('admin.create_user_error'))
    } finally {
      setCreating(false)
    }
  }

  const toggleRole = async (u: UserRecord) => {
    const newRole = u.role === 'admin' ? 'user' : 'admin'
    await axios.put(`/api/users/${u.id}`, { role: newRole })
    setUsers(prev => prev.map(x => x.id === u.id ? { ...x, role: newRole } : x))
  }

  const toggleActive = async (u: UserRecord) => {
    await axios.put(`/api/users/${u.id}`, { is_active: !u.is_active })
    setUsers(prev => prev.map(x => x.id === u.id ? { ...x, is_active: !u.is_active } : x))
  }

  const deleteUser = async (id: number) => {
    if (!window.confirm(t('admin.delete_user_confirm'))) return
    await axios.delete(`/api/users/${id}`)
    setUsers(prev => prev.filter(u => u.id !== id))
    if (selectedUserId === id) setSelectedUserId(null)
  }

  const saveSystemSettings = async () => {
    if (!systemSettings) return
    try {
      await axios.put('/api/system-settings', systemSettings)
      setSysSaved(true)
      setTimeout(() => setSysSaved(false), 2000)
    } catch (err) {
      console.error('Failed to save system settings:', err)
    }
  }



  const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'users',       label: t('admin.tab_users') || 'User Management',       icon: <UserCog size={14} /> },
    { key: 'permissions', label: t('admin.tab_permissions') || 'Access Control',  icon: <ShieldCheck size={14} /> },
    { key: 'user-settings', label: t('admin.tab_user_settings') || 'User Preferences', icon: <Sliders size={14} /> },
    { key: 'system',      label: t('admin.tab_system') || 'Global Settings',       icon: <Globe size={14} /> },
    { key: 'api-keys',    label: t('admin.tab_apikeys') || 'User API Keys',        icon: <Key size={14} /> },
  ]

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('admin.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">Global platform configurations, user creation, permissions matrices, and credentials setups</p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 p-1 bg-slate-900/50 border border-white/[0.04] rounded-2xl w-fit">
        {TABS.map(tb => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer border border-transparent ${
              tab === tb.key
                ? 'bg-amber-500/10 text-amber-300 border-amber-500/20 active-nav-glow'
                : 'text-slate-500 hover:text-white'
            }`}
          >
            {tb.icon} {tb.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="space-y-6 animate-in fade-in duration-200">
        {tab === 'users' && (
          <>
            <Section title={t('admin.section_create_user')}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <input
                  className={Input}
                  placeholder={t('admin.username_placeholder')}
                  value={newUser.username}
                  onChange={e => setNewUser(f => ({ ...f, username: e.target.value }))}
                />
                <input
                  className={Input}
                  type="password"
                  placeholder={t('admin.password_placeholder')}
                  value={newUser.password}
                  onChange={e => setNewUser(f => ({ ...f, password: e.target.value }))}
                  autoComplete="new-password"
                />
                <input
                  className={Input}
                  type="email"
                  placeholder={t('admin.email_placeholder')}
                  value={newUser.email}
                  onChange={e => setNewUser(f => ({ ...f, email: e.target.value }))}
                />
                {isOwner ? (
                  <select
                    className={Input}
                    value={newUser.role}
                    onChange={e => setNewUser(f => ({ ...f, role: e.target.value }))}
                  >
                    <option value="user">{t('admin.role_user')}</option>
                    <option value="admin">{t('admin.role_admin')}</option>
                  </select>
                ) : (
                  <div className="flex items-center bg-slate-900/60 border border-white/[0.08] text-slate-500 rounded-xl px-3 py-2 text-xs w-full select-none font-semibold">
                    {t('admin.default_role_label')}: {t('admin.role_user')}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3 pt-2">
                <button
                  onClick={createUser}
                  disabled={creating}
                  className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer"
                >
                  <Plus size={13} /> {t('admin.create_user_button')}
                </button>
                {createError && <span className="text-rose-400 text-xs font-semibold">{createError}</span>}
              </div>
            </Section>

            <Section title={t('admin.section_user_list')}>
              {users.length === 0 ? (
                <p className="text-slate-600 text-xs">{t('admin.no_users')}</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-slate-300 min-w-[500px]">
                    <thead>
                      <tr className="text-left text-slate-500 text-[10px] uppercase tracking-wider border-b border-white/[0.04] bg-white/[0.01]">
                        <th className="px-3 py-2 pr-4 font-bold">{t('admin.col_username')}</th>
                        <th className="px-3 py-2 pr-4 font-bold">{t('admin.col_email')}</th>
                        <th className="px-3 py-2 pr-4 font-bold">{t('admin.col_role')}</th>
                        <th className="px-3 py-2 pr-4 font-bold">{t('admin.col_active')}</th>
                        <th className="px-3 py-2 pr-4 font-bold">{t('admin.col_created')}</th>
                        <th className="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.02]">
                      {users.map(u => (
                        <tr key={u.id} className="group hover:bg-white/[0.01]">
                          <td className="py-2.5 px-3 pr-4">
                            <div className="flex items-center gap-2">
                              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white text-[10px] font-bold shrink-0 shadow shadow-violet-500/10">
                                {u.username.charAt(0).toUpperCase()}
                              </div>
                              <span className="text-white font-semibold">{u.username}</span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 pr-4 text-slate-400 font-semibold">{u.email || '—'}</td>
                          <td className="py-2.5 px-3 pr-4">
                            {u.role === 'owner' ? (
                              <span className="text-[9px] px-2 py-0.5 rounded-full border bg-amber-500/10 text-amber-300 border-amber-500/20 font-bold uppercase tracking-wide select-none">
                                {t('admin.role_owner')}
                              </span>
                            ) : isOwner ? (
                              <button
                                onClick={() => toggleRole(u)}
                                className={`text-[9px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wide transition-colors cursor-pointer ${
                                  u.role === 'admin'
                                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                                    : 'bg-violet-500/10 text-violet-400 border-violet-500/20 hover:bg-violet-500/20'
                                }`}
                              >
                                {t(`admin.role_${u.role}`)}
                              </button>
                            ) : (
                              <span className={`text-[9px] px-2 py-0.5 rounded-full border font-bold uppercase tracking-wide select-none ${
                                u.role === 'admin'
                                  ? 'bg-amber-500/5 text-amber-400/60 border-amber-500/10'
                                  : 'bg-violet-500/5 text-violet-400/60 border-violet-500/10'
                              }`}>
                                {t(`admin.role_${u.role}`)}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 pr-4">
                            {u.role === 'owner' ? (
                              <div className="relative inline-flex h-4 w-7 items-center rounded-full bg-emerald-600/30 cursor-not-allowed select-none">
                                <span className="inline-block h-3 w-3 transform rounded-full bg-white/55 translate-x-3.5" />
                              </div>
                            ) : (
                              <button
                                onClick={() => toggleActive(u)}
                                className={`relative inline-flex h-4.5 w-8 items-center rounded-full transition-colors cursor-pointer ${u.is_active ? 'bg-emerald-600' : 'bg-slate-700'}`}
                              >
                                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${u.is_active ? 'translate-x-4' : 'translate-x-0.5'}`} />
                              </button>
                            )}
                          </td>
                          <td className="py-2.5 px-3 pr-4 text-slate-500 font-mono text-[10px]">
                            {new Date(u.created_at).toLocaleDateString()}
                          </td>
                          <td className="py-2.5 px-3">
                            {u.role !== 'owner' && (
                              <button
                                onClick={() => deleteUser(u.id)}
                                className="text-slate-500 hover:text-rose-400 transition-colors opacity-0 group-hover:opacity-100 cursor-pointer"
                                title={t('admin.delete_user')}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>
          </>
        )}        {tab === 'permissions' && (
          <div className="space-y-6">
            <Section title={t('admin.section_page_permissions')}>
              <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
                <select
                  className={`${Input} sm:max-w-xs`}
                  value={selectedUserId ?? ''}
                  onChange={e => {
                    const id = parseInt(e.target.value)
                    if (!isNaN(id)) loadUserPermissions(id)
                  }}
                >
                  <option value="">{t('admin.select_user')}</option>
                  {users.filter(u => u.role === 'user').map(u => (
                    <option key={u.id} value={u.id}>{u.username}</option>
                  ))}
                </select>
                {selectedUserId && (
                  <button
                    onClick={savePermissions}
                    className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer"
                  >
                    {permSaved ? <CheckCircle2 size={13} className="text-emerald-300 animate-pulse" /> : <Save size={13} />}
                    {permSaved ? t('admin.saved') : t('admin.save_permissions')}
                  </button>
                )}
              </div>

              {selectedUserId && (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
                    {ALL_PAGE_KEYS.map(key => (
                      <label key={key} className="flex items-center gap-2.5 text-xs font-semibold text-slate-300 cursor-pointer bg-slate-900/40 hover:bg-slate-900/80 rounded-xl px-3 py-2 border border-white/[0.03] transition-colors select-none">
                        <input
                          type="checkbox"
                          className="accent-violet-600 w-4 h-4 rounded cursor-pointer"
                          checked={permissions[key] ?? false}
                          onChange={e => setPermissions(prev => ({ ...prev, [key]: e.target.checked }))}
                        />
                        {PAGE_LABELS[key] || key}
                      </label>
                    ))}
                  </div>

                  <div className="border-t border-white/[0.04] mt-5 pt-4 space-y-3">
                    <h4 className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">
                      {t('admin.section_settings_permissions') || 'Settings Edit Permissions'}
                    </h4>
                    <p className="text-[10px] text-slate-500 font-semibold mb-1">Select which settings tabs this user is permitted to edit:</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {[
                        { key: 'general',  label: t('settings.general') || 'Preferences' },
                        { key: 'llm',      label: t('settings.llm_settings') || 'AI Engine' },
                        { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety' },
                        { key: 'webhooks', label: t('settings.section_notifications') || 'Personal Webhooks' },
                        { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler' },
                        { key: 'presets',  label: t('settings.section_presets') || 'Configuration Templates' },
                      ].map(s => (
                        <label key={s.key} className="flex items-center gap-2.5 text-xs font-semibold text-slate-300 cursor-pointer bg-slate-900/40 hover:bg-slate-900/80 rounded-xl px-3 py-2 border border-white/[0.03] transition-colors select-none">
                          <input
                            type="checkbox"
                            className="accent-amber-500 w-4 h-4 rounded cursor-pointer"
                            checked={settingPermissions[s.key] ?? false}
                            onChange={e => setSettingPermissions(prev => ({ ...prev, [s.key]: e.target.checked }))}
                          />
                          {s.label}
                        </label>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </Section>

            {selectedUserId && (
              <>
                <Section title={t('admin.section_agent_access') || 'Agent Analyst Permissions'}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
                    {meta?.analysts?.map(analyst => (
                      <label key={analyst.key} className="flex items-center gap-3 text-xs font-semibold text-slate-350 cursor-pointer bg-slate-900/40 hover:bg-slate-900/80 rounded-xl px-3 py-2.5 border border-white/[0.03] transition-colors select-none">
                        <input
                          type="checkbox"
                          className="accent-violet-600 w-4 h-4 rounded cursor-pointer shrink-0"
                          checked={agentAccess[analyst.key] ?? analyst.default}
                          onChange={e => setAgentAccess(prev => ({ ...prev, [analyst.key]: e.target.checked }))}
                        />
                        <div className="space-y-0.5">
                          <div className="text-slate-250 font-bold">{analyst.label || analyst.key}</div>
                          <div className="text-[10px] text-slate-500 font-normal leading-tight">{analyst.description}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </Section>

                <Section title={t('admin.section_tool_access') || 'Tool Access Control Matrix'}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-slate-300 min-w-[500px]">
                      <thead>
                        <tr className="text-left text-slate-500 text-[10px] uppercase tracking-wider border-b border-white/[0.04] bg-white/[0.01]">
                          <th className="px-3 py-2 pr-4 font-bold text-slate-450">Tool</th>
                          <th className="px-3 py-2 text-center font-bold text-slate-450">View Settings</th>
                          <th className="px-3 py-2 text-center font-bold text-slate-450">Use in Run</th>
                          <th className="px-3 py-2 text-center font-bold text-slate-450">Edit Settings</th>
                          <th className="px-3 py-2 text-center font-bold text-slate-450">Enable/Disable</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.02]">
                        {meta?.tools?.map(tool => {
                          const toolState = toolAccess[tool.key] || {
                            can_view: true,
                            can_use: true,
                            can_edit: false,
                            can_enable: false,
                          }

                          const handleToggle = (permKey: string, val: boolean) => {
                            setToolAccess(prev => ({
                              ...prev,
                              [tool.key]: {
                                ...toolState,
                                [permKey]: val,
                              }
                            }))
                          }

                          return (
                            <tr key={tool.key} className="hover:bg-white/[0.01]">
                              <td className="py-2.5 px-3 pr-4">
                                <div className="font-semibold text-slate-200">{t(tool.label_key)}</div>
                                <div className="text-[10px] text-slate-500 font-normal leading-relaxed">{t(tool.description_key)}</div>
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <input
                                  type="checkbox"
                                  className="accent-violet-600 w-4 h-4 rounded cursor-pointer mx-auto"
                                  checked={toolState.can_view ?? true}
                                  onChange={e => handleToggle('can_view', e.target.checked)}
                                />
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <input
                                  type="checkbox"
                                  className="accent-violet-600 w-4 h-4 rounded cursor-pointer mx-auto"
                                  checked={toolState.can_use ?? true}
                                  onChange={e => handleToggle('can_use', e.target.checked)}
                                />
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <input
                                  type="checkbox"
                                  className="accent-violet-600 w-4 h-4 rounded cursor-pointer mx-auto"
                                  checked={toolState.can_edit ?? false}
                                  onChange={e => handleToggle('can_edit', e.target.checked)}
                                />
                              </td>
                              <td className="py-2.5 px-3 text-center">
                                <input
                                  type="checkbox"
                                  className="accent-violet-600 w-4 h-4 rounded cursor-pointer mx-auto"
                                  checked={toolState.can_enable ?? false}
                                  onChange={e => handleToggle('can_enable', e.target.checked)}
                                />
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </Section>
              </>
            )}
          </div>
        )}

        {tab === 'system' && (
          <div className="space-y-6">
            <ToolSettingsPanel serverScope={true} />
            
            <Section title={t('settings.section_advanced') || 'Engine Core Settings'}>
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs text-slate-400">Global server-wide engine configuration affecting all users</p>
                <button
                  onClick={saveSystemSettings}
                  className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer"
                >
                  {sysSaved ? <CheckCircle2 size={13} className="text-emerald-300 animate-pulse" /> : <Save size={13} />}
                  {sysSaved ? t('admin.saved') : 'Save'}
                </button>
              </div>

              {systemSettings && (
                <div className="space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Trading Mode</span>
                    <div className="flex-1 sm:max-w-xs w-full">
                      <select
                        className={Input}
                        value={systemSettings.trading_mode || 'simulation'}
                        onChange={e => setSystemSettings({ ...systemSettings, trading_mode: e.target.value })}
                      >
                        {meta?.trading_modes?.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Active Broker</span>
                    <div className="flex-1 sm:max-w-xs w-full">
                      <select
                        className={Input}
                        value={systemSettings.active_broker || 'simulation'}
                        onChange={e => setSystemSettings({ ...systemSettings, active_broker: e.target.value })}
                      >
                        {meta?.brokers?.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Active Data Vendor</span>
                    <div className="flex-1 sm:max-w-xs w-full">
                      <select
                        className={Input}
                        value={systemSettings.active_data_vendor || 'yfinance'}
                        onChange={e => setSystemSettings({ ...systemSettings, active_data_vendor: e.target.value })}
                      >
                        {meta?.data_vendors?.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                      </select>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Checkpoint Enabled</span>
                    <div className="flex-1 sm:max-w-xs w-full">
                      <input
                        type="checkbox"
                        className="w-5 h-5 accent-violet-600 rounded cursor-pointer"
                        checked={systemSettings.checkpoint_enabled || false}
                        onChange={e => setSystemSettings({ ...systemSettings, checkpoint_enabled: e.target.checked })}
                      />
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Include Historical Analyses</span>
                    <div className="flex-1 sm:max-w-xs w-full">
                      <input
                        type="checkbox"
                        className="w-4 h-4 accent-violet-600 rounded cursor-pointer"
                        checked={systemSettings.include_historical_analyses || false}
                        onChange={e => setSystemSettings({ ...systemSettings, include_historical_analyses: e.target.checked })}
                      />
                    </div>
                  </div>

                  {systemSettings.include_historical_analyses && (
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3 pl-6">
                      <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">Historical Analyses Limit</span>
                      <div className="flex-1 sm:max-w-xs w-full">
                        <input
                          type="number"
                          min="1"
                          max="50"
                          className={`${Input} w-32 py-1 font-mono`}
                          value={systemSettings.historical_analyses_limit || 5}
                          onChange={e => setSystemSettings({ ...systemSettings, historical_analyses_limit: parseInt(e.target.value) || 5 })}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Section>
          </div>
        )}

        {tab === 'api-keys' && (
          <Section title={t('admin.tab_apikeys') || 'User API Keys'}>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <select
                className={`${Input} sm:max-w-xs`}
                value={selectedUserId ?? ''}
                onChange={e => {
                  const id = parseInt(e.target.value)
                  if (!isNaN(id)) loadUserApiKeys(id)
                  else setSelectedUserId(null)
                }}
              >
                <option value="">{t('admin.select_user')}</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.username} ({t(`admin.role_${u.role}`)})</option>
                ))}
              </select>
              {keySaved && <span className="text-emerald-400 text-xs font-semibold">✓ Key saved successfully</span>}
              {keyError && <span className="text-rose-400 text-xs font-semibold">{keyError}</span>}
            </div>

            {selectedUserId && (
              <div className="space-y-4 mt-4">
                <p className="text-[10px] text-slate-500 font-semibold pb-1 border-b border-white/[0.04]">
                  Admins cannot see existing API key characters, but can define/set or delete them.
                </p>
                <div className="space-y-3 bg-slate-900/40 border border-white/[0.04] p-4 rounded-2xl">
                  {[
                    { key: 'openai',       label: 'OpenAI' },
                    { key: 'anthropic',    label: 'Anthropic (Claude)' },
                    { key: 'google',       label: 'Google (Gemini)' },
                    { key: 'xai',          label: 'xAI (Grok)' },
                    { key: 'deepseek',     label: 'DeepSeek' },
                    { key: 'qwen',         label: 'Qwen (Global)' },
                    { key: 'glm',          label: 'GLM / Z.AI' },
                    { key: 'minimax',      label: 'MiniMax' },
                    { key: 'ollama',       label: 'Ollama (Local)' },
                    { key: 'nvidia',       label: 'NVIDIA NIM' },
                    { key: 'litellm',      label: 'LiteLLM Proxy' },
                    { key: 'azure',        label: 'Azure OpenAI' },
                  ].map(p => {
                    const hasKey = userKeyProviders.includes(p.key)
                    return (
                      <AdminApiKeyRow
                        key={p.key}
                        providerKey={p.key}
                        label={p.label}
                        hasKey={hasKey}
                        onSave={async (prov, val) => saveUserApiKey(selectedUserId, prov, val)}
                        onDelete={async (prov) => deleteUserApiKey(selectedUserId, prov)}
                      />
                    )
                  })}
                </div>
              </div>
            )}
          </Section>
        )}

        {tab === 'user-settings' && (
          <Section title={t('admin.tab_user_settings') || 'User Preferences'}>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center pb-2">
              <select
                className={`${Input} sm:max-w-xs`}
                value={selectedUserId ?? ''}
                onChange={e => {
                  const id = parseInt(e.target.value)
                  if (!isNaN(id)) setSelectedUserId(id)
                  else setSelectedUserId(null)
                }}
              >
                <option value="">{t('admin.select_user')}</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.username} ({t(`admin.role_${u.role}`)})</option>
                ))}
              </select>
            </div>

            {selectedUserId && (
              <div className="border-t border-white/[0.04] pt-4 mt-4">
                <Settings userId={selectedUserId} />
              </div>
            )}
          </Section>
        )}
      </div>
    </div>
  )
}

function AdminApiKeyRow({ providerKey, label, hasKey, onSave, onDelete }: {
  providerKey: string
  label: string
  hasKey: boolean
  onSave: (provider: string, key: string) => Promise<void>
  onDelete: (provider: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [show, setShow] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    if (!value.trim()) return
    setSaving(true)
    try {
      await onSave(providerKey, value.trim())
      setValue('')
      setEditing(false)
      setShow(false)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    await onDelete(providerKey)
  }

  return (
    <div className="flex flex-col gap-2 border-b border-white/[0.02] pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-300 font-semibold">{label}</span>
          {hasKey && (
            <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full px-2 py-0.5 font-bold uppercase tracking-wider">
              Configured
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasKey && (
            <button
              onClick={handleDelete}
              className="text-slate-500 hover:text-rose-400 transition-colors p-1 hover:bg-white/5 rounded cursor-pointer animate-in fade-in"
              title="Delete Key"
            >
              <Trash2 size={13} />
            </button>
          )}
          <button
            onClick={() => setEditing(e => !e)}
            className="text-[10px] bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white px-2.5 py-1 rounded-lg transition-colors font-bold cursor-pointer"
          >
            {editing ? 'Cancel' : hasKey ? 'Update Key' : 'Add Key'}
          </button>
        </div>
      </div>
      {editing && (
        <div className="flex gap-2 mt-1 animate-in slide-in-from-top-1 duration-150">
          <div className="relative flex-1">
            <input
              className="w-full glass-input rounded-xl px-3 py-1.5 text-xs outline-none font-mono"
              type={show ? 'text' : 'password'}
              placeholder="Enter API key"
              value={value}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSave()}
              autoFocus
            />
            <button
              type="button"
              onClick={() => setShow(s => !s)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-350 text-[10px] font-bold select-none cursor-pointer"
            >
              {show ? 'Hide' : 'Show'}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition whitespace-nowrap cursor-pointer"
          >
            <Save size={13} /> Save
          </button>
        </div>
      )}
    </div>
  )
}
