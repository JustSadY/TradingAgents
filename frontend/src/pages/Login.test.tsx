import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import Login from './Login'
import { useAuth } from '../contexts/AuthContext'

const navigate = vi.fn()

vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../contexts/LanguageContext', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const mockedUseAuth = vi.mocked(useAuth)

function setup(login: (username: string, password: string) => Promise<void>) {
  mockedUseAuth.mockReturnValue({ login } as unknown as ReturnType<typeof useAuth>)
  render(<Login />)
  fireEvent.change(screen.getByPlaceholderText('login.username_placeholder'), {
    target: { value: 'alice' },
  })
  fireEvent.change(screen.getByPlaceholderText('login.password_placeholder'), {
    target: { value: 's3cret' },
  })
  fireEvent.click(screen.getByRole('button'))
}

describe('Login', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('logs in with the entered credentials and navigates to the dashboard', async () => {
    const login = vi.fn().mockResolvedValue(undefined)
    setup(login)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/dashboard'))
    expect(login).toHaveBeenCalledWith('alice', 's3cret')
  })

  it('shows an error and stays put when credentials are rejected', async () => {
    setup(vi.fn().mockRejectedValue(new Error('401')))
    expect(await screen.findByText('login.error_credentials')).toBeDefined()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('disables the submit button while the request is in flight', async () => {
    let resolveLogin!: () => void
    const login = vi.fn().mockReturnValue(
      new Promise<void>(resolve => {
        resolveLogin = resolve
      })
    )
    setup(login)
    const button = screen.getByRole('button') as HTMLButtonElement
    await waitFor(() => expect(button.disabled).toBe(true))
    resolveLogin()
    await waitFor(() => expect(button.disabled).toBe(false))
  })

  it('clears a previous error on a successful retry', async () => {
    const login = vi.fn().mockRejectedValueOnce(new Error('401')).mockResolvedValueOnce(undefined)
    setup(login)
    expect(await screen.findByText('login.error_credentials')).toBeDefined()

    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/dashboard'))
    expect(screen.queryByText('login.error_credentials')).toBeNull()
  })
})
