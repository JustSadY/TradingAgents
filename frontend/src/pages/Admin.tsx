import { useEffect, useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useUsersListUsersRun,
  useUsersCreateUser,
  useUsersUpdateUser,
  useUsersDeleteUser,
  useUsersSetUserPermissions,
  useUsersSetUserSettingPermissions,
  useUsersSetAgentAccess,
  useUsersSetToolAccess,
  useUsersSetToolFieldAccess,
  useUsersSetUserApiKeyEndpoint,
  useUsersDeleteUserApiKeyEndpoint,
  usersGetUserPermissions,
  getUsersGetUserPermissionsQueryKey,
  usersGetUserSettingPermissions,
  getUsersGetUserSettingPermissionsQueryKey,
  usersGetAgentAccess,
  getUsersGetAgentAccessQueryKey,
  usersGetToolAccess,
  getUsersGetToolAccessQueryKey,
  usersGetToolFieldAccess,
  getUsersGetToolFieldAccessQueryKey,
  usersListUserApiKeys,
  getUsersListUserApiKeysQueryKey,
} from '../api/generated/users/users'
import { useSystemSettingsGetSystemSettings, useSystemSettingsUpdateSystemSettings } from '../api/generated/system-settings/system-settings'
import type { UsersGetToolAccess200, UsersGetToolFieldAccess200 } from '../api/generated/model'
import { useAnalyticsGetSystemMetrics, useAnalyticsGetSystemHealth } from '../api/generated/analytics/analytics'
import { Save, Trash2, Plus, UserCog, ShieldCheck, Globe, CheckCircle2, Key, Sliders, BarChart3, RefreshCw, Zap, AlertTriangle, Clock, Wifi } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { useAuth } from '../contexts/AuthContext'
import { ErrorBoundary } from '../components/ErrorBoundary'
import Settings from './Settings'
import ToolSettingsPanel from '../components/settings/ToolSettingsPanel'
import { useMeta } from '../hooks/useMeta'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell
} from 'recharts'
import { ResponsiveChart } from '../components/ui/ResponsiveChart'

interface UserRecord {
  id: number
  username: string
  email: string | null
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

const FALLBACK_PAGE_KEYS = [
  'dashboard', 'analysis', 'chart', 'trading', 'portfolio',
  'watchlist', 'orders', 'performance', 'backtest', 'alerts', 'ab-testing', 'logs', 'profile',
  'screener', 'sector-rotation', 'earnings'
]

const FALLBACK_PAGE_LABELS: Record<string, string> = {
  dashboard: 'Dashboard', analysis: 'Analysis', chart: 'Charts',
  trading: 'Simulation', portfolio: 'Portfolio', watchlist: 'Watchlist',
  orders: 'Orders', performance: 'Performance', alerts: 'Alerts',
  'ab-testing': 'A/B Testing', logs: 'Logs', profile: 'Profile',
  screener: 'Screener', 'sector-rotation': 'Sector Rotation', earnings: 'Earnings Calendar'
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

type Tab = 'users' | 'permissions' | 'system' | 'api-keys' | 'user-settings' | 'metrics'

export default function Admin() {
  const { t } = useTranslation()
  const { isOwner } = useAuth()
  const meta = useMeta()
  const ALL_PAGE_KEYS = meta?.page_keys ?? FALLBACK_PAGE_KEYS
  const PAGE_LABELS = meta?.section_labels ?? FALLBACK_PAGE_LABELS
  const [tab, setTab] = useState<Tab>('users')
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [permissions, setPermissions] = useState<Record<string, boolean>>({})
  const [settingPermissions, setSettingPermissions] = useState<Record<string, boolean>>({})
  const [agentAccess, setAgentAccess] = useState<Record<string, boolean>>({})
  const [toolAccess, setToolAccess] = useState<UsersGetToolAccess200>({})
  const [toolFieldAccess, setToolFieldAccess] = useState<UsersGetToolFieldAccess200>({})
  const [permSaved, setPermSaved] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', email: '', display_name: '', role: 'user' })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [userKeyProviders, setUserKeyProviders] = useState<string[]>([])
  const [keySaved, setKeySaved] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [systemSettings, setSystemSettings] = useState<any>(null)
  const [sysSaved, setSysSaved] = useState(false)
  const adminTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => { return () => { if (adminTimeoutRef.current) clearTimeout(adminTimeoutRef.current) } }, [])

  const queryClient = useQueryClient()
  const createUserMutation = useUsersCreateUser()
  const updateUserMutation = useUsersUpdateUser()
  const deleteUserMutation = useUsersDeleteUser()
  const setPerms = useUsersSetUserPermissions()
  const setSettingPerms = useUsersSetUserSettingPermissions()
  const setAgents = useUsersSetAgentAccess()
  const setTools = useUsersSetToolAccess()
  const setToolFields = useUsersSetToolFieldAccess()
  const setUserKey = useUsersSetUserApiKeyEndpoint()
  const deleteUserKey = useUsersDeleteUserApiKeyEndpoint()
  const updateSystemSettings = useSystemSettingsUpdateSystemSettings()

  const usersQuery = useUsersListUsersRun()
  const users = (usersQuery.data ?? []) as UserRecord[]
  const loadUsers = useCallback(() => usersQuery.refetch(), [usersQuery])

  // System settings are edited in place before saving, so the server copy seeds
  // local form state rather than being rendered directly.
  const systemSettingsQuery = useSystemSettingsGetSystemSettings()
  useEffect(() => {
    if (systemSettingsQuery.data) setSystemSettings(systemSettingsQuery.data)
  }, [systemSettingsQuery.data])

  // Metrics stay disabled until the tab is opened; they are polled server-side
  // work that the user-management tabs never need.
  const [metricsEnabled, setMetricsEnabled] = useState(false)
  const metricsQuery = useAnalyticsGetSystemMetrics({ query: { enabled: metricsEnabled } })
  const healthQuery = useAnalyticsGetSystemHealth({ query: { enabled: metricsEnabled } })
  const sysMetrics = metricsQuery.data ?? null
  const sysHealth = healthQuery.data ?? null
  const metricsLoading = metricsEnabled && (metricsQuery.isFetching || healthQuery.isFetching)
  // Each panel degrades independently, matching the previous allSettled().
  const loadMetrics = useCallback(() => {
    setMetricsEnabled(true)
    void metricsQuery.refetch()
    void healthQuery.refetch()
  }, [metricsQuery, healthQuery])

  useEffect(() => {
    setSelectedUserId(null)
  }, [tab])

  // Permission payloads seed editable form state, so they are fetched
  // imperatively on selection rather than rendered straight from the cache.
  const loadUserPermissions = async (userId: number) => {
    try {
      const [pRes, sRes, agentRes, toolRes, toolFieldRes] = await Promise.all([
        queryClient.fetchQuery({
          queryKey: getUsersGetUserPermissionsQueryKey(userId),
          queryFn: () => usersGetUserPermissions(userId),
        }),
        queryClient.fetchQuery({
          queryKey: getUsersGetUserSettingPermissionsQueryKey(userId),
          queryFn: () => usersGetUserSettingPermissions(userId),
        }),
        queryClient.fetchQuery({
          queryKey: getUsersGetAgentAccessQueryKey(userId),
          queryFn: () => usersGetAgentAccess(userId),
        }),
        queryClient.fetchQuery({
          queryKey: getUsersGetToolAccessQueryKey(userId),
          queryFn: () => usersGetToolAccess(userId),
        }),
        queryClient.fetchQuery({
          queryKey: getUsersGetToolFieldAccessQueryKey(userId),
          queryFn: () => usersGetToolFieldAccess(userId),
        }),
      ])
      setPermissions(pRes.permissions)
      setSettingPermissions(sRes.permissions)
      setAgentAccess(agentRes)
      setToolAccess(toolRes)
      setToolFieldAccess(toolFieldRes)
      setSelectedUserId(userId)
    } catch {
      setErrorMsg('Failed to load user permissions')
    }
  }

  const refetchUserKeys = async (userId: number) => {
    const res = await queryClient.fetchQuery({
      queryKey: getUsersListUserApiKeysQueryKey(userId),
      queryFn: () => usersListUserApiKeys(userId),
    })
    return res.providers ?? []
  }

  const loadUserApiKeys = async (userId: number) => {
    setSelectedUserId(userId)
    const r = await refetchUserKeys(userId)
    setUserKeyProviders(r)
  }

  const saveUserApiKey = async (userId: number, provider: string, apiKey: string) => {
    setKeyError(null)
    try {
      await setUserKey.mutateAsync({ userId, data: { provider, api_key: apiKey } })
      setKeySaved(true)
      adminTimeoutRef.current = setTimeout(() => setKeySaved(false), 2000)
      await loadUserApiKeys(userId)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setKeyError(detail || 'Key could not be saved')
    }
  }

  const deleteUserApiKey = async (userId: number, provider: string) => {
    setKeyError(null)
    try {
      await deleteUserKey.mutateAsync({ userId, provider })
      await loadUserApiKeys(userId)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setKeyError(detail || 'Key could not be deleted')
    }
  }

  const savePermissions = async () => {
    if (!selectedUserId) return
    setErrorMsg(null)
    try {
      await Promise.all([
        setPerms.mutateAsync({ userId: selectedUserId, data: { permissions } }),
        setSettingPerms.mutateAsync({ userId: selectedUserId, data: { permissions: settingPermissions } }),
        setAgents.mutateAsync({ userId: selectedUserId, data: { agents: agentAccess } }),
        setTools.mutateAsync({ userId: selectedUserId, data: { tools: toolAccess } }),
        setToolFields.mutateAsync({ userId: selectedUserId, data: { fields: toolFieldAccess } }),
      ])
      setPermSaved(true)
      adminTimeoutRef.current = setTimeout(() => setPermSaved(false), 2500)
    } catch {
      setErrorMsg('Failed to save permissions')
    }
  }

  const createUser = async () => {
    setCreateError(null)
    if (!newUser.username.trim() || !newUser.password.trim()) {
      setCreateError(t('admin.create_user_required'))
      return
    }
    setCreating(true)
    try {
      await createUserMutation.mutateAsync({
        data: {
          username: newUser.username.trim(),
          password: newUser.password.trim(),
          email: newUser.email.trim() || null,
          display_name: newUser.display_name.trim() || null,
          role: newUser.role,
        },
      })
      setNewUser({ username: '', password: '', email: '', display_name: '', role: 'user' })
      await loadUsers()
    } catch (err: any) {
      setCreateError(err.response?.data?.detail || t('admin.create_user_error'))
    } finally {
      setCreating(false)
    }
  }

  // The list is refetched instead of patched locally: the server is the only
  // authority on a role or activation change.
  const toggleRole = async (u: UserRecord) => {
    await updateUserMutation.mutateAsync({
      userId: u.id,
      data: { role: u.role === 'admin' ? 'user' : 'admin' },
    })
    await usersQuery.refetch()
  }

  const toggleActive = async (u: UserRecord) => {
    await updateUserMutation.mutateAsync({ userId: u.id, data: { is_active: !u.is_active } })
    await usersQuery.refetch()
  }

  const deleteUser = async (id: number) => {
    if (!window.confirm(t('admin.delete_user_confirm'))) return
    await deleteUserMutation.mutateAsync({ userId: id })
    await usersQuery.refetch()
    if (selectedUserId === id) setSelectedUserId(null)
  }

  const saveSystemSettings = async () => {
    if (!systemSettings) return
    try {
      await updateSystemSettings.mutateAsync({ data: systemSettings })
      setSysSaved(true)
      adminTimeoutRef.current = setTimeout(() => setSysSaved(false), 2000)
    } catch (err) {
      console.error('Failed to save system settings:', err)
    }
  }



  const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: 'users',       label: t('admin.tab_users'),       icon: <UserCog size={14} /> },
    { key: 'permissions', label: t('admin.tab_permissions'),  icon: <ShieldCheck size={14} /> },
    { key: 'user-settings', label: t('admin.tab_user_settings'), icon: <Sliders size={14} /> },
    { key: 'system',      label: t('admin.tab_system'),       icon: <Globe size={14} /> },
    { key: 'api-keys',    label: t('admin.tab_apikeys'),        icon: <Key size={14} /> },
    { key: 'metrics',     label: 'System Metrics',                                  icon: <BarChart3 size={14} /> },
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
                <input
                  className={Input}
                  placeholder={t('admin.display_name_placeholder')}
                  value={newUser.display_name}
                  onChange={e => setNewUser(f => ({ ...f, display_name: e.target.value }))}
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
                              <div className="flex flex-col">
                                <span className="text-white font-semibold">{u.username}</span>
                                {u.display_name && <span className="text-[10px] text-slate-500 font-medium">{u.display_name}</span>}
                              </div>
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
                    const id = Number.parseInt(e.target.value)
                    if (!Number.isNaN(id)) loadUserPermissions(id)
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
                {errorMsg && <p className="text-rose-400 text-[10px] font-semibold mt-2">{errorMsg}</p>}
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
                      {t('admin.section_settings_permissions')}
                    </h4>
                    <p className="text-[10px] text-slate-500 font-semibold mb-1">{t('admin.settings_permissions_hint')}</p>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {(meta?.setting_keys ?? [
                        { value: 'general',  label: t('settings.general') },
                        { value: 'llm',      label: t('settings.row_llm_provider') },
                        { value: 'agents',   label: 'AI Configuration' },
                        { value: 'tools',    label: t('settings.section_tools') },
                        { value: 'risk',     label: t('settings.section_risk') },
                        { value: 'alerts',   label: t('settings.section_alert_guardrails') },
                        { value: 'webhooks', label: t('settings.section_notifications') },
                        { value: 'cron',     label: t('settings.cron_settings') },
                        { value: 'presets',  label: t('settings.section_presets') },
                        { value: 'memory',   label: 'Memory' },
                        { value: 'personas', label: 'Personas' },
                      ]).map(s => (
                        <label key={s.value} className="flex items-center gap-2.5 text-xs font-semibold text-slate-300 cursor-pointer bg-slate-900/40 hover:bg-slate-900/80 rounded-xl px-3 py-2 border border-white/[0.03] transition-colors select-none">
                          <input
                            type="checkbox"
                            className="accent-amber-500 w-4 h-4 rounded cursor-pointer"
                            checked={settingPermissions[s.value] ?? false}
                            onChange={e => setSettingPermissions(prev => ({ ...prev, [s.value]: e.target.checked }))}
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
                <Section title={t('admin.section_agent_access')}>
                  <p className="text-[10px] text-slate-500 font-semibold mb-3">
                    Grant or revoke access to specific branches of the AI hierarchy. Disabling a parent agent automatically restricts all its sub-agents.
                  </p>
                  <div className="space-y-4">
                    {meta?.agents?.filter(a => !a.parent_key).map(mainAgent => (
                      <div key={mainAgent.key} className="space-y-2">
                        <label className="flex items-center gap-3 text-xs font-bold text-violet-400 cursor-pointer bg-violet-500/5 hover:bg-violet-500/10 rounded-xl px-4 py-3 border border-violet-500/10 transition-colors select-none">
                          <input
                            type="checkbox"
                            className="accent-violet-600 w-4 h-4 rounded cursor-pointer shrink-0"
                            checked={agentAccess[mainAgent.key] ?? mainAgent.default_enabled}
                            onChange={e => setAgentAccess(prev => ({ ...prev, [mainAgent.key]: e.target.checked }))}
                          />
                          <div className="space-y-0.5">
                            <div className="uppercase tracking-wider">{mainAgent.label || mainAgent.key}</div>
                            <div className="text-[10px] text-slate-500 font-normal normal-case leading-tight">{mainAgent.description}</div>
                          </div>
                        </label>
                        
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pl-6">
                          {meta?.agents?.filter(a => a.parent_key === mainAgent.key).map(subAgent => (
                            <label key={subAgent.key} className="flex items-center gap-3 text-xs font-semibold text-slate-300 cursor-pointer bg-slate-900/40 hover:bg-slate-900/80 rounded-xl px-3 py-2 border border-white/[0.03] transition-colors select-none">
                              <input
                                type="checkbox"
                                className="accent-violet-600 w-3.5 h-3.5 rounded cursor-pointer shrink-0"
                                checked={agentAccess[subAgent.key] ?? subAgent.default_enabled}
                                onChange={e => setAgentAccess(prev => ({ ...prev, [subAgent.key]: e.target.checked }))}
                              />
                              <div className="space-y-0.5">
                                <div className="text-slate-200">{subAgent.label || subAgent.key}</div>
                                <div className="text-[9px] text-slate-500 font-normal leading-tight line-clamp-1">{subAgent.description}</div>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>

                <Section title={t('admin.section_tool_field_access')}>
                  <div className="space-y-6">
                    {meta?.tools?.filter(t => t.settings_schema?.length > 0).map(tool => (
                      <div key={tool.key} className="bg-slate-900/40 border border-white/[0.04] rounded-2xl p-4 overflow-hidden">
                        <div className="flex items-center gap-2 mb-3 pb-2 border-b border-white/[0.03]">
                          <div className="w-1.5 h-1.5 rounded-full bg-violet-500 shadow-[0_0_8px_rgba(139,92,246,0.5)]"></div>
                          <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider">{t(tool.label_key)}</h4>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-[10px] text-slate-400">
                            <thead>
                              <tr className="text-left text-slate-500 uppercase tracking-widest border-b border-white/[0.02]">
                                <th className="py-2 px-1 font-bold">{t('admin.col_field')}</th>
                                <th className="py-2 px-1 text-center font-bold">{t('admin.col_view')}</th>
                                <th className="py-2 px-1 text-center font-bold">{t('admin.col_edit')}</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/[0.01]">
                              {tool.settings_schema.map(field => {
                                const fState = (toolFieldAccess[tool.key] || {})[field.key] || { can_view: true, can_edit: true }
                                
                                const updateField = (pk: 'can_view' | 'can_edit', val: boolean) => {
                                  setToolFieldAccess(prev => ({
                                    ...prev,
                                    [tool.key]: {
                                      ...(prev[tool.key] || {}),
                                      [field.key]: { ...fState, [pk]: val }
                                    }
                                  }))
                                }

                                return (
                                  <tr key={field.key} className="hover:bg-white/[0.01]">
                                    <td className="py-2 px-1">
                                      <div className="font-semibold text-slate-300">{t(field.label_key)}</div>
                                      <div className="text-[9px] text-slate-600 italic">ID: {field.key}</div>
                                    </td>
                                    <td className="py-2 px-1 text-center">
                                      <input
                                        type="checkbox"
                                        className="accent-amber-500 w-3.5 h-3.5 rounded cursor-pointer mx-auto"
                                        checked={fState.can_view}
                                        onChange={e => updateField('can_view', e.target.checked)}
                                      />
                                    </td>
                                    <td className="py-2 px-1 text-center">
                                      <input
                                        type="checkbox"
                                        className="accent-amber-500 w-3.5 h-3.5 rounded cursor-pointer mx-auto"
                                        checked={fState.can_edit}
                                        onChange={e => updateField('can_edit', e.target.checked)}
                                      />
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              </>
            )}
          </div>
        )}

        {tab === 'system' && (
          <div className="space-y-6">
            <ToolSettingsPanel serverScope={true} />
            
            <Section title={t('settings.section_advanced')}>
              <div className="flex items-center justify-between mb-4">
                <p className="text-xs text-slate-400">{t('admin.engine_settings_hint')}</p>
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
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{t('admin.trading_mode')}</span>
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
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{t('admin.active_broker')}</span>
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
                    <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{t('admin.active_data_vendor')}</span>
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

                  {(
                    [
                      ['data_vendor_core_stock', 'Core Stock Data Vendor'],
                      ['data_vendor_technicals', 'Technical Indicators Vendor'],
                      ['data_vendor_fundamentals', 'Fundamentals Vendor'],
                      ['data_vendor_news', 'News Vendor'],
                    ] as [string, string][]
                  ).map(([field, label]) => (
                    <div key={field} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3">
                      <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{label}</span>
                      <div className="flex-1 sm:max-w-xs w-full">
                        <select
                          className={Input}
                          value={(systemSettings as any)[field] || 'yfinance'}
                          onChange={e => setSystemSettings({ ...systemSettings, [field]: e.target.value })}
                        >
                          {meta?.data_vendors?.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                        </select>
                      </div>
                    </div>
                  ))}


                </div>
              )}
            </Section>
          </div>
        )}

        {tab === 'api-keys' && (
          <Section title={t('admin.tab_apikeys')}>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
              <select
                className={`${Input} sm:max-w-xs`}
                value={selectedUserId ?? ''}
                onChange={e => {
                  const id = Number.parseInt(e.target.value)
                  if (!Number.isNaN(id)) loadUserApiKeys(id)
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
                  {Object.entries(meta?.provider_labels ?? {
                    openai: 'OpenAI',
                    anthropic: 'Anthropic (Claude)',
                    google: 'Google (Gemini)',
                    nvidia: 'NVIDIA NIM',
                    ollama: 'Ollama (Local)',
                  }).map(([key, label]) => {
                    const hasKey = userKeyProviders.includes(key)
                    return (
                      <AdminApiKeyRow
                        key={key}
                        providerKey={key}
                        label={label}
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
          <Section title={t('admin.tab_user_settings')}>
            <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center pb-2">
              <select
                className={`${Input} sm:max-w-xs`}
                value={selectedUserId ?? ''}
                onChange={e => {
                  const id = Number.parseInt(e.target.value)
                  if (!Number.isNaN(id)) setSelectedUserId(id)
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

        {tab === 'metrics' && (
          <ErrorBoundary name="AdminMetrics">
          <Section title={t('admin.system_metrics')}>
            <div className="flex items-center justify-between">
              <p className="text-[10px] text-slate-500">{t('admin.metrics_hint')}</p>
              <button
                onClick={loadMetrics}
                disabled={metricsLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-600/20 hover:bg-amber-600/30 border border-amber-500/20 text-amber-300 text-[10px] font-bold transition cursor-pointer disabled:opacity-40"
              >
                <RefreshCw size={10} className={metricsLoading ? 'animate-spin' : ''} /> Refresh
              </button>
            </div>

            {!sysMetrics && !metricsLoading && (
              <div className="text-center py-10 opacity-50">
                <BarChart3 size={28} className="mx-auto text-slate-600 mb-2" />
                <p className="text-[10px] text-slate-500 font-semibold">{t('admin.metrics_prompt')}</p>
              </div>
            )}

            {metricsLoading && (
              <div className="text-center py-10 opacity-50">
                <RefreshCw size={20} className="mx-auto animate-spin text-amber-400 mb-2" />
                <p className="text-[10px] text-slate-500">{t('admin.loading')}</p>
              </div>
            )}

            {sysMetrics && !metricsLoading && (
              <div className="space-y-5">
                {/* KPI row */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: 'Total Runs', value: sysMetrics.total_runs, icon: <Zap size={13} />, color: 'text-violet-400' },
                    { label: 'Avg Duration', value: `${sysMetrics.analysis_duration.avg_seconds}s`, icon: <Clock size={13} />, color: 'text-sky-400' },
                    { label: 'Error Rate', value: `${sysMetrics.error_rate_pct}%`, icon: <AlertTriangle size={13} />, color: sysMetrics.error_rate_pct > 5 ? 'text-rose-400' : 'text-emerald-400' },
                    { label: 'Active WS', value: String(sysMetrics.websocket_connections), icon: <Wifi size={13} />, color: 'text-amber-400' },
                  ].map(k => (
                    <div key={k.label} className="bg-white/[0.02] border border-white/[0.04] rounded-xl p-3 flex items-center gap-2.5">
                      <div className="text-amber-400 shrink-0">{k.icon}</div>
                      <div className="min-w-0">
                        <p className="text-[9px] text-slate-500 uppercase font-bold tracking-wider truncate">{k.label}</p>
                        <p className={`text-base font-display font-bold leading-tight ${k.color}`}>{k.value}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Analysis runs by status */}
                {Object.keys(sysMetrics.analysis_runs).length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">{t('admin.runs_by_status')}</p>
                    <div className="h-36">
                      <ResponsiveChart width="100%" height="100%">
                        <BarChart data={Object.entries(sysMetrics.analysis_runs).map(([k, v]) => ({ status: k, count: v }))} barCategoryGap="40%">
                          <XAxis dataKey="status" tick={{ fontSize: 10, fill: '#94a3b8' }} tickLine={false} axisLine={false} />
                          <YAxis tick={{ fontSize: 10, fill: '#64748b' }} tickLine={false} axisLine={false} />
                          <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: 'none', borderRadius: '10px', fontSize: '10px' }} />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                            {Object.entries(sysMetrics.analysis_runs).map(([k], i) => (
                              <Cell key={i} fill={k === 'completed' ? '#10b981' : k === 'failed' ? '#f43f5e' : '#8b5cf6'} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveChart>
                    </div>
                  </div>
                )}

                {/* Node-level errors */}
                {Object.keys(sysMetrics.node_errors).length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-3">{t('admin.node_errors_fallbacks')}</p>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs text-slate-300 min-w-[380px]">
                        <thead>
                          <tr className="text-slate-500 text-[10px] uppercase tracking-wider bg-white/[0.01]">
                            <th className="px-4 py-2.5 text-left font-bold">{t('admin.col_node')}</th>
                            <th className="px-4 py-2.5 text-right font-bold">{t('admin.col_errors')}</th>
                            <th className="px-4 py-2.5 text-right font-bold">{t('admin.col_fallbacks')}</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.02]">
                          {Object.entries(sysMetrics.node_errors).map(([node, errs]) => (
                            <tr key={node} className="hover:bg-white/[0.01] transition-colors">
                              <td className="px-4 py-3 text-slate-300 font-mono text-[10px]">{node}</td>
                              <td className="px-4 py-3 text-right text-rose-400 font-mono font-bold">{errs}</td>
                              <td className="px-4 py-3 text-right text-amber-400 font-mono">{sysMetrics.node_fallbacks[node] ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-4 pt-2 border-t border-white/[0.04]">
                  <div className="text-[10px] text-slate-500">
                    Total retries: <span className="text-slate-300 font-mono font-bold">{sysMetrics.node_retries}</span>
                  </div>
                  <div className="text-[10px] text-slate-500">
                    Completed analyses used in duration avg: <span className="text-slate-300 font-mono font-bold">{sysMetrics.analysis_duration.count}</span>
                  </div>
                </div>

                {sysHealth && (
                  <div className="border-t border-white/[0.04] pt-4 space-y-3">
                    <h4 className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">{t('admin.guardrail_health')}</h4>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="glass-panel rounded-xl p-3">
                        <p className="text-[9px] text-slate-500 uppercase font-bold">{t('admin.signal_parse_fallbacks')}</p>
                        <p className={`text-lg font-mono font-bold ${sysHealth.signal_parse_fallbacks > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>{sysHealth.signal_parse_fallbacks}</p>
                      </div>
                      <div className="glass-panel rounded-xl p-3">
                        <p className="text-[9px] text-slate-500 uppercase font-bold">{t('admin.quality_gate_skips')}</p>
                        <p className="text-lg font-mono font-bold text-slate-200">{sysHealth.auto_order_skipped.quality_gate ?? 0}</p>
                      </div>
                      <div className="glass-panel rounded-xl p-3">
                        <p className="text-[9px] text-slate-500 uppercase font-bold">{t('admin.drawdown_breaker_skips')}</p>
                        <p className="text-lg font-mono font-bold text-slate-200">{sysHealth.auto_order_skipped.drawdown_breaker ?? 0}</p>
                      </div>
                      <div className="glass-panel rounded-xl p-3">
                        <p className="text-[9px] text-slate-500 uppercase font-bold">Avg Run Quality ({sysHealth.quality.period_days}d)</p>
                        <p className="text-lg font-mono font-bold text-slate-200">{sysHealth.quality.avg_score ?? '—'}</p>
                      </div>
                    </div>
                    {sysHealth.quality.total_runs > 0 && (
                      <p className="text-[10px] text-slate-500">
                        Last {sysHealth.quality.period_days}d: <span className="text-emerald-400 font-mono font-bold">{sysHealth.quality.confidence_counts.high}</span> high /{' '}
                        <span className="text-amber-400 font-mono font-bold">{sysHealth.quality.confidence_counts.medium}</span> medium /{' '}
                        <span className="text-rose-400 font-mono font-bold">{sysHealth.quality.confidence_counts.low}</span> low confidence
                        {sysHealth.quality.unknown > 0 && <> ({sysHealth.quality.unknown} unscored)</>}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
            </Section>
            </ErrorBoundary>
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
  const { t } = useTranslation()
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
              title={t('admin.delete_key')}
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
              placeholder={t('admin.enter_api_key')}
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
