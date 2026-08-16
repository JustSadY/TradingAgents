import { beforeEach, describe, expect, it } from 'vitest'
import {
  STORAGE_KEY,
  TASK_KEY,
  clearTaskMarkerFor,
  emptyRun,
  hasValidRunningTask,
  loadRunState,
} from '../runStorage'

beforeEach(() => {
  sessionStorage.clear()
})

describe('hasValidRunningTask', () => {
  it('accepts a marker naming a task', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'abc' }))
    expect(hasValidRunningTask()).toBe(true)
  })

  it.each([
    ['malformed JSON', 'not json'],
    ['a marker with no task id', '{}'],
    ['a blank task id', '{"taskId":"   "}'],
    ['an array', '[1]'],
  ])('rejects and clears %s', (_label, raw) => {
    sessionStorage.setItem(TASK_KEY, raw)

    expect(hasValidRunningTask()).toBe(false)
    // Left in place, a bad marker would keep every future load claiming the
    // run is still going.
    expect(sessionStorage.getItem(TASK_KEY)).toBeNull()
  })
})

describe('clearTaskMarkerFor', () => {
  it('clears the marker when it belongs to the abandoned task', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'old' }))
    clearTaskMarkerFor('old')
    expect(sessionStorage.getItem(TASK_KEY)).toBeNull()
  })

  it('leaves a newer task alone when a late response abandons an older one', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'new' }))
    clearTaskMarkerFor('old')
    expect(sessionStorage.getItem(TASK_KEY)).toBe(JSON.stringify({ taskId: 'new' }))
  })

  it('clears an unreadable marker', () => {
    sessionStorage.setItem(TASK_KEY, 'not json')
    clearTaskMarkerFor('old')
    expect(sessionStorage.getItem(TASK_KEY)).toBeNull()
  })
})

describe('loadRunState', () => {
  it('starts empty when nothing was persisted', () => {
    expect(loadRunState()).toEqual(emptyRun())
  })

  it('restores a completed run as it was left', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      ticker: 'NVDA',
      date: '2026-08-01',
      assetType: 'stock',
      runStatus: 'done',
      signal: 'Buy',
      reports: { market_report: 'text' },
      log: ['line'],
      activeSection: 'market_report',
      analysisId: 12,
      liveDebate: [{ sender: 'Bull', content: 'Buy', type: 'bull' }],
    }))

    const run = loadRunState()

    expect(run.ticker).toBe('NVDA')
    expect(run.runStatus).toBe('done')
    expect(run.reports).toEqual({ market_report: 'text' })
    expect(run.analysisId).toBe(12)
    expect(run.liveDebate).toHaveLength(1)
  })

  it('downgrades a persisted running status when no task is actually live', () => {
    // Otherwise a run interrupted by a crash or a closed tab comes back
    // looking like it is still in progress, and never finishes.
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ticker: 'NVDA', runStatus: 'running' }))

    expect(loadRunState().runStatus).toBe('idle')
  })

  it('keeps running when the task marker says the task is live', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'abc' }))
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ticker: 'NVDA', runStatus: 'done' }))

    expect(loadRunState().runStatus).toBe('running')
  })

  it('reports running from the marker alone when no run was persisted', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'abc' }))

    expect(loadRunState().runStatus).toBe('running')
  })

  it('keeps a persisted error even while a task marker exists', () => {
    sessionStorage.setItem(TASK_KEY, JSON.stringify({ taskId: 'abc' }))
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ runStatus: 'error' }))

    expect(loadRunState().runStatus).toBe('error')
  })

  it.each([
    ['malformed JSON', 'not json'],
    ['a non-object', '"a string"'],
    ['an array', '[1,2]'],
  ])('falls back to an empty run for %s', (_label, raw) => {
    sessionStorage.setItem(STORAGE_KEY, raw)
    expect(loadRunState()).toEqual(emptyRun())
  })

  it('re-validates every field rather than trusting the stored shape', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      ticker: 42,
      assetType: '   ',
      signal: { not: 'a string' },
      reports: 'not a record',
      log: ['ok', 7, null],
      analysisId: -3,
      liveDebate: 'nope',
      orderResult: { outcome: 'nonsense' },
    }))

    const run = loadRunState()

    expect(run.ticker).toBe('')
    expect(run.assetType).toBe('stock')
    expect(run.signal).toBeNull()
    expect(run.reports).toEqual({})
    expect(run.log).toEqual(['ok'])
    expect(run.analysisId).toBeNull()
    expect(run.liveDebate).toEqual([])
    expect(run.orderResult).toBeNull()
  })

  it('restores an order result against the run it belongs to', () => {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      ticker: 'nvda',
      orderResult: { outcome: 'filled', quantity: 2 },
    }))

    expect(loadRunState().orderResult).toMatchObject({ outcome: 'filled', ticker: 'NVDA', quantity: 2 })
  })
})
