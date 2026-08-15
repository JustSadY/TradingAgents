import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { ThemeProvider } from '@mui/material/styles'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { PermissionsProvider } from './contexts/PermissionsContext'
import RequirePage from './components/RequirePage'
import { ErrorBoundary } from './components/ErrorBoundary'
import Layout from './components/Layout'
import { SnackbarProvider } from 'notistack'
import NotificationAdapter from './components/ui/NotificationAdapter'
import { NotificationContent } from './components/ui/NotificationContent'

// Login eagerly (it's the entry point); every protected page is code-split so
// the initial bundle stays small and each page loads on demand.
import Login from './pages/Login'
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Analysis = lazy(() => import('./pages/Analysis'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const Orders = lazy(() => import('./pages/Orders'))
const Settings = lazy(() => import('./pages/Settings'))
const Logs = lazy(() => import('./pages/Logs'))
const MockTrading = lazy(() => import('./pages/MockTrading'))
const Portfolio = lazy(() => import('./pages/Portfolio'))
const Chart = lazy(() => import('./pages/Chart'))
const Backtest = lazy(() => import('./pages/Backtest'))
const Performance = lazy(() => import('./pages/Performance'))
const Alerts = lazy(() => import('./pages/Alerts'))
const ABTesting = lazy(() => import('./pages/ABTesting'))
const Profile = lazy(() => import('./pages/Profile'))
const Admin = lazy(() => import('./pages/Admin'))
const Screener = lazy(() => import('./pages/Screener'))
const SectorRotation = lazy(() => import('./pages/SectorRotation'))
const SharedReport = lazy(() => import('./pages/SharedReport'))
const EarningsCalendar = lazy(() => import('./pages/EarningsCalendar'))

import { QueryClientProvider } from '@tanstack/react-query'
import { LanguageProvider } from './contexts/LanguageContext'
import { CurrencyProvider } from './contexts/CurrencyContext'
import { queryClient } from './api/queryClient'
import { appTheme } from './theme/appTheme'

// Every severity uses the same alert; notistack still needs one entry per
// variant so it can type the options passed to `enqueueSnackbar`.
const notificationComponents = {
  success: NotificationContent,
  error: NotificationContent,
  warning: NotificationContent,
  info: NotificationContent,
  default: NotificationContent,
}

/**
 * Whole-app fallback.
 *
 * Deliberately does not render the exception message. A crash here is most
 * likely to be seen by an ordinary user, and the message can carry internals
 * — a stack frame, a URL, a serialised payload. `ErrorBoundary` already logs
 * the real error and component stack to the console for whoever is debugging.
 */
function AppCrashFallback() {
  return (
    <div style={{ padding: 32, color: '#e2e8f0', background: '#0f172a', minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16, textAlign: 'center' }}>
      <h2 style={{ color: '#fca5a5', margin: 0 }}>Something went wrong</h2>
      <p style={{ color: '#94a3b8', fontSize: 14, maxWidth: 420, lineHeight: 1.6, margin: 0 }}>
        The application could not finish loading. Reloading usually clears it; if
        it keeps happening, the details are in the browser console.
      </p>
      <button
        style={{ padding: '8px 16px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
        onClick={() => window.location.reload()}
      >
        Reload
      </button>
    </div>
  )
}

function AppRoutes() {
  const { isAuthenticated, isAdmin, loading } = useAuth()

  if (loading) {
    return <div style={{ background: '#0f172a', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6366f1', fontWeight: 600 }}>STARTING...</div>
  }

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />} />

      <Route path="/" element={isAuthenticated ? <Layout /> : <Navigate to="/login" replace />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<RequirePage page="dashboard"><Dashboard /></RequirePage>} />
        <Route path="analysis" element={<RequirePage page="analysis"><Analysis /></RequirePage>} />
        <Route path="chart" element={<RequirePage page="chart"><Chart /></RequirePage>} />
        <Route path="watchlist" element={<RequirePage page="watchlist"><Watchlist /></RequirePage>} />
        <Route path="orders" element={<RequirePage page="orders"><Orders /></RequirePage>} />
        <Route path="trading" element={<RequirePage page="trading"><MockTrading /></RequirePage>} />
        <Route path="portfolio" element={<RequirePage page="portfolio"><Portfolio /></RequirePage>} />
        <Route path="settings" element={<RequirePage page="settings"><Settings /></RequirePage>} />
        <Route path="preferences" element={<RequirePage page="settings"><Settings /></RequirePage>} />
        <Route path="performance" element={<RequirePage page="performance"><Performance /></RequirePage>} />
        <Route path="backtest" element={<RequirePage page="backtest"><Backtest /></RequirePage>} />
        <Route path="alerts" element={<RequirePage page="alerts"><Alerts /></RequirePage>} />
        <Route path="ab-testing" element={<RequirePage page="ab-testing"><ABTesting /></RequirePage>} />
        <Route path="logs" element={<RequirePage page="logs"><Logs /></RequirePage>} />
        <Route path="profile" element={<RequirePage page="profile"><Profile /></RequirePage>} />
        <Route path="admin" element={isAdmin ? <Admin /> : <Navigate to="/dashboard" replace />} />
        <Route path="screener" element={<RequirePage page="screener"><Screener /></RequirePage>} />
        <Route path="sector-rotation" element={<RequirePage page="sector-rotation"><SectorRotation /></RequirePage>} />
        <Route path="earnings" element={<RequirePage page="earnings"><EarningsCalendar /></RequirePage>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>

      <Route path="/share/:token" element={<Suspense fallback={null}><SharedReport /></Suspense>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary name="App" fallback={<AppCrashFallback />}>
      <ThemeProvider theme={appTheme}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <SnackbarProvider
              maxSnack={5}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              Components={notificationComponents}
            >
              <NotificationAdapter />
            </SnackbarProvider>
            <PermissionsProvider>
              <LanguageProvider>
                <CurrencyProvider>
                  <BrowserRouter>
                    <AppRoutes />
                  </BrowserRouter>
                </CurrencyProvider>
              </LanguageProvider>
            </PermissionsProvider>
          </AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
