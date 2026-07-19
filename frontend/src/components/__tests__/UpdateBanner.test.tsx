import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import UpdateBanner from '../UpdateBanner'
import axios from 'axios'

const mockUseAuth = vi.fn()

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
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

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  vi.spyOn(axios, 'get').mockResolvedValue({ data: defaultStatus })
})

describe('UpdateBanner', () => {
  it('renders nothing when update_supported is false', () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { ...defaultStatus, update_supported: false } })
    const { container } = render(<UpdateBanner />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing for non-owner when update is available', () => {
    mockUseAuth.mockReturnValue({ isOwner: false })
    render(<UpdateBanner />)
    expect(screen.queryByText(/Yeni sürüm/)).not.toBeInTheDocument()
  })

  it('shows update available banner for owner', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    render(<UpdateBanner />)
    await act(async () => { vi.advanceTimersByTime(100) })
    expect(await screen.findByText(/Yeni sürüm/)).toBeInTheDocument()
    expect(screen.getByText(/3 commit geride/)).toBeInTheDocument()
    expect(screen.getByText(/Güncelle/)).toBeInTheDocument()
  })

  it('shows updating state when busy', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    vi.spyOn(axios, 'get').mockResolvedValue({ data: { ...defaultStatus, updating: true } })
    render(<UpdateBanner />)
    await act(async () => { vi.advanceTimersByTime(100) })
    expect(await screen.findByText(/Güncelleniyor/)).toBeInTheDocument()
  })

  it('dismisses when close button is clicked', async () => {
    mockUseAuth.mockReturnValue({ isOwner: true })
    render(<UpdateBanner />)
    await act(async () => { vi.advanceTimersByTime(100) })
    const closeBtn = await screen.findByTitle('Gizle')
    await act(async () => { closeBtn.click() })
    expect(screen.queryByText(/Yeni sürüm/)).not.toBeInTheDocument()
  })
})
