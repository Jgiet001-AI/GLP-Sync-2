import { useState, useEffect, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useBackgroundTasks } from '../contexts/BackgroundTaskContext'
import {
  Users,
  Wifi,
  Cable,
  MapPin,
  ChevronDown,
  RefreshCw,
  Search,
  Heart,
  AlertCircle,
  CheckCircle,
  XCircle,
  Clock,
  Router,
  Laptop,
  Server,
  Signal,
  Filter,
  Info,
  AlertTriangle,
} from 'lucide-react'
import { clientsApiClient, type ClientItem, type SiteStats, type ClientsSummary } from '../api/client'
import { useClientsFilters, type FilterPreset, filtersToQueryParams } from '../hooks/useClientsFilters'
import { ClientsFilterPanel, ClientsFilterBar } from '../components/filters/ClientsFilterPanel'
import { ReportButton } from '../components/reports/ReportButton'
import { useDebouncedSearch } from '../hooks/useDebouncedSearch'
import { PaginationControls } from '../components/shared/PaginationControls'

// Health color mapping
const healthColors = {
  Good: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30', dot: 'bg-emerald-500' },
  Fair: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30', dot: 'bg-amber-500' },
  Poor: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30', dot: 'bg-rose-500' },
  Unknown: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/30', dot: 'bg-slate-500' },
}

// Status color mapping
const statusColors = {
  Connected: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', icon: CheckCircle },
  Disconnected: { bg: 'bg-slate-500/10', text: 'text-slate-400', icon: XCircle },
  Failed: { bg: 'bg-rose-500/10', text: 'text-rose-400', icon: AlertCircle },
  Blocked: { bg: 'bg-orange-500/10', text: 'text-orange-400', icon: XCircle },
  Connecting: { bg: 'bg-sky-500/10', text: 'text-sky-400', icon: Clock },
  Unknown: { bg: 'bg-slate-500/10', text: 'text-slate-400', icon: AlertCircle },
}

// KPI Card Component - Now clickable with accessibility support
function KPICard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = 'emerald',
  onClick,
  isActive = false,
  ariaLabel,
}: {
  title: string
  value: number | string
  subtitle?: string
  icon: typeof Users
  color?: 'emerald' | 'amber' | 'rose' | 'sky' | 'violet' | 'slate'
  onClick?: () => void
  isActive?: boolean
  ariaLabel?: string
}) {
  const colorClasses = {
    emerald: { bg: 'from-emerald-500/20 to-emerald-600/5', border: 'border-emerald-500/30', icon: 'text-emerald-400', activeBorder: 'border-emerald-400' },
    amber: { bg: 'from-amber-500/20 to-amber-600/5', border: 'border-amber-500/30', icon: 'text-amber-400', activeBorder: 'border-amber-400' },
    rose: { bg: 'from-rose-500/20 to-rose-600/5', border: 'border-rose-500/30', icon: 'text-rose-400', activeBorder: 'border-rose-400' },
    sky: { bg: 'from-sky-500/20 to-sky-600/5', border: 'border-sky-500/30', icon: 'text-sky-400', activeBorder: 'border-sky-400' },
    violet: { bg: 'from-violet-500/20 to-violet-600/5', border: 'border-violet-500/30', icon: 'text-violet-400', activeBorder: 'border-violet-400' },
    slate: { bg: 'from-slate-500/20 to-slate-600/5', border: 'border-slate-500/30', icon: 'text-slate-400', activeBorder: 'border-slate-400' },
  }
  const colors = colorClasses[color]

  const baseClasses = `relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 backdrop-blur-xl transition-all duration-300 w-full text-left`
  const interactiveClasses = onClick ? 'cursor-pointer hover:scale-[1.02] focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 focus:ring-violet-500' : ''
  const activeClasses = isActive ? `ring-2 ring-white/50 ${colors.activeBorder}` : colors.border

  const content = (
    <>
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs font-medium uppercase tracking-wider text-slate-400">{title}</p>
          <p className="mt-1 font-mono text-3xl font-bold tracking-tight text-white">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
          {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
        </div>
        <div className={`rounded-xl bg-slate-800/50 p-2.5 ${colors.icon}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      {isActive && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-white/50 to-transparent" />
      )}
    </>
  )

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`${baseClasses} ${interactiveClasses} ${activeClasses} ${colors.bg}`}
        aria-pressed={isActive}
        aria-label={ariaLabel || `Filter by ${title}`}
      >
        {content}
      </button>
    )
  }

  return (
    <div className={`${baseClasses} ${activeClasses} ${colors.bg}`}>
      {content}
    </div>
  )
}

// Health Badge Component
function HealthBadge({ health }: { health?: string }) {
  const healthConfig = healthColors[health as keyof typeof healthColors] || healthColors.Unknown
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${healthConfig.bg} ${healthConfig.text} border ${healthConfig.border}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${healthConfig.dot}`} />
      {health || 'Unknown'}
    </span>
  )
}

// Status Badge Component
function StatusBadge({ status }: { status?: string }) {
  const statusConfig = statusColors[status as keyof typeof statusColors] || statusColors.Unknown
  const Icon = statusConfig.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${statusConfig.bg} ${statusConfig.text}`}>
      <Icon className="h-3 w-3" />
      {status || 'Unknown'}
    </span>
  )
}

// Type Badge Component
function TypeBadge({ type }: { type?: string }) {
  const isWireless = type === 'Wireless'
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
      isWireless ? 'bg-violet-500/10 text-violet-400' : 'bg-sky-500/10 text-sky-400'
    }`}>
      {isWireless ? <Wifi className="h-3 w-3" /> : <Cable className="h-3 w-3" />}
      {type || 'Unknown'}
    </span>
  )
}

// Status Reason Tooltip Component
function StatusReasonTooltip({ reason }: { reason: string }) {
  return (
    <div className="group relative inline-flex">
      <AlertTriangle className="h-4 w-4 text-amber-500 cursor-help" />
      <div className="absolute left-full ml-2 z-20 hidden group-hover:block group-focus:block">
        <div className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs text-slate-300 shadow-xl max-w-xs whitespace-normal">
          <div className="font-medium text-amber-400 mb-1">Status Reason:</div>
          {reason}
        </div>
      </div>
    </div>
  )
}

// Client Row Component - Updated with status_reason tooltip
function ClientRow({ client }: { client: ClientItem }) {
  const hasIssue = client.health === 'Poor' || client.health === 'Fair' || client.status === 'Failed' || client.status === 'Blocked'

  return (
    <tr className="group border-b border-slate-700/30 hover:bg-slate-800/30 transition-colors">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-slate-700/50 p-2">
            <Laptop className="h-4 w-4 text-slate-400" />
          </div>
          <div>
            <p className="font-mono text-sm font-medium text-white">{client.mac}</p>
            {client.name && <p className="text-xs text-slate-400">{client.name}</p>}
          </div>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <HealthBadge health={client.health} />
          {client.status_reason && hasIssue && (
            <StatusReasonTooltip reason={client.status_reason} />
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <StatusBadge status={client.status} />
          {client.status_reason && !hasIssue && (
            <div className="group relative inline-flex">
              <Info className="h-3.5 w-3.5 text-slate-500 cursor-help" />
              <div className="absolute left-full ml-2 z-20 hidden group-hover:block">
                <div className="rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs text-slate-300 shadow-xl max-w-xs whitespace-normal">
                  {client.status_reason}
                </div>
              </div>
            </div>
          )}
        </div>
      </td>
      <td className="px-4 py-3">
        <TypeBadge type={client.type} />
      </td>
      <td className="px-4 py-3">
        {client.ipv4 && (
          <span className="font-mono text-sm text-slate-300">{client.ipv4}</span>
        )}
      </td>
      <td className="px-4 py-3">
        {client.connected_to && (
          <div className="flex items-center gap-2">
            <Router className="h-3.5 w-3.5 text-slate-400" />
            <span className="text-sm text-slate-300">{client.connected_to}</span>
          </div>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {client.last_seen_at && (
          <span className="text-xs text-slate-500">
            {new Date(client.last_seen_at).toLocaleString()}
          </span>
        )}
      </td>
    </tr>
  )
}

// Site Card Component
function SiteCard({ site, isExpanded, onToggle }: { site: SiteStats; isExpanded: boolean; onToggle: () => void }) {
  const { data: clientsData, isLoading } = useQuery({
    queryKey: ['site-clients', site.site_id],
    queryFn: () => clientsApiClient.getSiteClients(site.site_id, { page_size: 100 }),
    enabled: isExpanded,
    staleTime: 30000,
  })

  const healthBreakdown = useMemo(() => [
    { label: 'Good', count: site.good_health_count, color: 'emerald' },
    { label: 'Fair', count: site.fair_health_count, color: 'amber' },
    { label: 'Poor', count: site.poor_health_count, color: 'rose' },
  ], [site])

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-800/30 overflow-hidden transition-all duration-300 hover:border-slate-600/50">
      {/* Site Header */}
      <button
        onClick={onToggle}
        className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-800/50 transition-colors"
      >
        <div className="flex items-center gap-4">
          <div className="rounded-xl bg-gradient-to-br from-violet-500/20 to-violet-600/10 p-3 border border-violet-500/30">
            <MapPin className="h-5 w-5 text-violet-400" />
          </div>
          <div className="text-left">
            <h3 className="text-lg font-semibold text-white">{site.site_name || site.site_id}</h3>
            <div className="flex items-center gap-4 mt-1">
              <span className="flex items-center gap-1.5 text-sm text-slate-400">
                <Users className="h-3.5 w-3.5" />
                {site.client_count.toLocaleString()} clients
              </span>
              <span className="flex items-center gap-1.5 text-sm text-slate-400">
                <Server className="h-3.5 w-3.5" />
                {site.device_count.toLocaleString()} devices
              </span>
              <span className="flex items-center gap-1.5 text-sm text-emerald-400">
                <Signal className="h-3.5 w-3.5" />
                {site.connected_count.toLocaleString()} connected
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {/* Health breakdown mini-bars */}
          <div className="hidden sm:flex items-center gap-3">
            {healthBreakdown.map((item) => (
              <div key={item.label} className="flex items-center gap-1.5">
                <span className={`h-2 w-2 rounded-full bg-${item.color}-500`} />
                <span className={`text-xs text-${item.color}-400`}>{item.count}</span>
              </div>
            ))}
          </div>

          {/* Type breakdown */}
          <div className="hidden md:flex items-center gap-3">
            <span className="flex items-center gap-1 text-xs text-violet-400">
              <Wifi className="h-3 w-3" />
              {site.wireless_count}
            </span>
            <span className="flex items-center gap-1 text-xs text-sky-400">
              <Cable className="h-3 w-3" />
              {site.wired_count}
            </span>
          </div>

          {/* Expand icon */}
          <div className={`text-slate-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}>
            <ChevronDown className="h-5 w-5" />
          </div>
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-slate-700/50">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
            </div>
          ) : clientsData?.items?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-900/50">
                  <tr className="text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                    <th className="px-4 py-3">Client</th>
                    <th className="px-4 py-3">Health</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">IP Address</th>
                    <th className="px-4 py-3">Connected To</th>
                    <th className="px-4 py-3 text-right">Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {clientsData.items.map((client) => (
                    <ClientRow key={client.id} client={client} />
                  ))}
                </tbody>
              </table>
              {clientsData.total > clientsData.items.length && (
                <div className="px-4 py-3 text-center text-sm text-slate-400 bg-slate-900/30">
                  Showing {clientsData.items.length} of {clientsData.total.toLocaleString()} clients
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400">
              <Users className="h-10 w-10 mb-3 opacity-50" />
              <p>No clients found in this site</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Page Size Selector Component
function PageSizeSelector({
  value,
  onChange,
}: {
  value: number
  onChange: (size: number) => void
}) {
  const sizes = [100, 500, 1000]
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-400">Show:</span>
      <div className="flex rounded-lg border border-slate-700 overflow-hidden">
        {sizes.map((size) => (
          <button
            key={size}
            type="button"
            onClick={() => onChange(size)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              value === size
                ? 'bg-violet-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white'
            }`}
          >
            {size}
          </button>
        ))}
      </div>
    </div>
  )
}


// Filtered Clients Table Component
function FilteredClientsTable({ filters }: { filters: ReturnType<typeof useClientsFilters>['filters'] }) {
  const [pageSize, setPageSize] = useState(100)
  const [currentPage, setCurrentPage] = useState(1)
  const queryParams = filtersToQueryParams(filters)

  // Reset page when filters change
  const filterKey = `${queryParams.type}-${queryParams.status}-${queryParams.health}`
  useEffect(() => {
    setCurrentPage(1)
  }, [filterKey])

  const { data, isLoading, error } = useQuery({
    queryKey: ['filtered-clients', queryParams, pageSize, currentPage],
    queryFn: () => clientsApiClient.getFilteredClients({
      ...queryParams,
      page: currentPage,
      page_size: pageSize,
    }),
    staleTime: 30000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-400">
        <AlertCircle className="h-10 w-10 mb-3 text-rose-400" />
        <p>Error loading filtered clients</p>
      </div>
    )
  }

  if (!data?.items?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-slate-400 rounded-2xl border border-slate-700/50 bg-slate-800/30">
        <Users className="h-10 w-10 mb-3 opacity-50" />
        <p>No clients match the selected filters</p>
      </div>
    )
  }

  // Reset page when pageSize changes
  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    setCurrentPage(1)
  }

  return (
    <div className="rounded-2xl border border-slate-700/50 bg-slate-800/30 overflow-hidden">
      {/* Table Header with Page Size */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700/50 bg-slate-900/30">
        <span className="text-sm text-slate-400">
          {data.total.toLocaleString()} clients found
          {data.total_pages > 1 && (
            <span className="ml-2 text-slate-500">
              (Page {currentPage} of {data.total_pages})
            </span>
          )}
        </span>
        <PageSizeSelector value={pageSize} onChange={handlePageSizeChange} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-slate-900/50 sticky top-0">
            <tr className="text-left text-xs font-medium uppercase tracking-wider text-slate-400">
              <th className="px-4 py-3 whitespace-nowrap">Client</th>
              <th className="px-4 py-3 whitespace-nowrap">Site</th>
              <th className="px-4 py-3 whitespace-nowrap">Health</th>
              <th className="px-4 py-3 whitespace-nowrap">Status</th>
              <th className="px-4 py-3 whitespace-nowrap">Type</th>
              <th className="px-4 py-3 whitespace-nowrap">IP Address</th>
              <th className="px-4 py-3 whitespace-nowrap">Network</th>
              <th className="px-4 py-3 whitespace-nowrap">VLAN</th>
              <th className="px-4 py-3 whitespace-nowrap">Port</th>
              <th className="px-4 py-3 whitespace-nowrap">Role</th>
              <th className="px-4 py-3 whitespace-nowrap">Connected To</th>
              <th className="px-4 py-3 whitespace-nowrap">Connected Since</th>
              <th className="px-4 py-3 whitespace-nowrap">Tunnel</th>
              <th className="px-4 py-3 whitespace-nowrap">Auth</th>
              <th className="px-4 py-3 whitespace-nowrap">Key Mgmt</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((client) => (
              <tr key={client.id} className="border-b border-slate-700/30 hover:bg-slate-800/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="rounded-lg bg-slate-700/50 p-2">
                      <Laptop className="h-4 w-4 text-slate-400" />
                    </div>
                    <div>
                      <p className="font-mono text-sm font-medium text-white">{client.mac}</p>
                      {client.name && <p className="text-xs text-slate-400">{client.name}</p>}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-300 whitespace-nowrap">{client.site_name || client.site_id}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <HealthBadge health={client.health} />
                    {client.status_reason && (client.health === 'Poor' || client.health === 'Fair') && (
                      <StatusReasonTooltip reason={client.status_reason} />
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={client.status} />
                    {client.status_reason && (client.status === 'Failed' || client.status === 'Blocked') && (
                      <StatusReasonTooltip reason={client.status_reason} />
                    )}
                  </div>
                </td>
                <td className="px-4 py-3"><TypeBadge type={client.type} /></td>
                <td className="px-4 py-3">
                  <span className="font-mono text-sm text-slate-300 whitespace-nowrap">{client.ipv4 || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-300 whitespace-nowrap">{client.network || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-300">{client.vlan_id || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-300 whitespace-nowrap">{client.port || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-sm text-slate-300 whitespace-nowrap">{client.role || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  {client.connected_to ? (
                    <div className="flex items-center gap-2 whitespace-nowrap">
                      <Router className="h-3.5 w-3.5 text-slate-400" />
                      <span className="text-sm text-slate-300">{client.connected_to}</span>
                    </div>
                  ) : (
                    <span className="text-sm text-slate-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-slate-400 whitespace-nowrap">
                    {client.connected_since
                      ? new Date(client.connected_since).toLocaleString()
                      : '-'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  {client.tunnel ? (
                    <span className="text-xs px-2 py-1 rounded bg-slate-700/50 text-slate-300 whitespace-nowrap">
                      {client.tunnel}
                      {client.tunnel_id && <span className="text-slate-500 ml-1">#{client.tunnel_id}</span>}
                    </span>
                  ) : (
                    <span className="text-sm text-slate-500">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-slate-400 whitespace-nowrap">{client.authentication || '-'}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="text-xs text-slate-400 whitespace-nowrap">{client.key_management || '-'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls */}
      {data.total_pages > 1 && (
        <PaginationControls
          page={currentPage}
          totalPages={data.total_pages}
          total={data.total}
          pageSize={pageSize}
          itemName="clients"
          onPageChange={setCurrentPage}
          variant="text"
          theme="violet"
        />
      )}
    </div>
  )
}

// Main Component
export function ClientsPage() {
  const queryClient = useQueryClient()
  const [expandedSites, setExpandedSites] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [showFilterPanel, setShowFilterPanel] = useState(false)

  // Debounce search to avoid excessive API calls
  const debouncedSearchQuery = useDebouncedSearch(searchQuery, 300)

  // Filter state from URL
  const {
    filters,
    hasFilters,
    activeFilterCount,
    toggleFilterValue,
    applyPreset,
    clearFilters,
    isPresetActive,
  } = useClientsFilters()

  // Fetch summary
  const { data: summary, isLoading: summaryLoading } = useQuery<ClientsSummary>({
    queryKey: ['clients-summary'],
    queryFn: () => clientsApiClient.getSummary(),
    staleTime: 30000,
  })

  // Fetch sites
  const { data: sitesData, isLoading: sitesLoading } = useQuery({
    queryKey: ['clients-sites'],
    queryFn: () => clientsApiClient.getSites({ page_size: 100, sort_by: 'client_count', sort_order: 'desc' }),
    staleTime: 30000,
  })

  // Search results - using debounced search query
  const { data: searchResults, isLoading: searchLoading } = useQuery({
    queryKey: ['clients-search', debouncedSearchQuery],
    queryFn: () => clientsApiClient.searchClients(debouncedSearchQuery, { page_size: 50 }),
    enabled: debouncedSearchQuery.length >= 2,
    staleTime: 10000,
  })

  // Background task context
  const { addTask, updateTask } = useBackgroundTasks()

  // Sync mutation with background task tracking
  const syncMutation = useMutation({
    mutationFn: () => clientsApiClient.triggerSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients-summary'] })
      queryClient.invalidateQueries({ queryKey: ['clients-sites'] })
      queryClient.invalidateQueries({ queryKey: ['filtered-clients'] })
    },
    onError: () => {
      // Error handled via background task
    },
  })

  // Handle sync with background task tracking
  const handleSync = useCallback(() => {
    const taskId = addTask({
      type: 'clients-sync',
      title: 'Syncing Clients',
      description: 'Fetching latest data from Aruba Central',
      status: 'running',
    })

    syncMutation.mutate(undefined, {
      onSuccess: () => {
        updateTask(taskId, {
          status: 'completed',
          completedAt: Date.now(),
        })
      },
      onError: (error) => {
        updateTask(taskId, {
          status: 'failed',
          error: error instanceof Error ? error.message : 'Sync failed',
          completedAt: Date.now(),
        })
      },
    })
  }, [addTask, updateTask, syncMutation])

  const toggleSite = (siteId: string) => {
    setExpandedSites((prev) => {
      const next = new Set(prev)
      if (next.has(siteId)) {
        next.delete(siteId)
      } else {
        next.add(siteId)
      }
      return next
    })
  }

  const isLoading = summaryLoading || sitesLoading

  // KPI click handlers
  const handleKPIClick = (preset: FilterPreset) => {
    setSearchQuery('') // Clear search when clicking KPI
    applyPreset(preset)
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Background effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-1/2 -right-1/2 h-[1000px] w-[1000px] rounded-full bg-violet-500/5 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 h-[1000px] w-[1000px] rounded-full bg-emerald-500/5 blur-3xl" />
        <div className="absolute inset-0 bg-grid-pattern opacity-50" />
      </div>

      <div className="relative">
        {/* Header */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
          <div className="mx-auto max-w-7xl px-6 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  Aruba Central
                  <span className="ml-2 bg-gradient-to-r from-violet-400 to-violet-600 bg-clip-text text-transparent">
                    Clients
                  </span>
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  Network clients connected across all sites
                </p>
              </div>
              <div className="flex items-center gap-4">
                {/* Filter toggle */}
                <button
                  type="button"
                  onClick={() => setShowFilterPanel(!showFilterPanel)}
                  className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
                    showFilterPanel || hasFilters
                      ? 'border-violet-500 bg-violet-500/10 text-violet-400'
                      : 'border-slate-700 text-slate-400 hover:bg-slate-800'
                  }`}
                >
                  <Filter className="h-4 w-4" />
                  Filters
                  {hasFilters && (
                    <span className="rounded-full bg-violet-500 px-1.5 py-0.5 text-xs text-white">
                      {(filters.type?.length || 0) + (filters.status?.length || 0) + (filters.health?.length || 0)}
                    </span>
                  )}
                </button>

                {/* Search */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search by MAC, name, or IP..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-64 rounded-lg border border-slate-700 bg-slate-800/50 py-2 pl-10 pr-4 text-sm text-white placeholder-slate-400 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500"
                  />
                </div>

                {/* Export Report button */}
                <ReportButton
                  reportType="clients"
                  variant="secondary"
                  filters={{
                    type: filters.type?.[0],
                    health: filters.health?.[0],
                    status: filters.status?.[0],
                  }}
                />

                {/* Sync button */}
                <button
                  onClick={handleSync}
                  disabled={syncMutation.isPending}
                  className="flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-violet-500 disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                  {syncMutation.isPending ? 'Syncing...' : 'Sync Clients'}
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-6 py-8">
          {/* KPI Cards - Now clickable */}
          <section className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <KPICard
              title="Total Clients"
              value={summary?.total_clients || 0}
              icon={Users}
              color="violet"
              onClick={() => handleKPIClick('all')}
              isActive={isPresetActive('all')}
              ariaLabel="Show all clients"
            />
            <KPICard
              title="Connected"
              value={summary?.connected || 0}
              subtitle={`${summary?.total_clients ? Math.round((summary.connected / summary.total_clients) * 100) : 0}%`}
              icon={CheckCircle}
              color="emerald"
              onClick={() => handleKPIClick('connected')}
              isActive={isPresetActive('connected')}
              ariaLabel="Filter to connected clients only"
            />
            <KPICard
              title="Wireless"
              value={summary?.wireless || 0}
              icon={Wifi}
              color="sky"
              onClick={() => handleKPIClick('wireless')}
              isActive={isPresetActive('wireless')}
              ariaLabel="Filter to wireless clients only"
            />
            <KPICard
              title="Wired"
              value={summary?.wired || 0}
              icon={Cable}
              color="amber"
              onClick={() => handleKPIClick('wired')}
              isActive={isPresetActive('wired')}
              ariaLabel="Filter to wired clients only"
            />
            <KPICard
              title="Health Good"
              value={summary?.health_good || 0}
              icon={Heart}
              color="emerald"
              onClick={() => handleKPIClick('health_good')}
              isActive={isPresetActive('health_good')}
              ariaLabel="Filter to clients with good health only"
            />
            <KPICard
              title="Sites"
              value={summary?.total_sites || 0}
              icon={MapPin}
              color="violet"
              onClick={() => {
                clearFilters()
                setSearchQuery('')
              }}
              isActive={!hasFilters && !debouncedSearchQuery}
              ariaLabel="Show all sites"
            />
          </section>

          {/* Filter Panel (collapsible) */}
          {showFilterPanel && (
            <section className="mb-8">
              <ClientsFilterPanel
                filters={filters}
                onToggle={(key, value) => toggleFilterValue(key as any, value)}
                onClear={clearFilters}
                onClose={() => setShowFilterPanel(false)}
              />
            </section>
          )}

          {/* Active Filter Bar */}
          {hasFilters && !showFilterPanel && (
            <section className="mb-6">
              <ClientsFilterBar filters={filters} activeFilterCount={activeFilterCount} onClear={clearFilters} />
            </section>
          )}

          {/* Filtered View - Shows when filters are active */}
          {hasFilters && !debouncedSearchQuery && (
            <section className="mb-8">
              <h2 className="mb-4 text-lg font-semibold text-white flex items-center gap-2">
                <Filter className="h-5 w-5 text-violet-400" />
                Filtered Clients
                <span className="text-sm font-normal text-slate-400">
                  (matching selected filters)
                </span>
              </h2>
              <FilteredClientsTable filters={filters} />
            </section>
          )}

          {/* Search Results */}
          {debouncedSearchQuery.length >= 2 && (
            <section className="mb-8">
              <h2 className="mb-4 text-lg font-semibold text-white flex items-center gap-2">
                <Search className="h-5 w-5 text-slate-400" />
                Search Results
                {searchResults && (
                  <span className="text-sm font-normal text-slate-400">
                    ({searchResults.total.toLocaleString()} found)
                  </span>
                )}
              </h2>
              {searchLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="h-6 w-6 animate-spin text-slate-400" />
                </div>
              ) : searchResults?.items?.length ? (
                <div className="rounded-2xl border border-slate-700/50 bg-slate-800/30 overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-slate-900/50">
                      <tr className="text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                        <th className="px-4 py-3">Client</th>
                        <th className="px-4 py-3">Site</th>
                        <th className="px-4 py-3">Health</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">Type</th>
                        <th className="px-4 py-3">IP Address</th>
                        <th className="px-4 py-3">Connected To</th>
                      </tr>
                    </thead>
                    <tbody>
                      {searchResults.items.map((client) => (
                        <tr key={client.id} className="border-b border-slate-700/30 hover:bg-slate-800/30">
                          <td className="px-4 py-3">
                            <div>
                              <p className="font-mono text-sm font-medium text-white">{client.mac}</p>
                              {client.name && <p className="text-xs text-slate-400">{client.name}</p>}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-sm text-slate-300">{client.site_name || client.site_id}</span>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <HealthBadge health={client.health} />
                              {client.status_reason && (client.health === 'Poor' || client.health === 'Fair') && (
                                <StatusReasonTooltip reason={client.status_reason} />
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <StatusBadge status={client.status} />
                              {client.status_reason && (client.status === 'Failed' || client.status === 'Blocked') && (
                                <StatusReasonTooltip reason={client.status_reason} />
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3"><TypeBadge type={client.type} /></td>
                          <td className="px-4 py-3">
                            <span className="font-mono text-sm text-slate-300">{client.ipv4}</span>
                          </td>
                          <td className="px-4 py-3">
                            <span className="text-sm text-slate-300">{client.connected_to}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400 rounded-2xl border border-slate-700/50 bg-slate-800/30">
                  <Search className="h-10 w-10 mb-3 opacity-50" />
                  <p>No clients found matching "{debouncedSearchQuery}"</p>
                </div>
              )}
            </section>
          )}

          {/* Sites List - Shows when no filters or search */}
          {!debouncedSearchQuery && !hasFilters && (
            <section>
              <h2 className="mb-4 text-lg font-semibold text-white flex items-center gap-2">
                <MapPin className="h-5 w-5 text-violet-400" />
                Sites
                {sitesData && (
                  <span className="text-sm font-normal text-slate-400">
                    ({sitesData.total.toLocaleString()} total)
                  </span>
                )}
              </h2>

              {isLoading ? (
                <div className="flex items-center justify-center py-24">
                  <div className="flex flex-col items-center gap-4">
                    <RefreshCw className="h-10 w-10 animate-spin text-violet-500" />
                    <p className="text-slate-400">Loading sites...</p>
                  </div>
                </div>
              ) : sitesData?.items?.length ? (
                <div className="space-y-4">
                  {sitesData.items.map((site) => (
                    <SiteCard
                      key={site.site_id}
                      site={site}
                      isExpanded={expandedSites.has(site.site_id)}
                      onToggle={() => toggleSite(site.site_id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-24 text-slate-400 rounded-2xl border border-slate-700/50 bg-slate-800/30">
                  <MapPin className="h-16 w-16 mb-4 opacity-30" />
                  <h3 className="text-lg font-medium text-white mb-2">No sites found</h3>
                  <p className="text-center max-w-md">
                    Sites will appear here after syncing with Aruba Central.
                    Make sure you have devices with site information in the system.
                  </p>
                  <button
                    onClick={handleSync}
                    disabled={syncMutation.isPending}
                    className="mt-6 flex items-center gap-2 rounded-lg bg-violet-600 px-6 py-2.5 text-sm font-medium text-white transition-all hover:bg-violet-500 disabled:opacity-50"
                  >
                    <RefreshCw className={`h-4 w-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                    Sync with Aruba Central
                  </button>
                </div>
              )}
            </section>
          )}
        </main>
      </div>
    </div>
  )
}
