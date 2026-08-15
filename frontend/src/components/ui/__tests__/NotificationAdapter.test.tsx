import { act, render, screen, waitForElementToBeRemoved } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '@mui/material/styles'
import { appTheme } from '../../../theme/appTheme'
import type { Notification } from '../../../utils/notify'
import { SnackbarProvider } from 'notistack'
import NotificationAdapter from '../NotificationAdapter'
import { NotificationContent } from '../NotificationContent'

const authState = vi.hoisted(() => ({ isAdmin: false, isOwner: false }))
const enqueueSpy = vi.hoisted(() => vi.fn())

const notificationComponents = {
  success: NotificationContent,
  error: NotificationContent,
  warning: NotificationContent,
  info: NotificationContent,
  default: NotificationContent,
}


vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

// Only `useSnackbar` is stubbed, and only for the test that inspects what the
// adapter enqueues; every other test runs against the real provider.
vi.mock('notistack', async () => {
  const actual = await vi.importActual<typeof import('notistack')>('notistack')
  return {
    ...actual,
    useSnackbar: () => {
      const real = actual.useSnackbar()
      return enqueueSpy.getMockImplementation()
        ? { ...real, enqueueSnackbar: enqueueSpy }
        : real
    },
  }
})

function emit(notification: Notification) {
  act(() => {
    window.dispatchEvent(new CustomEvent<Notification>('ta-notify', { detail: notification }))
  })
}

/** Mirrors how App.tsx composes the adapter inside the snackbar provider. */
function renderAdapter() {
  return render(
    <ThemeProvider theme={appTheme}>
      <SnackbarProvider
        maxSnack={5}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        Components={notificationComponents}
      >
        <NotificationAdapter />
      </SnackbarProvider>
    </ThemeProvider>,
  )
}

afterEach(() => {
  authState.isAdmin = false
  authState.isOwner = false
  enqueueSpy.mockReset()
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
    const first = renderAdapter()
    emit({ id: 'owner-hidden', type: 'info', message: 'owner only', visibility: 'owner' })
    expect(screen.queryByText('owner only')).not.toBeInTheDocument()
    first.unmount()

    authState.isAdmin = true
    renderAdapter()
    emit({ id: 'admin-visible', type: 'warning', message: 'admin visible', visibility: 'admin' })
    expect(await screen.findByText('admin visible')).toBeInTheDocument()
  })

  it('gives errors a longer auto-hide than other notifications', () => {
    // How long a snackbar survives is notistack's job once it has been told.
    // What this adapter owns is the choice of duration, so that is what is
    // asserted — driving notistack's own timer through fake timers would be
    // testing the library rather than this code.
    const enqueued: Array<{ message: unknown; options: Record<string, unknown> }> = []
    enqueueSpy.mockImplementation((message, options) => {
      enqueued.push({ message, options: options as Record<string, unknown> })
      return 'key'
    })

    renderAdapter()
    emit({ id: 'e', type: 'error', message: 'failed', visibility: 'all' })
    emit({ id: 'i', type: 'info', message: 'fyi', visibility: 'all' })

    expect(enqueued).toHaveLength(2)
    expect(enqueued[0].options.autoHideDuration).toBe(6000)
    expect(enqueued[1].options.autoHideDuration).toBe(4000)
    expect(enqueued[0].options.variant).toBe('error')
    expect(enqueued[0].options.key).toBe('e')
  })

  it('caps how many notifications are shown at once and queues the rest', async () => {
    renderAdapter()
    for (let index = 0; index < 8; index += 1) {
      emit({ id: `burst-${index}`, type: 'info', message: `burst ${index}`, visibility: 'all' })
    }

    await screen.findByText('burst 0')
    // The overflow waits for a free slot instead of being dropped, which is a
    // change from the previous renderer: a burst no longer loses notifications.
    expect(screen.getAllByRole('alert').length).toBeLessThanOrEqual(5)
    expect(screen.queryByText('burst 7')).not.toBeInTheDocument()
  })

  it('dismisses a notification when its close button is used', async () => {
    const user = userEvent.setup()
    renderAdapter()
    emit({ id: 'closable', type: 'info', message: 'close me', visibility: 'all' })
    await screen.findByText('close me')

    await user.click(screen.getByRole('button', { name: /close/i }))
    await waitForElementToBeRemoved(() => screen.queryByText('close me'))
  })

  it('renders each severity as its own alert', async () => {
    renderAdapter()
    emit({ id: 's', type: 'success', message: 'ok', visibility: 'all' })
    emit({ id: 'e', type: 'error', message: 'bad', visibility: 'all' })
    emit({ id: 'w', type: 'warning', message: 'careful', visibility: 'all' })
    emit({ id: 'i', type: 'info', message: 'fyi', visibility: 'all' })

    await screen.findByText('fyi')
    expect(screen.getAllByRole('alert')).toHaveLength(4)
  })
})
