import { lazy, Suspense, useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { LayoutDashboard, Upload, Menu, X, Server, Shield, Search, Command, Users, FileText } from 'lucide-react'
import { CommandPalette } from './components/ui/CommandPalette'
import { Breadcrumbs } from './components/navigation/Breadcrumbs'
import { ChatWidget } from './components/chat'
import { BackgroundTaskProvider } from './contexts/BackgroundTaskContext'
import { BackgroundTaskIndicator } from './components/BackgroundTaskIndicator'
import { useConfig } from './hooks/useConfig'

// Lazy load page components for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })))
const DevicesList = lazy(() => import('./pages/DevicesList').then(m => ({ default: m.DevicesList })))
const SubscriptionsList = lazy(() => import('./pages/SubscriptionsList').then(m => ({ default: m.SubscriptionsList })))
const DeviceAssignment = lazy(() => import('./pages/DeviceAssignment').then(m => ({ default: m.DeviceAssignment })))
const ClientsPage = lazy(() => import('./pages/ClientsPage').then(m => ({ default: m.ClientsPage })))
const ReportBuilder = lazy(() => import('./pages/ReportBuilder').then(m => ({ default: m.ReportBuilder })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
})

// Loading fallback component
function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent" />
        <p className="text-slate-400">Loading...</p>
      </div>
    </div>
  )
}

// Breadcrumb wrapper - only shows on non-dashboard pages
function BreadcrumbWrapper() {
  const location = useLocation()

  // Don't show breadcrumbs on dashboard
  if (location.pathname === '/') return null

  return (
    <div className="border-b border-slate-800/50 bg-slate-900/50 backdrop-blur-sm">
      <div className="mx-auto max-w-[1600px] px-6 py-3">
        <Breadcrumbs />
      </div>
    </div>
  )
}

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/devices', label: 'Devices', icon: Server },
  { path: '/subscriptions', label: 'Subscriptions', icon: Shield },
  { path: '/clients', label: 'Clients', icon: Users },
  { path: '/assignment', label: 'Assignment', icon: Upload },
  { path: '/reports/builder', label: 'Reports', icon: FileText },
] as const

function Navigation({ onOpenSearch }: { onOpenSearch: () => void }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-slate-800 bg-slate-900/95 backdrop-blur-xl">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-600">
              <span className="text-lg font-bold text-white">G</span>
            </div>
            <div>
              <span className="text-lg font-semibold text-white">GreenLake</span>
              <span className="ml-1.5 text-lg font-light text-slate-400">Sync</span>
            </div>
          </div>

          {/* Desktop Navigation */}
          <div className="hidden sm:flex sm:items-center sm:gap-1">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  data-testid={`nav-${item.label.toLowerCase()}`}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all border-b-2 ${
                      isActive
                        ? 'bg-hpe-green/10 text-hpe-green border-hpe-green'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent'
                    }`
                  }
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              )
            })}

            {/* Search button */}
            <button
              onClick={onOpenSearch}
              className="ml-2 flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm text-slate-400 transition-colors hover:border-slate-600 hover:text-white"
              aria-label="Open search"
            >
              <Search className="h-4 w-4" />
              <span className="hidden lg:inline">Search</span>
              <kbd className="hidden lg:inline-flex items-center gap-0.5 rounded bg-slate-700 px-1.5 py-0.5 text-xs">
                <Command className="h-3 w-3" />K
              </kbd>
            </button>
          </div>

          {/* Mobile menu button */}
          <div className="flex items-center gap-2 sm:hidden">
            <button
              onClick={onOpenSearch}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
              aria-label="Open search"
            >
              <Search className="h-5 w-5" />
            </button>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={mobileMenuOpen}
              data-testid="mobile-menu-button"
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav className="sm:hidden border-t border-slate-800 py-2" aria-label="Mobile navigation">
            {navItems.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  onClick={() => setMobileMenuOpen(false)}
                  data-testid={`mobile-nav-${item.label.toLowerCase()}`}
                  className={({ isActive }) =>
                    `flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-all border-b-2 ${
                      isActive
                        ? 'bg-hpe-green/10 text-hpe-green border-hpe-green'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white border-transparent'
                    }`
                  }
                >
                  <Icon className="h-5 w-5" />
                  {item.label}
                </NavLink>
              )
            })}
          </nav>
        )}
      </div>
    </nav>
  )
}

function App() {
  const [searchOpen, setSearchOpen] = useState(false)
  const { config } = useConfig()

  // Global keyboard shortcut for search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K to open search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <BackgroundTaskProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-slate-900">
            <Navigation onOpenSearch={() => setSearchOpen(true)} />
            <main className="pt-16">
              {/* Breadcrumb navigation - shows on all pages except dashboard */}
              <BreadcrumbWrapper />
              <Suspense fallback={<PageLoader />}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/devices" element={<DevicesList />} />
                  <Route path="/subscriptions" element={<SubscriptionsList />} />
                  <Route path="/clients" element={<ClientsPage />} />
                  <Route path="/assignment" element={<DeviceAssignment />} />
                  <Route path="/reports/builder" element={<ReportBuilder />} />
                </Routes>
              </Suspense>
            </main>
            <Toaster
              position="bottom-left"
              toastOptions={{
                className: '',
                style: {
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)',
                },
                success: {
                  iconTheme: {
                    primary: 'var(--color-hpe-green)',
                    secondary: 'var(--color-text-primary)',
                  },
                },
                error: {
                  iconTheme: {
                    primary: 'var(--color-error)',
                    secondary: 'var(--color-text-primary)',
                  },
                },
              }}
            />
            {/* Global Command Palette */}
            <CommandPalette open={searchOpen} onClose={() => setSearchOpen(false)} />
            {/* AI Chat Widget - only shown if chatbot is enabled */}
            {config.chatbot_enabled && (
              <ChatWidget apiBaseUrl="/api/agent" position="bottom-right" />
            )}
            {/* Background Task Indicator (bottom-right, above chat) */}
            <BackgroundTaskIndicator />
          </div>
        </BrowserRouter>
      </BackgroundTaskProvider>
    </QueryClientProvider>
  )
}

export default App
