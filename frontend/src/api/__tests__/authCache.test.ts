import { afterEach, describe, expect, it } from 'vitest'
import { queryClient } from '../queryClient'
import { clearAuthenticatedCacheAsync } from '../authCache'

afterEach(() => {
  queryClient.clear()
})

describe('authenticated TanStack cache isolation', () => {
  it('clears both query and mutation caches', async () => {
    queryClient.setQueryData(['alerts'], [{ id: 1 }])
    queryClient.getMutationCache().build(queryClient, {
      mutationKey: ['settings', 'save'],
      mutationFn: async () => ({ secret: 'old-user' }),
    })

    expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
    expect(queryClient.getMutationCache().getAll()).toHaveLength(1)

    await clearAuthenticatedCacheAsync()

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0)
  })

  it('does not let a late previous-user request overwrite the new-user cache', async () => {
    let resolveOld: ((value: string) => void) | undefined
    const oldRequest = queryClient.fetchQuery({
      queryKey: ['portfolio'],
      queryFn: () => new Promise<string>(resolve => { resolveOld = resolve }),
    })

    await Promise.resolve()
    await clearAuthenticatedCacheAsync()
    queryClient.setQueryData(['portfolio'], 'new-user')

    resolveOld?.('old-user')
    await oldRequest.catch(() => undefined)
    await Promise.resolve()

    expect(queryClient.getQueryData(['portfolio'])).toBe('new-user')
  })
})
