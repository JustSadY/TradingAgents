import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import { useState } from 'react'
import type { ReactElement, ReactNode } from 'react'

/**
 * Render a component that uses Orval-generated TanStack Query hooks.
 *
 * Each call gets a fresh QueryClient so cached data never leaks between tests,
 * and retries are off so a deliberately failing request fails immediately
 * instead of stalling the test for the duration of the backoff.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

/** Wrapper for `renderHook`, which takes a component rather than a render fn. */
export function QueryWrapper({ children }: { children: ReactNode }) {
  const [client] = useState(createTestQueryClient)
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

export function renderWithQuery(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  const queryClient = createTestQueryClient()

  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) }
}

export default renderWithQuery
