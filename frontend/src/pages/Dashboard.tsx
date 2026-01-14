import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardApiClient } from '../api/client'
import { useBackgroundTasks } from '../contexts/BackgroundTaskContext'
import { Tooltip } from '../components/ui/Tooltip'
import {
  Server,
  Shield,
  AlertTriangle,
  Clock,
  RefreshCw,
  Wifi,
  Router,
  HardDrive,
  Activity,
  ChevronRight,
  Zap,
  TrendingUp,
  Database,
  CloudDownload,
} from 'lucide-react'
import { ReportButton } from '../components/reports/ReportButton'
import type {
  DashboardResponse,
  DeviceTypeBreakdown,
  SubscriptionTypeBreakdown,
  ExpiringItem,
  SyncHistoryItem,
} from '../types'

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

// Format relative time
function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  return `${diffDays}d ago`
}

// Format duration
function formatDuration(ms: number | null): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

// KPI Card Component - Now clickable with link
function KPICard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  color = 'emerald',
  href,
}: {
  title: string
  value: string | number
  subtitle?: string
  icon: typeof Server
  trend?: { value: number; label: string }
  color?: 'emerald' | 'amber' | 'rose' | 'sky' | 'violet'
  href?: string
}) {
  const colorClasses = {
    emerald: {
      bg: 'from-emerald-500/20 to-emerald-600/5',
      border: 'border-emerald-500/30',
      icon: 'text-emerald-400',
      glow: 'shadow-emerald-500/20',
    },
    amber: {
      bg: 'from-amber-500/20 to-amber-600/5',
      border: 'border-amber-500/30',
      icon: 'text-amber-400',
      glow: 'shadow-amber-500/20',
    },
    rose: {
      bg: 'from-rose-500/20 to-rose-600/5',
      border: 'border-rose-500/30',
      icon: 'text-rose-400',
      glow: 'shadow-rose-500/20',
    },
    sky: {
      bg: 'from-sky-500/20 to-sky-600/5',
      border: 'border-sky-500/30',
      icon: 'text-sky-400',
      glow: 'shadow-sky-500/20',
    },
    violet: {
      bg: 'from-violet-500/20 to-violet-600/5',
      border: 'border-violet-500/30',
      icon: 'text-violet-400',
      glow: 'shadow-violet-500/20',
    },
  }

  const colors = colorClasses[color]

  const cardContent = (
    <div
      className={`relative overflow-hidden rounded-2xl border ${colors.border} bg-gradient-to-br ${colors.bg} p-6 backdrop-blur-xl transition-all duration-500 hover:scale-[1.02] hover:shadow-lg ${colors.glow} animate-fade-slide-up ${href ? 'cursor-pointer' : ''}`}
      data-testid={`kpi-card-${title.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="relative flex items-start justify-between">
        <div>
          <p className="font-mono text-xs font-medium uppercase tracking-wider text-slate-400">
            {title}
          </p>
          <p className="mt-2 font-mono text-4xl font-bold tracking-tight text-white">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
          {subtitle && (
            <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
          )}
          {trend && (
            <div className="mt-3 flex items-center gap-1.5">
              <TrendingUp className={`h-3.5 w-3.5 ${trend.value >= 0 ? 'text-emerald-400' : 'text-rose-400'}`} />
              <span className={`font-mono text-xs ${trend.value >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {trend.value >= 0 ? '+' : ''}{trend.value}%
              </span>
              <span className="text-xs text-slate-500">{trend.label}</span>
            </div>
          )}
        </div>
        <div className={`rounded-xl bg-slate-800/50 p-3 ${colors.icon}`}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
      {href && (
        <div className="absolute bottom-3 right-3">
          <ChevronRight className="h-4 w-4 text-slate-500" />
        </div>
      )}
    </div>
  )

  if (href) {
    return <Link to={href}>{cardContent}</Link>
  }

  return cardContent
}

// Progress Bar Component
function ProgressBar({
  value,
  max,
  label,
  color = 'emerald',
  loading = false,
}: {
  value: number
  max: number
  label?: string
  color?: 'emerald' | 'amber' | 'rose' | 'sky' | 'violet'
  loading?: boolean
}) {
  const percent = max > 0 ? (value / max) * 100 : 0
  const colorClasses = {
    emerald: 'bg-emerald-500',
    amber: 'bg-amber-500',
    rose: 'bg-rose-500',
    sky: 'bg-sky-500',
    violet: 'bg-violet-500',
  }

  return (
    <div className="space-y-1.5">
      {label && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-400">{label}</span>
          <span className="font-mono text-xs text-slate-300">{Math.round(percent)}%</span>
        </div>
      )}
      <div className="h-2 overflow-hidden rounded-full bg-slate-700/50">
        <div
          className={`h-full ${colorClasses[color]} transition-all duration-1000 ease-out ${loading ? 'progress-shine' : ''}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  )
}

// Bar Chart Component with tooltips and click navigation
function HorizontalBarChart({
  data,
  valueKey,
  labelKey,
  maxValue,
  renderLabel,
  renderValue,
  renderTooltip,
  getHref,
  loading = false,
}: {
  data: { [key: string]: unknown }[]
  valueKey: string
  labelKey: string
  maxValue?: number
  renderLabel?: (item: { [key: string]: unknown }) => React.ReactNode
  renderValue?: (item: { [key: string]: unknown }) => React.ReactNode
  renderTooltip?: (item: { [key: string]: unknown }) => React.ReactNode
  getHref?: (item: { [key: string]: unknown }) => string
  loading?: boolean
}) {
  const max = maxValue || Math.max(...data.map((d) => d[valueKey] as number))

  return (
    <div className="space-y-3">
      {data.map((item, idx) => {
        const value = item[valueKey] as number
        const percent = max > 0 ? (value / max) * 100 : 0
        const colors = [
          'from-emerald-500 to-emerald-600',
          'from-sky-500 to-sky-600',
          'from-violet-500 to-violet-600',
          'from-amber-500 to-amber-600',
          'from-rose-500 to-rose-600',
          'from-cyan-500 to-cyan-600',
        ]

        const href = getHref?.(item)

        const barContent = (
          <div className={`group animate-fade-slide-up ${href ? 'cursor-pointer' : ''}`}>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm text-slate-300">
                {renderLabel ? renderLabel(item) : String(item[labelKey])}
              </span>
              <span className="font-mono text-sm font-medium text-white">
                {renderValue ? renderValue(item) : value.toLocaleString()}
              </span>
            </div>
            <Tooltip
              content={renderTooltip ? renderTooltip(item) : `${value.toLocaleString()} items`}
              position="top"
            >
              <div className="h-3 w-full overflow-hidden rounded-full bg-slate-700/30">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${colors[idx % colors.length]} transition-all duration-700 ease-out group-hover:brightness-110 ${loading ? 'progress-shine' : ''}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </Tooltip>
          </div>
        )

        if (href) {
          return (
            <Link key={idx} to={href}>
              {barContent}
            </Link>
          )
        }

        return <div key={idx}>{barContent}</div>
      })}
    </div>
  )
}

// Expiring Item Row
function ExpiringItemRow({ item }: { item: ExpiringItem }) {
  const urgencyColor =
    item.days_remaining <= 7
      ? 'text-rose-400 bg-rose-500/10 border-rose-500/30'
      : item.days_remaining <= 30
        ? 'text-amber-400 bg-amber-500/10 border-amber-500/30'
        : 'text-slate-400 bg-slate-500/10 border-slate-500/30'

  const Icon = item.item_type === 'device' ? Server : Shield
  const href = item.item_type === 'device'
    ? `/devices?search=${encodeURIComponent(item.identifier)}`
    : `/subscriptions?search=${encodeURIComponent(item.identifier)}`

  return (
    <Link
      to={href}
      className="group flex items-center justify-between rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 transition-all hover:border-slate-600/50 hover:bg-slate-800/50 animate-fade-slide-up"
    >
      <div className="flex items-center gap-4">
        <div className={`rounded-lg p-2 ${item.item_type === 'device' ? 'bg-sky-500/10 text-sky-400' : 'bg-violet-500/10 text-violet-400'}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="font-mono text-sm font-medium text-white">{item.identifier}</p>
          <p className="text-xs text-slate-400">
            {item.item_type === 'device' ? 'Device' : 'Subscription'} · {item.sub_type || 'Unknown'}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className={`rounded-lg border px-3 py-1.5 ${urgencyColor}`}>
          <span className="font-mono text-sm font-medium">
            {item.days_remaining}d
          </span>
        </div>
        <ChevronRight className="h-4 w-4 text-slate-500 opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
    </Link>
  )
}

// Format date/time for display
function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return 'N/A'
  const date = new Date(dateStr)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
}

// Sync History Row
function SyncHistoryRow({ item }: { item: SyncHistoryItem }) {
  const statusColors = {
    completed: 'text-emerald-400 bg-emerald-500/10',
    success: 'text-emerald-400 bg-emerald-500/10',
    running: 'text-sky-400 bg-sky-500/10',
    failed: 'text-rose-400 bg-rose-500/10',
  }

  const status = item.status as keyof typeof statusColors
  const colorClass = statusColors[status] || statusColors.completed

  return (
    <div className="group flex items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/30 p-4 transition-all hover:border-slate-600/50 hover:bg-slate-800/50 animate-fade-slide-up">
      <div className={`rounded-lg p-2 ${colorClass}`}>
        {item.status === 'running' ? (
          <RefreshCw className="h-5 w-5 animate-spin" />
        ) : item.status === 'success' || item.status === 'completed' ? (
          <Activity className="h-5 w-5" />
        ) : (
          <AlertTriangle className="h-5 w-5" />
        )}
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <p className="font-mono text-sm font-medium capitalize text-white">
            {item.resource_type}
          </p>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}>
            {item.status}
          </span>
        </div>
        <p className="text-xs text-slate-400">
          {formatDateTime(item.started_at)} · {formatDuration(item.duration_ms)}
        </p>
      </div>
      <div className="text-right">
        <p className="font-mono text-sm text-slate-300">
          {item.records_fetched.toLocaleString()} fetched
        </p>
        <p className="text-xs text-slate-500">+{item.records_inserted} / ~{item.records_updated}</p>
      </div>
    </div>
  )
}

// Clickable Region Card
function RegionCard({ region, count }: { region: string; count: number }) {
  return (
    <Link
      to={`/devices?region=${encodeURIComponent(region)}`}
      className="group rounded-xl border border-slate-700/30 bg-slate-800/50 p-4 text-center transition-all hover:border-slate-600/50 hover:bg-slate-800 animate-fade-slide-up"
    >
      <p className="font-mono text-2xl font-bold text-white group-hover:text-hpe-green transition-colors">
        {count.toLocaleString()}
      </p>
      <p className="mt-1 text-xs uppercase tracking-wider text-slate-400">
        {region}
      </p>
    </Link>
  )
}

// Clickable Device Status Row
function DeviceStatusRow({
  label,
  count,
  colorClass,
  dotColor,
  href
}: {
  label: string
  count: number
  colorClass: string
  dotColor: string
  href: string
}) {
  return (
    <Link
      to={href}
      className={`flex items-center justify-between rounded-lg px-4 py-3 transition-all hover:brightness-125 ${colorClass}`}
    >
      <span className="flex items-center gap-2 text-sm">
        <span className={`h-2 w-2 rounded-full ${dotColor}`} />
        {label}
      </span>
      <span className="font-mono text-lg font-bold">
        {count.toLocaleString()}
      </span>
    </Link>
  )
}

// Main Dashboard Component
export function Dashboard() {
  const queryClient = useQueryClient()
  const [syncProgress, setSyncProgress] = useState('')

  // Background task context
  const { addTask, updateTask } = useBackgroundTasks()

  const { data, isLoading, error, refetch } = useQuery<DashboardResponse>({
    queryKey: ['dashboard'],
    queryFn: () => dashboardApiClient.getDashboard(),
    refetchInterval: 60000, // Refresh every minute
  })

  // Sync mutation - triggers GreenLake sync then refreshes dashboard
  const syncMutation = useMutation({
    mutationFn: async () => {
      setSyncProgress('Connecting to GreenLake...')
      const result = await dashboardApiClient.triggerSync()
      return result
    },
    onSuccess: (result) => {
      setSyncProgress('Refreshing dashboard...')
      // Invalidate all queries to refresh data
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['devices-list'] })
      queryClient.invalidateQueries({ queryKey: ['subscriptions-list'] })
      setSyncProgress('')
      return result
    },
    onError: () => {
      setSyncProgress('')
    },
  })

  // Handle sync with background task tracking
  const handleSync = useCallback(() => {
    const taskId = addTask({
      type: 'sync',
      title: 'Syncing with GreenLake',
      description: 'Fetching devices and subscriptions',
      status: 'running',
    })

    syncMutation.mutate(undefined, {
      onSuccess: (result) => {
        const deviceCount = result.devices?.total || result.devices?.upserted || result.devices?.fetched || 0
        const subCount = result.subscriptions?.total || result.subscriptions?.upserted || result.subscriptions?.fetched || 0

        updateTask(taskId, {
          status: 'completed',
          completedAt: Date.now(),
          result: { devices: deviceCount, subscriptions: subCount },
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

  const isSyncing = syncMutation.isPending

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-16 w-16 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-500" />
            <Zap className="absolute left-1/2 top-1/2 h-6 w-6 -translate-x-1/2 -translate-y-1/2 text-emerald-500" />
          </div>
          <p className="font-mono text-sm text-slate-400">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <div className="max-w-md rounded-2xl border border-rose-500/30 bg-rose-500/10 p-8 text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-rose-400" />
          <h2 className="mt-4 text-xl font-semibold text-white">Failed to Load Dashboard</h2>
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

  if (!data) return null

  const {
    device_stats,
    device_by_type,
    device_by_region,
    subscription_stats,
    subscription_by_type,
    expiring_items,
    sync_history,
    last_sync_at,
    last_sync_status,
  } = data

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Background effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
        <div className="absolute -top-1/2 -right-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-green/5 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/2 h-[1000px] w-[1000px] rounded-full bg-hpe-purple/5 blur-3xl" />
        {/* Grid pattern */}
        <div className="absolute inset-0 bg-grid-pattern opacity-50" />
      </div>

      <div className="relative">
        {/* Header */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
          <div className="mx-auto max-w-7xl px-6 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white">
                  HPE GreenLake
                  <span className="ml-2 bg-gradient-to-r from-emerald-400 to-emerald-600 bg-clip-text text-transparent">
                    Dashboard
                  </span>
                </h1>
                <p className="mt-1 text-sm text-slate-400">
                  Device & Subscription Inventory Overview
                </p>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-2">
                  <Clock className="h-4 w-4 text-slate-400" />
                  <span className="font-mono text-sm text-slate-300">
                    {isSyncing ? syncProgress : `Last sync: ${formatRelativeTime(last_sync_at)}`}
                  </span>
                  {!isSyncing && last_sync_status === 'completed' && (
                    <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  )}
                </div>
                <ReportButton
                  reportType="dashboard"
                  variant="secondary"
                  label="Export Report"
                />
                <button
                  onClick={handleSync}
                  disabled={isSyncing}
                  className="flex items-center gap-2 rounded-lg bg-hpe-green px-4 py-2 text-sm font-medium text-white transition-all hover:bg-hpe-green/90 disabled:opacity-50 cursor-pointer"
                >
                  {isSyncing ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <CloudDownload className="h-4 w-4" />
                  )}
                  {isSyncing ? 'Syncing...' : 'Sync with GreenLake'}
                </button>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-6 py-8">
          {/* KPI Cards - Now clickable */}
          <section className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              title="Total Devices"
              value={device_stats.total}
              subtitle={`${device_stats.assigned} assigned`}
              icon={Server}
              color="emerald"
              href="/devices"
            />
            <KPICard
              title="Active Licenses"
              value={subscription_stats.active}
              subtitle={`${subscription_stats.total_licenses.toLocaleString()} total`}
              icon={Shield}
              color="sky"
              href="/subscriptions?status=STARTED"
            />
            <KPICard
              title="License Utilization"
              value={`${subscription_stats.utilization_percent}%`}
              subtitle={`${(subscription_stats.total_licenses - subscription_stats.available_licenses).toLocaleString()} used`}
              icon={Activity}
              color="violet"
              href="/subscriptions"
            />
            <KPICard
              title="Expiring Soon"
              value={subscription_stats.expiring_soon + expiring_items.filter(i => i.item_type === 'device').length}
              subtitle="Within 90 days"
              icon={AlertTriangle}
              color={subscription_stats.expiring_soon > 0 ? 'amber' : 'emerald'}
              href="/subscriptions?sort_by=end_time&sort_order=asc"
            />
          </section>

          {/* Main Content Grid */}
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            {/* Left Column - Device Breakdown */}
            <div className="lg:col-span-2 space-y-8">
              {/* Device by Type */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Devices by Type</h2>
                    <p className="text-sm text-slate-400">Distribution across device categories</p>
                  </div>
                  <Database className="h-5 w-5 text-slate-400" />
                </div>
                <HorizontalBarChart
                  data={device_by_type as unknown as { [key: string]: unknown }[]}
                  valueKey="count"
                  labelKey="device_type"
                  loading={isSyncing}
                  getHref={(item) => {
                    const dt = item as unknown as DeviceTypeBreakdown
                    return `/devices?device_type=${encodeURIComponent(dt.device_type)}`
                  }}
                  renderLabel={(item) => {
                    const dt = item as unknown as DeviceTypeBreakdown
                    const Icon = deviceIcons[dt.device_type] || Server
                    return (
                      <>
                        <Icon className="h-4 w-4 text-slate-400" />
                        <span>{dt.device_type}</span>
                      </>
                    )
                  }}
                  renderValue={(item) => {
                    const dt = item as unknown as DeviceTypeBreakdown
                    return (
                      <span>
                        {dt.count.toLocaleString()}
                        <span className="ml-2 text-xs text-slate-500">
                          ({dt.assigned} assigned)
                        </span>
                      </span>
                    )
                  }}
                  renderTooltip={(item) => {
                    const dt = item as unknown as DeviceTypeBreakdown
                    return (
                      <div className="space-y-1">
                        <p className="font-medium">{dt.device_type}</p>
                        <p>Total: {dt.count.toLocaleString()}</p>
                        <p>Assigned: {dt.assigned.toLocaleString()}</p>
                        <p>Unassigned: {dt.unassigned.toLocaleString()}</p>
                        <p className="text-slate-400 text-[10px] mt-1">Click to view devices</p>
                      </div>
                    )
                  }}
                />
              </section>

              {/* Subscription by Type */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
                <div className="mb-6 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-semibold text-white">Subscriptions by Type</h2>
                    <p className="text-sm text-slate-400">Active license distribution</p>
                  </div>
                  <Shield className="h-5 w-5 text-slate-400" />
                </div>
                <HorizontalBarChart
                  data={subscription_by_type as unknown as { [key: string]: unknown }[]}
                  valueKey="total_quantity"
                  labelKey="subscription_type"
                  loading={isSyncing}
                  getHref={(item) => {
                    const st = item as unknown as SubscriptionTypeBreakdown
                    return `/subscriptions?subscription_type=${encodeURIComponent(st.subscription_type)}`
                  }}
                  renderLabel={(item) => {
                    const st = item as unknown as SubscriptionTypeBreakdown
                    return <span>{st.subscription_type.replace('CENTRAL_', '')}</span>
                  }}
                  renderValue={(item) => {
                    const st = item as unknown as SubscriptionTypeBreakdown
                    const used = st.total_quantity - st.available_quantity
                    return (
                      <span>
                        {used.toLocaleString()}/{st.total_quantity.toLocaleString()}
                        <span className="ml-2 text-xs text-slate-500">
                          ({st.available_quantity} free)
                        </span>
                      </span>
                    )
                  }}
                  renderTooltip={(item) => {
                    const st = item as unknown as SubscriptionTypeBreakdown
                    const used = st.total_quantity - st.available_quantity
                    const utilization = st.total_quantity > 0 ? Math.round((used / st.total_quantity) * 100) : 0
                    return (
                      <div className="space-y-1">
                        <p className="font-medium">{st.subscription_type}</p>
                        <p>Total Licenses: {st.total_quantity.toLocaleString()}</p>
                        <p>Used: {used.toLocaleString()}</p>
                        <p>Available: {st.available_quantity.toLocaleString()}</p>
                        <p>Utilization: {utilization}%</p>
                        <p className="text-slate-400 text-[10px] mt-1">Click to view subscriptions</p>
                      </div>
                    )
                  }}
                />
              </section>

              {/* Region Distribution - Now clickable */}
              {device_by_region.length > 0 && (
                <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
                  <div className="mb-6 flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-white">Devices by Region</h2>
                      <p className="text-sm text-slate-400">Geographic distribution</p>
                    </div>
                    <Wifi className="h-5 w-5 text-slate-400" />
                  </div>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
                    {device_by_region.slice(0, 8).map((region) => (
                      <RegionCard
                        key={region.region}
                        region={region.region}
                        count={region.count}
                      />
                    ))}
                  </div>
                </section>
              )}
            </div>

            {/* Right Column - Sidebar */}
            <div className="space-y-8">
              {/* Utilization Gauge */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
                <h2 className="mb-4 text-lg font-semibold text-white">License Usage</h2>
                <div className="relative mx-auto w-48 h-48">
                  {/* Background ring */}
                  <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="12"
                      className="text-slate-700/50"
                    />
                    <circle
                      cx="50"
                      cy="50"
                      r="40"
                      fill="none"
                      stroke="url(#gauge-gradient)"
                      strokeWidth="12"
                      strokeLinecap="round"
                      strokeDasharray={`${subscription_stats.utilization_percent * 2.51} 251`}
                      className="transition-all duration-1000 ease-out"
                    />
                    <defs>
                      <linearGradient id="gauge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#10b981" />
                        <stop offset="100%" stopColor="#06b6d4" />
                      </linearGradient>
                    </defs>
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-mono text-3xl font-bold text-white">
                      {subscription_stats.utilization_percent}%
                    </span>
                    <span className="text-xs text-slate-400">utilized</span>
                  </div>
                </div>
                <div className="mt-4 space-y-2">
                  <ProgressBar
                    value={subscription_stats.total_licenses - subscription_stats.available_licenses}
                    max={subscription_stats.total_licenses}
                    label="Used licenses"
                    color="emerald"
                    loading={isSyncing}
                  />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4 text-center">
                  <div>
                    <p className="font-mono text-xl font-bold text-emerald-400">
                      {(subscription_stats.total_licenses - subscription_stats.available_licenses).toLocaleString()}
                    </p>
                    <p className="text-xs text-slate-400">Used</p>
                  </div>
                  <div>
                    <p className="font-mono text-xl font-bold text-slate-400">
                      {subscription_stats.available_licenses.toLocaleString()}
                    </p>
                    <p className="text-xs text-slate-400">Available</p>
                  </div>
                </div>
              </section>

              {/* Device Status - Now clickable */}
              <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
                <h2 className="mb-4 text-lg font-semibold text-white">Device Status</h2>
                <div className="space-y-3">
                  <DeviceStatusRow
                    label="Assigned"
                    count={device_stats.assigned}
                    colorClass="bg-emerald-500/10 text-emerald-400"
                    dotColor="bg-emerald-500"
                    href="/devices?assigned_state=ASSIGNED_TO_SERVICE"
                  />
                  <DeviceStatusRow
                    label="Unassigned"
                    count={device_stats.unassigned}
                    colorClass="bg-amber-500/10 text-amber-400"
                    dotColor="bg-amber-500"
                    href="/devices?assigned_state=UNASSIGNED"
                  />
                  <DeviceStatusRow
                    label="Archived"
                    count={device_stats.archived}
                    colorClass="bg-slate-500/10 text-slate-400"
                    dotColor="bg-slate-500"
                    href="/devices?include_archived=true"
                  />
                </div>
              </section>
            </div>
          </div>

          {/* Bottom Section - Expiring & Sync History */}
          <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-2">
            {/* Expiring Items */}
            <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Expiring Soon</h2>
                  <p className="text-sm text-slate-400">Items expiring within 90 days</p>
                </div>
                <Link
                  to="/subscriptions?sort_by=end_time&sort_order=asc"
                  className="flex items-center gap-1 text-sm text-emerald-400 hover:text-emerald-300"
                >
                  View all <ChevronRight className="h-4 w-4" />
                </Link>
              </div>
              {expiring_items.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <div className="rounded-full bg-emerald-500/10 p-4">
                    <Shield className="h-8 w-8 text-emerald-400" />
                  </div>
                  <p className="mt-4 text-sm text-slate-400">
                    No items expiring soon. You're all set!
                  </p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                  {expiring_items.map((item) => (
                    <ExpiringItemRow key={item.id} item={item} />
                  ))}
                </div>
              )}
            </section>

            {/* Sync History */}
            <section className="rounded-2xl border border-slate-700/50 bg-slate-800/30 p-6 backdrop-blur-sm animate-fade-slide-up">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Sync History</h2>
                  <p className="text-sm text-slate-400">Recent synchronization activity</p>
                </div>
                <Activity className="h-5 w-5 text-slate-400" />
              </div>
              {sync_history.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <div className="rounded-full bg-slate-500/10 p-4">
                    <RefreshCw className="h-8 w-8 text-slate-400" />
                  </div>
                  <p className="mt-4 text-sm text-slate-400">
                    No sync history available yet.
                  </p>
                </div>
              ) : (
                <div className="space-y-3 max-h-[400px] overflow-y-auto pr-2">
                  {sync_history.map((item) => (
                    <SyncHistoryRow key={item.id} item={item} />
                  ))}
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
