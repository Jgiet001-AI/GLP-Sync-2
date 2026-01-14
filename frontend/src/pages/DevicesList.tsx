import { useState, useCallback, useEffect, memo, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApiClient, type DeviceListParams } from '../api/client'
import type { DeviceListItem } from '../types'
import { Drawer, DetailRow, DetailSection } from '../components/ui/Drawer'
import { DropdownMenu } from '../components/ui/DropdownMenu'
import { FilterChips, type FilterChip } from '../components/filters/FilterChips'
import { SortableHeader } from '../components/shared/SortableHeader'
import { useDebouncedSearch } from '../hooks/useDebouncedSearch'
import { usePaginatedList } from '../hooks/usePaginatedList'
import {
  Server,
  Search,
  Wifi,
  Router,
  HardDrive,
  Filter,
  X,
  RefreshCw,
  Check,
  AlertCircle,
  Copy,
  Eye,
  Calendar,
  MapPin,
  Shield,
  Cloud,
  Globe,
  Activity,
  Tag,
} from 'lucide-react'
import { ReportButton } from '../components/reports/ReportButton'
import toast from 'react-hot-toast'
import { formatDate, formatDateTime, formatUptime } from '../utils/formatting'
import { PAGE_SIZE_OPTIONS } from '../utils/pagination'
import { PaginationControls } from '../components/shared/PaginationControls'

// Device type icon mapping
const deviceIcons: Record<string, typeof Server> = {
  AP: Wifi,
  SWITCH: Router,
  GATEWAY: Router,
  IAP: Wifi,
  COMPUTE: Server,
  STORAGE: HardDrive,
  UNKNOWN: Server,
}

// Filter fields for devices
interface DeviceFilters {
  device_type?: string
  region?: string
  assigned_state?: string
  subscription_key?: string
  search?: string
  [key: string]: string | undefined
}

export function DevicesList() {
  // Use paginated list hook for URL-synced state
  const { state, handlers } = usePaginatedList<DeviceFilters>({
    page: 1,
    page_size: 100,
    sort_by: 'updated_at',
    sort_order: 'desc',
    filters: {
      device_type: undefined,
      region: undefined,
      assigned_state: undefined,
      subscription_key: undefined,
      search: undefined,
    },
  })

  const [searchInput, setSearchInput] = useState(state.filters.search || '')
  const [showFilters, setShowFilters] = useState(
    !!(state.filters.device_type || state.filters.region || state.filters.assigned_state || state.filters.subscription_key)
  )
  const [selectedDevice, setSelectedDevice] = useState<DeviceListItem | null>(null)

  // Sync search input with URL state on mount
  useEffect(() => {
    if (state.filters.search && state.filters.search !== searchInput) {
      setSearchInput(state.filters.search)
    }
    if (state.filters.device_type || state.filters.region || state.filters.assigned_state || state.filters.subscription_key) {
      setShowFilters(true)
    }
  }, [state.filters.device_type, state.filters.region, state.filters.assigned_state, state.filters.subscription_key, state.filters.search])

  // Debounced search
  const debouncedSearch = useDebouncedSearch(searchInput, 300)

  useEffect(() => {
    if (debouncedSearch !== state.filters.search) {
      handlers.handleFilterChange('search', debouncedSearch || undefined)
    }
  }, [debouncedSearch])

  // Build params for API from state
  const params = useMemo<DeviceListParams>(() => ({
    page: state.page,
    page_size: state.page_size,
    sort_by: state.sort_by,
    sort_order: state.sort_order,
    ...state.filters,
  }), [state])

  // Fetch devices
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['devices-list', params],
    queryFn: () => dashboardApiClient.getDevices(params),
    staleTime: 30000,
  })

  // Fetch filter options
  const { data: filterOptions } = useQuery({
    queryKey: ['filter-options'],
    queryFn: () => dashboardApiClient.getFilterOptions(),
    staleTime: 60000,
  })

  const handleFilterChange = useCallback((key: keyof DeviceFilters, value: string | undefined) => {
    handlers.handleFilterChange(key, value)
  }, [handlers])

  const clearFilters = useCallback(() => {
    handlers.clearFilters()
    setSearchInput('')
  }, [handlers])

  const copyToClipboard = useCallback((text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard`)
  }, [])

  const hasActiveFilters = state.filters.device_type || state.filters.region || state.filters.assigned_state || state.filters.search || state.filters.subscription_key

  // Generate filter chips from active params
  const filterChips = useMemo<FilterChip[]>(() => {
    const chips: FilterChip[] = []
    if (state.filters.device_type) {
      chips.push({
        key: 'device_type',
        label: 'Type',
        value: state.filters.device_type,
        color: 'sky',
      })
    }
    if (state.filters.region) {
      chips.push({
        key: 'region',
        label: 'Region',
        value: state.filters.region,
        color: 'violet',
      })
    }
    if (state.filters.assigned_state) {
      chips.push({
        key: 'assigned_state',
        label: 'Status',
        value: state.filters.assigned_state,
        displayValue: state.filters.assigned_state === 'ASSIGNED_TO_SERVICE' ? 'Assigned' : state.filters.assigned_state === 'UNASSIGNED' ? 'Unassigned' : state.filters.assigned_state,
        color: state.filters.assigned_state === 'ASSIGNED_TO_SERVICE' ? 'emerald' : 'amber',
      })
    }
    if (state.filters.subscription_key) {
      chips.push({
        key: 'subscription_key',
        label: 'Subscription',
        value: state.filters.subscription_key,
        color: 'rose',
      })
    }
    if (state.filters.search) {
      chips.push({
        key: 'search',
        label: 'Search',
        value: state.filters.search,
        color: 'slate',
      })
    }
    return chips
  }, [state.filters.device_type, state.filters.region, state.filters.assigned_state, state.filters.subscription_key, state.filters.search])

  // Remove a specific filter
  const removeFilter = useCallback((key: string) => {
    if (key === 'search') setSearchInput('')
    handlers.handleFilterChange(key as keyof DeviceFilters, undefined)
  }, [handlers])

  if (error) {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center bg-slate-900">
        <div className="max-w-md rounded-2xl border border-rose-500/30 bg-rose-500/10 p-8 text-center">
          <AlertCircle className="mx-auto h-12 w-12 text-rose-400" />
          <h2 className="mt-4 text-xl font-semibold text-white">Failed to Load Devices</h2>
          <p className="mt-2 text-sm text-slate-400">
            {error instanceof Error ? error.message : 'Unknown error occurred'}
          </p>
          <button
            onClick={() => refetch()}
            className="mt-6 rounded-lg bg-rose-500 px-6 py-2 font-medium text-white transition-colors hover:bg-rose-600"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Background effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-1/2 -right-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-green/5 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 h-[1000px] w-[1000px] rounded-full bg-emerald-500/5 blur-3xl" />
        <div className="absolute inset-0 bg-grid-pattern opacity-50" />
      </div>

      <div className="relative">
        {/* Header */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
          <div className="mx-auto max-w-[1600px] px-6 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  <span className="bg-gradient-to-r from-sky-400 to-sky-600 bg-clip-text text-transparent">
                    Devices
                  </span>
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  {data ? `${data.total.toLocaleString()} devices` : 'Loading...'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <ReportButton
                  reportType="devices"
                  variant="secondary"
                  filters={{
                    device_type: state.filters.device_type,
                    region: state.filters.region,
                    assigned_state: state.filters.assigned_state,
                    search: state.filters.search,
                  }}
                />
                <button
                  onClick={() => {
                    toast.promise(refetch(), {
                      loading: 'Refreshing...',
                      success: 'Devices updated',
                      error: 'Failed to refresh',
                    })
                  }}
                  disabled={isFetching}
                  className="flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-slate-700 disabled:opacity-50"
                >
                  <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                  Refresh
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-6 py-6">
          {/* Search and Filters Bar */}
          <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <label htmlFor="device-search" className="sr-only">Search devices</label>
              <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input
                id="device-search"
                type="text"
                placeholder="Search serial, MAC, name, model..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-400 transition-all focus:border-hpe-green focus:outline-none focus:ring-2 focus:ring-hpe-green/20"
                data-testid="device-search-input"
              />
              {searchInput && (
                <button
                  onClick={() => setSearchInput('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-all animate-scale-in"
                  aria-label="Clear search"
                  data-testid="clear-search-btn"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Filter Toggle and Page Size */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-all ${
                  hasActiveFilters
                    ? 'border-sky-500/50 bg-sky-500/10 text-sky-400'
                    : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:bg-slate-800'
                }`}
              >
                <Filter className="h-4 w-4" />
                Filters
                {hasActiveFilters && (
                  <span className="ml-1 rounded-full bg-sky-500 px-1.5 py-0.5 text-xs text-white">
                    {[state.filters.device_type, state.filters.region, state.filters.assigned_state, state.filters.search].filter(Boolean).length}
                  </span>
                )}
              </button>

              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="flex items-center gap-1 text-sm text-slate-400 hover:text-white"
                >
                  <X className="h-4 w-4" />
                  Clear
                </button>
              )}

              {/* Page Size Selector */}
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-400">Show:</span>
                <select
                  value={state.page_size}
                  onChange={(e) => handlers.handlePageSizeChange(Number(e.target.value))}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/20"
                >
                  {PAGE_SIZE_OPTIONS.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Filter Panel */}
          {showFilters && filterOptions && (
            <div
              className="mb-6 rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 backdrop-blur-sm animate-fade-slide-down"
              data-testid="filter-panel"
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {/* Device Type Filter */}
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">
                    Device Type
                  </label>
                  <select
                    value={state.filters.device_type || ''}
                    onChange={(e) => handleFilterChange('device_type', e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All Types</option>
                    {filterOptions.device_types.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Region Filter */}
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">
                    Region
                  </label>
                  <select
                    value={state.filters.region || ''}
                    onChange={(e) => handleFilterChange('region', e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All Regions</option>
                    {filterOptions.regions.map((region) => (
                      <option key={region} value={region}>
                        {region}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Assignment State Filter */}
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">
                    Assignment State
                  </label>
                  <select
                    value={state.filters.assigned_state || ''}
                    onChange={(e) => handleFilterChange('assigned_state', e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-sky-500 focus:outline-none"
                  >
                    <option value="">All States</option>
                    <option value="ASSIGNED_TO_SERVICE">Assigned</option>
                    <option value="UNASSIGNED">Unassigned</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Active Filter Chips */}
          {filterChips.length > 0 && (
            <FilterChips
              filters={filterChips}
              onRemove={removeFilter}
              onClear={clearFilters}
              className="mb-6"
            />
          )}

          {/* Table */}
          <div className="rounded-2xl border border-slate-700/50 bg-slate-800/30 backdrop-blur-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700/50">
                    <SortableHeader
                      column="serial_number"
                      label="Serial Number"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      MAC Address
                    </th>
                    <SortableHeader
                      column="device_type"
                      label="Type"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <SortableHeader
                      column="model"
                      label="Model"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <SortableHeader
                      column="region"
                      label="Region"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Location
                    </th>
                    <SortableHeader
                      column="assigned_state"
                      label="Status"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      <div className="flex items-center gap-1">
                        <Tag className="h-3.5 w-3.5" />
                        Tags
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      <div className="flex items-center gap-1">
                        <Cloud className="h-3.5 w-3.5" />
                        Central
                      </div>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Subscription
                    </th>
                    <SortableHeader
                      column="updated_at"
                      label="Updated"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {isLoading ? (
                    <tr>
                      <td colSpan={12} className="py-20 text-center">
                        <div className="flex flex-col items-center gap-3">
                          <RefreshCw className="h-8 w-8 animate-spin text-sky-500" />
                          <span className="text-sm text-slate-400">Loading devices...</span>
                        </div>
                      </td>
                    </tr>
                  ) : data?.items.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="py-20 text-center">
                        <div className="flex flex-col items-center gap-3">
                          <Server className="h-12 w-12 text-slate-600" />
                          <span className="text-sm text-slate-400">No devices found</span>
                          {hasActiveFilters && (
                            <button
                              onClick={clearFilters}
                              className="text-sm text-sky-400 hover:text-sky-300"
                            >
                              Clear filters
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ) : (
                    data?.items.map((device) => (
                      <DeviceRow
                        key={device.id}
                        device={device}
                        onViewDetails={() => setSelectedDevice(device)}
                        onCopySerial={() => copyToClipboard(device.serial_number, 'Serial number')}
                        onCopyMac={() => device.mac_address && copyToClipboard(device.mac_address, 'MAC address')}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {data && data.total_pages > 1 && (
              <PaginationControls
                page={data.page}
                totalPages={data.total_pages}
                total={data.total}
                pageSize={data.page_size}
                itemName="devices"
                onPageChange={handlers.handlePageChange}
                variant="icon"
                theme="sky"
              />
            )}
          </div>
        </main>
      </div>

      {/* Device Detail Drawer */}
      <Drawer
        open={!!selectedDevice}
        onClose={() => setSelectedDevice(null)}
        title={selectedDevice?.serial_number || ''}
        subtitle={selectedDevice?.device_type || 'Device'}
        width="lg"
      >
        {selectedDevice && (
          <DeviceDetailContent
            device={selectedDevice}
            onCopySerial={() => copyToClipboard(selectedDevice.serial_number, 'Serial number')}
            onCopyMac={() => selectedDevice.mac_address && copyToClipboard(selectedDevice.mac_address, 'MAC address')}
          />
        )}
      </Drawer>
    </div>
  )
}

// Device Detail Content for Drawer
function DeviceDetailContent({
  device,
  onCopySerial,
  onCopyMac,
}: {
  device: DeviceListItem
  onCopySerial: () => void
  onCopyMac: () => void
}) {
  const Icon = deviceIcons[device.device_type || 'UNKNOWN'] || Server
  const isAssigned = device.assigned_state === 'ASSIGNED_TO_SERVICE'

  return (
    <div className="space-y-6">
      {/* Header with icon and status */}
      <div className="flex items-center gap-4">
        <div className="rounded-xl bg-slate-700/50 p-4">
          <Icon className="h-8 w-8 text-hpe-green" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                isAssigned
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : 'bg-amber-500/10 text-amber-400'
              }`}
            >
              {isAssigned ? <Check className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
              {isAssigned ? 'Assigned' : 'Unassigned'}
            </span>
          </div>
          {device.device_name && (
            <p className="mt-1 text-sm text-slate-400">{device.device_name}</p>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <button
          onClick={onCopySerial}
          className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700"
        >
          <Copy className="h-4 w-4" />
          Copy Serial
        </button>
        {device.mac_address && (
          <button
            onClick={onCopyMac}
            className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700"
          >
            <Copy className="h-4 w-4" />
            Copy MAC
          </button>
        )}
      </div>

      {/* Device Information */}
      <DetailSection title="Device Information">
        <DetailRow label="Serial Number" value={device.serial_number} mono />
        <DetailRow label="MAC Address" value={device.mac_address} mono />
        <DetailRow label="Device Type" value={device.device_type} />
        <DetailRow label="Model" value={device.model} />
        <DetailRow label="Device Name" value={device.device_name} />
      </DetailSection>

      {/* Location */}
      <DetailSection title="Location">
        <DetailRow label="Region" value={device.region} />
        <DetailRow
          label="City"
          value={
            device.location_city || device.location_country ? (
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3 text-slate-500" />
                {[device.location_city, device.location_country].filter(Boolean).join(', ')}
              </span>
            ) : null
          }
        />
      </DetailSection>

      {/* Subscription */}
      <DetailSection title="Subscription">
        <DetailRow
          label="Subscription Key"
          value={
            device.subscription_key ? (
              <span className="flex items-center gap-1">
                <Shield className="h-3 w-3 text-violet-400" />
                {device.subscription_key}
              </span>
            ) : (
              <span className="text-slate-500">Not assigned</span>
            )
          }
          mono={!!device.subscription_key}
        />
        <DetailRow
          label="Type"
          value={device.subscription_type?.replace('CENTRAL_', '')}
        />
        <DetailRow
          label="Expires"
          value={
            device.subscription_end ? (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3 text-slate-500" />
                {formatDate(device.subscription_end)}
              </span>
            ) : null
          }
        />
      </DetailSection>

      {/* GreenLake Tags */}
      <DetailSection title="GreenLake Tags">
        {Object.keys(device.tags || {}).length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {Object.entries(device.tags).map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1 rounded-lg bg-violet-500/10 px-2.5 py-1.5 text-sm"
              >
                <Tag className="h-3.5 w-3.5 text-violet-400" />
                <span className="text-slate-400">{key}:</span>
                <span className="text-white">{value}</span>
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">No tags assigned</p>
        )}
      </DetailSection>

      {/* Aruba Central */}
      <DetailSection title="Aruba Central">
        <DetailRow
          label="Platform Status"
          value={
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                  device.in_greenlake
                    ? 'bg-hpe-green/10 text-hpe-green'
                    : 'bg-slate-500/10 text-slate-400'
                }`}
              >
                <Globe className="h-3 w-3" />
                GreenLake
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                  device.in_central
                    ? 'bg-sky-500/10 text-sky-400'
                    : 'bg-slate-500/10 text-slate-400'
                }`}
              >
                <Cloud className="h-3 w-3" />
                Central
              </span>
            </div>
          }
        />
        {device.in_central && (
          <>
            <DetailRow
              label="Central Status"
              value={
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                    device.central_status === 'ONLINE'
                      ? 'bg-emerald-500/10 text-emerald-400'
                      : device.central_status === 'OFFLINE'
                      ? 'bg-rose-500/10 text-rose-400'
                      : 'bg-slate-500/10 text-slate-400'
                  }`}
                >
                  <Activity className="h-3 w-3" />
                  {device.central_status || 'Unknown'}
                </span>
              }
            />
            <DetailRow label="Central Name" value={device.central_device_name} />
            <DetailRow label="Central Type" value={device.central_device_type} />
            <DetailRow label="Model" value={device.central_model} />
            <DetailRow label="Part Number" value={device.central_part_number} mono />
            <DetailRow label="Software Version" value={device.central_software_version} />
            <DetailRow label="IPv4" value={device.central_ipv4} mono />
            <DetailRow label="IPv6" value={device.central_ipv6} mono />
            <DetailRow label="Uptime" value={formatUptime(device.central_uptime_millis)} />
            <DetailRow label="Last Seen" value={formatDateTime(device.central_last_seen_at)} />
            <DetailRow label="Deployment" value={device.central_deployment} />
            <DetailRow label="Role" value={device.central_device_role} />
            <DetailRow label="Function" value={device.central_device_function} />
            <DetailRow label="Site" value={device.central_site_name} />
            <DetailRow label="Cluster" value={device.central_cluster_name} />
            <DetailRow
              label="Config Status"
              value={
                device.central_config_status ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                      device.central_config_status === 'SYNCED' || device.central_config_status === 'IN_SYNC'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-amber-500/10 text-amber-400'
                    }`}
                  >
                    {device.central_config_status}
                  </span>
                ) : null
              }
            />
            <DetailRow label="Config Modified" value={formatDateTime(device.central_config_last_modified_at)} />
          </>
        )}
      </DetailSection>

      {/* Metadata */}
      <DetailSection title="Metadata">
        <DetailRow
          label="Last Updated"
          value={formatDateTime(device.updated_at)}
        />
        <DetailRow label="Device ID" value={device.id} mono />
      </DetailSection>
    </div>
  )
}

// Device Row Component with actions
const DeviceRow = memo(function DeviceRow({
  device,
  onViewDetails,
  onCopySerial,
  onCopyMac,
}: {
  device: DeviceListItem
  onViewDetails: () => void
  onCopySerial: () => void
  onCopyMac: () => void
}) {
  const Icon = deviceIcons[device.device_type || 'UNKNOWN'] || Server
  const isAssigned = device.assigned_state === 'ASSIGNED_TO_SERVICE'

  const menuItems = [
    {
      label: 'View Details',
      icon: <Eye className="h-4 w-4" />,
      onClick: onViewDetails,
    },
    {
      label: 'Copy Serial',
      icon: <Copy className="h-4 w-4" />,
      onClick: onCopySerial,
    },
    ...(device.mac_address
      ? [
          {
            label: 'Copy MAC',
            icon: <Copy className="h-4 w-4" />,
            onClick: onCopyMac,
          },
        ]
      : []),
  ]

  return (
    <tr
      className="transition-colors hover:bg-slate-800/50 animate-fade-in cursor-pointer"
      onClick={onViewDetails}
      data-testid={`device-row-${device.serial_number}`}
    >
      <td className="whitespace-nowrap px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-slate-700/50 p-2">
            <Icon className="h-4 w-4 text-hpe-green" aria-hidden="true" />
          </div>
          <div>
            <p className="font-mono text-sm font-medium text-white">{device.serial_number}</p>
            {device.device_name && (
              <p className="text-xs text-slate-400">{device.device_name}</p>
            )}
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3 font-mono text-sm text-slate-300">
        {device.mac_address || '-'}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span className="inline-flex items-center rounded-md bg-slate-700/50 px-2 py-1 text-xs font-medium text-slate-300">
          {device.device_type || 'Unknown'}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
        {device.model || '-'}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
        {device.region || '-'}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
        {device.location_city || device.location_country
          ? `${device.location_city || ''}${device.location_city && device.location_country ? ', ' : ''}${device.location_country || ''}`
          : '-'}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
            isAssigned
              ? 'bg-emerald-500/10 text-emerald-400'
              : 'bg-amber-500/10 text-amber-400'
          }`}
        >
          {isAssigned ? <Check className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
          {isAssigned ? 'Assigned' : 'Unassigned'}
        </span>
      </td>
      <td className="px-4 py-3">
        {Object.keys(device.tags || {}).length > 0 ? (
          <div className="flex flex-wrap gap-1 max-w-[200px]">
            {Object.entries(device.tags).slice(0, 3).map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center rounded bg-violet-500/10 px-1.5 py-0.5 text-xs text-violet-400"
                title={`${key}: ${value}`}
              >
                {value || key}
              </span>
            ))}
            {Object.keys(device.tags).length > 3 && (
              <span className="text-xs text-slate-500">
                +{Object.keys(device.tags).length - 3}
              </span>
            )}
          </div>
        ) : (
          <span className="text-xs text-slate-500">-</span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        {device.in_central ? (
          <div className="flex flex-col gap-0.5">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
                device.central_status === 'ONLINE'
                  ? 'bg-emerald-500/10 text-emerald-400'
                  : device.central_status === 'OFFLINE'
                  ? 'bg-rose-500/10 text-rose-400'
                  : 'bg-slate-500/10 text-slate-400'
              }`}
            >
              <Activity className="h-3 w-3" />
              {device.central_status || 'Unknown'}
            </span>
            {device.central_device_name && (
              <span className="text-xs text-white font-medium truncate max-w-[180px]" title={device.central_device_name}>
                {device.central_device_name}
              </span>
            )}
            <span className="text-xs text-slate-400">
              {device.central_model || device.central_device_type || '-'}
              {device.central_part_number && ` (${device.central_part_number})`}
            </span>
            {device.central_software_version && (
              <span className="text-xs text-slate-500">v{device.central_software_version}</span>
            )}
            {device.central_ipv4 && (
              <span className="font-mono text-xs text-slate-400">{device.central_ipv4}</span>
            )}
            {device.central_site_name && (
              <span className="text-xs text-sky-400">{device.central_site_name}</span>
            )}
          </div>
        ) : (
          <span className="text-xs text-slate-500">Not in Central</span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
        {device.subscription_key ? (
          <Link
            to={`/subscriptions?search=${encodeURIComponent(device.subscription_key)}`}
            className="block hover:bg-slate-700/30 rounded p-1 -m-1 transition-colors"
          >
            <p className="font-mono text-xs text-violet-400 hover:text-violet-300">{device.subscription_key}</p>
            <p className="text-xs text-slate-500">{device.subscription_type?.replace('CENTRAL_', '')}</p>
          </Link>
        ) : (
          <span className="text-sm text-slate-500">-</span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
        {formatDate(device.updated_at)}
      </td>
      <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <DropdownMenu items={menuItems} />
      </td>
    </tr>
  )
})
