import { QueryClient } from '@tanstack/react-query'

/**
 * Shared TanStack Query client.
 *
 * Retry is deliberately low: the axios interceptors in AuthContext already
 * handle 401 by refreshing and replaying the request, and surface 5xx as a
 * toast. Letting TanStack retry three times on top of that multiplies both the
 * request count and the number of toasts a single outage produces.
 *
 * 4xx are never retried — they are deterministic and retrying only delays the
 * error reaching the user.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = (error as { response?: { status?: number } })?.response?.status
        if (status !== undefined && status >= 400 && status < 500) return false
        return failureCount < 1
      },
    },
    mutations: {
      retry: false,
    },
  },
})

export default queryClient
