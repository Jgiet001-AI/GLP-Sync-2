import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { dashboardApiClient, clientsApiClient } from '../../api/client'
import { useSearchHistory, useSearchNamespace } from '../../hooks/useSearchHistory'
import { normalizeDeviceType } from '../../utils/deviceType'
import type { DeviceListItem, SubscriptionListItem } from '../../types'
import type { ClientItem } from '../../api/client'
import {
  Search,
  Server,
  Shield,
  Wifi,
  Router,
  HardDrive,
  LayoutDashboard,
  Upload,
  ArrowRight,
  Command,
  Clock,
  X,
  Copy,
  Users,
  Hash,
  Trash2,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

// Device type icons
const deviceIcons: Record<string, typeof Server> = {
  AP: Wifi,
  SWITCH: Router,
  GATEWAY: Router,
  IAP: Wifi,
  COMPUTE: Server,
  STORAGE: HardDrive,
  UNKNOWN: Server,
}

// Quick navigation items
const quickNavItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard, keywords: ['home', 'overview', 'stats', 'kpi'] },
  { label: 'Devices', path: '/devices', icon: Server, keywords: ['device', 'serial', 'mac', 'network'] },
  { label: 'Subscriptions', path: '/subscriptions', icon: Shield, keywords: ['license', 'subscription', 'key', 'expiring'] },
  { label: 'Clients', path: '/clients', icon: Users, keywords: ['client', 'wireless', 'wired', 'connected'] },
  { label: 'Assignment', path: '/assignment', icon: Upload, keywords: ['assign', 'upload', 'bulk', 'excel'] },
]

// Quick filter shortcuts
const quickFilters = [
  { label: 'Unassigned Devices', path: '/devices?assigned_state=UNASSIGNED', icon: Server, color: 'amber' },
  { label: 'Expiring Soon', path: '/subscriptions?sort_by=end_time&sort_order=asc', icon: Shield, color: 'rose' },
  { label: 'APs Only', path: '/devices?device_type=AP', icon: Wifi, color: 'sky' },
  { label: 'Active Subscriptions', path: '/subscriptions?status=STARTED', icon: Shield, color: 'emerald' },
]

type ResultType = 'nav' | 'filter' | 'device' | 'subscription' | 'client' | 'recent'

interface SearchResult {
  type: ResultType
  id: string
  title: string
  subtitle: string
  icon: typeof Server
  href: string
  color?: string
  metadata?: Record<string, string>
  onAction?: () => void
}

/**
 * Debounce hook for search input
 * Addresses Codex feedback: avoid firing network requests on every keystroke
 */
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [activeSection, setActiveSection] = useState<ResultType | 'all'>('all')
  const inputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // Search history with namespacing
  const namespace = useSearchNamespace()
  const { history, addSearch, removeSearch, getRecent, formatRelativeTime } = useSearchHistory({
    namespace,
    maxItems: 10,
  })

  // Debounced search query (300ms) - Codex recommendation
  const debouncedQuery = useDebounce(query, 300)

  // Search devices with debounced query
  const { data: deviceResults, isLoading: loadingDevices } = useQuery({
    queryKey: ['device-search', debouncedQuery],
    queryFn: () => dashboardApiClient.searchDevices(debouncedQuery, 5),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30000,
  })

  // Search subscriptions
  const { data: subscriptionResults, isLoading: loadingSubscriptions } = useQuery({
    queryKey: ['subscription-search', debouncedQuery],
    queryFn: () =>
      dashboardApiClient.getSubscriptions({
        search: debouncedQuery,
        page_size: 5,
      }),
    enabled: debouncedQuery.length >= 2,
    staleTime: 30000,
  })

  // Search clients
  const { data: clientResults, isLoading: loadingClients } = useQuery({
    queryKey: ['client-search', debouncedQuery],
    queryFn: () => clientsApiClient.searchClients(debouncedQuery, { page_size: 5 }),
    enabled: debouncedQuery.length >= 3,
    staleTime: 30000,
  })

  const isLoading = loadingDevices || loadingSubscriptions || loadingClients

  // Filter quick nav items based on query
  const filteredNavItems = useMemo(() => {
    if (!query) return quickNavItems
    const lowerQuery = query.toLowerCase()
    return quickNavItems.filter(
      (item) =>
        item.label.toLowerCase().includes(lowerQuery) ||
        item.keywords.some((k) => k.includes(lowerQuery))
    )
  }, [query])

  // Filter quick filters based on query
  const filteredQuickFilters = useMemo(() => {
    if (!query) return quickFilters
    const lowerQuery = query.toLowerCase()
    return quickFilters.filter((item) => item.label.toLowerCase().includes(lowerQuery))
  }, [query])

  // Combine all results into unified list
  const allResults = useMemo<SearchResult[]>(() => {
    const results: SearchResult[] = []

    // Recent searches (only when no query)
    if (!query && history.length > 0) {
      getRecent(undefined, 3).forEach((item) => {
        results.push({
          type: 'recent',
          id: `recent-${item.query}-${item.type}`,
          title: item.query,
          subtitle: `Searched ${formatRelativeTime(item.timestamp)}${item.resultCount !== undefined ? ` · ${item.resultCount} results` : ''}`,
          icon: Clock,
          href: item.type === 'device'
            ? `/devices?search=${encodeURIComponent(item.query)}`
            : item.type === 'subscription'
              ? `/subscriptions?search=${encodeURIComponent(item.query)}`
              : `/devices?search=${encodeURIComponent(item.query)}`,
          color: 'slate',
          onAction: () => {
            setQuery(item.query)
          },
        })
      })
    }

    // Navigation items
    filteredNavItems.forEach((item) => {
      results.push({
        type: 'nav',
        id: `nav-${item.path}`,
        title: item.label,
        subtitle: 'Navigate',
        icon: item.icon,
        href: item.path,
        color: 'emerald',
      })
    })

    // Quick filters (when no search query)
    if (!query) {
      filteredQuickFilters.forEach((item) => {
        results.push({
          type: 'filter',
          id: `filter-${item.path}`,
          title: item.label,
          subtitle: 'Quick Filter',
          icon: item.icon,
          href: item.path,
          color: item.color,
        })
      })
    }

    // Device results
    if (deviceResults?.items) {
      deviceResults.items.forEach((device: DeviceListItem) => {
        const displayType = normalizeDeviceType(device.device_type)
        const Icon = deviceIcons[displayType] || Server
        results.push({
          type: 'device',
          id: `device-${device.id}`,
          title: device.serial_number,
          subtitle: `${displayType} · ${device.mac_address || 'No MAC'}${device.region ? ` · ${device.region}` : ''}`,
          icon: Icon,
          href: `/devices?search=${encodeURIComponent(device.serial_number)}`,
          color: 'sky',
          metadata: {
            serial: device.serial_number,
            mac: device.mac_address || '',
            status: device.assigned_state || '',
          },
        })
      })
    }

    // Subscription results
    if (subscriptionResults?.items) {
      subscriptionResults.items.forEach((sub: SubscriptionListItem) => {
        results.push({
          type: 'subscription',
          id: `subscription-${sub.id}`,
          title: sub.key,
          subtitle: `${sub.subscription_type?.replace('CENTRAL_', '') || 'Subscription'} · ${sub.device_count} devices`,
          icon: Shield,
          href: `/subscriptions?search=${encodeURIComponent(sub.key)}`,
          color: 'violet',
          metadata: {
            key: sub.key,
            status: sub.subscription_status || '',
          },
        })
      })
    }

    // Client results
    if (clientResults?.items) {
      clientResults.items.forEach((client: ClientItem) => {
        results.push({
          type: 'client',
          id: `client-${client.id}`,
          title: client.name || client.mac,
          subtitle: `${client.type || 'Client'} · ${client.ipv4 || 'No IP'}${client.site_name ? ` · ${client.site_name}` : ''}`,
          icon: Users,
          href: `/clients?search=${encodeURIComponent(client.mac)}`,
          color: 'cyan',
          metadata: {
            mac: client.mac,
            ip: client.ipv4 || '',
          },
        })
      })
    }

    // Filter by active section
    if (activeSection !== 'all') {
      return results.filter((r) => r.type === activeSection)
    }

    return results
  }, [
    query,
    history,
    filteredNavItems,
    filteredQuickFilters,
    deviceResults,
    subscriptionResults,
    clientResults,
    activeSection,
    getRecent,
    formatRelativeTime,
  ])

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [allResults.length])

  // Focus input when opened
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus()
    }
  }, [open])

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery('')
      setSelectedIndex(0)
      setActiveSection('all')
    }
  }, [open])

  // Scroll selected item into view
  useEffect(() => {
    if (resultsRef.current && allResults.length > 0) {
      const selectedEl = resultsRef.current.querySelector(`[data-index="${selectedIndex}"]`)
      selectedEl?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex, allResults.length])

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex((prev) => Math.min(prev + 1, allResults.length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex((prev) => Math.max(prev - 1, 0))
          break
        case 'Enter': {
          e.preventDefault()
          const selected = allResults[selectedIndex]
          if (selected) {
            if (selected.onAction) {
              selected.onAction()
            } else {
              // Record in search history
              if (query && (selected.type === 'device' || selected.type === 'subscription' || selected.type === 'client')) {
                const totalResults =
                  (deviceResults?.items?.length || 0) +
                  (subscriptionResults?.items?.length || 0) +
                  (clientResults?.items?.length || 0)
                addSearch(query, selected.type as 'device' | 'subscription' | 'client', totalResults)
              }
              navigate(selected.href)
              onClose()
            }
          }
          break
        }
        case 'Escape':
          onClose()
          break
        case 'Tab': {
          e.preventDefault()
          // Cycle through sections
          const sections: (ResultType | 'all')[] = ['all', 'device', 'subscription', 'client', 'nav']
          const currentIdx = sections.indexOf(activeSection)
          setActiveSection(sections[(currentIdx + 1) % sections.length])
          break
        }
      }
    },
    [allResults, selectedIndex, navigate, onClose, query, addSearch, deviceResults, subscriptionResults, clientResults, activeSection]
  )

  // Copy to clipboard action
  const copyToClipboard = useCallback((text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied`)
  }, [])

  if (!open) return null

  const getColorClass = (color?: string) => {
    switch (color) {
      case 'emerald':
        return 'bg-emerald-500/10 text-emerald-400'
      case 'sky':
        return 'bg-sky-500/10 text-sky-400'
      case 'violet':
        return 'bg-violet-500/10 text-violet-400'
      case 'amber':
        return 'bg-amber-500/10 text-amber-400'
      case 'rose':
        return 'bg-rose-500/10 text-rose-400'
      case 'cyan':
        return 'bg-cyan-500/10 text-cyan-400'
      case 'slate':
        return 'bg-slate-500/10 text-slate-400'
      default:
        return 'bg-slate-700/50 text-slate-400'
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Command palette */}
      <div className="fixed left-1/2 top-[15%] w-full max-w-2xl -translate-x-1/2 transform px-4">
        <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-800 shadow-2xl ring-1 ring-black/10">
          {/* Search input */}
          <div className="relative border-b border-slate-700">
            <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search devices, subscriptions, clients, or type a command..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent py-4 pl-12 pr-24 text-white placeholder-slate-400 focus:outline-none"
              aria-label="Search"
            />
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
              {query && (
                <button
                  onClick={() => setQuery('')}
                  className="rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
                  aria-label="Clear search"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
              <kbd className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">esc</kbd>
            </div>
          </div>

          {/* Section tabs */}
          <div className="flex gap-1 border-b border-slate-700/50 px-2 py-2">
            {[
              { key: 'all', label: 'All' },
              { key: 'device', label: 'Devices' },
              { key: 'subscription', label: 'Subscriptions' },
              { key: 'client', label: 'Clients' },
              { key: 'nav', label: 'Pages' },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveSection(tab.key as ResultType | 'all')}
                className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
                  activeSection === tab.key
                    ? 'bg-hpe-green/20 text-hpe-green'
                    : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Results */}
          <div ref={resultsRef} className="max-h-[60vh] overflow-y-auto">
            {/* Loading state */}
            {isLoading && query.length >= 2 && (
              <div className="flex items-center gap-2 px-4 py-6 text-slate-400">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-hpe-green" />
                Searching...
              </div>
            )}

            {/* Empty state */}
            {!isLoading && query.length >= 2 && allResults.length === 0 && (
              <div className="px-4 py-8 text-center">
                <Search className="mx-auto h-8 w-8 text-slate-600" />
                <p className="mt-2 text-sm text-slate-400">No results found for "{query}"</p>
                <p className="mt-1 text-xs text-slate-500">
                  Try searching by serial number, MAC address, or subscription key
                </p>
              </div>
            )}

            {/* Results list */}
            {allResults.length > 0 && (
              <div className="p-2">
                {/* Group results by type */}
                {['recent', 'nav', 'filter', 'device', 'subscription', 'client']
                  .filter((type) => activeSection === 'all' || activeSection === type)
                  .map((type) => {
                    const typeResults = allResults.filter((r) => r.type === type)
                    if (typeResults.length === 0) return null

                    const labels: Record<string, string> = {
                      recent: 'Recent Searches',
                      nav: 'Pages',
                      filter: 'Quick Filters',
                      device: 'Devices',
                      subscription: 'Subscriptions',
                      client: 'Clients',
                    }

                    return (
                      <div key={type} className="mb-2">
                        <p className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                          {labels[type]}
                        </p>
                        {typeResults.map((result) => {
                          const globalIndex = allResults.indexOf(result)
                          const isSelected = globalIndex === selectedIndex
                          const Icon = result.icon

                          return (
                            <div
                              key={result.id}
                              data-index={globalIndex}
                              className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                                isSelected
                                  ? 'bg-hpe-green/10 text-white'
                                  : 'text-slate-300 hover:bg-slate-700/50'
                              }`}
                              onClick={() => {
                                if (result.onAction) {
                                  result.onAction()
                                } else {
                                  if (query && (result.type === 'device' || result.type === 'subscription' || result.type === 'client')) {
                                    addSearch(query, result.type, allResults.filter((r) => r.type === result.type).length)
                                  }
                                  navigate(result.href)
                                  onClose()
                                }
                              }}
                              onMouseEnter={() => setSelectedIndex(globalIndex)}
                            >
                              <div className={`rounded-lg p-2 ${getColorClass(result.color)}`}>
                                <Icon className="h-4 w-4" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className={`text-sm font-medium ${result.type === 'device' || result.type === 'subscription' ? 'font-mono' : ''}`}>
                                  {result.title}
                                </p>
                                <p className="truncate text-xs text-slate-500">{result.subtitle}</p>
                              </div>

                              {/* Quick actions */}
                              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                {result.metadata?.serial && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      copyToClipboard(result.metadata!.serial!, 'Serial')
                                    }}
                                    className="rounded p-1 text-slate-400 hover:bg-slate-600 hover:text-white"
                                    title="Copy serial"
                                  >
                                    <Hash className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                {result.metadata?.mac && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      copyToClipboard(result.metadata!.mac!, 'MAC')
                                    }}
                                    className="rounded p-1 text-slate-400 hover:bg-slate-600 hover:text-white"
                                    title="Copy MAC"
                                  >
                                    <Copy className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                {result.metadata?.key && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      copyToClipboard(result.metadata!.key!, 'Key')
                                    }}
                                    className="rounded p-1 text-slate-400 hover:bg-slate-600 hover:text-white"
                                    title="Copy key"
                                  >
                                    <Copy className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                {result.type === 'recent' && (
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      removeSearch(result.title, 'all')
                                    }}
                                    className="rounded p-1 text-slate-400 hover:bg-slate-600 hover:text-rose-400"
                                    title="Remove from history"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                <ArrowRight className="h-4 w-4 text-slate-500" />
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )
                  })}
              </div>
            )}

            {/* Initial state - show recent + quick access */}
            {!query && allResults.length === 0 && (
              <div className="p-4 text-center text-sm text-slate-500">
                <p>Type to search devices, subscriptions, or clients</p>
                <p className="mt-1 text-xs">
                  Use <kbd className="rounded bg-slate-700 px-1 py-0.5 text-xs">Tab</kbd> to filter by type
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-slate-700 bg-slate-800/50 px-4 py-2">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1">
                  <kbd className="rounded bg-slate-700 px-1 py-0.5">↑</kbd>
                  <kbd className="rounded bg-slate-700 px-1 py-0.5">↓</kbd>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="rounded bg-slate-700 px-1.5 py-0.5">↵</kbd>
                  select
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="rounded bg-slate-700 px-1.5 py-0.5">tab</kbd>
                  filter
                </span>
              </div>
              <span className="flex items-center gap-1">
                <Command className="h-3 w-3" />K to open
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
