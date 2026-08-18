import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { TrendingUp } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'

const FIELD_CLASS = 'w-full glass-input rounded-xl px-4 py-2.5 text-xs outline-none'
const MIN_PASSWORD_LENGTH = 8

export default function Login() {
  const { login, completeSetup, setupRequired } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (setupRequired) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(t('login.setup_password_too_short'))
        return
      }
      if (password !== passwordConfirm) {
        setError(t('login.setup_password_mismatch'))
        return
      }
    }

    setLoading(true)
    try {
      if (setupRequired) {
        await completeSetup({ username, password, email })
      } else {
        await login(username, password)
      }
      navigate('/dashboard')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || t(setupRequired ? 'login.setup_error' : 'login.error_credentials'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#020617] relative overflow-hidden p-4">
      {/* Background glowing decorations */}
      <div className="absolute top-1/4 left-1/4 w-80 h-80 bg-violet-600/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-indigo-600/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Login Card */}
      <div className="w-full max-w-sm glass-panel rounded-3xl p-8 relative z-10">
        <div className="flex flex-col items-center mb-7">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/25 mb-3.5">
            <TrendingUp className="text-white" size={20} strokeWidth={2.5} />
          </div>
          <h1 className="text-xl font-display font-bold text-white tracking-tight">TradingAgents</h1>
          <p className="text-slate-400 text-xs mt-1.5 font-medium">
            {t(setupRequired ? 'login.setup_subtitle' : 'login.subtitle')}
          </p>
        </div>

        {setupRequired && (
          <p className="mb-5 rounded-xl border border-violet-400/20 bg-violet-500/[0.06] px-3 py-2.5 text-[11px] leading-relaxed text-violet-200">
            {t('login.setup_hint')}
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            className={FIELD_CLASS}
            placeholder={t('login.username_placeholder')}
            value={username}
            onChange={e => setUsername(e.target.value)}
            autoComplete="username"
            minLength={setupRequired ? 3 : undefined}
            required
          />
          <input
            type="password"
            className={FIELD_CLASS}
            placeholder={t('login.password_placeholder')}
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete={setupRequired ? 'new-password' : 'current-password'}
            minLength={setupRequired ? MIN_PASSWORD_LENGTH : undefined}
            required
          />

          {setupRequired && (
            <>
              <input
                type="password"
                className={FIELD_CLASS}
                placeholder={t('login.setup_password_confirm_placeholder')}
                value={passwordConfirm}
                onChange={e => setPasswordConfirm(e.target.value)}
                autoComplete="new-password"
                required
              />
              <input
                type="email"
                className={FIELD_CLASS}
                placeholder={t('login.setup_email_placeholder')}
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />
            </>
          )}

          {error && <p className="text-rose-400 text-xs font-semibold">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-50 text-white font-semibold text-xs py-2.5 rounded-xl transition shadow-md shadow-violet-600/10 mt-2 cursor-pointer"
          >
            {loading
              ? t(setupRequired ? 'login.setup_submitting' : 'login.submitting')
              : t(setupRequired ? 'login.setup_submit' : 'login.submit')}
          </button>
        </form>
      </div>
    </div>
  )
}
