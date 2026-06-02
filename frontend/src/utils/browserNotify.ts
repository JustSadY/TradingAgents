const PREF_KEY = 'ta_browser_notify'

// The Notification API is undefined in insecure contexts (HTTP on a non-localhost
// host) and some embedded webviews. Accessing `Notification.permission` there
// throws a ReferenceError — which, if it happens inside the WebSocket onmessage
// handler, would break analysis completion handling. Always feature-detect first.
function notifySupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function isBrowserNotifyEnabled(): boolean {
  if (!notifySupported()) return false
  return localStorage.getItem(PREF_KEY) === 'true' && Notification.permission === 'granted'
}

export async function requestBrowserNotifyPermission(): Promise<boolean> {
  if (!notifySupported()) return false
  const result = await Notification.requestPermission()
  const granted = result === 'granted'
  localStorage.setItem(PREF_KEY, granted ? 'true' : 'false')
  return granted
}

export function setBrowserNotifyPref(enabled: boolean): void {
  localStorage.setItem(PREF_KEY, enabled ? 'true' : 'false')
}

export function sendBrowserNotification(title: string, body: string, icon = '/favicon.ico'): void {
  try {
    if (!isBrowserNotifyEnabled()) return
    if (document.visibilityState === 'visible') return  // already in focus
    new Notification(title, { body, icon })
  } catch { /* ignore — never let a notification failure break the caller */ }
}
