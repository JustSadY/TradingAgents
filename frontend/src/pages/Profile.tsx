import { useEffect, useState } from 'react'
import axios from 'axios'
import { Save, Key, Trash2, Eye, EyeOff, CheckCircle2, User2 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

interface UserProfile {
  id: number
  username: string
  email: string | null
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string
}

const PROVIDERS = [
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
]

const Input = "bg-gray-800 border border-gray-700 text-white rounded-xl px-3 py-1.5 focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none text-sm w-full transition"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-4 md:p-5 space-y-3">
      <h3 className="text-sm font-semibold text-violet-400 uppercase tracking-wider mb-1">{title}</h3>
      {children}
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1.5 sm:gap-4">
      <span className="text-sm text-gray-400 whitespace-nowrap sm:pt-2 min-w-0 shrink-0">{label}</span>
      <div className="flex-1 sm:max-w-xs">{children}</div>
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
    <div className="flex flex-col gap-1.5 border-b border-gray-800/50 pb-3 last:border-b-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Key size={13} className={hasKey ? 'text-emerald-400' : 'text-gray-600'} />
          <span className="text-sm text-gray-300">{label}</span>
          {hasKey && (
            <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full px-2 py-0.5">
              {t('profile.key_set')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {hasKey && (
            <button
              onClick={handleDelete}
              className="text-xs text-gray-600 hover:text-red-400 transition-colors"
              title={t('profile.delete_key')}
            >
              <Trash2 size={13} />
            </button>
          )}
          <button
            onClick={() => setEditing(e => !e)}
            className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white px-2.5 py-1 rounded-lg transition-colors"
          >
            {editing ? t('profile.cancel') : hasKey ? t('profile.update_key') : t('profile.add_key')}
          </button>
        </div>
      </div>
      {editing && (
        <div className="flex gap-2 mt-0.5">
          <div className="relative flex-1">
            <input
              className={Input}
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
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
            >
              {show ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !value.trim()}
            className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white text-sm px-3 py-1.5 rounded-xl transition whitespace-nowrap"
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
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [keyProviders, setKeyProviders] = useState<string[]>([])
  const [profileForm, setProfileForm] = useState({ email: '', display_name: '', password: '', password2: '' })
  const [profileSaved, setProfileSaved] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

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

  if (!profile) return <div className="p-8 text-slate-400">{t('common.loading')}</div>

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5 max-w-2xl">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white font-bold text-lg shrink-0">
          {profile.username.charAt(0).toUpperCase()}
        </div>
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">{t('profile.title')}</h2>
          <p className="text-sm text-gray-500">
            @{profile.username} ·{' '}
            <span
              className={
                profile.role === 'owner'
                  ? 'text-amber-400 font-semibold'
                  : profile.role === 'admin'
                  ? 'text-amber-300'
                  : 'text-violet-400'
              }
            >
              {t(`admin.role_${profile.role}`)}
            </span>
          </p>
        </div>
      </div>

      <Section title={t('profile.section_info')}>
        <Row label={t('profile.username')}>
          <div className="flex items-center gap-2">
            <User2 size={14} className="text-gray-500" />
            <span className="text-sm text-gray-300">{profile.username}</span>
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
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={saveProfile}
            className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-xl px-5 py-2.5 text-sm font-semibold shadow-lg shadow-violet-500/20 transition-all"
          >
            {profileSaved ? <CheckCircle2 size={15} className="text-emerald-300" /> : <Save size={15} />}
            {profileSaved ? t('profile.saved') : t('profile.save')}
          </button>
          {profileError && <span className="text-red-400 text-sm">{profileError}</span>}
        </div>
      </Section>

      <Section title={t('profile.section_api_keys')}>
        <p className="text-xs text-gray-500 pb-1">{t('profile.api_keys_hint')}</p>
        {PROVIDERS.map(p => (
          <ApiKeyRow
            key={p.key}
            providerKey={p.key}
            label={p.label}
            hasKey={keyProviders.includes(p.key)}
            onSave={saveApiKey}
            onDelete={deleteApiKey}
          />
        ))}
      </Section>
    </div>
  )
}
