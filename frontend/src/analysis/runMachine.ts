import { setup } from 'xstate'
import type { RunStatus } from './runStorage'

/**
 * The lifecycle of one analysis run.
 *
 * The page used to track this in three pieces of React state — `running`,
 * `runStatus` and `stopping` — set from twenty-odd call sites that each had to
 * remember to keep them agreeing. Nothing enforced the agreement, and the
 * combinations that should never occur (`running` false while `runStatus` is
 * `'running'`, or `stopping` true with nothing running) were reachable.
 *
 * The states are the ones the UI actually distinguishes:
 *
 *   idle ──START──▶ running ──COMPLETE──▶ done
 *                    │  │  └──FAIL─────▶ failed
 *                    │  └──STOP──▶ stopping ──STOPPED──▶ idle
 *                    │                   └──STOP_REFUSED──▶ running
 *                    └──RESET──▶ idle
 *
 * `stopping` is its own state rather than a flag because a refused Stop has to
 * return to `running`: the worker keeps consuming LLM and API budget until the
 * server accepts the cancellation, so the UI must not pretend it stopped.
 *
 * A terminal event can arrive while a Stop request is in flight, which is why
 * `stopping` accepts COMPLETE and FAIL — the real outcome wins over the Stop.
 */

export type RunState = 'idle' | 'running' | 'stopping' | 'done' | 'failed'

export type RunEvent =
  | { type: 'START' }
  | { type: 'COMPLETE' }
  | { type: 'FAIL' }
  | { type: 'STOP' }
  | { type: 'STOPPED' }
  | { type: 'STOP_REFUSED' }
  | { type: 'RESET' }

export const runMachine = setup({
  types: {} as { events: RunEvent },
}).createMachine({
  id: 'analysisRun',
  initial: 'idle',
  states: {
    idle: {
      on: {
        START: 'running',
        // Mount loads the last completed analysis from the server, so a run can
        // reach `done` without this page ever having watched it run.
        COMPLETE: 'done',
      },
    },
    running: {
      on: {
        COMPLETE: 'done',
        FAIL: 'failed',
        STOP: 'stopping',
        // A cancellation this page did not ask for — another device, or an
        // operator — arrives as a plain terminal event while still `running`.
        STOPPED: 'idle',
        RESET: 'idle',
        // Starting a new run while one is live replaces it.
        START: { target: 'running', reenter: true },
      },
    },
    stopping: {
      on: {
        STOPPED: 'idle',
        // The server would not accept the cancellation; the worker is still
        // running, so say so rather than showing a stopped run.
        STOP_REFUSED: 'running',
        // A terminal event won the race with the Stop request.
        COMPLETE: 'done',
        FAIL: 'failed',
      },
    },
    done: {
      on: { START: 'running', RESET: 'idle' },
    },
    failed: {
      on: { START: 'running', RESET: 'idle' },
    },
  },
})

/** True while a run occupies the page, including one being stopped. */
export function isRunActive(state: RunState): boolean {
  return state === 'running' || state === 'stopping'
}

/**
 * The persisted status for `runStorage`, which has four values rather than
 * five: a run being stopped is still a running run as far as a reload is
 * concerned.
 */
export function persistedStatus(state: RunState): RunStatus {
  if (state === 'running' || state === 'stopping') return 'running'
  if (state === 'failed') return 'error'
  return state
}

/** The reverse, for restoring a persisted run on load. */
export function stateForPersisted(status: RunStatus): RunState {
  return status === 'error' ? 'failed' : status
}

/**
 * A starting snapshot for a page mounting onto an already-persisted run, so
 * the first render shows the restored state instead of flashing `idle` and
 * transitioning out of it in an effect.
 */
export function snapshotForPersisted(status: RunStatus) {
  return runMachine.resolveState({ value: stateForPersisted(status) })
}
