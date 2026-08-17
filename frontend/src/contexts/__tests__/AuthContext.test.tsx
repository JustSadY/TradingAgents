import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axios from 'axios'
import { AuthProvider, useAuth, getAccessToken } from '../AuthContext'
import { queryClient } from '../../api/queryClient'
import type { ReactNode } from 'react'

// AuthContext registers its axios interceptors once, at module import time.
// Capture the response-error handler here, before beforeEach's clearAllMocks()
// wipes the recorded call and leaves mock.calls empty.
const responseErrorHandler = vi.mocked(axios.interceptors.response.use).mock.calls.at(-1)?.[1]

function jwt(sub: string, role = 'user', seconds = 3600) {
  const payload = { sub, role, exp: Math.floor(Date.now() / 1000) + seconds }
  return `header.${btoa(JSON.stringify(payload))}.signature`
}

function TestConsumer() {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="user">{auth.user ?? 'null'}</span>
      <span data-testid="role">{auth.role ?? 'null'}</span>
      <span data-testid="isAdmin">{String(auth.isAdmin)}</span>
      <span data-testid="isOwner">{String(auth.isOwner)}</span>
      <span data-testid="isAuthenticated">{String(auth.isAuthenticated)}</span>
      <span data-testid="loading">{String(auth.loading)}</span>
      <button data-testid="login" onClick={() => auth.login('test', 'pass')}>Login</button>
      <button data-testid="logout" onClick={() => auth.logout()}>Logout</button>
    </div>
  )
}

function renderWithAuth(children: ReactNode) {
  return render(<AuthProvider>{children}</AuthProvider>)
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  queryClient.clear()
  vi.clearAllMocks()
  vi.mocked(axios.post).mockRejectedValue(new Error('no refresh cookie'))
})

afterEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  queryClient.clear()
})

describe('AuthContext', () => {
  it('shows unauthenticated after refresh-cookie bootstrap fails', async () => {
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
  })

  it('restores a session from the HttpOnly refresh cookie', async () => {
    vi.mocked(axios.post).mockResolvedValueOnce({ data: { access_token: jwt('alice', 'admin') } })
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('alice'))
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('true')
    expect(sessionStorage.getItem('ta_access')).toBeTruthy()
    expect(localStorage.getItem('ta_access')).toBeNull()
  })

  it('does not authenticate from legacy localStorage tokens and purges them', async () => {
    localStorage.setItem('ta_access', jwt('legacy'))
    localStorage.setItem('ta_refresh', 'legacy-refresh-token')

    renderWithAuth(<TestConsumer />)

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
    expect(localStorage.getItem('ta_access')).toBeNull()
    expect(localStorage.getItem('ta_refresh')).toBeNull()
    expect(sessionStorage.getItem('ta_access')).toBeNull()
    expect(vi.mocked(axios.post)).toHaveBeenCalledWith('/auth/refresh')
  })

  it('ignores an expired token and clears it', async () => {
    sessionStorage.setItem('ta_access', jwt('expired', 'user', -3600))
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
    expect(sessionStorage.getItem('ta_access')).toBeNull()
  })

  it('logs in without exposing a refresh token to JavaScript storage', async () => {
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'))
    vi.mocked(axios.post).mockResolvedValueOnce({ data: { access_token: jwt('bob') } })
    await userEvent.click(screen.getByTestId('login'))
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('bob'))
    expect(sessionStorage.getItem('ta_access')).toBeTruthy()
    expect(localStorage.getItem('ta_refresh')).toBeNull()
  })

  it('clears query and mutation caches when the authenticated user changes', async () => {
    sessionStorage.setItem('ta_access', jwt('alice'))
    localStorage.setItem('ta_user_scope', 'alice')
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('alice'))

    queryClient.setQueryData(['alerts'], [{ id: 1, user: 'alice' }])
    queryClient.getMutationCache().build(queryClient, {
      mutationKey: ['settings', 'save'],
      mutationFn: async () => ({ user: 'alice' }),
    })
    expect(queryClient.getQueryCache().getAll()).toHaveLength(1)
    expect(queryClient.getMutationCache().getAll()).toHaveLength(1)

    vi.mocked(axios.post).mockResolvedValueOnce({ data: { access_token: jwt('bob') } })
    await userEvent.click(screen.getByTestId('login'))
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('bob'))

    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0)
  })

  it('logout clears sensitive browser state, query caches and calls the server', async () => {
    sessionStorage.setItem('ta_access', jwt('alice'))
    localStorage.setItem('ta_user_scope', 'alice')
    sessionStorage.setItem('ta_last_run', JSON.stringify({ ticker: 'AAPL', reports: { market_report: 'private' } }))
    sessionStorage.setItem('ta_task_running', JSON.stringify({ taskId: 'alice-task' }))
    vi.mocked(axios.post).mockResolvedValue({ data: {} })
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('alice'))

    queryClient.setQueryData(['portfolio'], { user: 'alice' })
    queryClient.getMutationCache().build(queryClient, {
      mutationKey: ['portfolio', 'save'],
      mutationFn: async () => ({ user: 'alice' }),
    })

    await userEvent.click(screen.getByTestId('logout'))
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('null'))
    expect(sessionStorage.getItem('ta_access')).toBeNull()
    expect(sessionStorage.getItem('ta_last_run')).toBeNull()
    expect(sessionStorage.getItem('ta_task_running')).toBeNull()
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0)
    expect(vi.mocked(axios.post)).toHaveBeenCalledWith('/auth/logout')
  })

  it('getAccessToken reads session storage only', () => {
    localStorage.setItem('ta_access', 'legacy_token')
    sessionStorage.setItem('ta_access', 'session_token')
    expect(getAccessToken()).toBe('session_token')
  })

  it('throws when useAuth is used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<TestConsumer />)).toThrow('useAuth must be used within an AuthProvider')
    consoleError.mockRestore()
  })

  it('clears React auth state when cookie refresh fails', async () => {
    sessionStorage.setItem('ta_access', jwt('alice'))
    renderWithAuth(<TestConsumer />)
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('alice'))

    vi.mocked(axios.post).mockRejectedValue(new Error('refresh rejected'))
    expect(responseErrorHandler).toBeDefined()
    const fakeError = { config: { url: '/api/portfolio', headers: {} }, response: { status: 401, data: {} } }
    await expect(responseErrorHandler!(fakeError)).rejects.toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false'))
  })
})
