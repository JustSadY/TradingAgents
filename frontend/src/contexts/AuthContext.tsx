import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'
import axios from 'axios'
import { formatErrorDetail, notify } from '../utils/notify'

const TOKEN_KEY = 'ta_access'
const REFRESH_KEY = 'ta_refresh'

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY)
}

interface JwtPayload {
  sub: string
  role?: string
  type: string
  exp: number
}

function decodeToken(token: string): JwtPayload | null {
  try {
    // JWT segments are base64url; normalize to base64 (+ padding) before atob,
    // otherwise tokens whose payload contains '-' or '_' fail to decode and the
    // user is silently logged out.
    let b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    b64 += '='.repeat((4 - (b64.length % 4)) % 4)
    return JSON.parse(atob(b64)) as JwtPayload
  } catch {
    return null
  }
}

interface AuthContextType {
  user: string | null
  role: string | null
  isAdmin: boolean
  isOwner: boolean
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const initAuth = useCallback(() => {
    const t = localStorage.getItem(TOKEN_KEY)
    if (t) {
      const payload = decodeToken(t)
      if (payload && payload.exp * 1000 > Date.now()) {
        setUser(payload.sub)
        setRole(payload.role || 'user')
      } else {
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(REFRESH_KEY)
      }
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    initAuth()
  }, [initAuth])

  const login = useCallback(async (username: string, password: string) => {
    const res = await axios.post('/auth/login', { username, password })
    const { access_token, refresh_token } = res.data
    localStorage.setItem(TOKEN_KEY, access_token)
    localStorage.setItem(REFRESH_KEY, refresh_token)
    const payload = decodeToken(access_token)
    setUser(payload?.sub ?? username)
    setRole(payload?.role ?? 'user')
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    setUser(null)
    setRole(null)
  }, [])

  const value = {
    user,
    role,
    isAdmin: role === 'admin' || role === 'owner',
    isOwner: role === 'owner',
    isAuthenticated: !!user,
    login,
    logout,
    loading
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

// Global Axios Interceptors
axios.interceptors.request.use(cfg => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token && cfg.headers) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

let _refreshing = false
let _queue: Array<(token: string) => void> = []

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

    if (status !== 401 || original._retried) {
      return Promise.reject(err)
    }
    original._retried = true

    if (_refreshing) {
      return new Promise(resolve => {
        _queue.push((token: string) => {
          original.headers.Authorization = `Bearer ${token}`
          resolve(axios(original))
        })
      })
    }

    _refreshing = true
    try {
      const refreshToken = localStorage.getItem(REFRESH_KEY)
      if (!refreshToken) throw new Error('No refresh token')
      const res = await axios.post('/auth/refresh', { refresh_token: refreshToken })
      const newToken: string = res.data.access_token
      localStorage.setItem(TOKEN_KEY, newToken)
      _queue.forEach(cb => cb(newToken))
      _queue = []
      original.headers.Authorization = `Bearer ${newToken}`
      return axios(original)
    } catch {
      _queue = []
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
      window.location.href = '/login'
      return Promise.reject(err)
    } finally {
      _refreshing = false
    }
  }
)
