import { useMetaGetMeta, getMetaGetMetaQueryKey } from '../api/generated/meta/meta'
import { queryClient } from '../api/queryClient'
import type { MetaResponse } from '../api/generated/model'

/**
 * The `/api/meta` payload, as the backend declares it.
 *
 * This used to be a hand-written mirror of the response — around eighty lines
 * of interfaces plus a `data as unknown as Meta` cast — because the endpoint
 * was once `response_model=dict[str, Any]` and OpenAPI described it as a
 * free-form object. It has a Pydantic model now, so the generated type is both
 * accurate and wider than the copy was: `chart_periods`, `order_actions`,
 * `order_statuses` and `sections` were missing from the hand-written version.
 */
export type Meta = MetaResponse

// Metadata is user-scoped (custom personas and tool/agent visibility are
// filtered by the API), shared by many components, and must not survive a
// logout. That used to be a hand-rolled module cache with a listener set, an
// in-flight promise and a generation counter guarding against a response from
// the previous account landing after login. TanStack Query provides the shared
// cache, the request de-duplication and the cancellation, so only the
// user-scoping policy lives here.

/** Clear all in-memory metadata associated with the authenticated account. */
export function clearMetaCache() {
  const queryKey = getMetaGetMetaQueryKey()
  // cancel before remove: an in-flight request started by the previous account
  // must not repopulate the cache after the switch.
  void queryClient.cancelQueries({ queryKey })
  queryClient.removeQueries({ queryKey })
}

export function triggerMetaRefetch() {
  return queryClient.invalidateQueries({ queryKey: getMetaGetMetaQueryKey() })
}

export function useMeta(): Meta | null {
  const { data } = useMetaGetMeta()
  return data ?? null
}
