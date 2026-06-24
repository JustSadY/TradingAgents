const PREF_KEY = 'ta_browser_notify'





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
    if (document.visibilityState === 'visible') return
    const notification = new Notification(title, { body, icon })
    notification.onclick = () => {
      window.focus()
    }
  } catch (e) {
    // Notification API can throw on unsupported/denied environments — non-fatal.
    console.debug('Browser notification failed:', e)
  }
}

