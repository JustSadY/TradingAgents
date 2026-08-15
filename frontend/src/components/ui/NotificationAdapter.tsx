import { useEffect } from 'react'
import { useSnackbar } from 'notistack'
import { useAuth } from '../../contexts/AuthContext'
import type { Notification } from '../../utils/notify'

/** Errors stay up longer because they usually need reading, not just noticing. */
const ERROR_DURATION_MS = 6000
const DEFAULT_DURATION_MS = 4000

function isVisible(notification: Notification, isAdmin: boolean, isOwner: boolean): boolean {
  const visibility = notification.visibility ?? 'all'
  if (visibility === 'all') return true
  if (visibility === 'admin') return isAdmin
  return isOwner
}

/**
 * Bridges the app's `ta-notify` event contract onto notistack.
 *
 * The event stays the public API because `notify()` is called from places with
 * no React context — most importantly the axios interceptors — so this listener
 * is the only thing that needs to live inside the provider. What remains here
 * is the part no snackbar library knows about: which roles may see a given
 * notification, and how long each severity should stay up.
 */
export function NotificationAdapter() {
  const { isAdmin, isOwner } = useAuth()
  const { enqueueSnackbar } = useSnackbar()

  useEffect(() => {
    const handler = (event: Event) => {
      const notification = (event as CustomEvent<Notification>).detail
      if (!notification || !isVisible(notification, isAdmin, isOwner)) return

      enqueueSnackbar(notification.message, {
        key: notification.id,
        variant: notification.type,
        autoHideDuration: notification.type === 'error' ? ERROR_DURATION_MS : DEFAULT_DURATION_MS,
        title: notification.title,
      })
    }

    window.addEventListener('ta-notify', handler)
    return () => window.removeEventListener('ta-notify', handler)
  }, [enqueueSnackbar, isAdmin, isOwner])

  return null
}

export default NotificationAdapter
