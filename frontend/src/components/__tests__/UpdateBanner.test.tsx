import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import UpdateBanner from '../UpdateBanner'

vi.mock('../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../test/i18nMock')).useTranslationMock,
}))

const mocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
  statusQuery: {
    data: null as Record<string, unknown> | null,
    dataUpdatedAt: 1,
    isError: false,
  },
  statusOptions: null as Record<string, unknown> | null,
  applyMutate: vi.fn(),
  applyPending: false,
  applySuccess: undefined as (() => void) | undefined,
  applyError: undefined as ((error: unknown) => void) | undefined,
  notify: vi.fn(),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mocks.useAuth(),
}))

vi.mock('../../api/generated/update/update', () => ({
  getUpdateUpdateStatusQueryKey: () => ['/api/update/status'],
  useUpdateUpdateStatus: (options: Record<string, unknown>) => {
    mocks.statusOptions = options
    return mocks.statusQuery
  },
  useUpdateUpdateApply: (options: { mutation?: { onSuccess?: () => void; onError?: (error: unknown) => void } }) => {
    mocks.applySuccess = options.mutation?.onSuccess
    mocks.applyError = options.mutation?.onError
    return { mutate: mocks.applyMutate, isPending: mocks.applyPending }
  },
}))

vi.mock('../../utils/notify', () => ({
  notify: (...args: unknown[]) => mocks.notify(...args),
}))

const defaultStatus = {
  git: true,
  update_supported: true,
  update_available: true,
  updating: false,
  current_short: 'abc1234',
  latest_short: 'def5678',
  behind: 3,
  commits: ['fix: thing', 'feat: other'],
  last_update: undefined,
}

function renderBanner() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  const view = render(
    <QueryClientProvider client={queryClient}>
      <UpdateBanner />
    </QueryClientProvider>,
  )
  return { ...view, queryClient, invalidateSpy }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.clearAllMocks()
  mocks.useAuth.mockReturnValue({ isOwner: true })
  mocks.statusQuery.data = defaultStatus
  mocks.statusQuery.dataUpdatedAt += 1
  mocks.statusQuery.isError = false
  mocks.statusOptions = null
  mocks.applyPending = false
  mocks.applySuccess = undefined
  mocks.applyError = undefined
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('UpdateBanner', () => {
  it('uses the generated status hook with controlled polling', () => {
    renderBanner()
    const query = mocks.statusOptions?.query as Record<string, unknown>
    expect(query.retry).toBe(false)
    expect(query.refetchOnWindowFocus).toBe(false)
    expect(query.refetchInterval).toBe(60 * 60 * 1000)
  })

  it('renders nothing when update_supported is false', () => {
    mocks.statusQuery.data = { ...defaultStatus, update_supported: false }
    const { container } = renderBanner()
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing for non-owner when update is available', () => {
    mocks.useAuth.mockReturnValue({ isOwner: false })
    renderBanner()
    expect(screen.queryByText(/A new version is available/)).not.toBeInTheDocument()
  })

  it('shows update available banner for owner', () => {
    renderBanner()
    expect(screen.getByText(/A new version is available/)).toBeInTheDocument()
    expect(screen.getByText(/3 commits behind/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Update/ })).toBeInTheDocument()
  })

  it('shows updating state when server reports an active update', () => {
    mocks.statusQuery.data = { ...defaultStatus, updating: true }
    renderBanner()
    expect(screen.getByText(/Updating —/)).toBeInTheDocument()
  })

  it('dismisses the available update banner', async () => {
    const user = userEvent.setup()
    renderBanner()
    await user.click(screen.getByTitle('Dismiss'))
    expect(screen.queryByText(/A new version is available/)).not.toBeInTheDocument()
  })

  it('starts the generated update mutation and invalidates status on success', async () => {
    const user = userEvent.setup()
    const { invalidateSpy } = renderBanner()

    await user.click(screen.getByRole('button', { name: /Update/ }))
    expect(window.confirm).toHaveBeenCalled()
    expect(mocks.applyMutate).toHaveBeenCalledTimes(1)

    mocks.applySuccess?.()
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['/api/update/status'] })
    })
    expect(mocks.notify).toHaveBeenCalledWith('info', expect.stringContaining('Update started'), 'Update', 'owner')
  })

  it('reports generated update mutation errors through notify', async () => {
    const user = userEvent.setup()
    renderBanner()

    await user.click(screen.getByRole('button', { name: /Update/ }))
    mocks.applyError?.({ response: { data: { detail: 'update failed' } } })

    expect(mocks.notify).toHaveBeenCalledWith('error', 'update failed', 'Update', 'owner')
  })
})
