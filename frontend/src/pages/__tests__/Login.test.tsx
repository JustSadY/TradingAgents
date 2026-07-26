import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import Login from '../Login'

const mockLogin = vi.hoisted(() => vi.fn())
const mockNavigate = vi.hoisted(() => vi.fn())

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: mockLogin,
    user: null,
    role: null,
    isAdmin: false,
    isOwner: false,
    isAuthenticated: false,
    loading: false,
    logout: vi.fn(),
  }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../../contexts/LanguageContext', () => {
  const t = (key: string) => {
    const map: Record<string, string> = {
      'login.subtitle': 'Sign in to your account',
      'login.username_placeholder': 'Username',
      'login.password_placeholder': 'Password',
      'login.submit': 'Sign In',
      'login.submitting': 'Signing In...',
      'login.error_credentials': 'Invalid credentials',
    }
    return map[key] || key
  }
  return {
    useTranslation: () => ({ t, language: 'en', setLanguage: vi.fn() }),
  }
})

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders login form', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    expect(screen.getByText('TradingAgents')).toBeInTheDocument()
    expect(screen.getByText('Sign in to your account')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Username')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument()
    expect(screen.getByText('Sign In')).toBeInTheDocument()
  })

  it('calls login and navigates on submit', async () => {
    mockLogin.mockResolvedValue(undefined)
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    await userEvent.type(screen.getByPlaceholderText('Username'), 'testuser')
    await userEvent.type(screen.getByPlaceholderText('Password'), 'testpass')
    await userEvent.click(screen.getByText('Sign In'))
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('testuser', 'testpass')
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('shows error on login failure', async () => {
    mockLogin.mockRejectedValue(new Error('Login failed'))
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    await userEvent.type(screen.getByPlaceholderText('Username'), 'baduser')
    await userEvent.type(screen.getByPlaceholderText('Password'), 'badpass')
    await userEvent.click(screen.getByText('Sign In'))
    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })
  })

  it('shows submitting state while logging in', async () => {
    let resolveLogin: () => void = () => {}
    mockLogin.mockImplementation(() => new Promise<void>(resolve => { resolveLogin = resolve }))
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    )
    await userEvent.type(screen.getByPlaceholderText('Username'), 'test')
    await userEvent.type(screen.getByPlaceholderText('Password'), 'test')
    await userEvent.click(screen.getByText('Sign In'))
    expect(screen.getByText('Signing In...')).toBeInTheDocument()
    resolveLogin()
    await waitFor(() => {
      expect(screen.getByText('Sign In')).toBeInTheDocument()
    })
  })
})
