export type NotifyType = 'error' | 'warning' | 'success' | 'info'
export type Visibility = 'all' | 'admin' | 'owner'

export interface Notification {
  id: string
  type: NotifyType
  message: string
  title?: string
  visibility?: Visibility
}


export function formatErrorDetail(detail: any): string {
  if (detail == null) {
    return 'Unknown error'
  }
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail
      .map(err => {
        if (err && typeof err === 'object') {
          const loc = Array.isArray(err.loc)
            ? err.loc.filter((x: any) => x !== 'body' && x !== 'query').join('.')
            : ''
          const msg = err.msg || JSON.stringify(err)
          return loc ? `${loc}: ${msg}` : msg
        }
        return String(err)
      })
      .join(', ')
  }
  if (typeof detail === 'object') {
    if (detail.message) return String(detail.message)
    if (detail.msg) return String(detail.msg)
    if (detail.detail) return formatErrorDetail(detail.detail)
    return JSON.stringify(detail)
  }
  return String(detail)
}

const lastNotifications = new Map<string, number>()

export function notify(type: NotifyType, message: any, title?: string, visibility: Visibility = 'all') {
  const msgStr = typeof message === 'string' ? message : formatErrorDetail(message)

  // Deduplicate errors/warnings to avoid flood of identical toasts (e.g. on backend disconnect)
  if (type === 'error' || type === 'warning') {
    const key = `${type}:${title || ''}:${msgStr}`
    const now = Date.now()
    const lastTime = lastNotifications.get(key)
    if (lastTime && now - lastTime < 3000) {
      return
    }
    lastNotifications.set(key, now)

    // Clean up old entries periodically
    if (lastNotifications.size > 50) {
      for (const [k, t] of lastNotifications.entries()) {
        if (now - t > 10000) {
          lastNotifications.delete(k)
        }
      }
    }
  }

  window.dispatchEvent(
    new CustomEvent<Notification>('ta-notify', {
      detail: { id: crypto.randomUUID(), type, message: msgStr, title, visibility },
    })
  )
}


