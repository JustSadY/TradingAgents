import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { AuthProvider, useAuth } from './AuthContext'

function b64url(value: unknown): string {
  return btoa(JSON.stringify(value)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeToken(payload: Record<string, unknown>): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.signature`
}

function Probe() {
  const { user, role, isAdmin, isOwner, isAuthenticated, loading } = useAuth()
  if (loading) return <div>loading</div>
  return <div data-testid="auth">{JSON.stringify({ user, role, isAdmin, isOwner, isAuthenticated })}</div>
}

async function renderAuthState() {
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  )
  const el = await screen.findByTestId('auth')
  return JSON.parse(el.textContent ?? '{}')
}

describe('AuthProvider', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => cleanup())

  it('restores the session from a valid token, including base64url payloads', async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    // '~~~' forces '+' characters in raw base64, exercising the base64url path.
    localStorage.setItem('ta_access', makeToken({ sub: 'boss', role: 'owner', type: 'access', exp, pad: '~~~' }))

    const state = await renderAuthState()
    expect(state).toEqual({ user: 'boss', role: 'owner', isAdmin: true, isOwner: true, isAuthenticated: true })
  })

  it('maps the admin role without owner privileges', async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    localStorage.setItem('ta_access', makeToken({ sub: 'mgr', role: 'admin', type: 'access', exp }))

    const state = await renderAuthState()
    expect(state.isAdmin).toBe(true)
    expect(state.isOwner).toBe(false)
  })

  it('defaults to the user role when the token has none', async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    localStorage.setItem('ta_access', makeToken({ sub: 'plain', type: 'access', exp }))

    const state = await renderAuthState()
    expect(state).toEqual({ user: 'plain', role: 'user', isAdmin: false, isOwner: false, isAuthenticated: true })
  })

  it('clears storage and stays logged out when the token is expired', async () => {
    const exp = Math.floor(Date.now() / 1000) - 60
    localStorage.setItem('ta_access', makeToken({ sub: 'old', role: 'admin', type: 'access', exp }))
    localStorage.setItem('ta_refresh', 'stale-refresh')

    const state = await renderAuthState()
    expect(state.isAuthenticated).toBe(false)
    expect(localStorage.getItem('ta_access')).toBeNull()
    expect(localStorage.getItem('ta_refresh')).toBeNull()
  })

  it('survives malformed tokens without crashing', async () => {
    localStorage.setItem('ta_access', 'not-a-jwt')

    const state = await renderAuthState()
    expect(state.isAuthenticated).toBe(false)
  })
})
