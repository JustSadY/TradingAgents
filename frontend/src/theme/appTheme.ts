import { alpha, createTheme } from '@mui/material/styles'

const glassBorder = alpha('#ffffff', 0.08)
const glassBackground = alpha('#0f172a', 0.72)

export const appTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#7c3aed', light: '#a78bfa' },
    secondary: { main: '#4f46e5' },
    background: { default: '#030712', paper: glassBackground },
    text: { primary: '#f8fafc', secondary: '#94a3b8' },
    divider: glassBorder,
    error: { main: '#f43f5e' },
    warning: { main: '#f59e0b' },
    success: { main: '#10b981' },
    info: { main: '#3b82f6' },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    button: { textTransform: 'none', fontWeight: 700 },
  },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: `1px solid ${glassBorder}`,
          backdropFilter: 'blur(18px)',
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { borderRadius: 12 } },
    },
    MuiTextField: {
      defaultProps: { variant: 'outlined' },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: alpha('#0f172a', 0.58),
          '& fieldset': { borderColor: glassBorder },
          '&:hover fieldset': { borderColor: alpha('#a78bfa', 0.42) },
          '&.Mui-focused fieldset': { borderColor: '#7c3aed' },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          backgroundColor: alpha('#080f1f', 0.96),
          boxShadow: '0 24px 80px rgba(0,0,0,.55)',
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: alpha('#111827', 0.96),
          border: `1px solid ${glassBorder}`,
          fontSize: 11,
        },
      },
    },
    MuiAlert: {
      styleOverrides: { root: { borderRadius: 12 } },
    },
    MuiSwitch: {
      styleOverrides: {
        switchBase: {
          '&.Mui-checked': {
            color: '#a78bfa',
            '& + .MuiSwitch-track': { backgroundColor: '#7c3aed' },
          },
        },
      },
    },
  },
})

export default appTheme
