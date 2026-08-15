import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import {
  WS_APPLICATION_SUBPROTOCOL,
  WS_CLOSED,
  WS_CLOSING,
  WS_CONNECTING,
  WS_NORMAL_CLOSE_CODE,
  WS_OPEN,
  activeTaskState,
  analysisWsUrl,
  closeAnalysisWebSocket,
  openAnalysisWebSocket,
  probeActiveTask,
} from '../analysisSocket'

/** Just enough socket to exercise the close rules. */
class FakeSocket {
  onopen: (() => void) | null = null
  onmessage: (() => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  closeCalls: Array<[number | undefined, string | undefined]> = []

  constructor(public readyState: number) {}

  close(code?: number, reason?: string) {
    this.closeCalls.push([code, reason])
  }
}

const asSocket = (fake: FakeSocket) => fake as unknown as WebSocket

describe('analysisWsUrl', () => {
  it('builds an absolute URL against the current host', () => {
    // A bare relative path is only reliably accepted by recent browsers;
    // older ones throw a SyntaxError on `new WebSocket('/path')`.
    expect(analysisWsUrl('task-1')).toBe(`ws://${window.location.host}/ws/analysis/task-1`)
  })
})

describe('openAnalysisWebSocket', () => {
  const created: Array<[string, string[] | undefined]> = []

  beforeEach(() => {
    created.length = 0
    vi.stubGlobal('WebSocket', class {
      constructor(url: string, protocols?: string[]) {
        created.push([url, protocols])
      }
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('carries the token in a subprotocol, never in the URL', () => {
    // A token in the URL lands in every proxy and access log request line.
    openAnalysisWebSocket('task-1', 'jwt-value')

    const [url, protocols] = created[0]
    expect(url).not.toContain('jwt-value')
    expect(protocols).toEqual([WS_APPLICATION_SUBPROTOCOL, 'tradingagents.jwt.jwt-value'])
  })

  it('still offers the application protocol when there is no token', () => {
    openAnalysisWebSocket('task-1', null)
    expect(created[0][1]).toEqual([WS_APPLICATION_SUBPROTOCOL])
  })
})

describe('closeAnalysisWebSocket', () => {
  it('detaches every handler so a late event cannot reach the page', () => {
    const socket = new FakeSocket(WS_OPEN)
    socket.onmessage = () => {}
    socket.onerror = () => {}
    socket.onclose = () => {}

    closeAnalysisWebSocket(asSocket(socket), 'done')

    expect(socket.onmessage).toBeNull()
    expect(socket.onerror).toBeNull()
    expect(socket.onclose).toBeNull()
  })

  it('closes an open socket with a normal close code', () => {
    const socket = new FakeSocket(WS_OPEN)
    closeAnalysisWebSocket(asSocket(socket), 'done')
    expect(socket.closeCalls).toEqual([[WS_NORMAL_CLOSE_CODE, 'done']])
  })

  it('waits for a connecting socket to open before closing it', () => {
    // Closing mid-handshake aborts it and can produce an abnormal 1005/1006.
    const socket = new FakeSocket(WS_CONNECTING)

    closeAnalysisWebSocket(asSocket(socket), 'superseded')
    expect(socket.closeCalls).toEqual([])

    socket.readyState = WS_OPEN
    socket.onopen?.()
    expect(socket.closeCalls).toEqual([[WS_NORMAL_CLOSE_CODE, 'superseded']])
  })

  it.each([
    ['closing', WS_CLOSING],
    ['closed', WS_CLOSED],
  ])('does not re-close an already %s socket', (_label, readyState) => {
    const socket = new FakeSocket(readyState)
    closeAnalysisWebSocket(asSocket(socket), 'done')
    expect(socket.closeCalls).toEqual([])
  })

  it('survives a browser that throws from close', () => {
    const socket = new FakeSocket(WS_OPEN)
    socket.close = () => { throw new Error('already gone') }

    expect(() => closeAnalysisWebSocket(asSocket(socket), 'done')).not.toThrow()
  })
})

describe('activeTaskState', () => {
  it('finds the task in the registry', () => {
    expect(activeTaskState([{ task_id: 'a' }, { task_id: 'b' }], 'b')).toBe(true)
  })

  it('reports a missing task as finished', () => {
    expect(activeTaskState([{ task_id: 'a' }], 'b')).toBe(false)
  })

  it.each([null, undefined, {}, 'nope'])('returns null for an unusable payload %s', value => {
    // Distinct from false: a broken probe must not be read as a failed run.
    expect(activeTaskState(value, 'b')).toBeNull()
  })
})

describe('probeActiveTask', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reports a listed task as active', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: [{ task_id: 'a' }] })
    await expect(probeActiveTask('a')).resolves.toBe('active')
  })

  it('reports an unlisted task as inactive', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: [] })
    await expect(probeActiveTask('a')).resolves.toBe('inactive')
  })

  it('reports an unreadable payload as unavailable, not as a finished run', async () => {
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { not: 'a list' } })
    await expect(probeActiveTask('a')).resolves.toBe('unavailable')
  })

  it.each([
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [500, 'unavailable'],
  ])('classifies HTTP %s as %s', async (status, expected) => {
    // 401/403 are terminal for a reconnect: axios has already tried its
    // refresh, so retrying the socket cannot help.
    vi.spyOn(axios, 'get').mockRejectedValue({ response: { status } })
    await expect(probeActiveTask('a')).resolves.toBe(expected)
  })

  it('treats a network failure as unavailable', async () => {
    vi.spyOn(axios, 'get').mockRejectedValue(new Error('offline'))
    await expect(probeActiveTask('a')).resolves.toBe('unavailable')
  })
})
