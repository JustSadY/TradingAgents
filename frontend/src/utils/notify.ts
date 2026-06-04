export type NotifyType = 'error' | 'warning' | 'success' | 'info'
export type Visibility = 'all' | 'admin' | 'owner'

export interface Notification {
  id: string
  type: NotifyType
  message: string
  title?: string
  visibility?: Visibility
}


export function notify(type: NotifyType, message: string, title?: string, visibility: Visibility = 'all') {
  window.dispatchEvent(
    new CustomEvent<Notification>('ta-notify', {
      detail: { id: crypto.randomUUID(), type, message, title, visibility },
    })
  )
}

