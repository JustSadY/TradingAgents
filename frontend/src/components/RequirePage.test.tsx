import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirePage from './RequirePage'
import { usePermissions } from '../contexts/PermissionsContext'

vi.mock('../contexts/PermissionsContext', () => ({ usePermissions: vi.fn() }))

const mockedUsePermissions = vi.mocked(usePermissions)

function permissions(overrides: Partial<ReturnType<typeof usePermissions>>) {
  return {
    canAccess: () => true,
    loading: false,
    allowedPages: [] as string[],
    refresh: async () => {},
    ...overrides,
  } as ReturnType<typeof usePermissions>
}

function renderGuarded() {
  render(
    <MemoryRouter initialEntries={['/trading']}>
      <Routes>
        <Route path="/dashboard" element={<div>dashboard page</div>} />
        <Route
          path="/trading"
          element={
            <RequirePage page="trading">
              <div>trading page</div>
            </RequirePage>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

describe('RequirePage', () => {
  beforeEach(() => vi.clearAllMocks())
  afterEach(() => cleanup())

  it('renders children when the page is allowed', () => {
    mockedUsePermissions.mockReturnValue(permissions({}))
    renderGuarded()
    expect(screen.getByText('trading page')).toBeDefined()
  })

  it('redirects to the dashboard when the page is forbidden', () => {
    mockedUsePermissions.mockReturnValue(permissions({ canAccess: () => false }))
    renderGuarded()
    expect(screen.getByText('dashboard page')).toBeDefined()
    expect(screen.queryByText('trading page')).toBeNull()
  })

  it('renders neither page nor redirect while permissions load', () => {
    mockedUsePermissions.mockReturnValue(permissions({ loading: true }))
    renderGuarded()
    expect(screen.queryByText('trading page')).toBeNull()
    expect(screen.queryByText('dashboard page')).toBeNull()
  })

  it('checks the specific page key it guards', () => {
    const canAccess = vi.fn().mockReturnValue(true)
    mockedUsePermissions.mockReturnValue(permissions({ canAccess }))
    renderGuarded()
    expect(canAccess).toHaveBeenCalledWith('trading')
  })
})
