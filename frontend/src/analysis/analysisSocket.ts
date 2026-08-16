import axios from 'axios'
import { isRecord } from '../utils/isRecord'

/**
 * The analysis progress WebSocket: how it is addressed, authenticated, and
 * retired, plus the probe that decides whether reconnecting is worth it.
 *
 * Lifted out of `pages/Analysis.tsx` unchanged. None of it needs React, and
 * the close and reconnect rules are the subtle part of that page — they are
 * easier to see, and to test, on their own.
 */

export const WS_KEEPALIVE_INTERVAL_MS = 20_000
export const WS_KEEPALIVE_MESSAGE = '__tradingagents_keepalive__'
export const WS_NORMAL_CLOSE_CODE = 1000
export const WS_CONNECTING = 0
export const WS_OPEN = 1
export const WS_CLOSING = 2
export const WS_CLOSED = 3
export const WS_MAX_RECONNECT_RETRIES = 3

// Build an absolute ws(s)://host URL rather than a bare relative path —
// `new WebSocket('/path')` (protocol-relative-by-omission) is only reliably
// supported by fairly recent browsers; older ones throw a SyntaxError.
export function analysisWsUrl(taskId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/analysis/${taskId}`
}

// Native browser WebSockets cannot set Authorization. Carry the JWT in a
// private handshake subprotocol instead of the URL so proxy/access logs never
// receive a bearer token in their request line. The fixed application
// protocol is the only value the backend selects in its 101 response; it
// makes the handshake valid for strict WebSocket clients without echoing JWT.
export const WS_APPLICATION_SUBPROTOCOL = 'tradingagents.v1'
export const WS_TOKEN_SUBPROTOCOL_PREFIX = 'tradingagents.jwt.'

export function openAnalysisWebSocket(taskId: string, token: string | null): WebSocket {
  const url = analysisWsUrl(taskId)
  const protocols = [WS_APPLICATION_SUBPROTOCOL]
  if (token) protocols.push(`${WS_TOKEN_SUBPROTOCOL_PREFIX}${token}`)
  return new WebSocket(url, protocols)
}

/** Retire a client-owned socket with a normal close frame when possible. */
export function closeAnalysisWebSocket(socket: WebSocket, reason: string): void {
  socket.onopen = null
  socket.onmessage = null
  socket.onerror = null
  socket.onclose = null

  const closeNormally = () => {
    if (socket.readyState === WS_CLOSING || socket.readyState === WS_CLOSED) return
    try {
      socket.close(WS_NORMAL_CLOSE_CODE, reason)
    } catch {
      // The browser owns the final close event.
    }
  }

  // Calling close while CONNECTING aborts the handshake and can produce an
  // abnormal 1005/1006 pair, so wait until the connection opens.
  if (socket.readyState === WS_CONNECTING) {
    socket.onopen = closeNormally
    return
  }

  closeNormally()
}

/**
 * ``/api/analysis/active`` is the authoritative live-task registry.  A
 * WebSocket can close after the worker has already reached a terminal state
 * (for example if it could not flush its final event), so its close alone is
 * not enough evidence that the browser should keep reconnecting.
 *
 * ``null`` means the probe itself was unusable.  In that case callers retain
 * the bounded reconnect behaviour rather than treating a transient API
 * failure as a failed analysis.
 */
export function activeTaskState(value: unknown, taskId: string): boolean | null {
  if (!Array.isArray(value)) return null
  return value.some(task => isRecord(task) && task.task_id === taskId)
}

export type ActiveTaskProbeState = 'active' | 'inactive' | 'unauthorized' | 'forbidden' | 'unavailable'

/**
 * Resolve whether a task is still live before reconnecting its WebSocket.
 * A WebSocket close is transport state, not job state: blindly reconnecting
 * after a worker has already reached a terminal state causes noisy connection
 * churn and makes the UI look as if it is repeatedly restarting.
 *
 * This deliberately keeps a direct axios call rather than a generated hook: it
 * is a reconnect-policy probe with its own 2s timeout that must classify
 * 401/403/unavailable itself, not server state worth caching.
 */
export async function probeActiveTask(taskId: string): Promise<ActiveTaskProbeState> {
  try {
    const { data } = await axios.get('/api/analysis/active', { timeout: 2_000 })
    const state = activeTaskState(data, taskId)
    if (state === true) return 'active'
    if (state === false) return 'inactive'
    return 'unavailable'
  } catch (error) {
    // Axios has already attempted its normal token refresh. Retrying a
    // WebSocket with an explicitly rejected session/permission cannot help.
    const status = (error as { response?: { status?: number } }).response?.status
    if (status === 401) return 'unauthorized'
    if (status === 403) return 'forbidden'
    return 'unavailable'
  }
}
