import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ThemeProvider } from '@mui/material/styles'
import { appTheme } from '../../../theme/appTheme'
import type { Notification } from '../../../utils/notify'
import NotificationAdapter from '../NotificationAdapter'

const authState = { isAdmin: false, isOwner: false }

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

function emit(notification: Notification) {
  window.dispatchEvent(new CustomEvent<Notification>('ta-notify', { detail: notification }))
}

function renderAdapter() {
  return render(
    <ThemeProvider theme={appTheme}>
      <NotificationAdapter />
    </ThemeProvider>,
  )
}

afterEach(() => {
  authState.isAdmin = false
  authState.isOwner = false
  vi.useRealTimers()
})

describe('NotificationAdapter', () => {
  it('renders the existing ta-notify event as an MUI snackbar alert', async () => {
    renderAdapter()
    emit({ id: 'success-1', type: 'success', title: 'Saved', message: 'Settings updated.', visibility: 'all' })

    expect(await screen.findByText('Settings updated.')).toBeInTheDocument()
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('preserves admin and owner visibility rules', async () => {
    renderAdapter()
    emit({ id: 'owner-hidden', type: 'info', message: 'owner only', visibility: 'owner' })
    expect(screen.queryByText('owner only')).not.toBeInTheDocument()

    authState.isAdmin = true
    emit({ id: 'admin-visible', type: 'warning', message: 'admin visible', visibility: 'admin' })
    expect(await screen.findByText('admin visible')).toBeInTheDocument()
  })

  it('automatically removes non-error notifications after four seconds', async () => {
    vi.useFakeTimers()
    renderAdapter()
    emit({ id: 'info-1', type: 'info', message: 'temporary', visibility: 'all' })
    expect(screen.getByText('temporary')).toBeInTheDocument()

    vi.advanceTimersByTime(4000)
    await waitFor(() => expect(screen.queryByText('temporary')).not.toBeInTheDocument())
  })
})
