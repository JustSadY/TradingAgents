import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import axios from 'axios'
import { clearAuthenticatedCache } from '../api/authCache'
import { formatErrorDetail, notify } from '../utils/notify'

const TOKEN_KEY = 'ta_access'
const USER_SCOPE_KEY = 'ta_user_scope'
const USER_SCOPED_STORAGE_KEYS = ['ta_last_run', 'ta_task_running']

axios.defaults.withCredentials = true

/**
 * Access tokens are scoped to the current browser tab/session. Refresh tokens
 * are HttpOnly cookies and are never exposed to JavaScript.
 */
export function getAccessToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

function setAccessToken(token: string | null) {
  // Auth secrets are never valid localStorage state. Purge stale values left by
  // older releases instead of authenticating from them.
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem('ta_refresh')
  if (token) sessionStorage.setItem(TOKEN_KEY, token)
  else sessionStorage.removeItem(TOKEN_KEY)
}

function clearUserScopedBrowserState() {
  USER_SCOPED_STORAGE_KEYS.forEach(key => {
    sessionStorage.removeItem(key)
    localStorage.removeItem(key)
  })
  localStorage.removeItem(USER_SCOPE_KEY)
  clearAuthenticatedCache()
}

function activateUserScope(username: string) {
  if (localStorage.getItem(USER_SCOPE_KEY) !== username) {
    clearUserScopedBrowserState()
    localStorage.setItem(USER_SCOPE_KEY, username)
  }
}

let _onForceLogout: (() => void) | null = null
let _onSessionRestored: ((token: string) => boolean) | null = null

/**
 * Generation counter for the current authentication attempt.
 *
 * Bumped whenever auth state is *established* or torn down, so slow work
 * started under an earlier generation cannot write over a newer one. It used
 * to be bumped only by `logout()`, which left this race on a browser's first
 * visit: `initAuth` runs twice under StrictMode, both refresh calls fail
 * because there is no cookie yet, the first rejection reveals the login form,
 * the user signs in — and then the second rejection cleared the session that
 * login had just established, bouncing them back to the login screen. Signing
 * in a second time worked only because by then both calls had settled.
 */
let _authEpoch = 0

/**
 * The one in-flight `/auth/refresh` call, shared by every caller.
 *
 * Refresh tokens rotate, so two concurrent calls presenting the same cookie
 * make the server issue two live tokens while only one can be the current one
 * — and the browser keeps whichever `Set-Cookie` arrived last. When that was
 * the superseded one, the next refresh looked like a replay and the server
 * revoked the whole session, which is what made a second tab (or simply a
 * page load whose first API call 401'd while the bootstrap refresh was still
 * in flight) bounce back to the login screen. Bootstrap and the 401 retry
 * queue therefore share a single promise instead of each firing their own.
 */
let _refreshPromise: Promise<string> | null = null

function refreshAccessToken(): Promise<string> {
  if (_refreshPromise) return _refreshPromise
  const startEpoch = _authEpoch
  _refreshPromise = axios
    .post('/auth/refresh')
    .then(res => {
      const token = res.data?.access_token
      if (typeof token !== 'string') throw new Error('No access token returned')
      // A logout or a completed login during the round trip means this result
      // belongs to an auth generation that no longer exists.
      if (startEpoch !== _authEpoch) throw new Error('Session changed during refresh')
      // Establish the restored session once, centrally. The fallback covers a
      // refresh that resolves before the provider has registered its setter.
      if (_onSessionRestored) {
        if (!_onSessionRestored(token)) throw new Error('Refreshed token is not usable')
      } else {
        setAccessToken(token)
      }
      return token
    })
    .finally(() => {
      _refreshPromise = null
    })
  return _refreshPromise
}

interface JwtPayload {
  sub: string
  role?: string
  type?: string
  exp: number
}

function decodeToken(token: string): JwtPayload | null {
  try {
    let b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    b64 += '='.repeat((4 - (b64.length % 4)) % 4)
    return JSON.parse(atob(b64)) as JwtPayload
  } catch {
    return null
  }
}

export interface SetupPayload {
  username: string
  password: string
  email?: string | null
  display_name?: string | null
}

interface AuthContextType {
  user: string | null
  role: string | null
  isAdmin: boolean
  isOwner: boolean
  isAuthenticated: boolean
  /** True while the installation has no accounts and needs its first owner. */
  setupRequired: boolean
  login: (username: string, password: string) => Promise<void>
  completeSetup: (payload: SetupPayload) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [setupRequired, setSetupRequired] = useState(false)
  const [loading, setLoading] = useState(true)

  const applyAccessToken = useCallback((token: string): boolean => {
    const payload = decodeToken(token)
    if (!payload?.sub || payload.exp * 1000 <= Date.now()) return false
    // A session now exists. Anything still in flight from before this point
    // belongs to an older generation and must not clear it.
    _authEpoch += 1
    setAccessToken(token)
    activateUserScope(payload.sub)
    setUser(payload.sub)
    setRole(payload.role || 'user')
    return true
  }, [])

  const clearLocalAuthState = useCallback(() => {
    setAccessToken(null)
    clearUserScopedBrowserState()
    setUser(null)
    setRole(null)
  }, [])

  const initAuth = useCallback(async () => {
    const epoch = _authEpoch
    try {
      const current = getAccessToken()
      if (current && applyAccessToken(current)) return
      setAccessToken(null)

      // Restore a server-side session using the HttpOnly refresh cookie.
      // `refreshAccessToken` applies the token itself, so a second caller
      // (StrictMode's repeated effect, or a 401 from a query that raced this
      // bootstrap) reuses the same round trip rather than rotating again.
      await refreshAccessToken()
    } catch {
      // A failed restore says nothing about a session established after this
      // attempt started, so it must not tear one down.
      if (epoch !== _authEpoch) return
      clearLocalAuthState()
      // Only an installation with no accounts at all can be set up, so this is
      // asked once, after a failed session restore, rather than on every load.
      try {
        const status = await axios.get('/auth/setup-status')
        if (epoch === _authEpoch) setSetupRequired(status.data?.setup_required === true)
      } catch {
        if (epoch === _authEpoch) setSetupRequired(false)
      }
    } finally {
      setLoading(false)
    }
  }, [applyAccessToken, clearLocalAuthState])

  useEffect(() => {
    void initAuth()
  }, [initAuth])

  const login = useCallback(async (username: string, password: string) => {
    const res = await axios.post('/auth/login', { username, password })
    const token = res.data?.access_token
    if (typeof token !== 'string' || !applyAccessToken(token)) {
      throw new Error('Sunucu geçerli bir erişim belirteci döndürmedi')
    }
    setSetupRequired(false)
  }, [applyAccessToken])

  const completeSetup = useCallback(async (payload: SetupPayload) => {
    const res = await axios.post('/auth/setup', {
      username: payload.username,
      password: payload.password,
      email: payload.email || null,
      display_name: payload.display_name || null,
    })
    const token = res.data?.access_token
    if (typeof token !== 'string' || !applyAccessToken(token)) {
      throw new Error('Sunucu geçerli bir erişim belirteci döndürmedi')
    }
    setSetupRequired(false)
  }, [applyAccessToken])

  const logout = useCallback(() => {
    // Invalidate every in-flight init/refresh and TanStack request before the
    // next auth scope can mount queries using the same generated query keys.
    // Bumping the epoch is enough: a refresh already in flight resolves into
    // the epoch check in `refreshAccessToken` and is discarded there.
    _authEpoch += 1
    clearLocalAuthState()
    // The server call is intentionally best-effort after local invalidation.
    void axios.post('/auth/logout').catch(() => {})
  }, [clearLocalAuthState])

  useEffect(() => {
    _onForceLogout = clearLocalAuthState
    _onSessionRestored = applyAccessToken
    return () => {
      if (_onForceLogout === clearLocalAuthState) _onForceLogout = null
      if (_onSessionRestored === applyAccessToken) _onSessionRestored = null
    }
  }, [clearLocalAuthState, applyAccessToken])

  const value = {
    user,
    role,
    isAdmin: role === 'admin' || role === 'owner',
    isOwner: role === 'owner',
    isAuthenticated: !!user,
    setupRequired,
    login,
    completeSetup,
    logout,
    loading,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) throw new Error('useAuth must be used within an AuthProvider')
  return context
}

axios.interceptors.request.use(cfg => {
  const token = getAccessToken()
  if (token && cfg.headers) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

axios.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    const status: number | undefined = err.response?.status

    if (err.response?.data && typeof err.response.data === 'object' && 'detail' in err.response.data) {
      err.response.data.detail = formatErrorDetail(err.response.data.detail)
    }

    if (status && status >= 500) {
      const detail = err.response?.data?.detail || err.message || 'Sunucu hatası'
      notify('error', detail, `HTTP ${status}`)
    }

    const isAuthEndpoint = typeof original?.url === 'string' && original.url.startsWith('/auth/')
    if (status !== 401 || original?._retried || isAuthEndpoint) throw err
    original._retried = true
    original.headers = original.headers || {}

    try {
      // Concurrent 401s all await the same round trip and then replay
      // themselves with the token it produced.
      const newToken = await refreshAccessToken()
      original.headers.Authorization = `Bearer ${newToken}`
      return axios(original)
    } catch (refreshErr) {
      // Only the server actually rejecting the refresh credential means the
      // session is gone. A rate limit (the endpoint allows 30/min), a 5xx, or
      // a dropped connection says nothing about the refresh cookie — tearing
      // the session down on those turned a transient hiccup into an
      // unexplained trip back to the login screen.
      const refreshStatus = (refreshErr as { response?: { status?: number } })?.response?.status
      if (refreshStatus === 401 || refreshStatus === 403) {
        setAccessToken(null)
        _onForceLogout?.()
      }
      throw err
    }
  },
)
