import { describe, expect, it } from 'vitest'
import { createActor } from 'xstate'

import {
  isRunActive,
  persistedStatus,
  runMachine,
  snapshotForPersisted,
  stateForPersisted,
  type RunEvent,
  type RunState,
} from '../runMachine'

/** Feed a fresh actor a sequence of events and report where it lands. */
function after(...events: RunEvent['type'][]): RunState {
  const actor = createActor(runMachine).start()
  for (const type of events) actor.send({ type } as RunEvent)
  const value = actor.getSnapshot().value as RunState
  actor.stop()
  return value
}

describe('runMachine', () => {
  it('starts idle', () => {
    expect(after()).toBe('idle')
  })

  it('runs, then completes or fails', () => {
    expect(after('START')).toBe('running')
    expect(after('START', 'COMPLETE')).toBe('done')
    expect(after('START', 'FAIL')).toBe('failed')
  })

  it('stays running until the server accepts the cancellation', () => {
    // The whole reason `stopping` is a state and not a flag: a refused Stop
    // leaves a worker burning LLM and API budget, so the UI has to go back to
    // showing a live run rather than a stopped one.
    expect(after('START', 'STOP')).toBe('stopping')
    expect(after('START', 'STOP', 'STOP_REFUSED')).toBe('running')
    expect(after('START', 'STOP', 'STOPPED')).toBe('idle')
  })

  it('lets a real outcome win the race against a Stop request', () => {
    expect(after('START', 'STOP', 'COMPLETE')).toBe('done')
    expect(after('START', 'STOP', 'FAIL')).toBe('failed')
  })

  it('accepts a cancellation this page did not ask for', () => {
    // Another device or an operator can cancel the run; it arrives as a
    // terminal socket event with no Stop request of ours in flight.
    expect(after('START', 'STOPPED')).toBe('idle')
  })

  it('restarts from any settled state', () => {
    expect(after('START', 'COMPLETE', 'START')).toBe('running')
    expect(after('START', 'FAIL', 'START')).toBe('running')
    expect(after('START', 'START')).toBe('running')
  })

  it('clears a settled run back to idle', () => {
    expect(after('START', 'COMPLETE', 'RESET')).toBe('idle')
    expect(after('START', 'FAIL', 'RESET')).toBe('idle')
  })

  it('shows a completed analysis loaded on mount without a run preceding it', () => {
    expect(after('COMPLETE')).toBe('done')
  })

  it('ignores events that do not apply, rather than stalling', () => {
    // A late STOP_REFUSED after the run already finished must not revive it.
    expect(after('START', 'COMPLETE', 'STOP_REFUSED')).toBe('done')
    expect(after('STOP')).toBe('idle')
    expect(after('START', 'FAIL', 'COMPLETE')).toBe('failed')
  })
})

describe('run state projections', () => {
  it('treats a run being stopped as still occupying the page', () => {
    expect(isRunActive('running')).toBe(true)
    expect(isRunActive('stopping')).toBe(true)
    expect(isRunActive('idle')).toBe(false)
    expect(isRunActive('done')).toBe(false)
    expect(isRunActive('failed')).toBe(false)
  })

  it('persists a run being stopped as still running', () => {
    // A reload during a Stop must resume the run, not show it as finished.
    expect(persistedStatus('stopping')).toBe('running')
    expect(persistedStatus('running')).toBe('running')
    expect(persistedStatus('failed')).toBe('error')
    expect(persistedStatus('done')).toBe('done')
    expect(persistedStatus('idle')).toBe('idle')
  })

  it('round-trips every persisted status', () => {
    for (const status of ['idle', 'running', 'done', 'error'] as const) {
      expect(persistedStatus(stateForPersisted(status))).toBe(status)
    }
  })

  it('mounts straight into the persisted state', () => {
    // Without this the page would flash `idle` on every reload of a live run.
    expect(snapshotForPersisted('running').value).toBe('running')
    expect(snapshotForPersisted('error').value).toBe('failed')
    expect(snapshotForPersisted('done').value).toBe('done')
    expect(snapshotForPersisted('idle').value).toBe('idle')
  })

  it('resumes a restored run rather than starting a second one', () => {
    const actor = createActor(runMachine, { snapshot: snapshotForPersisted('running') }).start()
    actor.send({ type: 'COMPLETE' })
    expect(actor.getSnapshot().value).toBe('done')
    actor.stop()
  })
})
