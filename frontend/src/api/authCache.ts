import { queryClient } from './queryClient'

/**
 * Cancels requests from the previous auth scope before removing every query and
 * mutation entry. QueryClient.clear() removes both caches, so mutation results
 * and callbacks cannot be reused by the next signed-in user.
 *
 * The Orval mutator forwards TanStack's AbortSignal to axios. Cancelling first
 * therefore aborts transport work; clearing immediately afterwards also makes
 * a late non-abortable response belong to an orphaned Query instance rather
 * than the next user's cache entry.
 */
export function clearAuthenticatedCache(): void {
  void queryClient.cancelQueries()
  queryClient.clear()
}

/**
 * Awaitable variant for tests and flows that need an explicit cancellation
 * barrier before continuing.
 */
export async function clearAuthenticatedCacheAsync(): Promise<void> {
  await queryClient.cancelQueries()
  queryClient.clear()
}
