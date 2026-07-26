import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthProvider, useAuth, getAccessToken } from '../AuthContext'
import type { ReactNode } from 'react'

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
  vi.restoreAllMocks()
})

afterEach(() => {
  localStorage.clear()
})

describe('AuthContext', () => {
  it('renders with loading state initially', () => {
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
  })

  it('shows unauthenticated when no token', () => {
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
    expect(screen.getByTestId('user')).toHaveTextContent('null')
  })

  it('loads user from valid token in localStorage', () => {
    const payload = { sub: 'alice', role: 'admin', exp: Math.floor(Date.now() / 1000) + 3600 }
    const token = `header.${btoa(JSON.stringify(payload))}.signature`
    localStorage.setItem('ta_access', token)
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('user')).toHaveTextContent('alice')
    expect(screen.getByTestId('role')).toHaveTextContent('admin')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('true')
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('true')
  })

  it('handles owner role', () => {
    const payload = { sub: 'owner', role: 'owner', exp: Math.floor(Date.now() / 1000) + 3600 }
    const token = `header.${btoa(JSON.stringify(payload))}.signature`
    localStorage.setItem('ta_access', token)
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('isOwner')).toHaveTextContent('true')
    expect(screen.getByTestId('isAdmin')).toHaveTextContent('true')
  })

  it('ignores expired token', () => {
    const payload = { sub: 'bob', role: 'user', exp: Math.floor(Date.now() / 1000) - 3600 }
    const token = `header.${btoa(JSON.stringify(payload))}.signature`
    localStorage.setItem('ta_access', token)
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
    expect(localStorage.getItem('ta_access')).toBeNull()
  })

  it('handles token with base64url encoding (- and _)', () => {
    const payload = { sub: 'alice_smith', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 }
    const b64url = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    const token = `header.${b64url}.signature`
    localStorage.setItem('ta_access', token)
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('user')).toHaveTextContent('alice_smith')
  })

  it('throws when useAuth is used outside provider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<TestConsumer />)).toThrow('useAuth must be used within an AuthProvider')
    consoleError.mockRestore()
  })

  it('login calls axios and stores tokens', async () => {
    const axios = await import('axios')
    const mockPost = vi.mocked(axios.default.post).mockResolvedValue({
      data: { access_token: 'new_token', refresh_token: 'new_refresh' },
    })
    renderWithAuth(<TestConsumer />)
    await userEvent.click(screen.getByTestId('login'))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/login', { username: 'test', password: 'pass' })
    })
    expect(localStorage.getItem('ta_access')).toBe('new_token')
  })

  it('logout clears state and calls /auth/logout', async () => {
    const payload = { sub: 'alice', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 }
    localStorage.setItem('ta_access', `header.${btoa(JSON.stringify(payload))}.signature`)
    localStorage.setItem('ta_refresh', 'refresh_token')
    const axios = await import('axios')
    vi.mocked(axios.default.post).mockResolvedValue({ data: {} })
    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('true')
    await userEvent.click(screen.getByTestId('logout'))
    await waitFor(() => {
      expect(screen.getByTestId('user')).toHaveTextContent('null')
    })
    expect(localStorage.getItem('ta_access')).toBeNull()
  })

  it('getAccessToken returns token from localStorage', () => {
    localStorage.setItem('ta_access', 'my_token')
    expect(getAccessToken()).toBe('my_token')
  })

  it('getAccessToken returns null when no token', () => {
    expect(getAccessToken()).toBeNull()
  })

  it('clears React auth state (not just localStorage) when token refresh fails', async () => {
    const payload = { sub: 'alice', role: 'user', exp: Math.floor(Date.now() / 1000) + 3600 }
    localStorage.setItem('ta_access', `header.${btoa(JSON.stringify(payload))}.signature`)
    localStorage.setItem('ta_refresh', 'stale_refresh_token')

    const axios = await import('axios')
    const mockedAxios = vi.mocked(axios.default)
    // /auth/refresh itself fails (e.g. refresh token revoked/expired)
    mockedAxios.post.mockImplementation((url: string) => {
      if (url === '/auth/refresh') return Promise.reject(new Error('refresh rejected'))
      return Promise.resolve({ data: {} })
    })

    renderWithAuth(<TestConsumer />)
    expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('true')

    // Grab the response error-handler AuthContext registered on the (mocked)
    // axios.interceptors.response.use, and invoke it as axios would for a
    // downstream 401 — this is what used to leave localStorage cleared but
    // React state (and thus the UI) still showing "logged in".
    const responseUseCalls = vi.mocked(mockedAxios.interceptors.response.use).mock.calls
    const errorHandler = responseUseCalls[responseUseCalls.length - 1][1]

    const fakeError = {
      config: { url: '/api/portfolio', headers: {} },
      response: { status: 401, data: {} },
    }
    await expect(errorHandler(fakeError)).rejects.toBeTruthy()

    await waitFor(() => {
      expect(screen.getByTestId('isAuthenticated')).toHaveTextContent('false')
    })
    expect(screen.getByTestId('user')).toHaveTextContent('null')
    expect(localStorage.getItem('ta_access')).toBeNull()
  })
})
