import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import React from 'react'
import { useAuth } from './hooks/useAuth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Analysis from './pages/Analysis'
import Watchlist from './pages/Watchlist'
import Orders from './pages/Orders'
import Settings from './pages/Settings'
import Logs from './pages/Logs'
import MockTrading from './pages/MockTrading'
import Portfolio from './pages/Portfolio'
import Chart from './pages/Chart'
import Performance from './pages/Performance'
import Alerts from './pages/Alerts'
import ABTesting from './pages/ABTesting'
import Profile from './pages/Profile'
import Admin from './pages/Admin'

import { LanguageProvider } from './contexts/LanguageContext'

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: 'monospace', color: '#f87171', background: '#0f172a', minHeight: '100vh' }}>
          <h2 style={{ color: '#fca5a5', marginBottom: 12 }}>⚠ Uygulama Hatası</h2>
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: '#1e293b', padding: 16, borderRadius: 8, fontSize: 12 }}>
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
          <button
            style={{ marginTop: 16, padding: '8px 16px', background: '#7c3aed', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
            onClick={() => window.location.reload()}
          >
            Yenile
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin, isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return isAdmin ? <>{children}</> : <Navigate to="/dashboard" replace />
}

function AppRoutes() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/dashboard" /> : <Login />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/analysis" element={<Analysis />} />
                <Route path="/chart" element={<Chart />} />
                <Route path="/watchlist" element={<Watchlist />} />
                <Route path="/orders" element={<Orders />} />
                <Route path="/trading" element={<MockTrading />} />
                <Route path="/portfolio" element={<Portfolio />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/performance" element={<Performance />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/ab-testing" element={<ABTesting />} />
                <Route path="/logs" element={<Logs />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
                <Route path="*" element={<Navigate to="/dashboard" />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <LanguageProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </LanguageProvider>
    </ErrorBoundary>
  )
}

