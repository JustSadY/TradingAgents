import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import UpdateBanner from '../UpdateBanner'

const mockUseAuth = vi.hoisted(() => vi.fn())
const mockAxiosGet = vi.hoisted(() => vi.fn())

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  return {
    ...actual,
    default: {
      ...(actual as any).default,
      get: mockAxiosGet,
    },
    get: mockAxiosGet,
  }
})

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

beforeEach(() => {
  vi.clearAllMocks()
  mockAxiosGet.mockResolvedValue({ data: defaultStatus })
})

describe('UpdateBanner', () => {
  it('renders nothing when update_supported is false', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    mockAxiosGet.mockResolvedValue({ data: { ...defaultStatus, update_supported: false } })
    const { container } = render(<UpdateBanner />)
    await waitFor(() => { expect(mockAxiosGet).toHaveBeenCalled() })
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing for non-owner when update is available', async () => {
    mockUseAuth.mockReturnValue({ isOwner: false })
    render(<UpdateBanner />)
    await waitFor(() => { expect(mockAxiosGet).toHaveBeenCalled() })
    expect(screen.queryByText(/Yeni sürüm/)).not.toBeInTheDocument()
  })

  it('shows update available banner for owner', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    render(<UpdateBanner />)
    expect(await screen.findByText(/Yeni sürüm/)).toBeInTheDocument()
    expect(screen.getByText(/3 commit geride/)).toBeInTheDocument()
    expect(screen.getByText(/Güncelle/)).toBeInTheDocument()
  })

  it('shows updating state when busy', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    mockAxiosGet.mockResolvedValue({ data: { ...defaultStatus, updating: true } })
    render(<UpdateBanner />)
    expect(await screen.findByText(/Güncelleniyor/)).toBeInTheDocument()
  })

  it('dismisses when close button is clicked', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    render(<UpdateBanner />)
    expect(await screen.findByText(/Güncelle/)).toBeInTheDocument()
    const closeBtn = screen.getByTitle('Gizle')
    closeBtn.click()
    await waitFor(() => {
      expect(screen.queryByText(/Yeni sürüm/)).not.toBeInTheDocument()
    })
  })
})
