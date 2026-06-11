import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import axios from 'axios'
import { useAuth } from './AuthContext'

/**
 * Single source of truth for which pages the current user may access.
 *
 * Previously each consumer (the sidebar) fetched `/api/users/me/permissions`
 * on its own, and route components rendered regardless of permission — so a
 * user could reach a forbidden page by typing its URL even though the nav link
 * was hidden. This context fetches the allowed pages once after login and both
 * the sidebar and the route guard read from it.
 */
interface PermissionsContextType {
  allowedPages: string[]
  loading: boolean
  canAccess: (page: string) => boolean
  refresh: () => void
}

const PermissionsContext = createContext<PermissionsContextType | undefined>(undefined)

// Always reachable for any authenticated user regardless of granted pages.
const ALWAYS_ALLOWED = new Set(['settings', 'profile'])

export function PermissionsProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isAdmin } = useAuth()
  const [allowedPages, setAllowedPages] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(() => {
    if (!isAuthenticated) {
      setAllowedPages([])
      setLoading(false)
      return
    }
    setLoading(true)
    axios.get('/api/users/me/permissions')
      .then(r => setAllowedPages(r.data.allowed_pages ?? []))
      .catch(() => setAllowedPages(['settings', 'profile']))
      .finally(() => setLoading(false))
  }, [isAuthenticated])

  useEffect(() => { refresh() }, [refresh])

  const canAccess = useCallback((page: string): boolean => {
    if (isAdmin) return true
    if (ALWAYS_ALLOWED.has(page)) return true
    return allowedPages.includes(page)
  }, [isAdmin, allowedPages])

  return (
    <PermissionsContext.Provider value={{ allowedPages, loading, canAccess, refresh }}>
      {children}
    </PermissionsContext.Provider>
  )
}

export function usePermissions() {
  const ctx = useContext(PermissionsContext)
  if (ctx === undefined) throw new Error('usePermissions must be used within a PermissionsProvider')
  return ctx
}
