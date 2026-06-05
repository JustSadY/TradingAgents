import { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import { Save, Key, Trash2, Eye, EyeOff, CheckCircle2, User2 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import { useMeta } from '../hooks/useMeta'

interface UserProfile {
  id: number
  username: string
  email: string | null
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

const Input = "w-full glass-input rounded-xl px-3 py-2 text-xs outline-none"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-panel rounded-2xl p-4 md:p-5 space-y-4">
      <h3 className="text-xs font-bold text-violet-400 uppercase tracking-widest border-b border-white/[0.04] pb-2.5">{title}</h3>
      {children}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-4 border-b border-white/[0.01] pb-3.5 last:border-b-0 last:pb-0">
      <span className="text-xs text-slate-400 font-semibold uppercase tracking-wider shrink-0">{label}</span>
      <div className="flex-1 sm:max-w-xs w-full">{children}</div>
    </div>
  )
}

function ApiKeyRow({ providerKey, label, hasKey, onSave, onDelete }: {
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
  const { t } = useTranslation()

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
          <Key size={13} className={hasKey ? 'text-emerald-400' : 'text-slate-600'} />
          <span className="text-xs text-slate-300 font-semibold">{label}</span>
          {hasKey && (
            <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full px-2 py-0.5 font-bold uppercase tracking-wider">
              {t('profile.key_set')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasKey && (
            <button
              onClick={handleDelete}
              className="text-slate-500 hover:text-rose-400 transition-colors p-1 hover:bg-white/5 rounded cursor-pointer"
              title={t('profile.delete_key')}
            >
              <Trash2 size={13} />
            </button>
          )}
          <button
            onClick={() => setEditing(e => !e)}
            className="text-[10px] bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white px-2.5 py-1 rounded-lg transition-colors font-bold cursor-pointer"
          >
            {editing ? t('profile.cancel') : hasKey ? t('profile.update_key') : t('profile.add_key')}
          </button>
        </div>
      </div>
      {editing && (
        <div className="flex gap-2 mt-1 animate-in slide-in-from-top-1 duration-150">
          <div className="relative flex-1">
            <input
              className="w-full glass-input rounded-xl px-3 py-1.5 text-xs outline-none font-mono"
              type={show ? 'text' : 'password'}
              placeholder={t('profile.key_placeholder')}
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
              {show ? <EyeOff size={13} /> : <Eye size={13} />}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition whitespace-nowrap cursor-pointer"
          >
            <Save size={13} /> {t('profile.save')}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Profile() {
  const { t } = useTranslation()
  const meta = useMeta()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [keyProviders, setKeyProviders] = useState<string[]>([])
  const [profileForm, setProfileForm] = useState({ email: '', display_name: '', password: '', password2: '' })
  const [profileSaved, setProfileSaved] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  const providers = useMemo(() => {
    if (!meta?.provider_labels) return []
    return Object.entries(meta.provider_labels).map(([key, label]) => ({
      key,
      label: label as string,
    }))
  }, [meta?.provider_labels])

  const load = async () => {
    const [p, k] = await Promise.all([
      axios.get('/api/users/me').then(r => r.data),
      axios.get('/api/users/me/api-keys').then(r => r.data.providers),
    ])
    setProfile(p)
    setKeyProviders(k)
    setProfileForm({ email: p.email || '', display_name: p.display_name || '', password: '', password2: '' })
  }

  useEffect(() => { load() }, [])

  const saveProfile = async () => {
    setProfileError(null)
    if (profileForm.password && profileForm.password !== profileForm.password2) {
      setProfileError(t('profile.password_mismatch'))
      return
    }
    try {
      const body: Record<string, string> = {}
      if (profileForm.email !== (profile?.email || '')) body.email = profileForm.email
      if (profileForm.display_name !== (profile?.display_name || '')) body.display_name = profileForm.display_name
      if (profileForm.password) body.password = profileForm.password
      await axios.put('/api/users/me', body)
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2500)
      await load()
    } catch (err: any) {
      setProfileError(err.response?.data?.detail || t('profile.save_error'))
    }
  }

  const saveApiKey = async (provider: string, apiKey: string) => {
    await axios.put('/api/users/me/api-keys', { provider, api_key: apiKey })
    setKeyProviders(prev => prev.includes(provider) ? prev : [...prev, provider])
  }

  const deleteApiKey = async (provider: string) => {
    await axios.delete(`/api/users/me/api-keys/${provider}`)
    setKeyProviders(prev => prev.filter(p => p !== provider))
  }

  if (!profile) return <div className="p-8 text-slate-500 text-xs font-semibold">{t('common.loading')}</div>

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white font-bold text-lg shrink-0 shadow shadow-violet-500/20">
          {profile.username.charAt(0).toUpperCase()}
        </div>
        <div>
          <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('profile.title')}</h2>
          <p className="text-xs text-slate-500 mt-1 flex items-center gap-1.5 font-medium">
            @{profile.username} ·{' '}
            <span
              className={
                profile.role === 'owner'
                  ? 'text-amber-400 font-bold uppercase tracking-wider'
                  : profile.role === 'admin'
                  ? 'text-amber-300 font-bold uppercase tracking-wider'
                  : 'text-violet-400 font-bold uppercase tracking-wider'
              }
            >
              {t(`admin.role_${profile.role}`)}
            </span>
          </p>
        </div>
      </div>

      {/* Profile Form */}
      <Section title={t('profile.section_info')}>
        <Row label={t('profile.username')}>
          <div className="flex items-center gap-2">
            <User2 size={13} className="text-slate-500" />
            <span className="text-xs font-bold text-white">{profile.username}</span>
          </div>
        </Row>
        <Row label={t('profile.display_name')}>
          <input
            className={Input}
            value={profileForm.display_name}
            onChange={e => setProfileForm(f => ({ ...f, display_name: e.target.value }))}
            placeholder={t('profile.display_name_placeholder')}
          />
        </Row>
        <Row label={t('profile.email')}>
          <input
            className={Input}
            type="email"
            value={profileForm.email}
            onChange={e => setProfileForm(f => ({ ...f, email: e.target.value }))}
            placeholder={t('profile.email_placeholder')}
          />
        </Row>
        <Row label={t('profile.new_password')}>
          <input
            className={Input}
            type="password"
            value={profileForm.password}
            onChange={e => setProfileForm(f => ({ ...f, password: e.target.value }))}
            placeholder={t('profile.password_placeholder')}
            autoComplete="new-password"
          />
        </Row>
        {profileForm.password && (
          <Row label={t('profile.confirm_password')}>
            <input
              className={Input}
              type="password"
              value={profileForm.password2}
              onChange={e => setProfileForm(f => ({ ...f, password2: e.target.value }))}
              placeholder={t('profile.confirm_password_placeholder')}
              autoComplete="new-password"
            />
          </Row>
        )}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={saveProfile}
            className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-xs font-semibold shadow-md shadow-violet-500/20 transition-all cursor-pointer"
          >
            {profileSaved ? <CheckCircle2 size={13} className="text-emerald-300" /> : <Save size={13} />}
            {profileSaved ? t('profile.saved') : t('profile.save')}
          </button>
          {profileError && <span className="text-rose-400 text-xs font-semibold">{profileError}</span>}
        </div>
      </Section>

      {/* User API Keys */}
      <Section title={t('profile.section_api_keys')}>
        <p className="text-[10px] text-slate-500 font-semibold pb-1.5 border-b border-white/[0.04] mb-3">{t('profile.api_keys_hint')}</p>
        <div className="space-y-3 bg-slate-900/40 border border-white/[0.04] p-4 rounded-2xl">
          {providers.map(p => (
            <ApiKeyRow
              key={p.key}
              providerKey={p.key}
              label={p.label}
              hasKey={keyProviders.includes(p.key)}
              onSave={saveApiKey}
              onDelete={deleteApiKey}
            />
          ))}
          {providers.length === 0 && (
            <div className="text-center py-4 text-slate-500 text-xs font-medium italic">
              {t('common.no_data')}
            </div>
          )}
        </div>
      </Section>
    </div>
  )
}
