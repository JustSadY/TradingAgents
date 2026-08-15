import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithQuery } from '../../test/renderWithQuery'
import { PermissionsProvider, usePermissions } from '../PermissionsContext'
import { AuthProvider } from '../AuthContext'
import type { ReactNode } from 'react'

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  const get = vi.fn().mockResolvedValue({ data: { allowed_pages: ['dashboard', 'analysis'] } })
  const post = vi.fn().mockResolvedValue({ data: {} })
  // The generated permissions query calls axios(config); route it to the mocks.
  const instance = Object.assign(
    vi.fn((config: { url?: string; method?: string } = {}) =>
      String(config.method ?? 'get').toLowerCase() === 'get' ? get(config.url, config) : post(config.url, config),
    ),
    {
      ...(actual as any).default,
      get,
      post,
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  )
  return { ...actual, default: instance }
})

function TestConsumer() {
  const { allowedPages, loading, canAccess, refresh } = usePermissions()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="pages">{allowedPages.join(',')}</span>
      <span data-testid="can-dashboard">{String(canAccess('dashboard'))}</span>
      <span data-testid="can-admin">{String(canAccess('admin'))}</span>
      <span data-testid="can-settings">{String(canAccess('settings'))}</span>
      <span data-testid="can-profile">{String(canAccess('profile'))}</span>
      <button data-testid="refresh" onClick={refresh}>Refresh</button>
    </div>
  )
}

function renderWithProviders(children: ReactNode) {
  // Set up a valid non-expired token so AuthContext initializes authenticated
  const payload = { sub: 'testuser', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 }
  const token = `header.${btoa(JSON.stringify(payload))}.signature`
  localStorage.setItem('ta_access', token)
  return renderWithQuery(
    <AuthProvider>
      <PermissionsProvider>{children}</PermissionsProvider>
    </AuthProvider>
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('PermissionsContext', () => {
  it('fetches allowed pages on mount', async () => {
    renderWithProviders(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('pages')).toHaveTextContent('dashboard,analysis')
    })
  })

  it('allows ALWAYS_ALLOWED pages (settings, profile) regardless', async () => {
    renderWithProviders(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('can-settings')).toHaveTextContent('true')
      expect(screen.getByTestId('can-profile')).toHaveTextContent('true')
    })
  })

  it('grants access to fetched allowed pages', async () => {
    renderWithProviders(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('can-dashboard')).toHaveTextContent('true')
    })
  })

  it('denies access to non-allowed pages for non-admin', async () => {
    renderWithProviders(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('can-admin')).toHaveTextContent('false')
    })
  })

  it('throws when used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => renderWithQuery(<TestConsumer />)).toThrow('usePermissions must be used within a PermissionsProvider')
    consoleError.mockRestore()
  })

  it('returns empty pages when unauthenticated', async () => {
    localStorage.removeItem('ta_access')
    function NoAuthWrapper({ children }: { children: ReactNode }) {
      return (
        <AuthProvider>
          <PermissionsProvider>{children}</PermissionsProvider>
        </AuthProvider>
      )
    }
    renderWithQuery(<NoAuthWrapper><TestConsumer /></NoAuthWrapper>)
    await waitFor(() => {
      expect(screen.getByTestId('pages')).toHaveTextContent('')
    })
  })
})
