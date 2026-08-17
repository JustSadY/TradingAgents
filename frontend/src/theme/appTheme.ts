import { alpha, createTheme } from '@mui/material/styles'

const glassBorder = alpha('#ffffff', 0.08)
const glassBackground = alpha('#0f172a', 0.72)

/**
 * Typography is shared with Tailwind, not defined twice.
 *
 * Pages are written in Tailwind (`text-xs` bodies, `text-[10px]` hints,
 * `font-display` headings) while the settings panels, data grids and dialogs
 * are MUI. MUI's defaults are a 14px base with 16px inputs, so the same screen
 * rendered noticeably larger text depending on which library drew the control.
 *
 * `fontSize: 12` rescales every rem-based MUI variant by 12/14, which lands
 * body2/button/subtitle2 on 12px (Tailwind `text-xs`) and caption/overline on
 * ~10px (`text-[10px]`). The families point at the same CSS variables
 * `index.css` gives Tailwind, so there is one font stack, not two.
 */
const FONT_SANS = 'var(--font-sans, Inter, ui-sans-serif, system-ui, -apple-system, sans-serif)'
const FONT_DISPLAY = 'var(--font-display, Outfit, ui-sans-serif, system-ui, sans-serif)'
const CONTROL_FONT_SIZE = 12
const HELPER_FONT_SIZE = 10

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
    fontFamily: FONT_SANS,
    fontSize: CONTROL_FONT_SIZE,
    button: { textTransform: 'none', fontWeight: 700 },
    // Tailwind headings use `font-display`; MUI headings must match rather
    // than falling back to the body stack.
    h1: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    h2: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    h3: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    h4: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    h5: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
    h6: { fontFamily: FONT_DISPLAY, fontWeight: 700 },
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
    // Inputs default to body1 (~16px), which is the single biggest source of
    // "this page's fields are bigger than that page's". Pin them to the same
    // size as a Tailwind `text-xs` field.
    MuiInputBase: {
      styleOverrides: { root: { fontSize: CONTROL_FONT_SIZE } },
    },
    MuiInputLabel: {
      styleOverrides: { root: { fontSize: CONTROL_FONT_SIZE } },
    },
    MuiFormLabel: {
      styleOverrides: { root: { fontSize: CONTROL_FONT_SIZE } },
    },
    MuiFormHelperText: {
      styleOverrides: { root: { fontSize: HELPER_FONT_SIZE, lineHeight: 1.5 } },
    },
    MuiFormControlLabel: {
      styleOverrides: { label: { fontSize: CONTROL_FONT_SIZE } },
    },
    MuiMenuItem: {
      styleOverrides: { root: { fontSize: CONTROL_FONT_SIZE } },
    },
    MuiTab: {
      styleOverrides: { root: { fontSize: CONTROL_FONT_SIZE, fontWeight: 700, textTransform: 'none' } },
    },
    MuiChip: {
      styleOverrides: { label: { fontSize: HELPER_FONT_SIZE, fontWeight: 700 } },
    },
    MuiDialogTitle: {
      styleOverrides: { root: { fontFamily: FONT_DISPLAY, fontSize: 16, fontWeight: 700 } },
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
      styleOverrides: { root: { borderRadius: 12, fontSize: CONTROL_FONT_SIZE } },
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
