import { MetaResponseAnalysisEventTypesItem } from '../api/generated/model'

/**
 * The event vocabulary of the analysis progress WebSocket.
 *
 * That socket carries no OpenAPI path, so the browser used to hand-write its
 * own idea of the payload and switch on a bare `string`. The backend declares
 * the union in `schemas/analysis_events.py` and publishes it through
 * `/api/meta`, which is how it reaches the generated client — this module just
 * gives it a name the page can use.
 */
export type AnalysisEventType = MetaResponseAnalysisEventTypesItem

export const ANALYSIS_EVENT_TYPES = Object.values(MetaResponseAnalysisEventTypesItem)

/**
 * The events `Analysis.tsx` actually acts on.
 *
 * Kept beside the branches rather than derived from them, because a list that
 * a test can read is the only way to notice an event the backend started
 * sending and the page quietly ignores — which is exactly how `stall_warning`
 * went unhandled while the user configured its timeout in Settings.
 *
 * Add an entry here only once the page does something with the event.
 */
export const HANDLED_ANALYSIS_EVENTS: readonly AnalysisEventType[] = [
  'status',
  'progress',
  'token',
  'stats',
  'report',
  'mental_model',
  'risk_metrics',
  'debate_bubble',
  'retry',
  'fallback',
  'node_error',
  'circuit_open',
  'stall_warning',
  'decision',
  'order_result',
  'complete',
  'error',
]
