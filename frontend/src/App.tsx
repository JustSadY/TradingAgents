import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import React, { lazy, Suspense } from 'react'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { PermissionsProvider } from './contexts/PermissionsContext'
import RequirePage from './components/RequirePage'
import Layout from './components/Layout'

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

import { LanguageProvider } from './contexts/LanguageContext'
import { CurrencyProvider } from './contexts/CurrencyContext'

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: 'monospace', color: '#f87171', background: '#0f172a', minHeight: '100vh' }}>
          <h2 style={{ color: '#fca5a5', marginBottom: 12 }}>⚠ App Error</h2>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#1e293b', padding: 16, borderRadius: 8, fontSize: 12 }}>
            {this.state.error.message}
          </pre>
          <button style={{ marginTop: 16, padding: '8px 16px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }} onClick={() => window.location.reload()}>Refresh</button>
        </div>
      )
    }
    return this.props.children
  }
}

function AppRoutes() {
  const { isAuthenticated, isAdmin, loading } = useAuth()

  if (loading) {
    return <div style={{ background: '#0f172a', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6366f1', fontWeight: 600 }}>STARTING...</div>
  }

  return (
    <Routes>
      {/* 1. Login Route */}
      <Route 
        path="/login" 
        element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <Login />} 
      />

      {/* 2. Protected Routes Container */}
      <Route 
        path="/" 
        element={isAuthenticated ? <Layout /> : <Navigate to="/login" replace />}
      >
        {/* Redirect base path to dashboard */}
        <Route index element={<Navigate to="/dashboard" replace />} />
        
        {/* All Main Pages — guarded by per-page permission */}
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
        
        {/* Admin Route with explicit check */}
        <Route 
          path="admin" 
          element={isAdmin ? <Admin /> : <Navigate to="/dashboard" replace />} 
        />

        <Route path="screener" element={<RequirePage page="screener"><Screener /></RequirePage>} />
        <Route path="sector-rotation" element={<RequirePage page="sector-rotation"><SectorRotation /></RequirePage>} />
        <Route path="earnings" element={<RequirePage page="earnings"><EarningsCalendar /></RequirePage>} />

        {/* Catch-all within the layout */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>

      {/* Public shared report — no auth */}
      <Route path="/share/:token" element={<Suspense fallback={null}><SharedReport /></Suspense>} />

      {/* 3. Global Fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
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
    </ErrorBoundary>
  )
}
