import { forwardRef } from 'react'
import Alert from '@mui/material/Alert'
import { SnackbarContent, useSnackbar } from 'notistack'
import type { CustomContentProps } from 'notistack'

// Notifications carry an optional bold title above the message, which is not
// part of notistack's own options. Declaring it per variant is how notistack v3
// threads extra props through `enqueueSnackbar` to a custom content component
// in a type-safe way.
declare module 'notistack' {
  interface VariantOverrides {
    default: { title?: string }
    error: { title?: string }
    success: { title?: string }
    warning: { title?: string }
    info: { title?: string }
  }
}

interface NotificationProps extends CustomContentProps {
  title?: string
}

/**
 * Renders a queued notification as the same filled MUI alert the app used
 * before notistack, so the appearance and the `role="alert"` contract are
 * unchanged. notistack owns the queue, the timers and the stacking.
 */
export const NotificationContent = forwardRef<HTMLDivElement, NotificationProps>(
  function NotificationContent({ id, message, variant, title }, ref) {
    // Taken from the hook rather than notistack's module-level helper so the
    // close button targets the provider this snackbar actually belongs to.
    const { closeSnackbar } = useSnackbar()
    const severity = variant === 'default' ? 'info' : variant

    return (
      <SnackbarContent ref={ref}>
        <Alert
          severity={severity}
          variant="filled"
          onClose={() => closeSnackbar(id)}
          sx={{ width: '100%', minWidth: { sm: 320 }, backdropFilter: 'blur(16px)' }}
        >
          {title && <strong style={{ display: 'block' }}>{title}</strong>}
          {message}
        </Alert>
      </SnackbarContent>
    )
  },
)
