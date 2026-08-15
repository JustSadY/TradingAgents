import { NavLink, useNavigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { usePermissions } from '../contexts/PermissionsContext'
import { useTranslation } from '../contexts/LanguageContext'
import { useCurrency, CURRENCIES, type Currency } from '../contexts/CurrencyContext'
import {
  LayoutDashboard, Search, BookMarked, Briefcase,
  Settings, ScrollText, TrendingUp, LogOut, Clock,
  FlaskConical, PieChart, Loader2, ChevronRight,
  AlertCircle, AlertTriangle, CheckCircle, Info, X,
  BarChart2, Bell, Menu, GitCompare, Shield, UserCircle, History, Filter, Globe2, CalendarDays,
} from 'lucide-react'
import { useEffect, useState, useCallback, Suspense } from 'react'
import { useCronCronStatus } from '../api/generated/cron/cron'
import type { Notification } from '../utils/notify'
import UpdateBanner from './UpdateBanner'
import { PortfolioAssistant } from './assistant/PortfolioAssistant'

interface NavItem {
  to: string
  key: string
  page: string
  icon: any
  adminOnly?: boolean
  isProfile?: boolean
}

interface NavSection {
  sectionKey: string
  items: NavItem[]
}

const NAV_SECTIONS: NavSection[] = [
  {
    sectionKey: 'nav.section.trading_desk',
    items: [
      { to: '/dashboard',   key: 'nav.dashboard',    page: 'dashboard',   icon: LayoutDashboard },
      { to: '/analysis',    key: 'nav.analysis',     page: 'analysis',    icon: Search },
      { to: '/chart',       key: 'nav.chart',        page: 'chart',       icon: TrendingUp },
      { to: '/ab-testing',  key: 'nav.ab_testing',   page: 'ab-testing',  icon: GitCompare },
    ]
  },
  {
    sectionKey: 'nav.section.portfolio_trading',
    items: [
      { to: '/portfolio',   key: 'nav.portfolio',    page: 'portfolio',   icon: PieChart },
      { to: '/trading',     key: 'nav.simulation',   page: 'trading',     icon: FlaskConical },
      { to: '/orders',      key: 'nav.orders',       page: 'orders',      icon: Briefcase },
      { to: '/performance', key: 'nav.performance',  page: 'performance', icon: BarChart2 },
      { to: '/backtest',    key: 'nav.backtest',     page: 'backtest',    icon: History },
    ]
  },
  {
    sectionKey: 'nav.section.market_tools',
    items: [
      { to: '/watchlist',        key: 'nav.watchlist',         page: 'watchlist',       icon: BookMarked },
      { to: '/screener',         key: 'nav.screener',          page: 'screener',        icon: Filter },
      { to: '/sector-rotation',  key: 'nav.sector_rotation',   page: 'sector-rotation', icon: Globe2 },
      { to: '/earnings',         key: 'nav.earnings_calendar', page: 'earnings',        icon: CalendarDays },
      { to: '/alerts',           key: 'nav.alerts',            page: 'alerts',          icon: Bell },
    ]
  },
  {
    sectionKey: 'nav.section.system_config',
    items: [
      { to: '/settings',    key: 'nav.settings',     page: 'settings',    icon: Settings },
      { to: '/profile',     key: 'nav.profile',      page: 'profile',     icon: UserCircle, isProfile: true },
      { to: '/logs',        key: 'nav.logs',         page: 'logs',        icon: ScrollText },
      { to: '/admin',       key: 'nav.admin',        page: 'admin',       icon: Shield, adminOnly: true },
    ]
  }
]

import { useActiveTasks } from '../hooks/useActiveTasks'

export default function Layout() {
  const { user, isAdmin, logout } = useAuth()
  const { canAccess } = usePermissions()
  const navigate = useNavigate()
  const { language, setLanguage, t } = useTranslation()
  const { currency, setCurrency } = useCurrency()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { activeTasks } = useActiveTasks()
  const activeTask = activeTasks[0] || null

  const cronQuery = useCronCronStatus({ query: { refetchInterval: 30_000 } })
  const cronStatus = (cronQuery.data ?? { next_run_time: null }) as { next_run_time: string | null }

  const handleLogout = () => { logout(); navigate('/login') }

  const [toasts, setToasts] = useState<Notification[]>([])
  const { isOwner, isAdmin: isAtLeastAdmin } = useAuth()

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const n = (e as CustomEvent<Notification>).detail
      const vis = n.visibility || 'all'
      let visible = false
      if (vis === 'all') visible = true
      else if (vis === 'admin') visible = isAtLeastAdmin
      else if (vis === 'owner') visible = isOwner

      if (!visible) return

      setToasts(prev => [...prev.slice(-4), n])
      const ms = n.type === 'error' ? 6000 : 4000
      setTimeout(() => dismiss(n.id), ms)
    }
    window.addEventListener('ta-notify', handler)
    return () => window.removeEventListener('ta-notify', handler)
  }, [dismiss, isAtLeastAdmin, isOwner])

  return (
    <div className="flex min-h-screen bg-[#030712] text-slate-100 font-sans">
      {/* Mobile Header */}
      <header className="md:hidden fixed top-0 left-0 right-0 z-[90] h-14 bg-gray-950/80 backdrop-blur-md border-b border-gray-800/60 flex items-center px-4 gap-3 shrink-0">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/5 transition-colors"
        >
          <Menu size={20} />
        </button>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-600/30">
            <TrendingUp size={14} className="text-white" strokeWidth={2.5} />
          </div>
          <p className="text-white font-display font-bold text-sm tracking-tight">TradingAgents</p>
        </div>
        {activeTask && (
          <div className="ml-auto flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-lg">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-emerald-400 text-[10px] font-mono font-bold uppercase">{activeTask.ticker}</span>
          </div>
        )}
      </header>

      {/* Backdrop for Mobile Sidebar */}
      {sidebarOpen && (
        <div
          className="md:hidden fixed inset-0 z-[95] bg-black/70 backdrop-blur-sm transition-opacity duration-200"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar Navigation */}
      <aside className={`
        fixed inset-y-0 left-0 z-[100] w-64 bg-gray-950 border-r border-white/[0.04] flex flex-col
        transition-transform duration-300 cubic-bezier(0.4, 0, 0.2, 1)
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        md:relative md:w-60 md:translate-x-0 md:shrink-0
      `}>
        {/* Brand Logo & Info */}
        <div className="px-5 py-5 border-b border-white/[0.04] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 via-violet-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-500/25">
              <TrendingUp size={16} className="text-white" strokeWidth={2.5} />
            </div>
            <div>
              <p className="text-white font-display font-bold text-sm tracking-tight leading-none">TradingAgents</p>
              <p className="text-slate-500 text-[10px] font-medium mt-1 uppercase tracking-wider">AI Portfolio manager</p>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="md:hidden p-1.5 rounded-lg text-slate-500 hover:text-white hover:bg-white/5 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Navigation Categories */}
        <nav className="flex-1 px-3 py-4 space-y-5 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-800">
          {NAV_SECTIONS.map(section => {
            const visibleItems = section.items.filter(item => {
              if (item.adminOnly) return isAdmin
              if (item.isProfile) return true
              return canAccess(item.page)
            })

            if (visibleItems.length === 0) return null

            return (
              <div key={section.sectionKey} className="space-y-1">
                <h3 className="px-3 text-[9px] font-bold text-slate-500 uppercase tracking-widest select-none mb-1.5 opacity-60">
                  {t(section.sectionKey)}
                </h3>

                <div className="space-y-0.5">
                  {visibleItems.map(({ to, key, icon: Icon, adminOnly }) => (
                    <NavLink
                      key={to}
                      to={to}
                      onClick={() => setSidebarOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-3 py-2.5 rounded-xl text-[11px] font-medium transition-all duration-200 group border border-transparent ` +
                        (isActive
                          ? adminOnly
                            ? 'bg-amber-500/10 text-amber-300 border-amber-500/20 active-nav-glow font-semibold'
                            : 'bg-violet-500/10 text-violet-300 border-violet-500/20 active-nav-glow font-semibold'
                          : 'text-slate-400 hover:text-white hover:bg-white/[0.02]')
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <Icon
                            size={14}
                            className={
                              isActive
                                ? adminOnly ? 'text-amber-400' : 'text-violet-400'
                                : 'text-slate-400 group-hover:text-slate-200'
                            }
                          />
                          <span className="flex-1">{t(key)}</span>
                          {isActive && (
                            <ChevronRight
                              size={10}
                              className={adminOnly ? 'text-amber-500 opacity-60' : 'text-violet-500 opacity-60'}
                            />
                          )}
                        </>
                      )}
                    </NavLink>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        {/* Background Task Indicator */}
        {activeTask && (
          <div className="mx-3 mb-2 px-3 py-2.5 rounded-xl bg-emerald-500/5 border border-emerald-500/15">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <Loader2 size={12} className="text-emerald-400 animate-spin shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-emerald-300 text-[10px] font-bold truncate leading-none mb-0.5">{activeTask.ticker} {t('nav.analyzing')}</p>
                <p className="text-emerald-500/70 text-[9px] font-medium">{t('nav.running_in_bg')}</p>
              </div>
            </div>
          </div>
        )}

        {/* Next Scheduled Scan */}
        {cronStatus.next_run_time && (
          <div className="mx-3 mb-2 px-3 py-2 rounded-xl bg-white/[0.02] border border-white/[0.04]">
            <div className="flex items-center gap-1.5 text-[9px] text-slate-500 font-medium">
              <Clock size={11} className="text-violet-400" />
              <span>{t('nav.next_run')}: {new Date(cronStatus.next_run_time).toLocaleTimeString(language === 'tr' ? 'tr-TR' : 'en-US', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>
        )}

        {/* Language / Currency Selection & User Menu */}
        <div className="px-3 py-3 border-t border-white/[0.04] space-y-3 bg-gray-950/40">
          <div className="flex items-center justify-between px-3 text-[10px] text-slate-500 font-medium">
            <span>{t('settings.language')}</span>
            <div className="flex gap-1 bg-white/[0.02] p-0.5 rounded-lg border border-white/[0.04]">
              <button
                onClick={() => setLanguage('en')}
                className={`px-2 py-0.5 rounded-md transition-all text-[9px] font-bold ${
                  language === 'en' ? 'bg-violet-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                EN
              </button>
              <button
                onClick={() => setLanguage('tr')}
                className={`px-2 py-0.5 rounded-md transition-all text-[9px] font-bold ${
                  language === 'tr' ? 'bg-violet-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                TR
              </button>
            </div>
          </div>
          <div className="flex items-center justify-between px-3 text-[10px] text-slate-500 font-medium">
            <span>Currency</span>
            <select
              value={currency}
              onChange={e => setCurrency(e.target.value as Currency)}
              className="bg-white/[0.04] border border-white/[0.06] text-slate-300 text-[9px] font-bold rounded-lg px-2 py-0.5 outline-none cursor-pointer"
            >
              {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/[0.02] transition-colors group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center text-white text-xs font-bold shrink-0 shadow shadow-violet-500/20">
              {user?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-slate-300 text-xs font-semibold block truncate leading-none">{user}</span>
              <span className="text-[9px] text-slate-500 uppercase tracking-wide block mt-1 font-medium">{isAdmin ? 'Admin' : 'User'}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-500 hover:text-red-400 transition-colors p-1 rounded-lg hover:bg-white/5 opacity-0 group-hover:opacity-100 shrink-0"
              title={t('nav.logout')}
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <main className="flex-1 overflow-y-auto min-h-screen pt-14 md:pt-0 flex flex-col bg-[#030712] relative z-0">
        <UpdateBanner />
        <div className="flex-1">
          <Suspense fallback={
            <div className="flex items-center justify-center h-[60vh] text-slate-600">
              <Loader2 size={20} className="animate-spin text-violet-400" />
            </div>
          }>
            <Outlet />
          </Suspense>
        </div>
      </main>

      {/* Portfolio Assistant floating widget */}
      <PortfolioAssistant />

      {/* Notification Toast Stream */}
      {toasts.length > 0 && (
        <div className="fixed bottom-5 right-3 z-50 flex flex-col gap-2 w-[calc(100vw-1.5rem)] max-w-sm sm:w-96 sm:right-5 sm:max-w-none">
          {toasts.map(t => <Toast key={t.id} n={t} onDismiss={dismiss} />)}
        </div>
      )}
    </div>
  )
}

const TOAST_STYLES = {
  error:   { bar: 'bg-red-500',    bg: 'bg-red-950/20 border-red-500/20',    icon: AlertCircle,   text: 'text-red-400'    },
  warning: { bar: 'bg-yellow-500', bg: 'bg-yellow-950/20 border-yellow-500/20', icon: AlertTriangle, text: 'text-yellow-400' },
  success: { bar: 'bg-emerald-500',bg: 'bg-emerald-950/20 border-emerald-500/20',icon: CheckCircle,   text: 'text-emerald-400'},
  info:    { bar: 'bg-blue-500',   bg: 'bg-blue-950/20 border-blue-500/20',   icon: Info,          text: 'text-blue-400'   },
}

function Toast({ n, onDismiss }: { n: Notification; onDismiss: (id: string) => void }) {
  const s = TOAST_STYLES[n.type]
  const Icon = s.icon
  return (
    <div className={`relative overflow-hidden rounded-2xl border shadow-xl shadow-black/60 backdrop-blur-md ${s.bg} animate-in slide-in-from-right-4 duration-300`}>
      <div className={`absolute left-0 top-0 bottom-0 w-1.5 ${s.bar}`} />
      <div className="flex items-start gap-3 px-4 py-3.5 pl-5">
        <Icon size={16} className={`${s.text} shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          {n.title && <p className={`text-xs font-bold mb-0.5 ${s.text}`}>{n.title}</p>}
          <p className="text-slate-300 text-xs leading-relaxed break-words">{n.message}</p>
        </div>
        <button
          onClick={() => onDismiss(n.id)}
          className="text-slate-500 hover:text-white transition-colors shrink-0 p-0.5 hover:bg-white/5 rounded"
        >
          <X size={13} />
        </button>
      </div>
    </div>
  )
}
