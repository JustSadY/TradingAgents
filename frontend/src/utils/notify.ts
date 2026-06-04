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

export function notify(type: NotifyType, message: any, title?: string, visibility: Visibility = 'all') {
  const msgStr = typeof message === 'string' ? message : formatErrorDetail(message)
  window.dispatchEvent(
    new CustomEvent<Notification>('ta-notify', {
      detail: { id: crypto.randomUUID(), type, message: msgStr, title, visibility },
    })
  )
}


