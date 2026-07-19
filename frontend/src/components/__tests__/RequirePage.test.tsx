import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirePage from '../RequirePage'

const mockUsePermissions = vi.fn()

vi.mock('../../contexts/PermissionsContext', () => ({
  usePermissions: () => mockUsePermissions(),
}))

describe('RequirePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading state while permissions load', () => {
    mockUsePermissions.mockReturnValue({ canAccess: () => false, loading: true })
    const { container } = render(
      <MemoryRouter>
        <RequirePage page="admin">
          <div data-testid="content">Admin Panel</div>
        </RequirePage>
      </MemoryRouter>
    )
    expect(screen.getByText('…')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="content"]')).toBeNull()
  })

  it('renders children when page is accessible', () => {
    mockUsePermissions.mockReturnValue({ canAccess: () => true, loading: false })
    render(
      <MemoryRouter>
        <RequirePage page="dashboard">
          <div data-testid="content">Dashboard Content</div>
        </RequirePage>
      </MemoryRouter>
    )
    expect(screen.getByTestId('content')).toHaveTextContent('Dashboard Content')
  })

  it('redirects to dashboard when page is not accessible', () => {
    mockUsePermissions.mockReturnValue({ canAccess: () => false, loading: false })
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <RequirePage page="admin">
          <div data-testid="content">Admin Panel</div>
        </RequirePage>
      </MemoryRouter>
    )
    expect(screen.queryByTestId('content')).toBeNull()
  })
})
