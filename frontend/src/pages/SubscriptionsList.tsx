import { useState, useCallback, useEffect, memo, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApiClient, type SubscriptionListParams } from '../api/client'
import type { SubscriptionListItem } from '../types'
import { Drawer, DetailRow, DetailSection } from '../components/ui/Drawer'
import { DropdownMenu } from '../components/ui/DropdownMenu'
import { FilterChips, type FilterChip } from '../components/filters/FilterChips'
import {
  Shield,
  Search,
  Filter,
  X,
  RefreshCw,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Server,
  FlaskConical,
  Copy,
  Eye,
  Calendar,
  ChevronRight,
} from 'lucide-react'
import { ReportButton } from '../components/reports/ReportButton'
import toast from 'react-hot-toast'
import { formatDate } from '../utils/formatting'
import { PAGE_SIZE_OPTIONS } from '../utils/pagination'
import { SortableHeader } from '../components/shared/SortableHeader'
import { PaginationControls } from '../components/shared/PaginationControls'
import { useDebouncedSearch } from '../hooks/useDebouncedSearch'
import { usePaginatedList } from '../hooks/usePaginatedList'

// Filter fields for subscriptions
interface SubscriptionFilters {
  subscription_type?: string
  subscription_status?: string
  search?: string
}

export function SubscriptionsList() {
  // Use paginated list hook for URL-synced state
  const { state, handlers } = usePaginatedList<SubscriptionFilters>({
    page: 1,
    page_size: 100,
    sort_by: 'end_time',
    sort_order: 'asc',
    filters: {
      subscription_type: undefined,
      subscription_status: undefined,
      search: undefined,
    },
  })

  const [searchInput, setSearchInput] = useState(state.filters.search || '')
  const [showFilters, setShowFilters] = useState(
    !!(state.filters.subscription_type || state.filters.subscription_status)
  )
  const [selectedSubscription, setSelectedSubscription] = useState<SubscriptionListItem | null>(null)

  // Sync search input with URL state on mount
  useEffect(() => {
    if (state.filters.search && state.filters.search !== searchInput) {
      setSearchInput(state.filters.search)
    }
    if (state.filters.subscription_type || state.filters.subscription_status) {
      setShowFilters(true)
    }
  }, [state.filters.subscription_type, state.filters.subscription_status, state.filters.search])

  // Debounced search
  const debouncedSearch = useDebouncedSearch(searchInput, 300)

  useEffect(() => {
    if (debouncedSearch !== state.filters.search) {
      handlers.handleFilterChange('search', debouncedSearch || undefined)
    }
  }, [debouncedSearch])

  // Build params for API from state
  const params = useMemo<SubscriptionListParams>(() => ({
    page: state.page,
    page_size: state.page_size,
    sort_by: state.sort_by,
    sort_order: state.sort_order,
    ...state.filters,
  }), [state])

  // Fetch subscriptions
  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['subscriptions-list', params],
    queryFn: () => dashboardApiClient.getSubscriptions(params),
    staleTime: 30000,
  })

  // Fetch filter options
  const { data: filterOptions } = useQuery({
    queryKey: ['filter-options'],
    queryFn: () => dashboardApiClient.getFilterOptions(),
    staleTime: 60000,
  })

  const handleFilterChange = useCallback((key: keyof SubscriptionFilters, value: string | undefined) => {
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

  const hasActiveFilters = state.filters.subscription_type || state.filters.subscription_status || state.filters.search

  // Generate filter chips from active params
  const filterChips = useMemo<FilterChip[]>(() => {
    const chips: FilterChip[] = []
    if (state.filters.subscription_type) {
      chips.push({
        key: 'subscription_type',
        label: 'Type',
        value: state.filters.subscription_type,
        displayValue: state.filters.subscription_type.replace('CENTRAL_', ''),
        color: 'violet',
      })
    }
    if (state.filters.subscription_status) {
      chips.push({
        key: 'subscription_status',
        label: 'Status',
        value: state.filters.subscription_status,
        color: 'emerald',
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
  }, [state.filters.subscription_type, state.filters.subscription_status, state.filters.search])

  // Remove a specific filter
  const removeFilter = useCallback((key: string) => {
    if (key === 'search') setSearchInput('')
    handlers.handleFilterChange(key as keyof SubscriptionFilters, undefined)
  }, [handlers])

  if (error) {
    return (
      <div className="flex h-[calc(100vh-4rem)] items-center justify-center bg-slate-900">
        <div className="max-w-md rounded-2xl border border-rose-500/30 bg-rose-500/10 p-8 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-rose-400" />
          <h2 className="mt-4 text-xl font-semibold text-white">Failed to Load Subscriptions</h2>
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
        <div className="absolute -top-1/2 -right-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-purple/5 blur-3xl" />
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
                  <span className="bg-gradient-to-r from-violet-400 to-violet-600 bg-clip-text text-transparent">
                    Subscriptions
                  </span>
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  {data ? `${data.total.toLocaleString()} subscription keys` : 'Loading...'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <ReportButton
                  reportType="subscriptions"
                  variant="secondary"
                  filters={{
                    subscription_type: state.filters.subscription_type,
                    status: state.filters.subscription_status,
                    search: state.filters.search,
                  }}
                />
                <button
                  onClick={() => {
                    toast.promise(refetch(), {
                      loading: 'Refreshing...',
                      success: 'Subscriptions updated',
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
              <label htmlFor="subscription-search" className="sr-only">Search subscriptions</label>
              <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" aria-hidden="true" />
              <input
                id="subscription-search"
                type="text"
                placeholder="Search key, SKU, tier..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-800/50 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-400 transition-all focus:border-hpe-purple focus:outline-none focus:ring-2 focus:ring-hpe-purple/20"
                data-testid="subscription-search-input"
              />
              {searchInput && (
                <button
                  onClick={() => setSearchInput('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                  aria-label="Clear search"
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
                    ? 'border-violet-500/50 bg-violet-500/10 text-violet-400'
                    : 'border-slate-700 bg-slate-800/50 text-slate-300 hover:bg-slate-800'
                }`}
              >
                <Filter className="h-4 w-4" />
                Filters
                {hasActiveFilters && (
                  <span className="ml-1 rounded-full bg-violet-500 px-1.5 py-0.5 text-xs text-white">
                    {[state.filters.subscription_type, state.filters.subscription_status, state.filters.search].filter(Boolean).length}
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
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
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
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* Subscription Type Filter */}
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">
                    Subscription Type
                  </label>
                  <select
                    value={state.filters.subscription_type || ''}
                    onChange={(e) => handleFilterChange('subscription_type', e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none"
                  >
                    <option value="">All Types</option>
                    {filterOptions.subscription_types.map((type) => (
                      <option key={type} value={type}>
                        {type.replace('CENTRAL_', '')}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Status Filter */}
                <div>
                  <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">
                    Status
                  </label>
                  <select
                    value={state.filters.subscription_status || ''}
                    onChange={(e) => handleFilterChange('subscription_status', e.target.value)}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none"
                  >
                    <option value="">All Statuses</option>
                    {filterOptions.subscription_statuses.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
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
                      column="key"
                      label="Subscription Key"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <SortableHeader
                      column="subscription_type"
                      label="Type"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Status
                    </th>
                    <SortableHeader
                      column="tier"
                      label="Tier"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <SortableHeader
                      column="quantity"
                      label="Licenses"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Utilization
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Devices
                    </th>
                    <SortableHeader
                      column="start_time"
                      label="Start Date"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <SortableHeader
                      column="end_time"
                      label="End Date"
                      currentSort={state.sort_by}
                      sortOrder={state.sort_order}
                      onSort={handlers.handleSort}
                    />
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Days Left
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {isLoading ? (
                    <tr>
                      <td colSpan={11} className="py-20 text-center">
                        <div className="flex flex-col items-center gap-3">
                          <RefreshCw className="h-8 w-8 animate-spin text-violet-500" />
                          <span className="text-sm text-slate-400">Loading subscriptions...</span>
                        </div>
                      </td>
                    </tr>
                  ) : data?.items.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="py-20 text-center">
                        <div className="flex flex-col items-center gap-3">
                          <Shield className="h-12 w-12 text-slate-600" />
                          <span className="text-sm text-slate-400">No subscriptions found</span>
                          {hasActiveFilters && (
                            <button
                              onClick={clearFilters}
                              className="text-sm text-violet-400 hover:text-violet-300"
                            >
                              Clear filters
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ) : (
                    data?.items.map((subscription) => (
                      <SubscriptionRow
                        key={subscription.id}
                        subscription={subscription}
                        onViewDetails={() => setSelectedSubscription(subscription)}
                        onCopyKey={() => copyToClipboard(subscription.key, 'Subscription key')}
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
                itemName="subscriptions"
                onPageChange={handlers.handlePageChange}
                variant="icon"
                theme="purple"
              />
            )}
          </div>
        </main>
      </div>

      {/* Subscription Detail Drawer */}
      <Drawer
        open={!!selectedSubscription}
        onClose={() => setSelectedSubscription(null)}
        title={selectedSubscription?.key || ''}
        subtitle={selectedSubscription?.subscription_type?.replace('CENTRAL_', '') || 'Subscription'}
        width="lg"
      >
        {selectedSubscription && (
          <SubscriptionDetailContent
            subscription={selectedSubscription}
            onCopyKey={() => copyToClipboard(selectedSubscription.key, 'Subscription key')}
          />
        )}
      </Drawer>
    </div>
  )
}

// Subscription Detail Content for Drawer
function SubscriptionDetailContent({
  subscription,
  onCopyKey,
}: {
  subscription: SubscriptionListItem
  onCopyKey: () => void
}) {
  const isActive = subscription.subscription_status === 'STARTED'
  const isExpired = subscription.subscription_status === 'ENDED' || subscription.subscription_status === 'CANCELLED'
  const utilizationPercent = subscription.quantity > 0
    ? Math.round((subscription.used_quantity / subscription.quantity) * 100)
    : 0

  const getStatusColor = () => {
    if (isActive) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    if (isExpired) return 'bg-slate-500/10 text-slate-400 border-slate-500/20'
    return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
  }

  const getDaysRemainingColor = () => {
    if (subscription.days_remaining === null) return 'text-slate-500'
    if (subscription.days_remaining <= 7) return 'text-rose-400'
    if (subscription.days_remaining <= 30) return 'text-amber-400'
    if (subscription.days_remaining <= 90) return 'text-yellow-400'
    return 'text-emerald-400'
  }

  return (
    <div className="space-y-6">
      {/* Header with icon and status */}
      <div className="flex items-center gap-4">
        <div className={`rounded-xl p-4 ${subscription.is_eval ? 'bg-amber-500/10' : 'bg-hpe-purple/10'}`}>
          {subscription.is_eval ? (
            <FlaskConical className="h-8 w-8 text-amber-400" />
          ) : (
            <Shield className="h-8 w-8 text-hpe-purple" />
          )}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusColor()}`}>
              {isActive ? <CheckCircle className="h-3 w-3" /> : isExpired ? <XCircle className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
              {subscription.subscription_status || 'Unknown'}
            </span>
            {subscription.is_eval && (
              <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-400">
                Evaluation
              </span>
            )}
          </div>
          {subscription.sku && (
            <p className="mt-1 text-sm text-slate-400">SKU: {subscription.sku}</p>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-2">
        <button
          onClick={onCopyKey}
          className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700"
        >
          <Copy className="h-4 w-4" />
          Copy Key
        </button>
        <Link
          to={`/devices?subscription_key=${encodeURIComponent(subscription.key)}`}
          className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-slate-300 transition-colors hover:bg-slate-700"
        >
          <Server className="h-4 w-4" />
          View Devices ({subscription.device_count})
        </Link>
      </div>

      {/* Subscription Information */}
      <DetailSection title="Subscription Details">
        <DetailRow label="Subscription Key" value={subscription.key} mono />
        <DetailRow label="Type" value={subscription.subscription_type?.replace('CENTRAL_', '')} />
        <DetailRow label="Tier" value={subscription.tier} />
        <DetailRow label="SKU" value={subscription.sku} />
      </DetailSection>

      {/* License Usage */}
      <DetailSection title="License Usage">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-400">Utilization</span>
            <span className={`font-mono text-lg font-bold ${utilizationPercent >= 90 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {utilizationPercent}%
            </span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-slate-700/50">
            <div
              className={`h-full rounded-full transition-all ${
                utilizationPercent >= 90 ? 'bg-amber-500' : 'bg-violet-500'
              }`}
              style={{ width: `${Math.min(utilizationPercent, 100)}%` }}
            />
          </div>
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="font-mono text-lg font-bold text-white">{subscription.quantity.toLocaleString()}</p>
              <p className="text-xs text-slate-400">Total</p>
            </div>
            <div>
              <p className="font-mono text-lg font-bold text-violet-400">{subscription.used_quantity.toLocaleString()}</p>
              <p className="text-xs text-slate-400">Used</p>
            </div>
            <div>
              <p className="font-mono text-lg font-bold text-slate-400">{subscription.available_quantity.toLocaleString()}</p>
              <p className="text-xs text-slate-400">Available</p>
            </div>
          </div>
        </div>
      </DetailSection>

      {/* Devices */}
      <DetailSection title="Assigned Devices">
        <div className="flex items-center justify-between py-3">
          <span className="flex items-center gap-2 text-sm text-slate-400">
            <Server className="h-4 w-4" />
            Devices using this subscription
          </span>
          <Link
            to={`/devices?subscription_key=${encodeURIComponent(subscription.key)}`}
            className="flex items-center gap-1 font-mono text-sm font-medium text-violet-400 hover:text-violet-300"
          >
            {subscription.device_count.toLocaleString()} devices
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </DetailSection>

      {/* Dates */}
      <DetailSection title="Validity Period">
        <DetailRow
          label="Start Date"
          value={
            subscription.start_time ? (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3 text-slate-500" />
                {formatDate(subscription.start_time)}
              </span>
            ) : null
          }
        />
        <DetailRow
          label="End Date"
          value={
            subscription.end_time ? (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3 text-slate-500" />
                {formatDate(subscription.end_time)}
              </span>
            ) : null
          }
        />
        <DetailRow
          label="Days Remaining"
          value={
            subscription.days_remaining !== null ? (
              <span className={`font-mono font-medium ${getDaysRemainingColor()}`}>
                {subscription.days_remaining <= 0 ? 'Expired' : `${subscription.days_remaining} days`}
              </span>
            ) : null
          }
        />
      </DetailSection>

      {/* Metadata */}
      <DetailSection title="Metadata">
        <DetailRow label="Subscription ID" value={subscription.id} mono />
      </DetailSection>
    </div>
  )
}

// Subscription Row Component with clickable device count
const SubscriptionRow = memo(function SubscriptionRow({
  subscription,
  onViewDetails,
  onCopyKey,
}: {
  subscription: SubscriptionListItem
  onViewDetails: () => void
  onCopyKey: () => void
}) {
  const isActive = subscription.subscription_status === 'STARTED'
  const isExpired = subscription.subscription_status === 'ENDED' || subscription.subscription_status === 'CANCELLED'
  const utilizationPercent = subscription.quantity > 0
    ? Math.round((subscription.used_quantity / subscription.quantity) * 100)
    : 0

  const getDaysRemainingColor = () => {
    if (subscription.days_remaining === null) return 'text-slate-500'
    if (subscription.days_remaining <= 7) return 'text-rose-400'
    if (subscription.days_remaining <= 30) return 'text-amber-400'
    if (subscription.days_remaining <= 90) return 'text-yellow-400'
    return 'text-emerald-400'
  }

  const getStatusIcon = () => {
    if (isActive) return <CheckCircle className="h-3.5 w-3.5" />
    if (isExpired) return <XCircle className="h-3.5 w-3.5" />
    return <Clock className="h-3.5 w-3.5" />
  }

  const getStatusColor = () => {
    if (isActive) return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
    if (isExpired) return 'bg-slate-500/10 text-slate-400 border-slate-500/20'
    return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
  }

  const menuItems = [
    {
      label: 'View Details',
      icon: <Eye className="h-4 w-4" />,
      onClick: onViewDetails,
    },
    {
      label: 'Copy Key',
      icon: <Copy className="h-4 w-4" />,
      onClick: onCopyKey,
    },
  ]

  return (
    <tr
      className="transition-colors hover:bg-slate-800/50 animate-fade-in cursor-pointer"
      onClick={onViewDetails}
    >
      <td className="whitespace-nowrap px-4 py-3">
        <div className="flex items-center gap-3">
          <div className={`rounded-lg p-2 ${subscription.is_eval ? 'bg-amber-500/10' : 'bg-hpe-purple/10'}`}>
            {subscription.is_eval ? (
              <FlaskConical className="h-4 w-4 text-amber-400" />
            ) : (
              <Shield className="h-4 w-4 text-hpe-purple" />
            )}
          </div>
          <div>
            <p className="font-mono text-sm font-medium text-white">{subscription.key}</p>
            {subscription.sku && (
              <p className="text-xs text-slate-500">{subscription.sku}</p>
            )}
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span className="inline-flex items-center rounded-md bg-slate-700/50 px-2 py-1 text-xs font-medium text-slate-300">
          {(subscription.subscription_type || 'Unknown').replace('CENTRAL_', '')}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusColor()}`}>
          {getStatusIcon()}
          {subscription.subscription_status || 'Unknown'}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
        {subscription.tier || '-'}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <div className="text-sm">
          <span className="font-mono font-medium text-white">{subscription.quantity.toLocaleString()}</span>
          <span className="text-slate-500"> total</span>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        <div className="w-28">
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-slate-400">{subscription.used_quantity}/{subscription.quantity}</span>
            <span className={utilizationPercent >= 90 ? 'text-amber-400' : 'text-slate-400'}>
              {utilizationPercent}%
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-700/50">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                utilizationPercent >= 90 ? 'bg-amber-500' : 'bg-violet-500'
              }`}
              style={{ width: `${Math.min(utilizationPercent, 100)}%` }}
            />
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
        {subscription.device_count > 0 ? (
          <Link
            to={`/devices?subscription_key=${encodeURIComponent(subscription.key)}`}
            className="flex items-center gap-1.5 text-sm text-violet-400 hover:text-violet-300"
          >
            <Server className="h-3.5 w-3.5" />
            <span className="font-mono">{subscription.device_count.toLocaleString()}</span>
          </Link>
        ) : (
          <span className="flex items-center gap-1.5 text-sm text-slate-500">
            <Server className="h-3.5 w-3.5" />
            <span className="font-mono">0</span>
          </span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
        {formatDate(subscription.start_time)}
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-400">
        {formatDate(subscription.end_time)}
      </td>
      <td className="whitespace-nowrap px-4 py-3">
        {subscription.days_remaining !== null ? (
          <span className={`font-mono text-sm font-medium ${getDaysRemainingColor()}`}>
            {subscription.days_remaining <= 0 ? 'Expired' : `${subscription.days_remaining}d`}
          </span>
        ) : (
          <span className="text-sm text-slate-500">-</span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <DropdownMenu items={menuItems} />
      </td>
    </tr>
  )
})
