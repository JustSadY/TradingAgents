import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import type { Notification } from '../../utils/notify'
import { AppSnackbar } from './AppPrimitives'

const MAX_VISIBLE = 5

function isVisible(notification: Notification, isAdmin: boolean, isOwner: boolean): boolean {
  const visibility = notification.visibility ?? 'all'
  if (visibility === 'all') return true
  if (visibility === 'admin') return isAdmin
  return isOwner
}

export function NotificationAdapter() {
  const { isAdmin, isOwner } = useAuth()
  const [notifications, setNotifications] = useState<Notification[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
    setNotifications(current => current.filter(notification => notification.id !== id))
  }, [])

  useEffect(() => {
    const activeTimers = timers.current
    const handler = (event: Event) => {
      const notification = (event as CustomEvent<Notification>).detail
      if (!notification || !isVisible(notification, isAdmin, isOwner)) return

      setNotifications(current => [...current.filter(item => item.id !== notification.id).slice(-(MAX_VISIBLE - 1)), notification])
      const timeout = setTimeout(() => dismiss(notification.id), notification.type === 'error' ? 6000 : 4000)
      activeTimers.set(notification.id, timeout)
    }

    window.addEventListener('ta-notify', handler)
    return () => {
      window.removeEventListener('ta-notify', handler)
      activeTimers.forEach(timer => clearTimeout(timer))
      activeTimers.clear()
    }
  }, [dismiss, isAdmin, isOwner])

  return (
    <>
      {notifications.map((notification, index) => (
        <AppSnackbar
          key={notification.id}
          open
          title={notification.title}
          message={notification.message}
          severity={notification.type}
          autoHideDuration={null}
          bottomOffset={24 + index * 82}
          onClose={() => dismiss(notification.id)}
        />
      ))}
    </>
  )
}

export default NotificationAdapter
