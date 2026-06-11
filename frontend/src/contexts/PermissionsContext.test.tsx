import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import axios from 'axios'
import { PermissionsProvider, usePermissions } from './PermissionsContext'
import { useAuth } from './AuthContext'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('./AuthContext', () => ({ useAuth: vi.fn() }))

const mockedGet = vi.mocked(axios.get)
const mockedUseAuth = vi.mocked(useAuth)

function authState(overrides: Partial<ReturnType<typeof useAuth>>) {
  return {
    user: 'someone',
    role: 'user',
    isAdmin: false,
    isOwner: false,
    isAuthenticated: true,
    login: async () => {},
    logout: () => {},
    loading: false,
    ...overrides,
  }
}

function Probe() {
  const { canAccess, loading } = usePermissions()
  if (loading) return <div>loading</div>
  return (
    <div data-testid="access">
      {JSON.stringify({
        dashboard: canAccess('dashboard'),
        trading: canAccess('trading'),
        settings: canAccess('settings'),
        profile: canAccess('profile'),
      })}
    </div>
  )
}

async function renderAccess() {
  render(
    <PermissionsProvider>
      <Probe />
    </PermissionsProvider>
  )
  const el = await screen.findByTestId('access')
  return JSON.parse(el.textContent ?? '{}')
}

describe('PermissionsProvider', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('grants only fetched pages plus settings/profile to regular users', async () => {
    mockedUseAuth.mockReturnValue(authState({}))
    mockedGet.mockResolvedValue({ data: { allowed_pages: ['dashboard'] } })

    const access = await renderAccess()
    expect(access).toEqual({ dashboard: true, trading: false, settings: true, profile: true })
  })

  it('grants every page to admins regardless of fetched permissions', async () => {
    mockedUseAuth.mockReturnValue(authState({ isAdmin: true, role: 'admin' }))
    mockedGet.mockResolvedValue({ data: { allowed_pages: [] } })

    const access = await renderAccess()
    expect(access).toEqual({ dashboard: true, trading: true, settings: true, profile: true })
  })

  it('falls back to settings/profile when the permissions fetch fails', async () => {
    mockedUseAuth.mockReturnValue(authState({}))
    mockedGet.mockRejectedValue(new Error('network down'))

    const access = await renderAccess()
    expect(access).toEqual({ dashboard: false, trading: false, settings: true, profile: true })
  })

  it('does not fetch and denies app pages when unauthenticated', async () => {
    mockedUseAuth.mockReturnValue(authState({ isAuthenticated: false, user: null }))

    const access = await renderAccess()
    expect(mockedGet).not.toHaveBeenCalled()
    expect(access.dashboard).toBe(false)
    expect(access.settings).toBe(true)
  })
})
