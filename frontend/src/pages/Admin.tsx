import { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { Save, Trash2, Plus, UserCog, ShieldCheck, Globe, CheckCircle2, Key, Sliders } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../hooks/useAuth'
import Settings from './Settings'

interface UserRecord {
  id: number
  username: string
  email: string | null
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

interface SystemSettings {
  searxng_url: string | null
  reddit_client_id: string | null
  reddit_client_secret: string | null
  reddit_user_agent: string | null
  alpha_vantage_api_key: string | null
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

const Input = "bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm w-full transition"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 space-y-3">
      <h3 className="text-sm font-semibold text-amber-400 uppercase tracking-wider mb-1">{title}</h3>
      {children}
    </div>
  )
}

type Tab = 'users' | 'permissions' | 'system' | 'api-keys' | 'user-settings'

export default function Admin() {
  const { t } = useTranslation()
  const { isOwner } = useAuth()
  const [tab, setTab] = useState<Tab>('users')
  const [users, setUsers] = useState<UserRecord[]>([])
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [permissions, setPermissions] = useState<Record<string, boolean>>({})
  const [settingPermissions, setSettingPermissions] = useState<Record<string, boolean>>({})
  const [permSaved, setPermSaved] = useState(false)
  const [sysSettings, setSysSettings] = useState<SystemSettings | null>(null)
  const [sysSaved, setSysSaved] = useState(false)
  const [sysError, setSysError] = useState<string | null>(null)
  const [newUser, setNewUser] = useState({ username: '', password: '', email: '', role: 'user' })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [userKeyProviders, setUserKeyProviders] = useState<string[]>([])
  const [keySaved, setKeySaved] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)

  const loadUsers = useCallback(async () => {
    const r = await axios.get('/api/users')
    setUsers(r.data)
  }, [])

  const loadSystemSettings = useCallback(async () => {
    const r = await axios.get('/api/system-settings')
    setSysSettings(r.data)
  }, [])

  useEffect(() => {
    loadUsers()
    loadSystemSettings()
  }, [loadUsers, loadSystemSettings])

  const loadUserPermissions = async (userId: number) => {
    const [pRes, sRes] = await Promise.all([
      axios.get(`/api/users/${userId}/permissions`),
      axios.get(`/api/users/${userId}/setting-permissions`),
    ])
    setPermissions(pRes.data.permissions)
    setSettingPermissions(sRes.data.permissions)
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
    if (!sysSettings) return
    setSysError(null)
    try {
      await axios.put('/api/system-settings', sysSettings)
      setSysSaved(true)
      setTimeout(() => setSysSaved(false), 2500)
    } catch (err: any) {
      setSysError(err.response?.data?.detail || t('admin.save_error'))
    }
  }

  const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'users',       label: t('admin.tab_users') || 'User Management',       icon: <UserCog size={15} /> },
    { key: 'permissions', label: t('admin.tab_permissions') || 'Access Control',  icon: <ShieldCheck size={15} /> },
    { key: 'user-settings', label: t('admin.tab_user_settings') || 'User Preferences', icon: <Sliders size={15} /> },
    { key: 'system',      label: t('admin.tab_system') || 'Global Settings',       icon: <Globe size={15} /> },
    { key: 'api-keys',    label: t('admin.tab_apikeys') || 'User API Keys',        icon: <Key size={15} /> },
  ]

  return (
    <div className="p-4 md:p-6 space-y-4 max-w-4xl">
      <h2 className="text-xl font-bold text-white tracking-tight">{t('admin.title')}</h2>

      {}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-2xl p-1 w-fit">
        {TABS.map(tb => (
          <button
            key={tb.key}
            onClick={() => setTab(tb.key)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-medium transition-all ${
              tab === tb.key
                ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {tb.icon} {tb.label}
          </button>
        ))}
      </div>

      {}
      {tab === 'users' && (
        <>
          <Section title={t('admin.section_create_user')}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
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
                <div className="flex items-center bg-gray-800/40 border border-gray-700 text-gray-500 rounded-xl px-3 py-1.5 text-sm w-full select-none">
                  {t('admin.default_role_label')}: {t('admin.role_user')}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={createUser}
                disabled={creating}
                className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-xl transition"
              >
                <Plus size={14} /> {t('admin.create_user_button')}
              </button>
              {createError && <span className="text-red-400 text-sm">{createError}</span>}
            </div>
          </Section>

          <Section title={t('admin.section_user_list')}>
            {users.length === 0 ? (
              <p className="text-gray-600 text-sm">{t('admin.no_users')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-gray-500 text-xs uppercase tracking-wider border-b border-gray-800">
                      <th className="pb-2 pr-4">{t('admin.col_username')}</th>
                      <th className="pb-2 pr-4">{t('admin.col_email')}</th>
                      <th className="pb-2 pr-4">{t('admin.col_role')}</th>
                      <th className="pb-2 pr-4">{t('admin.col_active')}</th>
                      <th className="pb-2 pr-4">{t('admin.col_created')}</th>
                      <th className="pb-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/50">
                    {users.map(u => (
                      <tr key={u.id} className="group">
                        <td className="py-2.5 pr-4">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white text-xs font-bold shrink-0">
                              {u.username.charAt(0).toUpperCase()}
                            </div>
                            <span className="text-gray-200 font-medium">{u.username}</span>
                          </div>
                        </td>
                        <td className="py-2.5 pr-4 text-gray-400">{u.email || '—'}</td>
                        <td className="py-2.5 pr-4">
                          {u.role === 'owner' ? (
                            <span className="text-xs px-2.5 py-0.5 rounded-full border bg-amber-500/10 text-amber-300 border-amber-500/20 font-bold uppercase tracking-wider select-none shadow-sm shadow-amber-500/5">
                              {t('admin.role_owner')}
                            </span>
                          ) : isOwner ? (
                            <button
                              onClick={() => toggleRole(u)}
                              className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                                u.role === 'admin'
                                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                                  : 'bg-violet-500/10 text-violet-400 border-violet-500/20 hover:bg-violet-500/20'
                              }`}
                            >
                              {t(`admin.role_${u.role}`)}
                            </button>
                          ) : (
                            <span className={`text-xs px-2 py-0.5 rounded-full border select-none ${
                              u.role === 'admin'
                                ? 'bg-amber-500/5 text-amber-400/60 border-amber-500/10'
                                : 'bg-violet-500/5 text-violet-400/60 border-violet-500/10'
                            }`}>
                              {t(`admin.role_${u.role}`)}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4">
                          {u.role === 'owner' ? (
                            <div className="relative inline-flex h-5 w-9 items-center rounded-full bg-emerald-600/50 cursor-not-allowed select-none">
                              <span className="inline-block h-3.5 w-3.5 transform rounded-full bg-white/70 translate-x-5" />
                            </div>
                          ) : (
                            <button
                              onClick={() => toggleActive(u)}
                              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${u.is_active ? 'bg-emerald-600' : 'bg-gray-700'}`}
                            >
                              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${u.is_active ? 'translate-x-5' : 'translate-x-0.5'}`} />
                            </button>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-gray-500 text-xs">
                          {new Date(u.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-2.5">
                          {u.role !== 'owner' && (
                            <button
                              onClick={() => deleteUser(u.id)}
                              className="text-gray-600 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                              title={t('admin.delete_user')}
                            >
                              <Trash2 size={14} />
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
      )}

      {}
      {tab === 'permissions' && (
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
                className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white text-sm px-4 py-2 rounded-xl transition"
              >
                {permSaved ? <CheckCircle2 size={14} className="text-emerald-300" /> : <Save size={14} />}
                {permSaved ? t('admin.saved') : t('admin.save_permissions')}
              </button>
            )}
          </div>

          {selectedUserId && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-2">
                {ALL_PAGE_KEYS.map(key => (
                  <label key={key} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer bg-gray-800 hover:bg-gray-750 rounded-xl px-3 py-2 transition-colors">
                    <input
                      type="checkbox"
                      className="accent-violet-600 w-4 h-4 rounded"
                      checked={permissions[key] ?? false}
                      onChange={e => setPermissions(prev => ({ ...prev, [key]: e.target.checked }))}
                    />
                    {PAGE_LABELS[key] || key}
                  </label>
                ))}
              </div>

              {}
              <div className="border-t border-gray-800 mt-5 pt-4 space-y-2">
                <h4 className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                  {t('admin.section_settings_permissions') || 'Settings Edit Permissions'}
                </h4>
                <p className="text-xs text-gray-500 mb-1">Select which settings tabs this user is permitted to edit:</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { key: 'general',  label: t('settings.general') || 'Preferences' },
                    { key: 'llm',      label: t('settings.llm_settings') || 'AI Engine' },
                    { key: 'risk',     label: t('settings.section_risk') || 'Risk & Safety' },
                    { key: 'webhooks', label: t('settings.section_notifications') || 'Personal Webhooks' },
                    { key: 'cron',     label: t('settings.cron_settings') || 'Cron Scheduler' },
                    { key: 'presets',  label: t('settings.section_presets') || 'Configuration Templates' },
                  ].map(s => (
                    <label key={s.key} className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer bg-gray-800 hover:bg-gray-750 rounded-xl px-3 py-2 transition-colors">
                      <input
                        type="checkbox"
                        className="accent-amber-500 w-4 h-4 rounded"
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
      )}

      {}
      {tab === 'system' && sysSettings && (
        <Section title={t('admin.section_system_settings')}>
          <div className="space-y-3">
            {}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-4">
              <span className="text-sm text-gray-400">SearXNG URL</span>
              <div className="flex-1 sm:max-w-xs">
                <input
                  className={Input}
                  value={sysSettings.searxng_url || ''}
                  onChange={e => setSysSettings(s => s ? { ...s, searxng_url: e.target.value || null } : s)}
                  placeholder="http://localhost:8080"
                />
              </div>
            </div>

            {}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-4">
              <span className="text-sm text-gray-400">Reddit Client ID</span>
              <div className="flex-1 sm:max-w-xs">
                <input
                  className={Input}
                  value={sysSettings.reddit_client_id || ''}
                  onChange={e => setSysSettings(s => s ? { ...s, reddit_client_id: e.target.value || null } : s)}
                  placeholder="Reddit Client ID"
                />
              </div>
            </div>

            {}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-4">
              <span className="text-sm text-gray-400">Reddit Client Secret</span>
              <div className="flex-1 sm:max-w-xs">
                <input
                  className={Input}
                  type="password"
                  value={sysSettings.reddit_client_secret || ''}
                  onChange={e => setSysSettings(s => s ? { ...s, reddit_client_secret: e.target.value || null } : s)}
                  placeholder="Reddit Client Secret"
                />
              </div>
            </div>

            {}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-4">
              <span className="text-sm text-gray-400">Reddit User Agent</span>
              <div className="flex-1 sm:max-w-xs">
                <input
                  className={Input}
                  value={sysSettings.reddit_user_agent || ''}
                  onChange={e => setSysSettings(s => s ? { ...s, reddit_user_agent: e.target.value || null } : s)}
                  placeholder="TradingAgents/1.0"
                />
              </div>
            </div>

            {}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 sm:gap-4">
              <span className="text-sm text-gray-400">Alpha Vantage API Key</span>
              <div className="flex-1 sm:max-w-xs">
                <input
                  className={Input}
                  type="password"
                  value={sysSettings.alpha_vantage_api_key || ''}
                  onChange={e => setSysSettings(s => s ? { ...s, alpha_vantage_api_key: e.target.value || null } : s)}
                  placeholder="Alpha Vantage API Key"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={saveSystemSettings}
                className="flex items-center gap-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white rounded-xl px-5 py-2.5 text-sm font-semibold shadow-lg shadow-amber-500/20 transition-all"
              >
                {sysSaved ? <CheckCircle2 size={15} className="text-emerald-200" /> : <Save size={15} />}
                {sysSaved ? t('admin.saved') : t('admin.save_system')}
              </button>
              {sysError && <span className="text-red-400 text-sm">{sysError}</span>}
            </div>
          </div>
        </Section>
      )}

      {}
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
            {keySaved && <span className="text-emerald-400 text-sm">✓ Key saved successfully</span>}
            {keyError && <span className="text-red-400 text-sm">{keyError}</span>}
          </div>

          {selectedUserId && (
            <div className="space-y-4 mt-4">
              <p className="text-xs text-gray-500 pb-1">
                Admins cannot see existing API key characters, but can define/set or delete them.
              </p>
              <div className="space-y-3 bg-gray-800 border border-gray-700/50 p-4 rounded-2xl">
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

      {}
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
            <div className="border-t border-gray-800 pt-4 mt-4">
              <Settings userId={selectedUserId} />
            </div>
          )}
        </Section>
      )}
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
    <div className="flex flex-col gap-1.5 border-b border-gray-800/50 pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-300 font-medium">{label}</span>
          {hasKey && (
            <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full px-2 py-0.5">
              Configured
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {hasKey && (
            <button
              onClick={handleDelete}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors p-1"
              title="Delete Key"
            >
              <Trash2 size={13} />
            </button>
          )}
          <button
            onClick={() => setEditing(e => !e)}
            className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white px-2.5 py-1 rounded-lg transition-colors font-medium"
          >
            {editing ? 'Cancel' : hasKey ? 'Update Key' : 'Add Key'}
          </button>
        </div>
      </div>
      {editing && (
        <div className="flex gap-2 mt-0.5">
          <div className="relative flex-1">
            <input
              className="bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm w-full transition"
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
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs font-semibold select-none"
            >
              {show ? 'Hide' : 'Show'}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm px-3 py-1.5 rounded-xl transition whitespace-nowrap font-medium"
          >
            <Save size={13} /> Save
          </button>
        </div>
      )}
    </div>
  )
}

