import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { usePermissions } from '../contexts/PermissionsContext'

/**
 * Route-level page guard. Renders ``children`` only when the user may access
 * ``page``; otherwise redirects to the dashboard. This enforces page
 * permissions at the route boundary, not just by hiding the nav link, so a
 * forbidden page cannot be reached by typing its URL.
 */
export default function RequirePage({ page, children }: { page: string; children: ReactNode }) {
  const { canAccess, loading } = usePermissions()

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh] text-slate-500 text-xs font-semibold">
        …
      </div>
    )
  }
  if (!canAccess(page)) {
    return <Navigate to="/dashboard" replace />
  }
  return <>{children}</>
}
