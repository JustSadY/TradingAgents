import { useState, type ReactNode } from 'react'
import {
  Alert,
  type AlertProps,
  Button,
  type ButtonProps,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  type SelectChangeEvent,
  Skeleton,
  type SkeletonProps,
  Snackbar,
  Switch,
  Tab,
  Tabs,
  TextField,
  type TextFieldProps,
  Tooltip,
  type TooltipProps,
} from '@mui/material'
import { Eye, EyeOff } from 'lucide-react'

export function AppButton(props: ButtonProps) {
  return <Button size="small" variant="contained" {...props} />
}

export function AppTextField(props: TextFieldProps) {
  return <TextField size="small" fullWidth {...props} />
}

export interface AppSelectOption {
  value: string | number
  label: ReactNode
  disabled?: boolean
}

export interface AppSelectProps {
  id?: string
  label?: string
  value: string | number
  options: AppSelectOption[]
  disabled?: boolean
  fullWidth?: boolean
  onChange: (value: string | number) => void
}

export function AppSelect({ id, label, value, options, disabled, fullWidth = true, onChange }: AppSelectProps) {
  const labelId = label && id ? `${id}-label` : undefined
  const handleChange = (event: SelectChangeEvent<string | number>) => onChange(event.target.value)
  return (
    <FormControl size="small" fullWidth={fullWidth} disabled={disabled}>
      {label && <InputLabel id={labelId}>{label}</InputLabel>}
      <Select
        id={id}
        labelId={labelId}
        label={label}
        value={value}
        onChange={handleChange}
      >
        {options.map(option => (
          <MenuItem key={String(option.value)} value={option.value} disabled={option.disabled}>
            {option.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  )
}

export interface AppSwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: ReactNode
  disabled?: boolean
  name?: string
}

export function AppSwitch({ checked, onChange, label, disabled, name }: AppSwitchProps) {
  const control = (
    <Switch
      size="small"
      checked={checked}
      disabled={disabled}
      name={name}
      onChange={event => onChange(event.target.checked)}
    />
  )
  return label ? <FormControlLabel control={control} label={label} /> : control
}

export interface AppTabItem {
  value: string
  label: ReactNode
  disabled?: boolean
}

export function AppTabs({ value, items, onChange }: { value: string; items: AppTabItem[]; onChange: (value: string) => void }) {
  return (
    <Tabs value={value} onChange={(_event, next: string) => onChange(next)} variant="scrollable" scrollButtons="auto">
      {items.map(item => <Tab key={item.value} value={item.value} label={item.label} disabled={item.disabled} />)}
    </Tabs>
  )
}

export interface AppDialogProps {
  open: boolean
  title?: ReactNode
  children: ReactNode
  actions?: ReactNode
  onClose: () => void
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}

export function AppDialog({ open, title, children, actions, onClose, maxWidth = 'sm' }: AppDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth={maxWidth} aria-labelledby={title ? 'app-dialog-title' : undefined}>
      {title && <DialogTitle id="app-dialog-title">{title}</DialogTitle>}
      <DialogContent>{children}</DialogContent>
      {actions && <DialogActions>{actions}</DialogActions>}
    </Dialog>
  )
}

export interface AppConfirmDialogProps {
  open: boolean
  title: ReactNode
  message: ReactNode
  confirmLabel?: ReactNode
  cancelLabel?: ReactNode
  confirmColor?: ButtonProps['color']
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function AppConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  confirmColor = 'error',
  busy = false,
  onConfirm,
  onCancel,
}: AppConfirmDialogProps) {
  return (
    <Dialog open={open} onClose={(_event, reason) => { if (reason !== 'backdropClick' && !busy) onCancel() }} aria-labelledby="app-confirm-title" aria-describedby="app-confirm-description">
      <DialogTitle id="app-confirm-title">{title}</DialogTitle>
      <DialogContent id="app-confirm-description">{message}</DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={busy}>{cancelLabel}</Button>
        <Button autoFocus variant="contained" color={confirmColor} onClick={onConfirm} disabled={busy}>{confirmLabel}</Button>
      </DialogActions>
    </Dialog>
  )
}

export function AppTooltip(props: TooltipProps) {
  return <Tooltip arrow {...props} />
}

export function AppSkeleton(props: SkeletonProps) {
  return <Skeleton animation="wave" {...props} />
}

export function AppAlert(props: AlertProps) {
  return <Alert variant="outlined" {...props} />
}

export interface AppSnackbarProps {
  open: boolean
  message: ReactNode
  title?: ReactNode
  severity?: AlertProps['severity']
  autoHideDuration?: number | null
  onClose: () => void
  bottomOffset?: number
}

export function AppSnackbar({ open, message, title, severity = 'info', autoHideDuration = 4000, onClose, bottomOffset = 24 }: AppSnackbarProps) {
  return (
    <Snackbar
      open={open}
      autoHideDuration={autoHideDuration}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      sx={{ bottom: { xs: bottomOffset, sm: bottomOffset } }}
    >
      <Alert severity={severity} variant="filled" onClose={onClose} sx={{ width: '100%', minWidth: { sm: 320 }, backdropFilter: 'blur(16px)' }}>
        {title && <strong style={{ display: 'block' }}>{title}</strong>}
        {message}
      </Alert>
    </Snackbar>
  )
}

export function SecretField(props: Omit<TextFieldProps, 'type'>) {
  const [visible, setVisible] = useState(false)
  return (
    <AppTextField
      {...props}
      type={visible ? 'text' : 'password'}
      slotProps={{
        ...props.slotProps,
        input: {
          ...(typeof props.slotProps?.input === 'object' ? props.slotProps.input : {}),
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                size="small"
                edge="end"
                aria-label={visible ? 'Hide secret' : 'Show secret'}
                onClick={() => setVisible(current => !current)}
              >
                {visible ? <EyeOff size={16} /> : <Eye size={16} />}
              </IconButton>
            </InputAdornment>
          ),
        },
      }}
    />
  )
}
