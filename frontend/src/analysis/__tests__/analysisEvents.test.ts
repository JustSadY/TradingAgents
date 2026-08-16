import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ANALYSIS_EVENT_TYPES, HANDLED_ANALYSIS_EVENTS, type AnalysisEventType } from '../analysisEvents'

/**
 * The analysis WebSocket is the one API boundary with no OpenAPI path, so it
 * is the one place where the backend can start sending something the browser
 * silently drops. `stall_warning` did exactly that: emitted with the user's
 * own configured timeout behind it, and never rendered.
 *
 * The backend declares the vocabulary and publishes it through `/api/meta`, so
 * these assertions run against the generated client rather than a copy of it.
 */

const PAGE = readFileSync(join(import.meta.dirname, '../../pages/Analysis.tsx'), 'utf8')

describe('analysis event coverage', () => {
  it('handles every event type the backend declares', () => {
    const unhandled = ANALYSIS_EVENT_TYPES.filter(type => !HANDLED_ANALYSIS_EVENTS.includes(type))

    expect(unhandled).toEqual([])
  })

  it('claims to handle only event types that exist', () => {
    const invented = HANDLED_ANALYSIS_EVENTS.filter(type => !ANALYSIS_EVENT_TYPES.includes(type))

    expect(invented).toEqual([])
  })

  it('has a branch in the page for each type it claims to handle', () => {
    // Guards the list against becoming a wish: an entry added here without a
    // branch would otherwise make the coverage assertion above pass on a lie.
    const missingBranch = HANDLED_ANALYSIS_EVENTS.filter(
      type => !PAGE.includes(`ev.type === '${type}'`),
    )

    expect(missingBranch).toEqual([])
  })

  it('finds the vocabulary at all, so the assertions are not vacuous', () => {
    expect(ANALYSIS_EVENT_TYPES.length).toBeGreaterThan(10)
  })

  it('renders a stall with its own message rather than a heartbeat', () => {
    // The regression this whole contract exists to prevent.
    expect(PAGE).toContain("ev.type === 'stall_warning'")
    expect(PAGE).toContain('analysis.stalled')
  })
})

describe('AnalysisEventType', () => {
  it('is the generated union, not a local copy', () => {
    // A hand-written duplicate would compile but stop tracking the backend.
    const type: AnalysisEventType = 'stall_warning'
    expect(ANALYSIS_EVENT_TYPES).toContain(type)
  })
})
